#!/usr/bin/env python3
import gzip
import xml.etree.ElementTree as ET

files = [
    ('/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor copie Project/censor copie.als', 'BON (193)'),
    ('/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor.als', 'SCRIPT (120)')
]

for file_path, label in files:
    print(f"\n=== {label} ===")
    try:
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
            root = tree.getroot()

        # Chercher les 3 premiers Tempo
        count = 0
        for elem in root.iter('Tempo'):
            manual = elem.find('Manual')
            if manual is not None:
                count += 1
                print(f"  Tempo {count}: {manual.get('Value')}")
                if count >= 3:
                    break

    except Exception as e:
        print(f"  Erreur: {e}")
