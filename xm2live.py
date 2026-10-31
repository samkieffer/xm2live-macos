#!/usr/bin/env python3
"""
Convertisseur XM/MOD vers Ableton Live
Convertit des fichiers FastTracker 2 Extended Module (.xm) et Amiga ProTracker (.mod)
en projets Ableton Live (.als)
"""

import sys
import os
import struct
import math
try:
    from lxml import etree as ET
except ImportError:
    import xml.etree.ElementTree as ET
import copy
import wave
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict

# Importer les fonctions de lecture XM et MOD
from xm_parser import extract_samples_and_patterns as extract_xm
from mod_parser import extract_samples_and_patterns as extract_mod

# Moteur de lecture commun (ordre de lecture, ticks, tempo)
from replayer import play_song, envelope_curve

# Assemblage du set Live à partir des fragments de templates/
from live_set import LiveSetBuilder, set_value

# Vérification du set généré
from als_validator import validate_als, print_report

# Source unique de la version (reprise par build_app.sh, make_dmg.sh et --version)
__version__ = '2.14.0'

def update_track_name(track, new_name):
    """Nom d'une piste : UserName (nom donné par l'utilisateur) et EffectiveName (nom affiché).
    Sans UserName, Live renomme la piste d'après son instrument."""
    set_value(track, 'Name/UserName', new_name)
    set_value(track, 'Name/EffectiveName', new_name)

def update_track_color(track, color_index):
    """Change la couleur d'une piste et de son clip MIDI"""
    set_value(track, 'Color', color_index)
    set_value(track, 'DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events/MidiClip/Color', color_index)

# Niveaux dans Live. FT2 joue un sample au volume du canal (0-64, linéaire). Dans Live :
# - la vélocité donne le volume du canal au début de la note (Vel → Vol à 100 %, velocity_for).
#   Mesuré (tools/live_calibration.py) : à Vel → Vol 0 % le Sampler est à gain 1, et le réglage
#   ajoute jusqu'à +22,7 dB à la vélocité 127 (à 100 % : +22,7 dB à 127, 0,4 dB de moins par pas) ;
# - la zone compense : -38,8 dB, pour le même niveau qu'avant la v2.14 à volume plein (zone -12 dB,
#   device -12 dB, Vel → Vol 35 % : -16,1 dB du sample), qui ne saturait pas (DISCOTEC : crête 0,77) ;
# - le volume du device (dB) reste à 0 dB et porte l'automation des changements pendant la note
#   (create_volume_automation), jusqu'à -36 dB, son minimum.
ZONE_GAIN = 0.0115
DEVICE_VOLUME_DB = 0.0
DEVICE_VOLUME_MIN_DB = -36.0


def velocity_for(volume):
    """Vélocité MIDI pour un volume FT2 (1-64, linéaire)

    Mesuré dans Live 12.4 (tools/live_calibration.py) : à Vel → Vol 100 %, le Sampler applique
    0,4 dB par pas de vélocité (1 = 50,4 dB sous 127). Pour retrouver 20·log10(v/64) dB :
    vélocité = 127 + 50·log10(v/64), soit 64 → 127, 32 → 112, 16 → 97, 1 → 37.
    """
    return max(1, min(127, round(127 + 50 * math.log10(max(volume, 0.01) / 64.0))))


def set_levels(device, sample_part):
    """Niveaux du Sampler / Simpler : zone à ZONE_GAIN, device à 0 dB, vélocité → volume à 100 %"""
    set_value(sample_part, 'Volume', ZONE_GAIN)
    set_value(device, 'VolumeAndPan/Volume/Manual', DEVICE_VOLUME_DB)
    set_value(device, 'VolumeAndPan/VolumeVelScale/Manual', 1.0)


def finetune_to_root_key_and_detune(relative_note, finetune):
    """Convertit relative_note + finetune XM en (RootKey, Detune) Ableton

    XM finetune: -128 à +127 en 1/128 de demi-ton (-128 = -1 demi-ton).
    FT2 n'en garde que 16 pas par demi-ton (finetune >> 3), soit 6.25 cents par pas.
    Ableton Detune: -50 à +50 cents, donc le demi-ton entier est reporté sur RootKey.

    Exemple: relative_note=17, finetune=-117 → -93.75 cents
             → RootKey = 60 - 17 + 1 = 44, Detune = +6.25
    """
    cents = (finetune >> 3) * 6.25
    semitones = round(cents / 100)
    detune = cents - semitones * 100
    # Dans XM: relative_note = -1 signifie 1 demi-ton plus bas
    # Dans Ableton: RootKey = 60 (C3) par défaut → RootKey = 60 - relative_note
    root_key = 60 - relative_note - semitones
    # Ableton n'accepte que 0-127 ; au-delà (relative_note extrême), FT2 ne joue de toute façon
    # plus ces notes (hauteur au-delà de B-9)
    root_key = max(0, min(127, root_key))
    return root_key, detune


def update_sampler_sample(track, sample_info, project_dir, template_sample_part, bpm=125, panning=None):
    """Change le sample chargé dans le Sampler/MultiSampler en copiant la structure du template

    Args:
        sample_info: Dict contenant path, relative_note, loop_start, loop_length, loop_type, volume, envelope
        project_dir: Répertoire du projet
        template_sample_part: Template du sample part
        bpm: BPM du module (release en ms, cf. configure_release)
        panning: panoramique de la zone (XM 0-255), par défaut celui du sample
    """

    sample_path = sample_info['path']
    relative_note = sample_info.get('relative_note', 0)

    # Trouver le device Sampler/MultiSampler
    devices = track.find('DeviceChain/DeviceChain/Devices')
    if devices is None:
        print(f"    ⚠️  Pas de DeviceChain/Devices trouvé")
        return False

    # Chercher MultiSampler comme enfant direct de Devices (pas descendant)
    sampler = devices.find('./MultiSampler')
    if sampler is None:
        sampler = devices.find('./OriginalSimpler')

    if sampler is None:
        print(f"    ⚠️  Pas de Sampler trouvé")
        return False

    # Trouver ou créer la structure Player/MultiSampleMap/SampleParts
    player = sampler.find('.//Player')
    if player is None:
        player = ET.SubElement(sampler, 'Player')

    multi_sample_map = player.find('.//MultiSampleMap')
    if multi_sample_map is None:
        multi_sample_map = ET.SubElement(player, 'MultiSampleMap')

    sample_parts = multi_sample_map.find('.//SampleParts')
    if sample_parts is None:
        sample_parts = ET.SubElement(multi_sample_map, 'SampleParts')

    # Supprimer tous les SampleParts existants
    for part in list(sample_parts):
        sample_parts.remove(part)

    # Cloner le MultiSamplePart du template
    new_sample_part = ET.fromstring(ET.tostring(template_sample_part))
    sample_parts.append(new_sample_part)

    # Mettre à jour les chemins du sample
    file_ref = new_sample_part.find('.//SampleRef/FileRef')
    if file_ref is not None:
        # Calculer le chemin relatif depuis le fichier .als
        # Le fichier .als est dans output_dir, les samples dans output_dir/Samples/
        sample_filename = os.path.basename(sample_path)
        rel_path_str = f"Samples/{sample_filename}"

        # Mettre à jour RelativePathType (1 = relative to .als file)
        rel_path_type_elem = file_ref.find('.//RelativePathType')
        if rel_path_type_elem is not None:
            rel_path_type_elem.set('Value', '1')

        # Mettre à jour RelativePath
        rel_path_elem = file_ref.find('.//RelativePath')
        if rel_path_elem is not None:
            rel_path_elem.set('Value', rel_path_str)

        # Mettre à jour Path
        path_elem = file_ref.find('.//Path')
        if path_elem is not None:
            path_elem.set('Value', os.path.abspath(sample_path))

        # Mettre à jour OriginalFileSize et OriginalCrc
        if os.path.exists(sample_path):
            file_size = os.path.getsize(sample_path)
            size_elem = file_ref.find('.//OriginalFileSize')
            if size_elem is not None:
                size_elem.set('Value', str(file_size))

            with open(sample_path, 'rb') as f:
                data = f.read()
                crc = sum(data) % 65536
            crc_elem = file_ref.find('.//OriginalCrc')
            if crc_elem is not None:
                crc_elem.set('Value', str(crc))

    # Mettre à jour le nom du sample
    name_elem = new_sample_part.find('.//Name')
    if name_elem is not None:
        sample_name = os.path.splitext(os.path.basename(sample_path))[0]
        name_elem.set('Value', sample_name)

    # Mettre à jour RootKey et Detune (relative_note + finetune du XM)
    finetune = sample_info.get('finetune', 0)
    root_key, detune_value = finetune_to_root_key_and_detune(relative_note, finetune)
    root_key_elem = new_sample_part.find('.//RootKey')
    if root_key_elem is not None:
        root_key_elem.set('Value', str(root_key))
        if root_key != 60:
            print(f"    → RootKey ajustée: {root_key} (relative_note={relative_note:+d})")

    detune_elem = new_sample_part.find('.//Detune')
    if detune_elem is not None:
        detune_elem.set('Value', str(detune_value))
        if finetune != 0:
            print(f"    → Detune: {detune_value:+.2f} cents (finetune={finetune:+d})")

    # Niveaux (cf. set_levels) : le volume du sample est porté par la vélocité des notes
    set_levels(sampler, new_sample_part)

    # Mettre à jour Panorama (panoramique de la piste, cf. track_panning)
    # XM panning: 0-255 (0=gauche, 128=centre, 255=droite)
    # Ableton Panorama: -1.0 à +1.0 (0=centre)
    xm_panning = panning if panning is not None else sample_info.get('panning', 128)
    panorama_elem = new_sample_part.find('.//Panorama')
    if panorama_elem is not None:
        # Conversion: (xm_pan - 128) / 128.0
        ableton_pan = (xm_panning - 128) / 128.0
        # Limiter à la plage Ableton
        ableton_pan = max(-1.0, min(1.0, ableton_pan))
        panorama_elem.set('Value', str(ableton_pan))

        # Afficher seulement si différent du centre
        if xm_panning != 128:
            if ableton_pan < 0:
                print(f"    → Panorama: {ableton_pan:.2f} (gauche, XM={xm_panning}/255)")
            else:
                print(f"    → Panorama: {ableton_pan:.2f} (droite, XM={xm_panning}/255)")

    # Lire la longueur du sample WAV pour mettre à jour SampleEnd
    if os.path.exists(sample_path):
        try:
            import wave
            with wave.open(sample_path, 'rb') as wav:
                num_frames = wav.getnframes()

                # Mettre à jour SampleEnd
                sample_end_elem = new_sample_part.find('.//SampleEnd')
                if sample_end_elem is not None:
                    sample_end_elem.set('Value', str(num_frames - 1))

                # Mettre à jour SustainLoop End
                sustain_loop_end = new_sample_part.find('.//SustainLoop/End')
                if sustain_loop_end is not None:
                    sustain_loop_end.set('Value', str(num_frames - 1))

                # Mettre à jour ReleaseLoop End
                release_loop_end = new_sample_part.find('.//ReleaseLoop/End')
                if release_loop_end is not None:
                    release_loop_end.set('Value', str(num_frames - 1))

                # Appliquer les paramètres de boucle du XM
                loop_type = sample_info.get('loop_type', 0)
                if loop_type > 0:  # 1=forward, 2=ping-pong
                    loop_start = sample_info.get('loop_start', 0)
                    loop_length = sample_info.get('loop_length', 0)
                    loop_end = loop_start + loop_length

                    # Activer la boucle dans SustainLoop
                    sustain_loop_on = new_sample_part.find('.//SustainLoop/LoopOn')
                    if sustain_loop_on is not None:
                        sustain_loop_on.set('Value', 'true')

                    # Loop start
                    sustain_loop_start = new_sample_part.find('.//SustainLoop/Start')
                    if sustain_loop_start is not None:
                        sustain_loop_start.set('Value', str(loop_start))

                    # Loop end
                    sustain_loop_end = new_sample_part.find('.//SustainLoop/End')
                    if sustain_loop_end is not None:
                        sustain_loop_end.set('Value', str(loop_end))

                    # Loop mode: 0=Off, 1=Forward, 2=Ping-Pong, 3=Backward
                    # XM: 1=Forward, 2=Ping-Pong → correspond à Ableton
                    sustain_loop_mode = new_sample_part.find('.//SustainLoop/Mode')
                    if sustain_loop_mode is not None:
                        sustain_loop_mode.set('Value', str(loop_type))

                    loop_mode_name = {1: "Forward", 2: "Ping-Pong"}.get(loop_type, "Unknown")
                    print(f"    → Boucle: {loop_start} - {loop_end} ({loop_mode_name})")

        except Exception as e:
            print(f"    ⚠️  Erreur lors de la lecture du WAV: {e}")

    # Paramétrer le nombre de voix à 1 (au lieu de 6 par défaut)
    # NumVoices est numéroté à partir de 0 : 0=1 voix, 5=6 voix
    num_voices = sampler.find('.//NumVoices')
    if num_voices is not None:
        num_voices.set('Value', '0')  # 0 = 1 voix
        print(f"    → Voix: 1 (monophonique)")

    configure_release(sampler, sample_info, bpm)

    return True


def detect_effect_9xx_per_instrument(tracks_data):
    """Détecte quels instruments utilisent l'effet 9xx (Sample Offset)

    Travaille sur les notes organisées (XM et MOD), où l'instrument des notes
    saisies sans numéro d'instrument est déjà résolu.

    Args:
        tracks_data: {canal: {instrument: [notes]}} (sortie de organize_tracks_by_channel)

    Returns:
        set: Ensemble des numéros d'instruments qui utilisent l'effet 9xx
    """
    return {
        instrument
        for channel_data in tracks_data.values()
        for instrument, notes in channel_data.items()
        if any(note.get('sample_offset_xm') is not None for note in notes)
    }


def populate_track_with_simpler(track, sample_info, project_dir, builder, bpm=125, panning=None):
    """Configure une piste avec OriginalSimpler au lieu de MultiSampler

    Utilisé pour les instruments qui ont l'effet 9xx (Sample Offset)
    car Sampler ne permet pas d'automatiser Sample Start.

    Args:
        track: élément MidiTrack
        sample_info: Dict contenant path, relative_note, loop_start, loop_length, loop_type, volume, panning, envelope
        project_dir: Répertoire du projet
        builder: LiveSetBuilder (fournit une copie de templates/simpler.xml)
        bpm: BPM du module (release en ms, cf. configure_release)
        panning: panoramique de la zone (XM 0-255), par défaut celui du sample

    Returns:
        Id de la cible d'automation Sample Start du Simpler (None si absente)

    Note:
        - Simpler ne supporte PAS les loops ping-pong (converti en forward)
        - Multi-sample non supporté (charge seulement le premier sample)
        - SNAP est toujours activé (évite les clics lors des automations Sample Start)
    """
    sample_path = sample_info['path']
    relative_note = sample_info.get('relative_note', 0)

    # Trouver le DeviceChain/Devices
    devices = track.find('DeviceChain/DeviceChain/Devices')
    if devices is None:
        print(f"    ⚠️  Pas de DeviceChain/Devices trouvé")
        return None

    # Supprimer le MultiSampler existant s'il y en a un
    sampler = devices.find('./MultiSampler')
    if sampler is not None:
        devices.remove(sampler)

    # Simpler de templates/simpler.xml, identifiants renumérotés
    simpler = builder.copy_fragment('simpler')
    devices.append(simpler)

    # Trouver la structure Player/MultiSampleMap/SampleParts/MultiSamplePart
    # (oui, Simpler a la même structure que Sampler pour les samples)
    sample_part = simpler.find('.//Player/MultiSampleMap/SampleParts/MultiSamplePart')
    if sample_part is None:
        print(f"    ⚠️  Pas de MultiSamplePart trouvé dans le template Simpler")
        return None

    # Mettre à jour les chemins du sample
    file_ref = sample_part.find('.//SampleRef/FileRef')
    if file_ref is not None:
        # Calculer le chemin relatif depuis le fichier .als
        sample_filename = os.path.basename(sample_path)
        rel_path_str = f"Samples/{sample_filename}"

        # Mettre à jour RelativePathType (1 = relative to .als file)
        rel_path_type_elem = file_ref.find('.//RelativePathType')
        if rel_path_type_elem is not None:
            rel_path_type_elem.set('Value', '1')

        # Mettre à jour RelativePath
        rel_path_elem = file_ref.find('.//RelativePath')
        if rel_path_elem is not None:
            rel_path_elem.set('Value', rel_path_str)

        # Mettre à jour Path
        path_elem = file_ref.find('.//Path')
        if path_elem is not None:
            path_elem.set('Value', os.path.abspath(sample_path))

        # Mettre à jour OriginalFileSize et OriginalCrc
        if os.path.exists(sample_path):
            file_size = os.path.getsize(sample_path)
            size_elem = file_ref.find('.//OriginalFileSize')
            if size_elem is not None:
                size_elem.set('Value', str(file_size))

            with open(sample_path, 'rb') as f:
                data = f.read()
                crc = sum(data) % 65536
            crc_elem = file_ref.find('.//OriginalCrc')
            if crc_elem is not None:
                crc_elem.set('Value', str(crc))

    # Mettre à jour le nom du sample
    name_elem = sample_part.find('.//Name')
    if name_elem is not None:
        sample_name = os.path.splitext(os.path.basename(sample_path))[0]
        name_elem.set('Value', sample_name)

    # Mettre à jour RootKey et Detune (relative_note + finetune)
    finetune = sample_info.get('finetune', 0)
    root_key, detune_value = finetune_to_root_key_and_detune(relative_note, finetune)
    root_key_elem = sample_part.find('.//RootKey')
    if root_key_elem is not None:
        root_key_elem.set('Value', str(root_key))
        if root_key != 60:
            print(f"    → RootKey ajustée: {root_key} (relative_note={relative_note:+d})")

    detune_elem = sample_part.find('.//Detune')
    if detune_elem is not None:
        detune_elem.set('Value', str(detune_value))
        if finetune != 0:
            print(f"    → Detune: {detune_value:+.2f} cents (finetune={finetune:+d})")

    # Mettre à jour Panorama (panoramique de la piste, cf. track_panning)
    xm_panning = panning if panning is not None else sample_info.get('panning', 128)
    panorama_elem = sample_part.find('.//Panorama')
    if panorama_elem is not None:
        ableton_pan = (xm_panning - 128) / 128.0
        ableton_pan = max(-1.0, min(1.0, ableton_pan))
        panorama_elem.set('Value', str(ableton_pan))

        if xm_panning != 128:
            if ableton_pan < 0:
                print(f"    → Panorama: {ableton_pan:.2f} (gauche, XM={xm_panning}/255)")
            else:
                print(f"    → Panorama: {ableton_pan:.2f} (droite, XM={xm_panning}/255)")

    # Niveaux (cf. set_levels) : le volume du sample est porté par la vélocité des notes
    set_levels(simpler, sample_part)

    # Lire la longueur du sample WAV pour configurer les loops
    if os.path.exists(sample_path):
        try:
            import wave
            with wave.open(sample_path, 'rb') as wav:
                num_frames = wav.getnframes()

                # Mettre à jour SampleEnd
                sample_end_elem = sample_part.find('.//SampleEnd')
                if sample_end_elem is not None:
                    sample_end_elem.set('Value', str(num_frames - 1))

                # Mettre à jour SustainLoop End
                sustain_loop_end = sample_part.find('.//SustainLoop/End')
                if sustain_loop_end is not None:
                    sustain_loop_end.set('Value', str(num_frames - 1))

                # Appliquer les paramètres de boucle
                loop_type = sample_info.get('loop_type', 0)

                # Trouver LoopOn dans LoopModulators
                loop_on_elem = simpler.find('.//LoopModulators/LoopOn/Manual')
                snap_elem = simpler.find('.//Snap/Manual')

                # IMPORTANT: SNAP toujours activé (évite les clics lors des automations Sample Start)
                if snap_elem is not None:
                    snap_elem.set('Value', 'true')

                if loop_type > 0:  # 1=forward, 2=ping-pong
                    # LIMITATION : Simpler ne supporte PAS ping-pong, conversion en forward
                    loop_start = sample_info.get('loop_start', 0)
                    loop_length = sample_info.get('loop_length', 0)
                    loop_end = loop_start + loop_length

                    # Activer la boucle dans SustainLoop
                    sustain_loop_on = sample_part.find('.//SustainLoop/LoopOn')
                    if sustain_loop_on is not None:
                        sustain_loop_on.set('Value', 'true')

                    # Loop start
                    sustain_loop_start = sample_part.find('.//SustainLoop/Start')
                    if sustain_loop_start is not None:
                        sustain_loop_start.set('Value', str(loop_start))

                    # Loop end
                    sustain_loop_end = sample_part.find('.//SustainLoop/End')
                    if sustain_loop_end is not None:
                        sustain_loop_end.set('Value', str(loop_end))

                    # Mode toujours Forward (1) pour Simpler
                    sustain_loop_mode = sample_part.find('.//SustainLoop/Mode')
                    if sustain_loop_mode is not None:
                        sustain_loop_mode.set('Value', '1')  # 1 = Forward

                    # Activer LoopOn dans LoopModulators
                    if loop_on_elem is not None:
                        loop_on_elem.set('Value', 'true')

                    if loop_type == 2:
                        print(f"    → Boucle: {loop_start} - {loop_end} (Ping-Pong → Forward, limitation Simpler)")
                    else:
                        print(f"    → Boucle: {loop_start} - {loop_end} (Forward)")

                else:
                    # Pas de loop : désactiver LoopOn
                    if loop_on_elem is not None:
                        loop_on_elem.set('Value', 'false')

        except Exception as e:
            print(f"    ⚠️  Erreur lors de la lecture du WAV: {e}")

    # Paramétrer le nombre de voix à 1 (au lieu de 6 par défaut)
    num_voices = simpler.find('.//NumVoices')
    if num_voices is not None:
        num_voices.set('Value', '0')  # 0 = 1 voix
        print(f"    → Voix: 1 (monophonique)")

    configure_release(simpler, sample_info, bpm)

    print(f"    ✅ Simpler configuré (effet 9xx supporté)")

    # Cible d'automation Sample Start (effet 9xx) ; IsModulated est requis pour voir l'automation
    sample_start_target = simpler.find('.//LoopModulators/SampleStart/AutomationTarget')
    if sample_start_target is None:
        return None
    loop_modulators = simpler.find('.//LoopModulators')
    is_modulated = loop_modulators.find('IsModulated')
    if is_modulated is None:
        is_modulated = ET.Element('IsModulated')
        loop_modulators.insert(0, is_modulated)
    is_modulated.set('Value', 'true')
    return sample_start_target.get('Id')


def update_midi_clip_notes(track, notes):
    """Remplace les notes dans le premier clip MIDI de la piste"""
    # Trouver le MainSequencer
    main_seq = track.find('DeviceChain/MainSequencer')
    if main_seq is None:
        print(f"    ⚠️  Pas de MainSequencer trouvé")
        return False

    # Trouver le premier clip MIDI
    midi_clip = main_seq.find('.//MidiClip')
    if midi_clip is None:
        print(f"    ⚠️  Pas de MidiClip trouvé")
        return False

    # Calculer la durée totale
    if not notes:
        return True

    # Le clip va jusqu'à la fin de sa dernière note (arrondie au temps) : Live coupe les notes au
    # bout du clip, et une note peut tenir bien plus que 4 temps depuis la v2.12
    max_time = math.ceil(max(note['time'] + note['duration'] for note in notes) + LEGATO_OVERLAP)

    # Mettre à jour CurrentEnd et LoopEnd
    current_end = midi_clip.find('.//CurrentEnd')
    if current_end is not None:
        current_end.set('Value', str(max_time))

    loop_end = midi_clip.find('.//Loop/LoopEnd')
    if loop_end is not None:
        loop_end.set('Value', str(max_time))

    out_marker = midi_clip.find('.//Loop/OutMarker')
    if out_marker is not None:
        out_marker.set('Value', str(max_time))

    # Trouver l'élément Notes/KeyTracks
    key_tracks = midi_clip.find('.//Notes/KeyTracks')
    if key_tracks is None:
        print(f"    ⚠️  Pas de KeyTracks trouvé")
        return False

    # Supprimer tous les KeyTracks existants
    for key_track in list(key_tracks):
        key_tracks.remove(key_track)

    # Tone portamento : la note qui précède une note en legato la chevauche, pour que le glide de
    # Live glisse sans redémarrer le sample
    durations = {}
    ordered = sorted(notes, key=lambda n: n['time'])
    for note, following in zip(ordered, ordered[1:]):
        if following.get('legato') and abs(note['time'] + note['duration'] - following['time']) < 1e-6:
            durations[id(note)] = note['duration'] + LEGATO_OVERLAP

    # Grouper les notes par hauteur MIDI
    notes_by_key = defaultdict(list)
    for note in notes:
        midi_key = int(note['note'])
        if 0 <= midi_key <= 127:
            notes_by_key[midi_key].append(note)

    # Créer les nouveaux KeyTracks ; chaque note a un NoteId unique dans le clip (1, 2...), comme Live
    note_id = 1
    for midi_key, key_notes in sorted(notes_by_key.items()):
        key_track = ET.SubElement(key_tracks, 'KeyTrack')
        key_track.set('Id', str(midi_key))

        notes_elem = ET.SubElement(key_track, 'Notes')

        for note in key_notes:
            note_event = ET.SubElement(notes_elem, 'MidiNoteEvent')
            note_event.set('Time', str(note['time']))
            note_event.set('Duration', str(durations.get(id(note), note['duration'])))
            note_event.set('Velocity', str(int(note['velocity'])))
            note_event.set('OffVelocity', '64')
            note_event.set('NoteId', str(note_id))
            note_id += 1

        midi_key_elem = ET.SubElement(key_track, 'MidiKey')
        midi_key_elem.set('Value', str(midi_key))

    set_value(midi_clip, 'Notes/NoteIdGenerator/NextId', note_id)
    return True

def note_spans(notes):
    """(note, début, fin) dans l'ordre du temps, la fin bornée au début de la note suivante

    Les points d'une automation doivent rester dans l'ordre du temps ; sur une piste fusionnée
    (--merge-tracks), deux notes de canaux différents peuvent se chevaucher d'un rien.
    """
    ordered = sorted(notes, key=lambda n: n['time'])
    for note, following in zip(ordered, ordered[1:] + [None]):
        end = note['time'] + note['duration']
        yield note, note['time'], min(end, following['time']) if following else end


def add_automation_envelope(track, target_id):
    """Ajoute à la piste une enveloppe d'automation vide liée à la cible `target_id`

    Returns:
        l'élément Events, à remplir avec add_float_event()
    """
    envelopes = track.find('AutomationEnvelopes/Envelopes')
    envelope = ET.SubElement(envelopes, 'AutomationEnvelope')
    envelope.set('Id', str(len(envelopes) - 1))  # index local à la piste, comme Live
    ET.SubElement(ET.SubElement(envelope, 'EnvelopeTarget'), 'PointeeId').set('Value', str(target_id))
    automation = ET.SubElement(envelope, 'Automation')
    events = ET.SubElement(automation, 'Events')
    # AutomationTransformViewState : requis par Live
    transform_state = ET.SubElement(automation, 'AutomationTransformViewState')
    ET.SubElement(transform_state, 'IsTransformPending').set('Value', 'false')
    ET.SubElement(transform_state, 'TimeAndValueTransforms')
    return events


def add_float_event(events, time, value):
    """Point d'automation (Id local à l'enveloppe, comme Live)"""
    event = ET.SubElement(events, 'FloatEvent')
    event.set('Id', str(len(events) - 1))
    event.set('Time', str(time))
    event.set('Value', str(value))


def create_sample_offset_automation(track, notes, target_id, sample_length):
    """Automation Sample Start du Simpler d'après les effets 9xx (plateau de 2 points par note)

    Args:
        track: élément MidiTrack
        notes: notes avec sample_offset_xm (0-255) ou None (retour au début du sample)
        target_id: Id de la cible Sample Start (populate_track_with_simpler)
        sample_length: longueur du sample en frames
    """
    events = add_automation_envelope(track, target_id)
    add_float_event(events, '0.0', '0.0')
    for note, start, end in note_spans(notes):
        offset = note.get('sample_offset_xm')
        sample_start = '0.0'
        if offset is not None:
            # 9xx : multiplicateur de 256 octets, soit offset × 128 frames pour un sample 16 bits
            sample_start = (offset * 256 / 2.0) / sample_length if sample_length > 0 else 0.0
            sample_start = max(0.0, min(1.0, sample_start))
        add_float_event(events, start, sample_start)
        add_float_event(events, end, sample_start)
    print(f"    → Automation Sample Start: {len(events)} points")


def pan_to_ableton(pan_xm):
    """Panoramique XM (0-255, 128 = centre) → Ableton (-1.0 à +1.0)"""
    return max(-1.0, min(1.0, (pan_xm - 128) / 128.0))


def track_panning(notes):
    """Panoramique d'une piste (XM 0-255) : (valeur unique, ou None s'il varie ; le plus entendu)

    Le panoramique d'une note est celui de son canal (replayer.py) : défaut du sample, Cx ou 8xx.
    """
    values = {note['pan'] for note in notes} | {pan for note in notes for _, pan in note['pan_moves']}
    heard = Counter()
    for note in notes:
        heard[note['pan']] += note['duration']
    return (values.pop() if len(values) == 1 else None), heard.most_common(1)[0][0]


def volume_db(gain):
    """Volume du device (dB) pour un gain relatif au volume de départ de la note"""
    if gain <= 0:
        return DEVICE_VOLUME_MIN_DB
    return max(DEVICE_VOLUME_MIN_DB, min(36.0, DEVICE_VOLUME_DB + 20 * math.log10(gain)))


def create_volume_automation(track, notes, envelope=None):
    """Automation du volume du Sampler / Simpler : ce qui change pendant chaque note

    La vélocité donne le volume du canal au début de la note ; l'automation suit, en dB relatifs, ses
    changements pendant la note (glissements, Cxx, volume haché, fondu d'entrée) et, si `envelope`
    est fournie (--envelope), la forme de l'enveloppe de volume FT2. Elle repart de 0 dB à chaque note.

    Returns:
        True si une automation a été écrite (sinon le volume reste à 0 dB)
    """
    if envelope is None and not any(note['volume_moves'] for note in notes):
        return False
    target = track.find('DeviceChain/DeviceChain/Devices/*/VolumeAndPan/Volume/AutomationTarget')
    if target is None:
        return False

    points = []  # (temps, dB) ; deux points au même instant = marche
    for note, start, end in note_spans(notes):
        reference = note['volume']
        curve = []  # (temps, valeur de l'enveloppe 0-64), reliés par des segments
        if envelope is not None:
            ticks = note['duration'] / note['tick']
            curve = [(start + tick * note['tick'], value) for tick, value in envelope_curve(envelope, ticks)]

        def envelope_at(time):
            if not curve:
                return 64.0
            if time <= curve[0][0]:
                return curve[0][1]
            for (t0, v0), (t1, v1) in zip(curve, curve[1:]):
                if t0 <= time <= t1:
                    return v1 if t1 == t0 else v0 + (v1 - v0) * (time - t0) / (t1 - t0)
            return curve[-1][1]

        def value(level, time):
            return volume_db(level / reference * envelope_at(time) / 64.0)

        level = reference
        changes = sorted([(t, 'level', v) for t, v in note['volume_moves']] +
                         [(t, 'envelope', v) for t, v in curve], key=lambda c: c[0])
        if changes and changes[0][0] <= start and changes[0][1] == 'level':
            level = changes.pop(0)[2]  # fondu d'entrée : la note part de 0
        points.append((start, value(level, start)))
        for time, kind, new in changes:
            if not start < time < end and kind == 'level':
                continue
            if kind == 'level':
                points.append((time, value(level, time)))
                level = new
            points.append((min(time, end), value(level, min(time, end))))
        points.append((end, value(level, end)))

    events = add_automation_envelope(track, target.get('Id'))
    add_float_event(events, '0.0', round(points[0][1], 4))  # valeur avant la première note
    previous = (0.0, points[0][1])
    for time, db in points:
        if time == previous[0] and abs(db - previous[1]) < 1e-9:
            continue
        add_float_event(events, time, round(db, 4))
        previous = (time, db)
    print(f"    → Automation volume: {len(events)} points")
    return True


def create_pan_automation(track, notes):
    """Automation du panoramique de la piste (mixer), en escalier

    Chaque note impose son panoramique à son début, puis ses changements pendant la note (Cx, 8xx,
    glissements). La zone du Sampler reste alors au centre : le mixer porte tout le panoramique.

    Args:
        track: élément MidiTrack
        notes: notes avec pan (0-255) et pan_moves [(temps, pan)]
    """
    pan_target = track.find('DeviceChain/Mixer/Pan/AutomationTarget')
    if pan_target is None:
        print("    ⚠️  AutomationTarget du Pan non trouvé")
        return
    events = add_automation_envelope(track, pan_target.get('Id'))

    changes = []
    for note, start, end in note_spans(notes):
        changes.append((start, note['pan']))
        changes.extend(move for move in note['pan_moves'] if move[0] < end)
    current = changes[0][1]
    add_float_event(events, '0.0', pan_to_ableton(current))
    for time, pan in changes[1:]:
        if pan != current:
            # Marche : deux points au même instant (ancienne valeur, nouvelle valeur)
            add_float_event(events, time, pan_to_ableton(current))
            add_float_event(events, time, pan_to_ableton(pan))
            current = pan

    print(f"    → Automation panning: {len(events)} points")


LIVE_TEMPO_MIN, LIVE_TEMPO_MAX = 20.0, 999.0


def write_tempo(live_set_element, tempo_changes):
    """Écrit le tempo du set : valeur initiale et automation en escalier

    Live code un saut de valeur par deux points au même instant (ancienne puis nouvelle
    valeur), comme dans les sets qu'il enregistre lui-même.

    Args:
        live_set_element: élément LiveSet
        tempo_changes: [(temps en beats, BPM Live)], le premier au temps 0 (replayer.play_song)

    Returns:
        Nombre de changements écrits en automation
    """
    tempos = []
    for time, tempo in tempo_changes:
        clamped = max(LIVE_TEMPO_MIN, min(LIVE_TEMPO_MAX, tempo))
        if clamped != tempo:
            print(f"   ⚠️  Tempo {tempo:.2f} hors de la plage de Live, ramené à {clamped:.0f} (temps {time})")
        tempos.append((time, clamped))

    main_track = live_set_element.find('MainTrack')
    if main_track is None:
        main_track = live_set_element.find('MasterTrack')  # nom avant Live 12
    tempo_param = main_track.find('DeviceChain/Mixer/Tempo')
    tempo_param.find('Manual').set('Value', str(tempos[0][1]))
    target_id = tempo_param.find('AutomationTarget').get('Id')

    # Enveloppe de tempo existante dans le template (un seul point initial)
    envelope = None
    for candidate in main_track.iter('AutomationEnvelope'):
        if candidate.find('EnvelopeTarget/PointeeId').get('Value') == target_id:
            envelope = candidate
            break
    if envelope is None:
        envelopes = main_track.find('AutomationEnvelopes/Envelopes')
        envelope = ET.SubElement(envelopes, 'AutomationEnvelope')
        envelope.set('Id', str(len(envelopes) - 1))
        ET.SubElement(ET.SubElement(envelope, 'EnvelopeTarget'), 'PointeeId').set('Value', target_id)
        automation = ET.SubElement(envelope, 'Automation')
        ET.SubElement(automation, 'Events')
        transform_state = ET.SubElement(automation, 'AutomationTransformViewState')
        ET.SubElement(transform_state, 'IsTransformPending').set('Value', 'false')
        ET.SubElement(transform_state, 'TimeAndValueTransforms')

    events = envelope.find('Automation/Events')
    for event in list(events):
        events.remove(event)

    def add_event(time, value):
        event = ET.SubElement(events, 'FloatEvent')
        event.set('Id', str(len(events) - 1))
        event.set('Time', str(time))
        event.set('Value', str(value))

    add_event(-63072000, tempos[0][1])  # valeur avant le début du morceau (convention Live)
    for (_, previous), (time, tempo) in zip(tempos, tempos[1:]):
        add_event(time, previous)
        add_event(time, tempo)

    print(f"   ✓ Tempo initial: {tempos[0][1]:.2f} BPM")
    if len(tempos) > 1:
        print(f"   ✓ {len(tempos) - 1} changement(s) de tempo en automation")
    return len(tempos) - 1


# Glide du Sampler / Simpler (PortamentoMode) : le mode qui ne glisse que sur des notes qui se
# chevauchent, sans redémarrer le sample (cf. tools/live_calibration.py). Une note suivie d'une note
# en tone portamento la chevauche de LEGATO_OVERLAP temps (update_midi_clip_notes)
GLIDE_MODE = 2  # mesuré : 1 glisse mais redémarre le sample, 2 glisse sans le redémarrer
LEGATO_OVERLAP = 1 / 64.0
LIVE_GLIDE_MAX_MS = 10000


def configure_glide(device, notes):
    """Tone portamento : glide du Sampler, durée typique (médiane) des glissements de la piste"""
    glides = sorted(note['glide_ms'] for note in notes if note.get('legato') and note.get('glide_ms'))
    if not glides:
        return
    glide_ms = max(0.1, min(LIVE_GLIDE_MAX_MS, glides[len(glides) // 2]))
    set_value(device, 'Globals/PortamentoMode/Manual', GLIDE_MODE)
    set_value(device, 'Globals/PortamentoTime/Manual', round(glide_ms, 1))
    print(f"    → Glide: {glide_ms:.0f} ms ({len(glides)} notes en tone portamento)")


LIVE_RELEASE_MAX_MS = 60000  # borne du paramètre Release du Sampler et du Simpler


def configure_release(device, sample_info, bpm):
    """Release du Sampler / Simpler = fin du son FT2 après un key-off

    Seulement pour les instruments qu'un key-off arrête avec une release (enveloppe de volume avec
    fadeout ou qui retombe à 0, cf. replayer.release_ticks) : la note MIDI s'arrête au key-off et le
    Sampler fait la fin du son. Les autres gardent la release du template.
    """
    ticks = sample_info.get('release_ticks')
    if not ticks:
        return
    release_ms = min(ticks * 2500.0 / bpm, LIVE_RELEASE_MAX_MS)  # 1 tick = 2,5 / BPM secondes
    release = device.find('.//VolumeAndPan/Envelope/ReleaseTime/Manual')
    if release is not None:
        release.set('Value', str(release_ms))
        print(f"    → Release: {release_ms:.0f} ms (fin du son FT2 après un key-off)")


def merge_and_deduplicate_notes(notes_lists):
    """Fusionne plusieurs listes de notes et déduplique les notes identiques au même moment

    Args:
        notes_lists: Liste de listes de notes à fusionner

    Returns:
        Liste de notes fusionnées et triées par temps, sans doublons
    """
    # Fusionner toutes les notes
    all_notes = []
    for notes in notes_lists:
        all_notes.extend(notes)

    # Trier par temps
    all_notes.sort(key=lambda x: x['time'])

    # Dédupliquer: si 2 notes ont même temps et même note MIDI, garder une seule
    deduplicated = []
    seen = set()

    for note in all_notes:
        # Clé unique: (temps, note MIDI)
        # On arrondit le temps à 4 décimales pour éviter les problèmes de float
        key = (round(note['time'], 4), note['note'])

        if key not in seen:
            seen.add(key)
            deduplicated.append(note)

    return deduplicated


def distribute_notes_to_avoid_overlap(merged_notes):
    """Distribue les notes sur plusieurs pistes pour éviter les chevauchements temporels

    Cette fonction implémente un algorithme de bin-packing pour assigner les notes
    à différentes pistes de manière à ce qu'aucune note ne chevauche une autre
    dans la même piste (éviter la polyphonie par piste).

    Args:
        merged_notes: Liste de notes triées par temps

    Returns:
        Liste de listes de notes (une liste par piste nécessaire)
        Exemple: [[notes_piste_1], [notes_piste_2], ...]
        La première liste correspond à "All notes", les suivantes aux auxiliaires
    """
    if not merged_notes:
        return [[]]

    # Liste de pistes, chaque piste contient des notes
    tracks = [[]]

    for note in merged_notes:
        note_start = note['time']
        note_end = note_start + note['duration']

        # Trouver une piste où cette note ne chevauche aucune note existante
        placed = False
        for track in tracks:
            # Vérifier si la note peut être placée dans cette piste
            has_overlap = False
            for existing_note in track:
                existing_start = existing_note['time']
                existing_end = existing_start + existing_note['duration']

                # Chevauchement si les intervalles se superposent
                # Note: on utilise une petite marge (0.001) pour éviter les problèmes de float
                if not (note_end <= existing_start + 0.001 or note_start >= existing_end - 0.001):
                    has_overlap = True
                    break

            if not has_overlap:
                track.append(note)
                placed = True
                break

        # Si aucune piste ne convient, créer une nouvelle piste auxiliaire
        if not placed:
            tracks.append([note])

    return tracks


def convert_xm_to_ableton(xm_path, template_path=None, output_dir=None, enable_pan_automation=False, enable_envelope=False, enable_sample_offset=False, enable_merge_tracks=False):
    """Convertit un fichier XM/MOD en projet Ableton

    Args:
        xm_path: Chemin vers le fichier XM/MOD
        template_path: set Live personnel dont reprendre les fragments (optionnel, cf. live_set.py)
        output_dir: Répertoire de sortie (optionnel)
        enable_pan_automation: Activer les automations de panning (effet 8xx)
        enable_envelope: Enveloppes de volume FT2 dans l'automation de volume
        enable_sample_offset: Activer l'effet 9xx (Sample Offset) avec Simpler
    """

    if not os.path.exists(xm_path):
        print(f"❌ Erreur: '{xm_path}' n'existe pas")
        return False

    # Détecter le format du fichier
    file_ext = os.path.splitext(xm_path)[1].lower()
    is_mod = (file_ext == '.mod')
    is_xm = (file_ext == '.xm')

    if not (is_mod or is_xm):
        print(f"⚠️  Attention: '{xm_path}' n'a pas l'extension .xm ou .mod")

    format_name = "MOD" if is_mod else "XM"
    print("="*60)
    print(f"CONVERSION {format_name} → ABLETON LIVE")
    print("="*60)

    # Préparer les répertoires
    if not output_dir:
        xm_basename = os.path.splitext(os.path.basename(xm_path))[0]
        # Créer dans le sous-répertoire "Conversions Ableton Live"
        base_dir = os.path.dirname(xm_path)
        conversions_dir = os.path.join(base_dir, "Conversions Ableton Live")
        os.makedirs(conversions_dir, exist_ok=True)
        output_dir = os.path.join(conversions_dir, f"{xm_basename}_Ableton_Project")

    os.makedirs(output_dir, exist_ok=True)

    samples_dir = os.path.join(output_dir, 'Samples')
    os.makedirs(samples_dir, exist_ok=True)

    # Extraire samples ET patterns selon le format
    print(f"\n📀 Extraction du fichier {format_name}...")
    if is_mod:
        samples, patterns, xm_info = extract_mod(xm_path, samples_dir)
    else:
        samples, patterns, xm_info = extract_xm(xm_path, samples_dir)

    if not samples:
        print("\n❌ Aucun sample extrait !")
        return False

    # Enveloppes de volume (lues par xm_parser.py ; le format MOD n'en a pas)
    if enable_envelope:
        with_envelope = {s['instrument'] for s in samples if (s.get('envelope') or {}).get('enabled')}
        print(f"\n🎛️  Enveloppes volume: {len(with_envelope)} instrument(s)")

    # Jouer le morceau comme le tracker : ordre de lecture réel, ticks, changements de tempo,
    # longueur réelle des notes (fin du sample, enveloppe, volume, key-off)
    song = play_song(patterns, xm_info['pattern_order'], xm_info['tempo'], xm_info['bpm'],
                     'mod' if is_mod else 'xm', samples)
    tracks_data = song['tracks']
    tempo_changes = song['tempo_changes']
    minutes, secs = divmod(song['duration_seconds'], 60)
    # Instruments arrêtés par un key-off avec release : la fin du son devient la release du Sampler
    for sample in samples:
        if sample['instrument'] in song['released_instruments']:
            sample['release_ticks'] = song['released_instruments'][sample['instrument']]

    print(f"\n{'='*60}")
    print(f"MODULE: {xm_info['name']}")
    print(f"Speed / BPM initiaux: {xm_info['tempo']} ticks/row, {xm_info['bpm']} BPM")
    print(f"Tempo Live initial: {tempo_changes[0][1]:.2f} BPM "
          f"({len(tempo_changes) - 1} changement(s) en cours de morceau)")
    print(f"Durée: {int(minutes)}:{secs:04.1f} ({song['end_time'] / 4:.0f} mesures)")
    print(f"Canaux: {xm_info['channels']}")
    print(f"Samples: {len(samples)}")
    print(f"Patterns: {len(patterns)}")
    print(f"{'='*60}")

    # Détecter les instruments qui utilisent l'effet 9xx (Sample Offset)
    instruments_with_9xx = set()
    if enable_sample_offset:
        instruments_with_9xx = detect_effect_9xx_per_instrument(tracks_data)
        if instruments_with_9xx:
            inst_hex_list = [f"{i:02X}" for i in sorted(instruments_with_9xx)]
            print(f"\n🎚️  Effet 9xx détecté sur {len(instruments_with_9xx)} instrument(s): {', '.join(inst_hex_list)}")
            print(f"   → Ces instruments utiliseront Simpler (Sample Start automatable)")
        else:
            print(f"\n🎚️  Aucun effet 9xx détecté")

    # Créer un mapping instrument -> sample
    instrument_to_sample = {s['instrument']: s for s in samples}

    # Set Live assemblé à partir des fragments de templates/ (ou d'un set personnel)
    if template_path and not os.path.exists(template_path):
        print(f"❌ Erreur: template '{template_path}' n'existe pas")
        return False
    print(f"\n📝 Fragments du set: {os.path.basename(template_path) if template_path else 'templates/'}")
    builder = LiveSetBuilder(template_path)

    # Créer un mapping instrument -> couleur
    # Utiliser des couleurs différentes pour chaque instrument (0-69 sont les couleurs d'Ableton)
    unique_instruments = sorted(set(inst for channel_data in tracks_data.values() for inst in channel_data.keys() if inst in instrument_to_sample))
    instrument_colors = {}
    color_palette = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                     21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
                     41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
                     61, 62, 63, 64, 65, 66, 67, 68, 69]

    for i, inst in enumerate(unique_instruments):
        instrument_colors[inst] = color_palette[i % len(color_palette)]

    # Organiser les pistes par instrument puis par canal
    # Créer une liste de toutes les pistes à créer
    tracks_to_create = []

    # D'abord grouper par instrument
    for instrument in unique_instruments:
        sample = instrument_to_sample[instrument]
        # Notation hexadécimale pour l'instrument (01, 02, ..., 0A, 0B, etc.)
        inst_hex = f"{instrument:02X}"
        sample_name = sample['name'].strip() if sample['name'].strip() else f"Instrument_{inst_hex}_Sample_1"

        # Collecter toutes les pistes (canaux) qui utilisent cet instrument
        instrument_tracks = []
        for channel in sorted(tracks_data.keys()):
            if instrument in tracks_data[channel]:
                notes = tracks_data[channel][instrument]
                track_name = f"Ch{channel+1} - {sample_name}"

                instrument_tracks.append({
                    'instrument': instrument,
                    'channel': channel,
                    'sample': sample,
                    'notes': notes,
                    'track_name': track_name,
                    'sample_name': sample_name,
                    'color': instrument_colors[instrument]
                })

        # Si --merge-tracks activé, créer uniquement les pistes fusionnées (pas les pistes individuelles)
        if enable_merge_tracks and len(instrument_tracks) > 0:
            # Fusionner toutes les notes de cet instrument
            all_notes_lists = [track['notes'] for track in instrument_tracks]
            merged_notes = merge_and_deduplicate_notes(all_notes_lists)

            # Distribuer les notes sur plusieurs pistes pour éviter les chevauchements
            distributed_tracks = distribute_notes_to_avoid_overlap(merged_notes)

            # Créer la piste "All notes" (première distribution) + pistes auxiliaires si nécessaire
            for i, notes_for_track in enumerate(distributed_tracks):
                if len(notes_for_track) == 0:
                    continue  # Skip empty tracks

                # Nom de la piste: "All notes" pour la première, "All notes (2)", "All notes (3)", etc. pour les auxiliaires
                if i == 0:
                    track_name = "All notes"
                else:
                    track_name = f"All notes ({i+1})"

                merged_track = {
                    'instrument': instrument,
                    'channel': None,  # Pas de canal spécifique
                    'sample': sample,
                    'notes': notes_for_track,
                    'track_name': track_name,
                    'sample_name': sample_name,
                    'color': instrument_colors[instrument]
                }

                tracks_to_create.append(merged_track)

        else:
            # Mode normal: créer les pistes individuelles par canal
            tracks_to_create.extend(instrument_tracks)

    print(f"\n🎹 {len(tracks_to_create)} pistes")
    pistes_creees = []

    for track_info in tracks_to_create:
        track = builder.add_track('midi_track')
        update_track_name(track, track_info['track_name'])
        update_track_color(track, track_info['color'])

        # Toutes les pistes (y compris ALL) ont un instrument
        instrument = track_info['instrument']
        use_simpler = (enable_sample_offset and instrument in instruments_with_9xx)

        # Panoramique : fixe sur la zone du Sampler s'il ne varie pas ; sinon automation du mixer
        # (--pan-automation, zone au centre) ou, sans elle, le panoramique le plus entendu
        constant_pan, heard_pan = track_panning(track_info['notes'])
        automate_pan = enable_pan_automation and constant_pan is None
        zone_pan = 128 if automate_pan else (constant_pan if constant_pan is not None else heard_pan)

        if use_simpler:
            # Utiliser Simpler (pour effet 9xx)
            sample_start_id = populate_track_with_simpler(track, track_info['sample'], output_dir, builder,
                                                          bpm=xm_info['bpm'], panning=zone_pan)
        else:
            # Utiliser Sampler (normal)
            update_sampler_sample(track, track_info['sample'], output_dir, builder.sample_part,
                                bpm=xm_info['bpm'], panning=zone_pan)

        # Tone portamento : notes en legato et glide du Sampler
        configure_glide(track.find('DeviceChain/DeviceChain/Devices')[0], track_info['notes'])

        # Ajouter les notes MIDI : vélocité = volume du canal au début de la note
        for note in track_info['notes']:
            note['velocity'] = velocity_for(note['volume'])
        update_midi_clip_notes(track, track_info['notes'])

        # Automation de volume : changements pendant les notes, enveloppe FT2 avec --envelope
        envelope = track_info['sample'].get('envelope') if enable_envelope else None
        create_volume_automation(track, track_info['notes'], envelope if envelope and envelope['enabled'] else None)

        # Automation Sample Start (effet 9xx, Simpler)
        if use_simpler and sample_start_id and any(n.get('sample_offset_xm') is not None for n in track_info['notes']):
            create_sample_offset_automation(track, track_info['notes'], sample_start_id, track_info['sample']['length'])

        if automate_pan:
            create_pan_automation(track, track_info['notes'])

        # Piste repliée, non armée
        set_value(track, 'DeviceChain/MainSequencer/Recorder/IsArmed', 'false')
        set_value(track, 'TrackUnfolded', 'false')

        track_info['track_element'] = track
        pistes_creees.append(track_info['track_name'])
        print(f"  ✓ {track_info['track_name']} ({len(track_info['notes'])} notes, color={track_info['color']})")

    # Groupes (repliés) pour les instruments joués sur 2 pistes ou plus, avant leur première piste
    print(f"\n📁 Création des groupes de pistes...")
    for instrument in unique_instruments:
        tracks_for_inst = [info for info in tracks_to_create if info['instrument'] == instrument]
        if len(tracks_for_inst) < 2:
            continue
        sample_name = tracks_for_inst[0]['sample_name']
        group = builder.add_track('group_track', before=tracks_for_inst[0]['track_element'])
        update_track_name(group, sample_name)
        set_value(group, 'Color', tracks_for_inst[0]['color'])
        set_value(group, 'TrackUnfolded', 'false')

        # Pistes du groupe : rattachées au groupe, sortie audio vers lui (nécessaire au Solo du groupe)
        for track_info in tracks_for_inst:
            track_elem = track_info['track_element']
            set_value(track_elem, 'TrackGroupId', group.get('Id'))
            set_value(track_elem, 'DeviceChain/AudioOutputRouting/Target', 'AudioOut/GroupTrack')
            set_value(track_elem, 'DeviceChain/AudioOutputRouting/UpperDisplayString', sample_name)
            set_value(track_elem, 'DeviceChain/AudioOutputRouting/LowerDisplayString', '')

        print(f"  ✓ Groupe créé: {sample_name} ({len(tracks_for_inst)} pistes)")

    # Tempo : BPM Live = BPM × 6 / Speed (formule FT2), plus une automation en escalier
    # pour chaque changement Fxx en cours de morceau
    print(f"\n🎵 Tempo:")
    write_tempo(builder.live_set, tempo_changes)

    # Tête de lecture et sélection au début (1.1.1)
    set_value(builder.live_set, 'Transport/CurrentTime', 0)
    set_value(builder.live_set, 'TimeSelection/AnchorTime', 0)
    set_value(builder.live_set, 'TimeSelection/OtherTime', 0)

    # Sauvegarder (utiliser le nom du fichier, pas le nom interne du module)
    # Cela évite les conflits quand plusieurs fichiers ont le même nom interne
    xm_basename = os.path.splitext(os.path.basename(xm_path))[0]
    als_path = os.path.join(output_dir, f"{xm_basename}.als")
    print(f"\n💾 Sauvegarde du projet...")
    builder.save(als_path)

    # Vérifier la cohérence du set final (IDs, automations, samples, boucles, accordage)
    print(f"\n🔍 Vérification du set...")
    print_report(als_path, validate_als(als_path))

    print(f"\n{'='*60}")
    print(f"✓ CONVERSION TERMINÉE")
    print(f"{'='*60}")
    print(f"\nProjet: {als_path}")
    print(f"Samples: {samples_dir}/")
    print(f"\n📊 RÉSUMÉ:")
    print(f"  • {len(pistes_creees)} pistes créées")
    print(f"  • {len(samples)} samples extraits")
    print(f"\n💡 Ouvrez le fichier .als dans Ableton Live !")

    return True

def main():
    import argparse
    import sys

    # Si aucun argument, afficher l'aide
    if len(sys.argv) == 1:
        sys.argv.append('--help')

    title = f"XM2LIVE v{__version__} - Tracker → Ableton Live Converter".center(60)
    parser = argparse.ArgumentParser(
        description=f'''
╔════════════════════════════════════════════════════════════╗
║{title}║
╚════════════════════════════════════════════════════════════╝

Convertit les fichiers tracker (FastTracker 2 XM, Amiga MOD) en
projets Ableton Live avec samples, notes, tempo et effets.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
════════════════════════════════════════════════════════════
EXEMPLES D'UTILISATION
════════════════════════════════════════════════════════════

Conversion simple (template auto-créé):
  python3 xm2live.py mon_fichier.xm
  python3 xm2live.py ma_musique.mod

Avec template personnalisé (optionnel):
  python3 xm2live.py mon_fichier.xm /path/to/template.als

Avec options avancées:
  python3 xm2live.py fichier.xm --pan-automation
  python3 xm2live.py fichier.xm --sample-offset
  python3 xm2live.py fichier.xm --pan-automation --sample-offset

Note: Le template est OPTIONNEL. Par défaut, le set est assemblé à partir
      des fragments de templates/ (enregistrés par Live). Un set personnel
      (enregistré par Live) remplace les fragments qu'il contient : piste MIDI
      avec Sampler, piste de groupe, Simpler, réglages du set.

════════════════════════════════════════════════════════════
SWITCHES DISPONIBLES
════════════════════════════════════════════════════════════

--pan-automation    Active les automations de panning (effet 8xx)
                    Crée des automations Track Pan dans Ableton
                    Par défaut: désactivé

--sample-offset     Active l'effet 9xx (Sample Offset) via Simpler
                    Crée des automations Sample Start
                    LIMITATION: ping-pong loops → forward
                    Par défaut: désactivé

--envelope          Ajoute les enveloppes de volume FT2 à l'automation de
                    volume du Sampler (forme exacte, note par note)
                    Par défaut: désactivé

--merge-tracks      Crée une piste de référence "ALL" par instrument
                    Contient toutes les notes fusionnées (sans dédoublons)
                    Piste sans instrument, utile comme référence visuelle
                    Placée en première position dans chaque groupe
                    Par défaut: désactivé

════════════════════════════════════════════════════════════
RÉSULTAT
════════════════════════════════════════════════════════════

Le projet converti sera créé dans:
  [répertoire source]/Conversions Ableton Live/[nom]_Ableton_Project/

Contenu:
  • [nom].als           - Projet Ableton Live
  • Samples/            - Samples WAV exportés (16-bit)

════════════════════════════════════════════════════════════
Pour plus d'aide: python3 xm2live.py --help
Documentation complète: README.md
        '''
    )

    parser.add_argument('fichier', help='Fichier XM ou MOD à convertir')
    parser.add_argument('template', nargs='?', help='Template Ableton (optionnel)')
    parser.add_argument('--pan-automation', action='store_true',
                        help='Activer les automations de panning (effet 8xx). '
                             'Par défaut désactivé car rare dans les modules.')
    parser.add_argument('--envelope', action='store_true',
                        help='Ajouter les enveloppes de volume FT2 à l\'automation de volume du Sampler '
                             '(forme exacte, note par note).')
    parser.add_argument('--sample-offset', action='store_true',
                        help='Activer l\'effet 9xx (Sample Offset) avec Simpler. '
                             'Les instruments avec effet 9xx utiliseront Simpler au lieu de Sampler. '
                             'LIMITATION: conversion ping-pong → forward.')
    parser.add_argument('--merge-tracks', action='store_true',
                        help='Mode fusion: créer une piste "All notes" par instrument au lieu des pistes individuelles par canal. '
                             'Détecte automatiquement les chevauchements temporels et crée des pistes auxiliaires si nécessaire.')
    parser.add_argument('--version', action='version', version=f'xm2live {__version__}')
    parser.add_argument('--output', metavar='DIR',
                        help='Répertoire de sortie du projet Ableton (optionnel). '
                             'Si non spécifié, le projet est créé à côté du fichier source dans '
                             '"Conversions Ableton Live/[nom]_Ableton_Project".')

    args = parser.parse_args()

    xm_path = args.fichier
    template_path = args.template  # None : fragments de templates/

    # Fix: Si template_path commence par '--', c'est un flag mal parsé, donc None
    if template_path and template_path.startswith('--'):
        template_path = None


    try:
        success = convert_xm_to_ableton(xm_path, template_path,
                                        output_dir=args.output,
                                        enable_pan_automation=args.pan_automation,
                                        enable_envelope=args.envelope,
                                        enable_sample_offset=args.sample_offset,
                                        enable_merge_tracks=args.merge_tracks)
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Conversion interrompue par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERREUR INATTENDUE:")
        print(f"   {type(e).__name__}: {e}")
        print(f"\n   Si cette erreur persiste, veuillez vérifier:")
        print(f"   1. Que le fichier XM n'est pas corrompu")
        print(f"   2. Que le template est valide")
        print(f"   3. Que vous avez les droits d'écriture dans le répertoire")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
