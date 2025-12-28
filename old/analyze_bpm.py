#!/usr/bin/env python3
"""Analyse les fichiers .als pour trouver où se trouve le BPM"""
import gzip
import xml.etree.ElementTree as ET

def analyze_bpm(file_path, expected_bpm):
    print(f"\n{'='*70}")
    print(f"Analyse: {file_path}")
    print(f"BPM attendu: {expected_bpm}")
    print(f"{'='*70}")

    try:
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
            root = tree.getroot()

        # Chercher tous les éléments Tempo
        tempo_count = 0
        for elem in root.iter('Tempo'):
            manual = elem.find('Manual')
            if manual is not None:
                tempo_count += 1
                value = manual.get('Value')
                print(f"  Tempo #{tempo_count}: Value={value}")

        print(f"\n  Total Tempo trouvés: {tempo_count}")

        # Chercher aussi toutes les occurrences de la valeur attendue
        print(f"\n  Recherche de la valeur '{expected_bpm}' dans tous les attributs...")
        count_193 = 0
        for elem in root.iter():
            for attr, value in elem.attrib.items():
                if value == str(expected_bpm):
                    count_193 += 1
                    if count_193 <= 5:  # Limiter l'affichage
                        print(f"    {elem.tag}.{attr} = {value}")

        print(f"  Total '{expected_bpm}' trouvés: {count_193}")

    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

# Analyser le fichier avec le bon BPM (193)
analyze_bpm('/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor copie Project/censor copie.als', 193)

# Analyser le fichier généré par le script (120)
analyze_bpm('/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor.als', 120)
