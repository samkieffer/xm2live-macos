#!/usr/bin/env python3
"""
Script pour extraire un template minimal depuis template_100_tracks.als
Garde seulement 1 MidiTrack et les structures essentielles
"""

import gzip
from lxml import etree

def extract_minimal_template(input_path, output_path):
    """Extrait un template minimal avec 1 seule piste"""

    print("📖 Chargement du template complet...")
    with gzip.open(input_path, 'rb') as f:
        tree = etree.parse(f)
        root = tree.getroot()

    # Trouver toutes les MidiTrack
    midi_tracks = root.findall('.//MidiTrack')
    print(f"   {len(midi_tracks)} pistes trouvées")

    if len(midi_tracks) == 0:
        print("❌ Aucune MidiTrack trouvée!")
        return False

    # Garder seulement la PREMIÈRE MidiTrack
    tracks_parent = root.find('.//Tracks')
    if tracks_parent is None:
        print("❌ Élément <Tracks> introuvable!")
        return False

    print(f"\n🗑️  Suppression de {len(midi_tracks) - 1} pistes...")

    # Supprimer toutes les pistes sauf la première
    for track in midi_tracks[1:]:
        tracks_parent.remove(track)

    # Vérifier qu'il reste bien 1 piste
    remaining_tracks = root.findall('.//MidiTrack')
    print(f"   ✓ {len(remaining_tracks)} piste restante")

    # Sauvegarder le template minimal
    print(f"\n💾 Sauvegarde du template minimal...")
    print(f"   {output_path}")

    xml_str = etree.tostring(root, encoding='UTF-8', xml_declaration=True)

    with gzip.open(output_path, 'wb', compresslevel=9) as f:
        f.write(xml_str)

    # Statistiques
    import os
    original_size = os.path.getsize(input_path) / 1024
    minimal_size = os.path.getsize(output_path) / 1024

    print(f"\n📊 Statistiques:")
    print(f"   Template original: {original_size:.1f} KB")
    print(f"   Template minimal:  {minimal_size:.1f} KB")
    print(f"   Réduction: {100 * (1 - minimal_size/original_size):.1f}%")

    # Compter les lignes XML
    with gzip.open(output_path, 'rb') as f:
        xml_lines = len(f.read().decode('utf-8').split('\n'))

    print(f"   Lignes XML: {xml_lines}")

    print("\n✓ Template minimal créé!")
    return True

if __name__ == "__main__":
    import sys
    import os

    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_template = os.path.join(script_dir, "template_100_tracks.als")
    output_template = os.path.join(script_dir, "template_minimal_1track.als")

    if not os.path.exists(input_template):
        print(f"❌ Template non trouvé: {input_template}")
        sys.exit(1)

    success = extract_minimal_template(input_template, output_template)
    sys.exit(0 if success else 1)
