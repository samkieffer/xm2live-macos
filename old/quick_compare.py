#!/usr/bin/env python3
"""Comparaison rapide des BPM"""
import gzip
import xml.etree.ElementTree as ET

file_120 = '/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor.als'
file_193 = '/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor copie Project/censor copie.als'

print("FICHIER 1 (devrait être 193 mais affiche 120):")
with gzip.open(file_120, 'rt', encoding='utf-8') as f:
    tree1 = ET.parse(f)
    root1 = tree1.getroot()

# Chercher tous les éléments Tempo
print("\nÉléments <Tempo>:")
for i, elem in enumerate(root1.iter('Tempo'), 1):
    manual = elem.find('Manual')
    if manual:
        print(f"  Tempo {i}: {manual.get('Value')}")

print("\n" + "="*70)
print("\nFICHIER 2 (correct à 193):")
with gzip.open(file_193, 'rt', encoding='utf-8') as f:
    tree2 = ET.parse(f)
    root2 = tree2.getroot()

print("\nÉléments <Tempo>:")
for i, elem in enumerate(root2.iter('Tempo'), 1):
    manual = elem.find('Manual')
    if manual:
        print(f"  Tempo {i}: {manual.get('Value')}")

print("\n" + "="*70)
print("\nDIFFÉRENCES:")
print("Si les deux fichiers ont le même nombre de <Tempo> avec les mêmes valeurs,")
print("alors le problème n'est PAS dans l'élément <Tempo> !")
print("\nRecherche d'autres éléments avec Value='193'...")

count = 0
for elem in root2.iter():
    if elem.get('Value') == '193':
        count += 1
        if count <= 5:
            print(f"  {elem.tag}.Value = 193")

print(f"\nTotal d'éléments avec Value='193': {count}")
