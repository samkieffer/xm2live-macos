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
from collections import defaultdict
from envelope_reader import read_xm_envelopes
from buildable.live_set import LiveSet

# Importer les fonctions de lecture XM
from xm_parser import (
    read_xm_header,
    read_patterns,
    parse_pattern_data,
    extract_samples_and_patterns as extract_xm,
    organize_tracks_by_channel as organize_xm
)

# Importer les fonctions de lecture MOD
from mod_parser import (
    extract_samples_and_patterns as extract_mod,
    organize_tracks_by_channel as organize_mod
)

def update_all_ids(element, next_id):
    """
    Met à jour tous les attributs Id dans l'élément et ses enfants.
    Retourne le prochain ID disponible.
    """
    # Mettre à jour l'Id de cet élément s'il en a un
    if 'Id' in element.attrib:
        try:
            int(element.get('Id'))  # Vérifier que c'est un nombre
            element.set('Id', str(next_id))
            next_id += 1
        except (ValueError, TypeError):
            # Si l'Id n'est pas un nombre, on le laisse tel quel
            pass

    # Récursivement mettre à jour tous les enfants
    for child in element:
        next_id = update_all_ids(child, next_id)

    return next_id

def update_track_name(track, new_name):
    """Change le nom d'une piste"""
    name_elem = track.element.find('.//Name/EffectiveName')
    if name_elem is not None:
        name_elem.set('Value', new_name)

def update_track_color(track, color_index):
    """Change la couleur d'une piste et de son clip MIDI"""
    # Couleur de la piste
    track_color = track.element.find('.//Color')
    if track_color is not None:
        track_color.set('Value', str(color_index))

    # Couleur du clip MIDI
    midi_clip = track.element.find('.//MidiClip')
    if midi_clip is not None:
        clip_color = midi_clip.find('.//Color')
        if clip_color is not None:
            clip_color.set('Value', str(color_index))

def update_sampler_sample(track, sample_info, project_dir, template_sample_part, bpm=125, speed=6, enable_envelope=False):
    """Change le sample chargé dans le Sampler/MultiSampler en copiant la structure du template

    Args:
        sample_info: Dict contenant path, relative_note, loop_start, loop_length, loop_type, volume, envelope
        project_dir: Répertoire du projet
        template_sample_part: Template du sample part
        bpm: BPM du module (pour conversion temps enveloppe)
        speed: Speed du module (ticks par row)
        enable_envelope: Activer la conversion enveloppe FT2 → ADSR
    """

    sample_path = sample_info['path']
    relative_note = sample_info.get('relative_note', 0)

    # Trouver le device Sampler/MultiSampler
    devices = track.element.find('.//DeviceChain/Devices')
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

    # Mettre à jour RootKey en fonction du relative_note du XM
    # Dans XM: relative_note = -1 signifie 1 demi-ton plus bas
    # Dans Ableton: RootKey = 60 (C3) par défaut
    # Donc: RootKey = 60 - relative_note
    root_key_elem = new_sample_part.find('.//RootKey')
    if root_key_elem is not None:
        root_key = 60 - relative_note
        root_key_elem.set('Value', str(root_key))
        if relative_note != 0:
            print(f"    → RootKey ajustée: {root_key} (relative_note={relative_note:+d})")

    # Mettre à jour Detune (finetune) juste après RootKey
    # XM finetune: -128 à +127 (centièmes de demi-ton)
    # Ableton Detune: -50 à +50 cents
    finetune = sample_info.get('finetune', 0)
    if finetune != 0:
        detune_elem = new_sample_part.find('.//Detune')
        if detune_elem is not None:
            # Conversion: XM utilise la plage complète -128/+127, Ableton -50/+50
            # Donc diviser par ~2.56 (128/50)
            detune_value = finetune / 2.56
            # Limiter à la plage Ableton
            detune_value = max(-50, min(50, detune_value))
            detune_elem.set('Value', str(detune_value))
            print(f"    → Detune: {detune_value:.1f} cents (finetune={finetune:+d})")

    # Mettre à jour Volume (volume par défaut du sample)
    # XM volume: 0-64 (64 = 100%)
    # Ableton Volume: 0.0-1.0 (1.0 = 0 dB)
    # Réduction à 0.25 (-12 dB) pour éviter la saturation avec velocity + Vol-Vel 35%
    xm_volume = sample_info.get('volume', 64)
    volume_elem = new_sample_part.find('.//Volume')
    if volume_elem is not None:
        # Conversion linéaire avec réduction de -12dB
        ableton_volume = (xm_volume / 64.0) * 0.25
        volume_elem.set('Value', str(ableton_volume))

        # Afficher seulement si différent du maximum
        if xm_volume != 64:
            # Calculer les dB pour l'affichage
            if ableton_volume > 0:
                db_value = 20 * math.log10(ableton_volume)
                print(f"    → Volume: {ableton_volume:.3f} ({db_value:.1f} dB, XM={xm_volume}/64)")
            else:
                print(f"    → Volume: 0.000 (-∞ dB, XM={xm_volume}/64)")

    # Configurer VolumeVelScale (Vol<Vel) à 35% pour que la velocity affecte le volume
    # Cela permet aux variations de volume des notes (velocity) d'influencer le volume final
    # 35% est la valeur par défaut d'Ableton Simpler/Sampler
    vel_scale = sampler.find('.//VolumeAndPan/VolumeVelScale/Manual')
    if vel_scale is not None:
        vel_scale.set('Value', '0.35')

    # Mettre à jour Panorama (panning par défaut du sample)
    # XM panning: 0-255 (0=gauche, 128=centre, 255=droite)
    # Ableton Panorama: -1.0 à +1.0 (0=centre)
    xm_panning = sample_info.get('panning', 128)
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

    # Configurer l'enveloppe ADSR si activé
    if enable_envelope:
        envelope_info = sample_info.get('envelope')
        if envelope_info and envelope_info.get('enabled'):
            configure_envelope_adsr(sampler, envelope_info, bpm, speed)

    return True


def detect_effect_9xx_per_instrument(patterns, pattern_order, file_format='xm'):
    """Détecte quels instruments utilisent l'effet 9xx (Sample Offset)

    Args:
        patterns: Liste des patterns du module
        pattern_order: Ordre de lecture des patterns
        file_format: 'xm' ou 'mod' (pour savoir quel champ utiliser)

    Returns:
        set: Ensemble des numéros d'instruments qui utilisent l'effet 9xx
    """
    instruments_with_9xx = set()

    # Parcourir les patterns dans l'ordre de lecture
    for pattern_idx in pattern_order:
        if pattern_idx >= len(patterns):
            continue

        pattern = patterns[pattern_idx]

        # Parcourir les events du pattern
        for note_event in pattern.get('data', []):
            instrument = note_event.get('instrument')

            if instrument is None:
                continue

            # Vérifier selon le format
            if file_format == 'xm':
                # XM : effet_type = 0x09
                if note_event.get('effect_type') == 0x09:
                    instruments_with_9xx.add(instrument)
            else:  # MOD
                # MOD : effect = 0x09
                if note_event.get('effect') == 0x09:
                    instruments_with_9xx.add(instrument)

    return instruments_with_9xx


def regenerate_ids(element, id_mapping, next_id):
    """Régénère récursivement tous les IDs d'un élément XML pour éviter les doublons

    Args:
        element: Element lxml à traiter
        id_mapping: Dict pour mapper anciens → nouveaux IDs
        next_id: Prochain ID disponible

    Returns:
        next_id mis à jour
    """
    # Traiter l'attribut Id de l'élément actuel
    if 'Id' in element.attrib:
        old_id = element.attrib['Id']
        if old_id not in id_mapping:
            id_mapping[old_id] = str(next_id)
            next_id += 1
        element.attrib['Id'] = id_mapping[old_id]

    # Traiter les références PointeeId et autres
    if element.tag == 'PointeeId' and 'Value' in element.attrib:
        old_value = element.attrib['Value']
        if old_value in id_mapping:
            element.attrib['Value'] = id_mapping[old_value]

    # Traiter AutomationTarget/Id
    if element.tag == 'AutomationTarget' and 'Id' in element.attrib:
        old_id = element.attrib['Id']
        if old_id not in id_mapping:
            id_mapping[old_id] = str(next_id)
            next_id += 1
        element.attrib['Id'] = id_mapping[old_id]

    # Traiter ModulationTarget/Id
    if element.tag == 'ModulationTarget' and 'Id' in element.attrib:
        old_id = element.attrib['Id']
        if old_id not in id_mapping:
            id_mapping[old_id] = str(next_id)
            next_id += 1
        element.attrib['Id'] = id_mapping[old_id]

    # Traiter récursivement tous les enfants
    for child in element:
        next_id = regenerate_ids(child, id_mapping, next_id)

    return next_id


def get_simpler_template(next_id):
    """Charge le template Simpler depuis simpler_template.xml

    Args:
        next_id: Prochain ID disponible pour la régénération des IDs

    Returns:
        (Element, next_id): Tuple (copie de l'élément OriginalSimpler, next_id mis à jour)
        (None, next_id) si le fichier n'existe pas
    """
    from lxml import etree
    from copy import deepcopy
    import os

    # Chemins possibles pour le template
    template_paths = [
        "/Users/sam/xm2live_v2/simpler_template.xml",
        "./simpler_template.xml"
    ]

    template_path = None
    for path in template_paths:
        if os.path.exists(path):
            template_path = path
            break

    if template_path is None:
        print("❌ Template Simpler non trouvé (simpler_template.xml)")
        return None, next_id

    try:
        # Utiliser lxml.etree pour compatibilité avec buildable
        tree = etree.parse(template_path)
        root = tree.getroot()

        # Faire une copie profonde
        simpler_copy = deepcopy(root)

        # IMPORTANT: Régénérer tous les IDs pour éviter les doublons (Pointee ID non uniques)
        id_mapping = {}
        next_id = regenerate_ids(simpler_copy, id_mapping, next_id)

        return simpler_copy, next_id

    except Exception as e:
        print(f"❌ Erreur lors du chargement du template Simpler : {e}")
        return None, next_id


def populate_track_with_simpler(track, sample_info, project_dir, next_id, bpm=125, speed=6, enable_envelope=False):
    """Configure une piste avec OriginalSimpler au lieu de MultiSampler

    Utilisé pour les instruments qui ont l'effet 9xx (Sample Offset)
    car Sampler ne permet pas d'automatiser Sample Start.

    Args:
        track: Objet buildable.live.Track
        sample_info: Dict contenant path, relative_note, loop_start, loop_length, loop_type, volume, panning, envelope
        project_dir: Répertoire du projet
        next_id: Prochain ID disponible (pour régénération IDs Simpler)
        bpm: BPM du module (pour conversion temps enveloppe)
        speed: Speed du module (ticks par row)
        enable_envelope: Activer la conversion enveloppe FT2 → ADSR

    Returns:
        next_id: next_id mis à jour après régénération des IDs

    Note:
        - Simpler ne supporte PAS les loops ping-pong (converti en forward)
        - Multi-sample non supporté (charge seulement le premier sample)
        - SNAP est activé si loop, désactivé sinon
    """
    sample_path = sample_info['path']
    relative_note = sample_info.get('relative_note', 0)

    # Trouver le DeviceChain/Devices
    devices = track.element.find('.//DeviceChain/Devices')
    if devices is None:
        print(f"    ⚠️  Pas de DeviceChain/Devices trouvé")
        return next_id

    # Supprimer le MultiSampler existant s'il y en a un
    sampler = devices.find('./MultiSampler')
    if sampler is not None:
        devices.remove(sampler)

    # Charger le template Simpler (avec régénération des IDs)
    simpler_template, next_id = get_simpler_template(next_id)
    if simpler_template is None:
        return next_id

    # Ajouter le Simpler à la piste
    devices.append(simpler_template)
    simpler = simpler_template  # Référence pour la suite

    # Trouver la structure Player/MultiSampleMap/SampleParts/MultiSamplePart
    # (oui, Simpler a la même structure que Sampler pour les samples)
    sample_part = simpler.find('.//Player/MultiSampleMap/SampleParts/MultiSamplePart')
    if sample_part is None:
        print(f"    ⚠️  Pas de MultiSamplePart trouvé dans le template Simpler")
        return False

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

    # Mettre à jour RootKey
    root_key_elem = sample_part.find('.//RootKey')
    if root_key_elem is not None:
        root_key = 60 - relative_note
        root_key_elem.set('Value', str(root_key))
        if relative_note != 0:
            print(f"    → RootKey ajustée: {root_key} (relative_note={relative_note:+d})")

    # Mettre à jour Detune (finetune)
    finetune = sample_info.get('finetune', 0)
    if finetune != 0:
        detune_elem = sample_part.find('.//Detune')
        if detune_elem is not None:
            detune_value = finetune / 2.56
            detune_value = max(-50, min(50, detune_value))
            detune_elem.set('Value', str(detune_value))
            print(f"    → Detune: {detune_value:.1f} cents (finetune={finetune:+d})")

    # Mettre à jour Panorama (panning par défaut du sample)
    xm_panning = sample_info.get('panning', 128)
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

    # Mettre à jour Volume du sample dans MultiSamplePart
    # (pas le Volume global du Simpler, qui est à -12dB dans le template)
    xm_volume = sample_info.get('volume', 64)
    volume_elem = sample_part.find('.//Volume')
    if volume_elem is not None:
        # Conversion linéaire avec réduction de -12dB
        ableton_volume = (xm_volume / 64.0) * 0.25
        volume_elem.set('Value', str(ableton_volume))

        if xm_volume != 64:
            if ableton_volume > 0:
                db_value = 20 * math.log10(ableton_volume)
                print(f"    → Volume: {ableton_volume:.3f} ({db_value:.1f} dB, XM={xm_volume}/64)")
            else:
                print(f"    → Volume: 0.000 (-∞ dB, XM={xm_volume}/64)")

    # VolumeVelScale est déjà à 35% dans le template (0.349999994)
    # Pas besoin de le modifier

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

                    # Activer SNAP (car il y a une loop)
                    if snap_elem is not None:
                        snap_elem.set('Value', 'true')

                    if loop_type == 2:
                        print(f"    → Boucle: {loop_start} - {loop_end} (Ping-Pong → Forward, limitation Simpler)")
                    else:
                        print(f"    → Boucle: {loop_start} - {loop_end} (Forward)")

                else:
                    # Pas de loop : désactiver LoopOn et SNAP
                    if loop_on_elem is not None:
                        loop_on_elem.set('Value', 'false')
                    if snap_elem is not None:
                        snap_elem.set('Value', 'false')

        except Exception as e:
            print(f"    ⚠️  Erreur lors de la lecture du WAV: {e}")

    # Paramétrer le nombre de voix à 1 (au lieu de 6 par défaut)
    num_voices = simpler.find('.//NumVoices')
    if num_voices is not None:
        num_voices.set('Value', '0')  # 0 = 1 voix
        print(f"    → Voix: 1 (monophonique)")

    # Configurer l'enveloppe ADSR si activé
    if enable_envelope:
        envelope_info = sample_info.get('envelope')
        if envelope_info and envelope_info.get('enabled'):
            # Note: configure_envelope_adsr() supporte déjà Simpler
            # Car il cherche VolumeAndPan/Envelope qui existe dans les deux devices
            configure_envelope_adsr(simpler, envelope_info, bpm, speed)

    print(f"    ✅ Simpler configuré (effet 9xx supporté)")
    return next_id


def update_midi_clip_notes(track, notes):
    """Remplace les notes dans le premier clip MIDI de la piste"""
    # Trouver le MainSequencer
    main_seq = track.element.find('.//DeviceChain/MainSequencer')
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

    max_time = max(note['time'] for note in notes) + 4.0

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

    # Grouper les notes par hauteur MIDI
    notes_by_key = defaultdict(list)
    for note in notes:
        midi_key = int(note['note'])
        if 0 <= midi_key <= 127:
            notes_by_key[midi_key].append(note)

    # Créer les nouveaux KeyTracks
    for midi_key, key_notes in sorted(notes_by_key.items()):
        key_track = ET.SubElement(key_tracks, 'KeyTrack')
        key_track.set('Id', str(midi_key))

        notes_elem = ET.SubElement(key_track, 'Notes')

        for note in key_notes:
            note_event = ET.SubElement(notes_elem, 'MidiNoteEvent')
            note_event.set('Time', str(note['time']))
            note_event.set('Duration', str(note['duration']))
            note_event.set('Velocity', str(int(note['velocity'])))
            note_event.set('OffVelocity', '64')
            note_event.set('NoteId', '0')

        midi_key_elem = ET.SubElement(key_track, 'MidiKey')
        midi_key_elem.set('Value', str(midi_key))

    return True

def create_sample_offset_automation(track, notes, next_id):
    """Crée une automation de Sample Start basée sur les effets 9xx des notes

    Args:
        track: L'élément Track Ableton
        notes: Liste des notes avec leur sample_offset_xm (0-255) ou None
        next_id: Prochain ID disponible (pour AutomationTarget)

    Returns:
        next_id mis à jour

    Note:
        - L'effet 9xx (Sample Offset) est converti en Sample Start (0.0-1.0)
        - Conversion approximative : offset_xm / 255.0 = sample_start
        - Utilise le pattern plateau (2 points par note) pour éviter l'interpolation
    """
    # Filtrer les notes qui ont un sample offset défini
    offset_notes = [(note['time'], note.get('sample_offset_xm'))
                    for note in notes
                    if note.get('sample_offset_xm') is not None]

    if not offset_notes:
        # Pas d'effet 9xx dans cette piste
        return next_id

    # Trouver le SampleStart AutomationTarget dans LoopModulators
    # LoopModulators est dans OriginalSimpler (pas dans MultiSampler)
    sample_start_target = track.element.find('.//OriginalSimpler/LoopModulators/SampleStart/AutomationTarget')
    if sample_start_target is None:
        print("    ⚠️  AutomationTarget du SampleStart non trouvé (Simpler uniquement)")
        return next_id

    sample_start_target_id = sample_start_target.get('Id')
    if not sample_start_target_id:
        # Créer un ID si absent
        sample_start_target_id = str(next_id)
        sample_start_target.set('Id', sample_start_target_id)
        next_id += 1

    # Trouver ou créer AutomationEnvelopes
    automation_envelopes = track.element.find('.//AutomationEnvelopes')
    if automation_envelopes is None:
        automation_envelopes = ET.SubElement(track.element, 'AutomationEnvelopes')

    envelopes_container = automation_envelopes.find('.//Envelopes')
    if envelopes_container is None:
        envelopes_container = ET.SubElement(automation_envelopes, 'Envelopes')

    # Créer l'AutomationEnvelope
    envelope = ET.SubElement(envelopes_container, 'AutomationEnvelope')
    envelope.set('Id', str(next_id))
    next_id += 1

    # EnvelopeTarget pointant vers le SampleStart
    envelope_target = ET.SubElement(envelope, 'EnvelopeTarget')
    pointee_id = ET.SubElement(envelope_target, 'PointeeId')
    pointee_id.set('Value', sample_start_target_id)

    # Automation avec Events
    automation = ET.SubElement(envelope, 'Automation')
    events = ET.SubElement(automation, 'Events')

    # Créer les points d'automation
    # IMPORTANT: Point initial à temps 0 avec Sample Start = 0.0
    event_initial = ET.SubElement(events, 'FloatEvent')
    event_initial.set('Id', str(next_id))
    next_id += 1
    event_initial.set('Time', '0.0')
    event_initial.set('Value', '0.0')

    # Trier les notes par temps
    sorted_notes = sorted(notes, key=lambda n: n['time'])

    # Ajouter les points pour chaque note
    for note in sorted_notes:
        time = note['time']
        duration = note.get('duration', 1.0)
        sample_offset_xm = note.get('sample_offset_xm')

        if sample_offset_xm is not None:
            # Note avec effet 9xx : créer 2 points (plateau)
            # Conversion : offset_xm (0-255) → sample_start (0.0-1.0)
            sample_start = sample_offset_xm / 255.0
            sample_start = max(0.0, min(1.0, sample_start))

            # Point au début de la note
            event_start = ET.SubElement(events, 'FloatEvent')
            event_start.set('Id', str(next_id))
            next_id += 1
            event_start.set('Time', str(time))
            event_start.set('Value', str(sample_start))

            # Point à la fin de la note (maintien du plateau)
            event_end = ET.SubElement(events, 'FloatEvent')
            event_end.set('Id', str(next_id))
            next_id += 1
            event_end.set('Time', str(time + duration))
            event_end.set('Value', str(sample_start))

        else:
            # Note SANS effet 9xx : retour à 0.0 (début du sample)
            event_return = ET.SubElement(events, 'FloatEvent')
            event_return.set('Id', str(next_id))
            next_id += 1
            event_return.set('Time', str(time))
            event_return.set('Value', '0.0')

    # Ajouter AutomationTransformViewState (requis par Ableton)
    transform_state = ET.SubElement(automation, 'AutomationTransformViewState')
    is_pending = ET.SubElement(transform_state, 'IsTransformPending')
    is_pending.set('Value', 'false')
    time_transforms = ET.SubElement(transform_state, 'TimeAndValueTransforms')

    num_points = len(events.findall('FloatEvent'))
    print(f"    → Automation Sample Start (9xx): {num_points} points")

    return next_id


def create_pan_automation(track, notes, sample_default_pan, next_id):
    """Crée une automation de panning basée sur les effets 8xx des notes

    Args:
        track: L'élément Track Ableton
        notes: Liste des notes avec leur panning_xm (0-255) ou None
        sample_default_pan: Panning par défaut du sample (0-255)
        next_id: Prochain ID disponible (pour AutomationTarget)

    Returns:
        next_id mis à jour
    """
    # Filtrer les notes qui ont un panning défini
    panning_notes = [(note['time'], note.get('panning_xm'))
                     for note in notes
                     if note.get('panning_xm') is not None]

    if not panning_notes:
        # Pas d'effet 8xx dans cette piste
        return next_id

    # Vérifier s'il y a des variations de panning (en incluant le panning par défaut)
    panning_values = [p[1] for p in panning_notes]
    if len(set(panning_values)) == 1 and panning_values[0] == sample_default_pan:
        # Tous les pannings sont identiques au panning par défaut, pas besoin d'automation
        return next_id

    # Trouver le Pan AutomationTarget du Mixer
    mixer_pan_target = track.element.find('.//DeviceChain/Mixer/Pan/AutomationTarget')
    if mixer_pan_target is None:
        print("    ⚠️  AutomationTarget du Pan non trouvé")
        return next_id

    pan_target_id = mixer_pan_target.get('Id')
    if not pan_target_id:
        # Créer un ID si absent
        pan_target_id = str(next_id)
        mixer_pan_target.set('Id', pan_target_id)
        next_id += 1

    # Trouver ou créer AutomationEnvelopes
    automation_envelopes = track.element.find('.//AutomationEnvelopes')
    if automation_envelopes is None:
        automation_envelopes = ET.SubElement(track.element, 'AutomationEnvelopes')

    envelopes_container = automation_envelopes.find('.//Envelopes')
    if envelopes_container is None:
        envelopes_container = ET.SubElement(automation_envelopes, 'Envelopes')

    # Créer l'AutomationEnvelope
    envelope = ET.SubElement(envelopes_container, 'AutomationEnvelope')
    envelope.set('Id', str(next_id))
    next_id += 1

    # EnvelopeTarget pointant vers le pan
    envelope_target = ET.SubElement(envelope, 'EnvelopeTarget')
    pointee_id = ET.SubElement(envelope_target, 'PointeeId')
    pointee_id.set('Value', pan_target_id)

    # Automation avec Events
    automation = ET.SubElement(envelope, 'Automation')
    events = ET.SubElement(automation, 'Events')

    # Créer les points d'automation
    # IMPORTANT: Ajouter un point initial à temps 0 avec le panning par défaut du sample
    # Cela reproduit le comportement FastTracker où le panning commence au défaut du sample
    sorted_pan_notes = sorted(panning_notes, key=lambda n: n[0])

    # Ajouter le point initial si la première note ne commence pas à temps 0
    if not sorted_pan_notes or sorted_pan_notes[0][0] > 0:
        pan_ableton_default = (sample_default_pan - 128) / 128.0
        pan_ableton_default = max(-1.0, min(1.0, pan_ableton_default))

        event_initial = ET.SubElement(events, 'FloatEvent')
        event_initial.set('Id', str(next_id))
        next_id += 1
        event_initial.set('Time', '0.0')
        event_initial.set('Value', str(pan_ableton_default))

    # Trier les notes par temps
    sorted_notes = sorted(notes, key=lambda n: n['time'])

    # Calculer le panning par défaut Ableton (pour le retour)
    pan_ableton_default = (sample_default_pan - 128) / 128.0
    pan_ableton_default = max(-1.0, min(1.0, pan_ableton_default))

    # Ajouter les points pour chaque note
    # Comportement FastTracker : retour au panning par défaut si pas d'effet 8xx
    previous_had_panning = False

    for note in sorted_notes:
        time = note['time']
        duration = note.get('duration', 1.0)
        has_panning = note.get('panning_xm') is not None

        if has_panning:
            # Note avec effet 8xx : créer 2 points (plateau)
            panning_xm = note['panning_xm']
            pan_ableton = (panning_xm - 128) / 128.0
            pan_ableton = max(-1.0, min(1.0, pan_ableton))

            # Point au début de la note
            event_start = ET.SubElement(events, 'FloatEvent')
            event_start.set('Id', str(next_id))
            next_id += 1
            event_start.set('Time', str(time))
            event_start.set('Value', str(pan_ableton))

            # Point à la fin de la note
            event_end = ET.SubElement(events, 'FloatEvent')
            event_end.set('Id', str(next_id))
            next_id += 1
            event_end.set('Time', str(time + duration))
            event_end.set('Value', str(pan_ableton))

            previous_had_panning = True

        elif previous_had_panning:
            # Note SANS effet 8xx après une note avec effet : retour au défaut
            event_return = ET.SubElement(events, 'FloatEvent')
            event_return.set('Id', str(next_id))
            next_id += 1
            event_return.set('Time', str(time))
            event_return.set('Value', str(pan_ableton_default))

            previous_had_panning = False

    # Ajouter AutomationTransformViewState (requis par Ableton, leçon apprise !)
    transform_state = ET.SubElement(automation, 'AutomationTransformViewState')
    is_pending = ET.SubElement(transform_state, 'IsTransformPending')
    is_pending.set('Value', 'false')
    time_transforms = ET.SubElement(transform_state, 'TimeAndValueTransforms')

    num_points = len(events.findall('FloatEvent'))
    print(f"    → Automation panning: {num_points} points")

    return next_id


def configure_envelope_adsr(sampler, envelope_info, bpm, speed):
    """Configure l'enveloppe ADSR du Sampler basée sur l'enveloppe volume FT2

    Args:
        sampler: L'élément MultiSampler Ableton
        envelope_info: Infos enveloppe FT2 {'enabled', 'points', 'sustain_point', 'sustain_enabled', 'num_points'}
        bpm: BPM du module (pour conversion temps)
        speed: Speed du module (ticks par row, défaut 6)

    Returns:
        True si enveloppe configurée, False sinon
    """

    # Si enveloppe désactivée ou pas de points, ne rien faire
    if not envelope_info.get('enabled') or not envelope_info.get('points'):
        return False

    points = envelope_info['points']
    num_points = envelope_info['num_points']
    sustain_enabled = envelope_info.get('sustain_enabled', False)
    sustain_point = envelope_info.get('sustain_point', 1)

    # Conversion temps FT2 (ticks) → millisecondes
    # 1 tick = (2500 / bpm) ms à Speed=6
    tick_to_ms = 2500.0 / bpm

    # Trouver l'enveloppe VOLUME (pas Filter !)
    # L'enveloppe de volume est dans VolumeAndPan, pas dans SimplerFilter
    volume_and_pan = sampler.find('.//VolumeAndPan')
    if volume_and_pan is None:
        print("    ⚠️  VolumeAndPan non trouvé dans le Sampler")
        return False

    envelope = volume_and_pan.find('.//Envelope')
    if envelope is None:
        print("    ⚠️  Enveloppe Volume non trouvée dans VolumeAndPan")
        return False

    # Trouver le pic (valeur max)
    max_val = 0
    max_idx = 0
    for i in range(num_points):
        if points[i][1] > max_val:
            max_val = points[i][1]
            max_idx = i

    # === STRATÉGIE SELON LE NOMBRE DE POINTS ===

    if num_points == 2:
        # Cas A : Enveloppe simple à 2 points (66% des cas)
        time_0, val_0 = points[0]
        time_1, val_1 = points[1]

        attack_time = 0.1
        attack_level = 0.0
        attack_slope = 0.0

        decay_time = max(1.0, time_1 * tick_to_ms)
        decay_level = val_0 / 64.0
        decay_slope = 1.0

        sustain_level = val_1 / 64.0

        release_time = 50.0
        release_level = 0.0
        release_slope = 0.0

    elif sustain_enabled and sustain_point < num_points:
        # Cas B : Enveloppe avec sustain FT2 défini
        peak_time, peak_val = points[max_idx]
        sustain_time, sustain_val = points[sustain_point]
        last_time, last_val = points[num_points - 1]

        attack_time = max(0.1, peak_time * tick_to_ms)
        attack_level = 0.0
        attack_slope = 0.0

        decay_time = max(1.0, (sustain_time - peak_time) * tick_to_ms)
        decay_level = peak_val / 64.0
        decay_slope = 0.5

        sustain_level = sustain_val / 64.0

        release_time = max(1.0, (last_time - sustain_time) * tick_to_ms)
        release_level = 0.0
        release_slope = 0.0

    else:
        # Cas C : Enveloppe complexe sans sustain
        peak_time, peak_val = points[max_idx]
        last_time, last_val = points[num_points - 1]

        mid_idx = (max_idx + num_points - 1) // 2
        mid_time, mid_val = points[mid_idx]

        attack_time = max(0.1, peak_time * tick_to_ms)
        attack_level = 0.0
        attack_slope = 0.0

        decay_time = max(1.0, (mid_time - peak_time) * tick_to_ms)
        decay_level = peak_val / 64.0
        decay_slope = 0.5

        sustain_level = mid_val / 64.0

        release_time = max(1.0, (last_time - mid_time) * tick_to_ms)
        release_level = 0.0
        release_slope = 0.0

    # === CONFIGURATION DES PARAMÈTRES ABLETON ===

    def set_envelope_param(param_name, value):
        elem = envelope.find(f'.//{param_name}/Manual')
        if elem is not None:
            elem.set('Value', str(value))

    set_envelope_param('AttackTime', attack_time)
    set_envelope_param('AttackLevel', attack_level)
    set_envelope_param('AttackSlope', attack_slope)

    set_envelope_param('DecayTime', decay_time)
    set_envelope_param('DecayLevel', decay_level)
    set_envelope_param('DecaySlope', decay_slope)

    set_envelope_param('SustainLevel', sustain_level)

    set_envelope_param('ReleaseTime', release_time)
    set_envelope_param('ReleaseLevel', release_level)
    set_envelope_param('ReleaseSlope', release_slope)

    print(f"    → Enveloppe ADSR: {num_points} pts FT2 → A={attack_time:.1f}ms D={decay_time:.1f}ms S={sustain_level:.2f} R={release_time:.1f}ms")

    return True


def convert_xm_to_ableton(xm_path, template_path, output_dir=None, enable_pan_automation=False, enable_envelope=False, enable_sample_offset=False):
    """Convertit un fichier XM/MOD en projet Ableton en utilisant un template

    Args:
        xm_path: Chemin vers le fichier XM/MOD
        template_path: Chemin vers le template Ableton
        output_dir: Répertoire de sortie (optionnel)
        enable_pan_automation: Activer les automations de panning (effet 8xx)
        enable_envelope: Activer la conversion des enveloppes volume (expérimental)
        enable_sample_offset: Activer l'effet 9xx (Sample Offset) avec Simpler
    """

    if not os.path.exists(xm_path):
        print(f"❌ Erreur: '{xm_path}' n'existe pas")
        return False

    if not os.path.exists(template_path):
        print(f"❌ Erreur: template '{template_path}' n'existe pas")
        return False

    # Détecter le format du fichier
    file_ext = os.path.splitext(xm_path)[1].lower()
    is_mod = (file_ext == '.mod')
    is_xm = (file_ext == '.xm')

    if not (is_mod or is_xm):
        print(f"⚠️  Attention: '{xm_path}' n'a pas l'extension .xm ou .mod")

    format_name = "MOD" if is_mod else "XM"
    print("="*60)
    print(f"CONVERSION {format_name} → ABLETON LIVE (avec buildable)")
    print("="*60)

    # Avertissement si enveloppes activées
    if enable_envelope:
        print("\n⚠️  MODE EXPÉRIMENTAL: Conversion des enveloppes activée")
        print("   Les enveloppes FT2 multi-points sont approximées en ADSR Ableton.")
        print("   Résultat approximatif, ajustements manuels recommandés.\n")

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
        organize_func = organize_mod
    else:
        samples, patterns, xm_info = extract_xm(xm_path, samples_dir)
        organize_func = organize_xm

    if not samples:
        print("\n❌ Aucun sample extrait !")
        return False

    # Lire les enveloppes si activé (fonction séparée, plus sûr)
    if enable_envelope and not is_mod:  # Seulement pour XM, pas MOD
        print(f"\n🎛️  Lecture des enveloppes volume...")
        envelopes = read_xm_envelopes(xm_path)
        # Merger les enveloppes avec les samples
        for sample in samples:
            inst_num = sample['instrument']
            if inst_num in envelopes:
                sample['envelope'] = envelopes[inst_num]
            else:
                # Enveloppe par défaut
                sample['envelope'] = {
                    'enabled': False,
                    'sustain_enabled': False,
                    'num_points': 0,
                    'sustain_point': 0,
                    'points': []
                }
        print(f"    → {len(envelopes)} enveloppes chargées")

    print(f"\n{'='*60}")
    print(f"MODULE: {xm_info['name']}")
    print(f"Speed: {xm_info['tempo']} ticks/row")
    print(f"BPM: {xm_info['bpm']}")
    real_bpm = xm_info['bpm'] * (6.0 / xm_info['tempo'])
    print(f"BPM réel: {real_bpm:.2f}")
    print(f"Canaux: {xm_info['channels']}")
    print(f"Samples: {len(samples)}")
    print(f"Patterns: {len(patterns)}")
    print(f"{'='*60}")

    # Détecter les instruments qui utilisent l'effet 9xx (Sample Offset)
    instruments_with_9xx = set()
    if enable_sample_offset:
        file_format = 'mod' if is_mod else 'xm'
        instruments_with_9xx = detect_effect_9xx_per_instrument(
            patterns,
            xm_info['pattern_order'],
            file_format
        )
        if instruments_with_9xx:
            inst_hex_list = [f"{i:02X}" for i in sorted(instruments_with_9xx)]
            print(f"\n🎚️  Effet 9xx détecté sur {len(instruments_with_9xx)} instrument(s): {', '.join(inst_hex_list)}")
            print(f"   → Ces instruments utiliseront Simpler (Sample Start automatable)")
        else:
            print(f"\n🎚️  Aucun effet 9xx détecté")

    # Organiser les pistes par canal
    tracks_data = organize_func(
        patterns,
        xm_info['pattern_order'],
        samples,
        xm_info['channels']
    )

    # Créer un mapping instrument -> sample
    instrument_to_sample = {s['instrument']: s for s in samples}

    # Charger le template
    print(f"\n📝 Chargement du template...")
    live_set = LiveSet.from_file(template_path)
    print(f"   Template chargé: {len(live_set.primary_tracks)} pistes")

    # Extraire le MultiSamplePart de la première piste pour l'utiliser comme template
    first_track = live_set.primary_tracks[0]
    template_sample_part = first_track.element.find('.//MultiSampler/Player/MultiSampleMap/SampleParts/MultiSamplePart')

    if template_sample_part is None:
        print(f"\n❌ ERREUR: La première piste doit contenir un MultiSampler avec un sample!")
        print(f"   Veuillez créer un template avec un sample dans la première piste.")
        return False

    print(f"   ✓ Template MultiSamplePart extrait de la première piste")

    print(f"\n🎹 Remplissage des pistes...")

    # Compter combien de pistes on va utiliser
    num_tracks_needed = sum(
        len([inst for inst in tracks_data[channel].keys() if inst in instrument_to_sample])
        for channel in tracks_data.keys()
    )

    if num_tracks_needed > len(live_set.primary_tracks):
        print(f"\n⚠️  ATTENTION: {num_tracks_needed} pistes nécessaires mais seulement {len(live_set.primary_tracks)} disponibles!")
        print(f"   Les pistes supplémentaires seront ignorées.")

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

        # Trouver toutes les pistes (canaux) qui utilisent cet instrument
        for channel in sorted(tracks_data.keys()):
            if instrument in tracks_data[channel]:
                notes = tracks_data[channel][instrument]
                track_name = f"Ch{channel+1} - {sample_name}"

                tracks_to_create.append({
                    'instrument': instrument,
                    'channel': channel,
                    'sample': sample,
                    'notes': notes,
                    'track_name': track_name,
                    'sample_name': sample_name,
                    'color': instrument_colors[instrument]
                })

    # Créer les pistes dans l'ordre
    track_index = 0
    pistes_creees = []

    # Compteur global pour tous les IDs (AutomationTarget, AutomationEnvelope, etc.)
    # Commence à 100000 pour éviter les conflits avec le template
    global_next_id = 100000

    for track_info in tracks_to_create:
        if track_index >= len(live_set.primary_tracks):
            print(f"\n⚠️  Plus de pistes disponibles dans le template!")
            break

        # Utiliser la piste existante du template
        track = live_set.primary_tracks[track_index]

        # Modifier la piste
        update_track_name(track, track_info['track_name'])
        update_track_color(track, track_info['color'])

        # Choisir Simpler ou Sampler selon si l'instrument utilise l'effet 9xx
        instrument = track_info['instrument']
        use_simpler = (enable_sample_offset and instrument in instruments_with_9xx)

        if use_simpler:
            # Utiliser Simpler (pour effet 9xx)
            global_next_id = populate_track_with_simpler(track, track_info['sample'], output_dir, global_next_id,
                                       bpm=xm_info['bpm'], speed=xm_info['tempo'], enable_envelope=enable_envelope)
        else:
            # Utiliser Sampler (normal)
            update_sampler_sample(track, track_info['sample'], output_dir, template_sample_part,
                                bpm=xm_info['bpm'], speed=xm_info['tempo'], enable_envelope=enable_envelope)

        update_midi_clip_notes(track, track_info['notes'])

        # Créer l'automation Sample Start basée sur les effets 9xx (si activé et Simpler)
        if use_simpler and enable_sample_offset:
            global_next_id = create_sample_offset_automation(track, track_info['notes'], global_next_id)

        # Créer l'automation de panning basée sur les effets 8xx (si activé)
        if enable_pan_automation:
            sample_default_pan = track_info['sample'].get('panning', 128)
            global_next_id = create_pan_automation(track, track_info['notes'], sample_default_pan, global_next_id)

        # Désactiver le mode record (arm) sur toutes les pistes
        recorder = track.element.find('.//Recorder')
        if recorder is not None:
            is_armed = recorder.find('.//IsArmed')
            if is_armed is not None:
                is_armed.set('Value', 'false')

        # Stocker une référence à l'élément XML pour la création de groupes
        track_info['track_element'] = track.element

        pistes_creees.append(track_info['track_name'])
        print(f"  ✓ {track_info['track_name']} ({len(track_info['notes'])} notes, color={track_info['color']})")
        track_index += 1

    # Créer des groupes pour les instruments avec 2+ pistes AVANT de supprimer les pistes
    print(f"\n📁 Création des groupes de pistes...")

    # Identifier les instruments avec plusieurs pistes
    # Ne garder que les tracks qui ont été réellement créées (avec track_element)
    instrument_track_counts = {}
    for track_info in tracks_to_create:
        # Ignorer les tracks qui n'ont pas été créées (manque de pistes dans le template)
        if 'track_element' not in track_info:
            continue
        inst = track_info['instrument']
        if inst not in instrument_track_counts:
            instrument_track_counts[inst] = []
        instrument_track_counts[inst].append(track_info)

    # Trouver le nombre de scènes pour créer les GroupTrackSlots
    num_scenes = 8  # Par défaut 8, mais on peut le lire du LiveSet
    scenes = live_set.element.find('.//Scenes')
    if scenes is not None:
        num_scenes = len(list(scenes))

    # Trouver l'élément Tracks
    tracks_container = live_set.element.find('.//Tracks')

    # Compteur pour l'ID du GroupTrack
    next_group_id = 10000

    # Compteur global pour tous les IDs (DeviceChain, AutomationTarget, etc.)
    # Commence à 100000 pour éviter les conflits avec le template
    global_next_id = 100000

    # Parcourir les instruments dans l'ordre (pour insérer les groups aux bons endroits)
    for instrument in unique_instruments:
        if instrument not in instrument_track_counts:
            continue

        tracks_for_inst = instrument_track_counts[instrument]

        # Créer un groupe seulement si 2+ pistes
        if len(tracks_for_inst) >= 2:
            sample_name = tracks_for_inst[0]['sample_name']
            color = tracks_for_inst[0]['color']

            # Créer le GroupTrack
            group_track = ET.Element('GroupTrack')
            group_track.set('Id', str(next_group_id))

            # Ajouter les éléments de base
            ET.SubElement(group_track, 'LomId').set('Value', '0')
            ET.SubElement(group_track, 'LomIdView').set('Value', '0')
            ET.SubElement(group_track, 'IsContentSelectedInDocument').set('Value', 'false')
            ET.SubElement(group_track, 'PreferredContentViewMode').set('Value', '0')

            # TrackDelay
            track_delay = ET.SubElement(group_track, 'TrackDelay')
            ET.SubElement(track_delay, 'Value').set('Value', '0')
            ET.SubElement(track_delay, 'IsValueSampleBased').set('Value', 'false')

            # Name
            name_elem = ET.SubElement(group_track, 'Name')
            ET.SubElement(name_elem, 'EffectiveName').set('Value', sample_name)
            ET.SubElement(name_elem, 'UserName').set('Value', sample_name)
            ET.SubElement(name_elem, 'Annotation').set('Value', '')
            ET.SubElement(name_elem, 'MemorizedFirstClipName').set('Value', '')

            # Color
            ET.SubElement(group_track, 'Color').set('Value', str(color))

            # AutomationEnvelopes
            auto_env = ET.SubElement(group_track, 'AutomationEnvelopes')
            ET.SubElement(auto_env, 'Envelopes')

            # TrackGroupId (pas de parent)
            ET.SubElement(group_track, 'TrackGroupId').set('Value', '-1')
            ET.SubElement(group_track, 'TrackUnfolded').set('Value', 'false')  # Replier le groupe par défaut

            # Autres éléments
            ET.SubElement(group_track, 'DevicesListWrapper').set('LomId', '0')
            ET.SubElement(group_track, 'ClipSlotsListWrapper').set('LomId', '0')
            ET.SubElement(group_track, 'ArrangementClipsListWrapper').set('LomId', '0')
            ET.SubElement(group_track, 'TakeLanesListWrapper').set('LomId', '0')
            ET.SubElement(group_track, 'ViewData').set('Value', '{}')

            # TakeLanes
            take_lanes = ET.SubElement(group_track, 'TakeLanes')
            ET.SubElement(take_lanes, 'TakeLanes')
            ET.SubElement(take_lanes, 'AreTakeLanesFolded').set('Value', 'true')

            ET.SubElement(group_track, 'LinkedTrackGroupId').set('Value', '-1')

            # Slots (GroupTrackSlot)
            slots = ET.SubElement(group_track, 'Slots')
            for i in range(num_scenes):
                slot = ET.SubElement(slots, 'GroupTrackSlot')
                slot.set('Id', str(i))
                ET.SubElement(slot, 'LomId').set('Value', '0')

            ET.SubElement(group_track, 'Freeze').set('Value', 'false')
            ET.SubElement(group_track, 'NeedArrangerRefreeze').set('Value', 'true')

            # DeviceChain complet pour GroupTrack (créé manuellement)
            device_chain = ET.SubElement(group_track, 'DeviceChain')

            # AudioOutputRouting
            audio_out = ET.SubElement(device_chain, 'AudioOutputRouting')
            ET.SubElement(audio_out, 'Target').set('Value', 'AudioOut/Main')
            ET.SubElement(audio_out, 'UpperDisplayString').set('Value', 'Main')
            ET.SubElement(audio_out, 'LowerDisplayString').set('Value', '')

            # Mixer (élément essentiel pour le Solo/Mute/Volume)
            mixer = ET.SubElement(device_chain, 'Mixer')
            ET.SubElement(mixer, 'LomId').set('Value', '0')
            ET.SubElement(mixer, 'LomIdView').set('Value', '0')

            # Speaker (contrôle on/off de la piste)
            speaker = ET.SubElement(mixer, 'Speaker')
            ET.SubElement(speaker, 'LomId').set('Value', '0')
            ET.SubElement(speaker, 'Manual').set('Value', 'true')
            speaker_auto = ET.SubElement(speaker, 'AutomationTarget')
            speaker_auto.set('Id', str(global_next_id))
            global_next_id += 1
            ET.SubElement(speaker_auto, 'LockEnvelope').set('Value', '0')

            # SoloSink (CRITIQUE pour le fonctionnement du Solo)
            ET.SubElement(mixer, 'SoloSink').set('Value', 'false')

            # Volume
            volume = ET.SubElement(mixer, 'Volume')
            ET.SubElement(volume, 'LomId').set('Value', '0')
            ET.SubElement(volume, 'Manual').set('Value', '1')
            volume_auto = ET.SubElement(volume, 'AutomationTarget')
            volume_auto.set('Id', str(global_next_id))
            global_next_id += 1
            ET.SubElement(volume_auto, 'LockEnvelope').set('Value', '0')

            # DeviceChain imbriqué (pour les effets, vide)
            inner_device_chain = ET.SubElement(device_chain, 'DeviceChain')
            ET.SubElement(inner_device_chain, 'Devices')
            ET.SubElement(inner_device_chain, 'SignalModulations')

            # Trouver la position de la première piste de ce groupe dans tracks_container
            first_track_elem = tracks_for_inst[0]['track_element']
            all_tracks = list(tracks_container)
            insert_position = all_tracks.index(first_track_elem)

            # Insérer le GroupTrack avant la première piste de ce groupe
            tracks_container.insert(insert_position, group_track)

            # Mettre à jour le TrackGroupId des pistes de ce groupe en utilisant les références directes
            for track_info in tracks_for_inst:
                track_elem = track_info['track_element']
                track_group_id = track_elem.find('.//TrackGroupId')
                if track_group_id is not None:
                    track_group_id.set('Value', str(next_group_id))

                # IMPORTANT: Router l'audio de la piste vers le GroupTrack parent
                # C'est ce qui permet au Solo du groupe de fonctionner
                audio_output = track_elem.find('.//AudioOutputRouting/Target')
                if audio_output is not None:
                    audio_output.set('Value', 'AudioOut/GroupTrack')

                # Mettre à jour aussi les DisplayStrings
                upper_display = track_elem.find('.//AudioOutputRouting/UpperDisplayString')
                if upper_display is not None:
                    upper_display.set('Value', sample_name)  # Nom du groupe

                lower_display = track_elem.find('.//AudioOutputRouting/LowerDisplayString')
                if lower_display is not None:
                    lower_display.set('Value', '')

            print(f"  ✓ Groupe créé: {sample_name} ({len(tracks_for_inst)} pistes)")

            next_group_id += 1

    # Supprimer les pistes non utilisées APRÈS avoir créé les groupes
    print(f"\n🗑️  Suppression des pistes non utilisées...")
    # Garder seulement les pistes que nous avons utilisées (et les GroupTracks)
    all_tracks_in_container = list(tracks_container)

    # Créer un set des éléments de piste utilisés
    used_track_elements = {info['track_element'] for info in tracks_to_create if 'track_element' in info}

    # Supprimer les pistes MIDI inutilisées
    # On ne supprime que les MidiTrack qui ne sont pas dans used_track_elements
    tracks_to_remove = []
    for track_elem in all_tracks_in_container:
        if track_elem.tag == 'MidiTrack' and track_elem not in used_track_elements:
            tracks_to_remove.append(track_elem)

    for track in tracks_to_remove:
        tracks_container.remove(track)

    print(f"   {len(tracks_to_remove)} pistes supprimées")

    # Replier toutes les pistes utilisées pour une meilleure vue d'ensemble
    print(f"\n📁 Repliement des pistes et groupes...")
    folded_count = 0
    for track_info in tracks_to_create:
        if 'track_element' in track_info:
            track_elem = track_info['track_element']
            track_unfolded = track_elem.find('.//TrackUnfolded')
            if track_unfolded is not None:
                track_unfolded.set('Value', 'false')
                folded_count += 1

    print(f"   {folded_count} pistes repliées")

    # Calculer le BPM réel selon la formule FastTracker 2
    # BPM réel = BPM × (6 / Speed)
    xm_speed = xm_info['tempo']  # Dans XM, "tempo" = speed (ticks par row)
    xm_bpm = xm_info['bpm']      # BPM XM (calibré pour speed=6)
    real_bpm = xm_bpm * (6.0 / xm_speed)

    # Mettre à jour le tempo partout où il apparaît
    print(f"\n🎵 Calcul du tempo réel:")
    print(f"   XM Speed: {xm_speed} ticks/row")
    print(f"   XM BPM: {xm_bpm}")
    print(f"   → BPM réel: {real_bpm:.2f} (formule: {xm_bpm} × 6/{xm_speed})")
    tempo_updated_count = 0
    floatevent_updated_count = 0

    # Le BPM n'est PAS dans <Tempo> mais directement dans <Manual> et <FloatEvent>
    # Chercher tous les éléments Manual avec Value="120" (le défaut du template)
    print(f"   Recherche des éléments <Manual> avec Value='120'...")
    for manual in live_set.element.iter('Manual'):
        if manual.get('Value') == '120':
            manual.set('Value', str(real_bpm))
            tempo_updated_count += 1
            print(f"   → Manual: 120 → {real_bpm:.2f} BPM")

    # Aussi mettre à jour les FloatEvent si présents
    print(f"   Recherche des éléments <FloatEvent> avec Value='120'...")
    for floatevent in live_set.element.iter('FloatEvent'):
        if floatevent.get('Value') == '120':
            floatevent.set('Value', str(real_bpm))
            floatevent_updated_count += 1
            print(f"   → FloatEvent: 120 → {real_bpm:.2f} BPM")

    total_updated = tempo_updated_count + floatevent_updated_count
    if total_updated > 0:
        print(f"   ✓ Tempo mis à jour ({tempo_updated_count} Manual, {floatevent_updated_count} FloatEvent)")
    else:
        print(f"   ⚠️  Aucun élément trouvé avec Value='120' - BPM peut-être déjà différent de 120?")

    # Réinitialiser la position de la tête de lecture au début (1.1.1)
    print(f"\n⏮️  Réinitialisation de la tête de lecture...")

    # 1. CurrentTime dans Transport (affichage de la tête de lecture)
    transport = live_set.element.find('.//Transport')
    if transport is not None:
        current_time = transport.find('.//CurrentTime')
        if current_time is not None:
            current_time.set('Value', '0')
            print(f"   ✓ Transport/CurrentTime réinitialisé à 0")
        else:
            print(f"   ⚠️  Élément CurrentTime non trouvé")
    else:
        print(f"   ⚠️  Élément Transport non trouvé")

    # 2. TimeSelection global (position de démarrage de la lecture)
    # Chercher le TimeSelection au niveau LiveSet (pas dans les clips)
    # Le chemin est Ableton/LiveSet/TimeSelection
    for time_selection in live_set.element.findall('.//TimeSelection'):
        # Vérifier si c'est le TimeSelection global (parent direct de LiveSet)
        parent = time_selection.getparent()
        if parent is not None and parent.tag == 'LiveSet':
            anchor_time = time_selection.find('.//AnchorTime')
            other_time = time_selection.find('.//OtherTime')
            if anchor_time is not None:
                anchor_time.set('Value', '0')
            if other_time is not None:
                other_time.set('Value', '0')
            print(f"   ✓ TimeSelection global réinitialisé à 0")
            break

    print(f"   → La lecture démarrera maintenant à 1.1.1")

    # Mettre à jour NextPointeeId pour refléter les nouveaux IDs créés
    print(f"\n🔢 Mise à jour du compteur NextPointeeId...")
    next_pointee_elem = live_set.element.find('.//NextPointeeId')
    if next_pointee_elem is not None:
        old_value = next_pointee_elem.get('Value')
        next_pointee_elem.set('Value', str(global_next_id))
        print(f"   ✓ NextPointeeId: {old_value} → {global_next_id}")
    else:
        print(f"   ⚠️  NextPointeeId non trouvé")

    # Sauvegarder (utiliser le nom du fichier, pas le nom interne du module)
    # Cela évite les conflits quand plusieurs fichiers ont le même nom interne
    xm_basename = os.path.splitext(os.path.basename(xm_path))[0]
    als_path = os.path.join(output_dir, f"{xm_basename}.als")
    print(f"\n💾 Sauvegarde du projet...")
    live_set.write_to_file(als_path)

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

    parser = argparse.ArgumentParser(
        description='Convertir un fichier XM/MOD en projet Ableton Live',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Exemples:
  python3 xm2live.py mon_module.xm
  python3 xm2live.py mon_module.mod
  python3 xm2live.py mon_module.xm template.als
  python3 xm2live.py mon_module.xm --pan-automation
        '''
    )

    parser.add_argument('fichier', help='Fichier XM ou MOD à convertir')
    parser.add_argument('template', nargs='?', help='Template Ableton (optionnel)')
    parser.add_argument('--pan-automation', action='store_true',
                        help='Activer les automations de panning (effet 8xx). '
                             'Par défaut désactivé car rare dans les modules.')
    parser.add_argument('--envelope', action='store_true',
                        help='Activer la conversion des enveloppes volume FT2 → ADSR Ableton. '
                             'Par défaut désactivé car approximation simplifiée.')
    parser.add_argument('--sample-offset', action='store_true',
                        help='Activer l\'effet 9xx (Sample Offset) avec Simpler. '
                             'Les instruments avec effet 9xx utiliseront Simpler au lieu de Sampler. '
                             'LIMITATION: conversion ping-pong → forward.')

    args = parser.parse_args()

    xm_path = args.fichier

    # Chercher le template dans plusieurs endroits
    if args.template:
        template_path = args.template
    else:
        # 1. À côté du script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_next_to_script = os.path.join(script_dir, "template_100_tracks.als")

        # 2. Chemin par défaut
        default_template = "/Users/sam/Music/Compo/All Compo/Modules/template_100_tracks.als"

        if os.path.exists(template_next_to_script):
            template_path = template_next_to_script
        elif os.path.exists(default_template):
            template_path = default_template
        else:
            print("❌ ERREUR: Template non trouvé!")
            print(f"   Cherché dans:")
            print(f"   - {template_next_to_script}")
            print(f"   - {default_template}")
            print(f"\n   Créez un template avec 100 pistes MIDI, chacune avec un Sampler")
            print(f"   La première piste doit contenir un sample pour servir d'exemple.")
            sys.exit(1)

    try:
        success = convert_xm_to_ableton(xm_path, template_path,
                                        enable_pan_automation=args.pan_automation,
                                        enable_envelope=args.envelope,
                                        enable_sample_offset=args.sample_offset)
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
