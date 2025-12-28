#!/usr/bin/env python3
"""
Convertisseur XM vers Ableton Live - Version avec template
Utilise un fichier .als existant comme base
"""

import sys
import os
import struct
import gzip
import xml.etree.ElementTree as ET
import wave
import numpy as np
from pathlib import Path
from collections import defaultdict

# Importer les fonctions de lecture XM du script original
import xm2live

def create_ableton_from_template(xm_info, samples, patterns, output_path, template_path):
    """Crée un projet Ableton en utilisant un template existant"""

    print(f"\nCréation du projet Ableton depuis template...")

    project_dir = os.path.dirname(output_path)

    # Lire le template
    with gzip.open(template_path, 'rt', encoding='utf-8') as f:
        tree = ET.parse(f)
        root = tree.getroot()

    liveset = root.find('LiveSet')

    # Organiser les pistes par canal
    tracks_data = xm2live.organize_tracks_by_channel(
        patterns,
        xm_info['pattern_order'],
        samples,
        xm_info['channels']
    )

    # Créer un mapping instrument -> sample
    instrument_to_sample = {s['instrument']: s for s in samples}

    # Trouver l'élément Tracks
    tracks_elem = liveset.find('Tracks')

    # Supprimer toutes les pistes existantes
    for track in list(tracks_elem):
        tracks_elem.remove(track)

    # Récupérer une MidiTrack template (on va la cloner)
    # On va lire le premier MidiTrack du template original pour avoir la structure
    with gzip.open(template_path, 'rt', encoding='utf-8') as f:
        template_tree = ET.parse(f)
        template_root = template_tree.getroot()

    template_tracks = template_root.find('.//Tracks')
    template_midi_track = template_tracks.find('.//MidiTrack')

    # ID tracking
    track_id = 10
    device_id = 1000
    clip_id = 1000

    # Créer les pistes par canal
    for channel in sorted(tracks_data.keys()):
        for instrument, notes in sorted(tracks_data[channel].items()):
            if instrument not in instrument_to_sample:
                continue

            sample = instrument_to_sample[instrument]
            track_name = f"Ch{channel+1} - {sample['name']}"

            # Cloner la piste template
            new_track = ET.fromstring(ET.tostring(template_midi_track))
            new_track.set('Id', str(track_id))

            # Changer le nom
            name_elem = new_track.find('.//Name/EffectiveName')
            if name_elem is not None:
                name_elem.set('Value', track_name)

            # TODO: Ajouter le sampler et les notes MIDI
            # Pour l'instant on garde la structure vide

            tracks_elem.append(new_track)
            track_id += 1

            print(f"  ✓ Piste créée: {track_name} ({len(notes)} notes)")

    # Mettre à jour NextPointeeId
    next_pointee = liveset.find('NextPointeeId')
    if next_pointee is not None:
        max_id = max(track_id, device_id, clip_id)
        next_pointee.set('Value', str(max_id + 1))

    # Sauvegarder
    tree.write(output_path, encoding='UTF-8', xml_declaration=True)

    # Compresser avec gzip
    with open(output_path, 'rb') as f_in:
        with gzip.open(output_path + '.gz', 'wb') as f_out:
            f_out.writelines(f_in)

    os.rename(output_path + '.gz', output_path)

    print(f"\n✓ Projet créé: {output_path}")

    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 xm2live_template.py <fichier.xm> [template.als]")
        sys.exit(1)

    xm_path = sys.argv[1]
    template_path = sys.argv[2] if len(sys.argv) > 2 else "/Users/sam/Music/Compo/All Compo/Modules/projet_qui_marche Project/projet_qui_marche.als"

    if not os.path.exists(template_path):
        print(f"Erreur: template '{template_path}' n'existe pas")
        sys.exit(1)

    # Utiliser les fonctions du script original pour extraire le XM
    xm_basename = os.path.splitext(os.path.basename(xm_path))[0]
    output_dir = os.path.join(os.path.dirname(xm_path), f"{xm_basename}_Ableton_Project")
    os.makedirs(output_dir, exist_ok=True)

    samples_dir = os.path.join(output_dir, 'Samples')
    os.makedirs(samples_dir, exist_ok=True)

    # Extraire samples ET patterns
    samples, patterns, xm_info = xm2live.extract_samples_and_patterns(xm_path, samples_dir)

    if not samples:
        print("\n❌ Aucun sample extrait !")
        return False

    # Créer le projet depuis le template
    als_path = os.path.join(output_dir, f"{xm_info['name'].strip() or 'project'}.als")
    create_ableton_from_template(xm_info, samples, patterns, als_path, template_path)

    print(f"\n✓ Conversion terminée")

    return True

if __name__ == "__main__":
    main()
