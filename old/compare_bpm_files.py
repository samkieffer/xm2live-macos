#!/usr/bin/env python3
"""Compare deux fichiers .als pour trouver les différences de BPM"""
import gzip
import xml.etree.ElementTree as ET

file_120 = '/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor.als'
file_193 = '/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor copie Project/censor copie.als'

print("="*70)
print("COMPARAISON DES FICHIERS BPM")
print("="*70)

print("\n📄 Fichier 1 (script, devrait être 193 mais affiche 120)")
print(f"   {file_120}")

print("\n📄 Fichier 2 (manuel, correct à 193)")
print(f"   {file_193}")

try:
    with gzip.open(file_120, 'rt', encoding='utf-8') as f:
        tree1 = ET.parse(f)
        root1 = tree1.getroot()

    with gzip.open(file_193, 'rt', encoding='utf-8') as f:
        tree2 = ET.parse(f)
        root2 = tree2.getroot()

    print("\n" + "="*70)
    print("RECHERCHE DE TOUS LES ÉLÉMENTS CONTENANT '120' ou '193'")
    print("="*70)

    # Fonction pour obtenir un chemin d'élément
    def get_path(root, elem):
        for parent in root.iter():
            for i, child in enumerate(parent):
                if child == elem:
                    parent_path = get_path(root, parent)
                    if parent_path:
                        return f"{parent_path}/{parent.tag}[{i}]/{elem.tag}"
                    return f"{parent.tag}[{i}]/{elem.tag}"
        return elem.tag

    print("\n🔍 Dans fichier 1 (120):")
    count_120 = 0
    for elem in root1.iter():
        for attr, value in elem.attrib.items():
            if value in ['120', '193']:
                count_120 += 1
                if count_120 <= 20:
                    print(f"   {count_120}. {elem.tag}.{attr} = {value}")

    print(f"\n   Total trouvé: {count_120}")

    print("\n🔍 Dans fichier 2 (193):")
    count_193 = 0
    for elem in root2.iter():
        for attr, value in elem.attrib.items():
            if value in ['120', '193']:
                count_193 += 1
                if count_193 <= 20:
                    print(f"   {count_193}. {elem.tag}.{attr} = {value}")

    print(f"\n   Total trouvé: {count_193}")

    # Comparer les éléments Tempo spécifiquement
    print("\n" + "="*70)
    print("ÉLÉMENTS <Tempo> UNIQUEMENT")
    print("="*70)

    print("\n📌 Fichier 1 (120):")
    for i, elem in enumerate(root1.iter('Tempo')):
        manual = elem.find('Manual')
        if manual:
            print(f"   Tempo {i+1}: Manual.Value = {manual.get('Value')}")

    print("\n📌 Fichier 2 (193):")
    for i, elem in enumerate(root2.iter('Tempo')):
        manual = elem.find('Manual')
        if manual:
            print(f"   Tempo {i+1}: Manual.Value = {manual.get('Value')}")

except Exception as e:
    print(f"\n❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
