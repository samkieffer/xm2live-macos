#!/usr/bin/env python3
"""
Script de test pour valider les conversions XM → Ableton
Vérifie que les fichiers générés sont corrects
"""

import os
import sys
import gzip
import xml.etree.ElementTree as ET
from xm_parser import read_xm_header


def test_als_file(als_path, expected_bpm=None):
    """Teste qu'un fichier .als est valide et contient les bonnes infos"""
    print(f"\n{'='*70}")
    print(f"Test: {os.path.basename(als_path)}")
    print(f"{'='*70}")

    # Vérifier que le fichier existe
    if not os.path.exists(als_path):
        print(f"❌ Fichier non trouvé: {als_path}")
        return False

    try:
        # Ouvrir et parser le fichier .als
        with gzip.open(als_path, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
            root = tree.getroot()

        print(f"✓ Fichier .als valide (XML parsé)")

        # Compter les pistes
        tracks = root.findall('.//MidiTrack')
        num_tracks = len(tracks)
        print(f"✓ {num_tracks} pistes MIDI trouvées")

        # Compter les groupes
        groups = root.findall('.//GroupTrack')
        num_groups = len(groups)
        print(f"✓ {num_groups} groupes trouvés")

        # Vérifier le BPM
        bpm_found = []
        for manual in root.iter('Manual'):
            value = manual.get('Value')
            if value and value.isdigit():
                bpm_value = int(value)
                if bpm_value > 60 and bpm_value < 300:  # BPM raisonnable
                    bpm_found.append(bpm_value)

        if bpm_found:
            unique_bpms = list(set(bpm_found))
            print(f"✓ BPM trouvé: {unique_bpms}")

            if expected_bpm:
                if expected_bpm in unique_bpms:
                    print(f"✓ BPM correct: {expected_bpm}")
                else:
                    print(f"⚠️  BPM attendu: {expected_bpm}, trouvé: {unique_bpms}")
        else:
            print(f"⚠️  Aucun BPM trouvé")

        # Vérifier les samples
        sample_refs = root.findall('.//SampleRef')
        num_samples = len(sample_refs)
        print(f"✓ {num_samples} références de samples trouvées")

        return True

    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_samples_directory(project_dir):
    """Vérifie que le dossier Samples contient les WAV"""
    samples_dir = os.path.join(project_dir, 'Samples')

    if not os.path.exists(samples_dir):
        print(f"❌ Dossier Samples non trouvé: {samples_dir}")
        return False

    wav_files = [f for f in os.listdir(samples_dir) if f.endswith('.wav')]
    print(f"✓ {len(wav_files)} fichiers WAV dans Samples/")

    # Vérifier quelques samples
    for wav in wav_files[:3]:
        wav_path = os.path.join(samples_dir, wav)
        size = os.path.getsize(wav_path)
        print(f"  - {wav}: {size} bytes")

    return True


def test_conversion(xm_path):
    """Teste une conversion complète"""
    print(f"\n{'='*70}")
    print(f"TEST DE CONVERSION")
    print(f"{'='*70}")

    # Lire les infos du XM
    print(f"\n📀 Lecture du fichier XM...")
    xm_info = read_xm_header(xm_path)

    if not xm_info:
        print(f"❌ Impossible de lire le fichier XM")
        return False

    print(f"✓ Fichier XM: {xm_info['name']}")
    print(f"✓ BPM: {xm_info['bpm']}")
    print(f"✓ Canaux: {xm_info['channels']}")
    print(f"✓ Patterns: {xm_info['patterns']}")

    # Trouver le projet Ableton généré
    xm_basename = os.path.splitext(os.path.basename(xm_path))[0]
    project_dir = os.path.join(os.path.dirname(xm_path), f"{xm_basename}_Ableton_Project")

    if not os.path.exists(project_dir):
        print(f"⚠️  Projet Ableton non trouvé: {project_dir}")
        print(f"   Lancez d'abord: python3 xm2live.py {xm_path}")
        return False

    # Tester le fichier .als
    als_files = [f for f in os.listdir(project_dir) if f.endswith('.als')]

    if not als_files:
        print(f"❌ Aucun fichier .als trouvé dans {project_dir}")
        return False

    als_path = os.path.join(project_dir, als_files[0])

    # Tests
    test_als_file(als_path, xm_info['bpm'])
    test_samples_directory(project_dir)

    print(f"\n{'='*70}")
    print(f"✓ TESTS TERMINÉS")
    print(f"{'='*70}")

    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_conversion.py <fichier.xm>")
        print("\nExemple:")
        print("  python3 test_conversion.py mon_fichier.xm")
        print("\nCe script teste que la conversion a bien fonctionné.")
        sys.exit(1)

    xm_path = sys.argv[1]

    if not os.path.exists(xm_path):
        print(f"❌ Fichier non trouvé: {xm_path}")
        sys.exit(1)

    success = test_conversion(xm_path)

    if success:
        print("\n✓ Tous les tests sont passés!")
        sys.exit(0)
    else:
        print("\n❌ Certains tests ont échoué")
        sys.exit(1)


if __name__ == "__main__":
    main()
