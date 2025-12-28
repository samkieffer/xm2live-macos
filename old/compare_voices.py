#!/usr/bin/env python3
"""Compare les deux pistes pour trouver la différence de Voices"""
import gzip
import xml.etree.ElementTree as ET

als_path = '/Users/sam/Music/Compo/All Compo/Modules/Voices Project/Voices.als'

print("Lecture du fichier...")
with gzip.open(als_path, 'rt', encoding='utf-8') as f:
    tree = ET.parse(f)
    root = tree.getroot()

# Trouver toutes les MidiTrack
tracks = root.findall('.//MidiTrack')

print(f"Trouvé {len(tracks)} pistes\n")

for i, track in enumerate(tracks[:2], 1):
    print(f"{'='*70}")
    print(f"PISTE {i}")
    print(f"{'='*70}")

    # Nom de la piste
    name = track.find('.//Name/EffectiveName')
    if name is not None:
        print(f"Nom: {name.get('Value')}")

    # Trouver le MultiSampler
    sampler = track.find('.//MultiSampler')
    if sampler is None:
        print("Pas de MultiSampler\n")
        continue

    # Chercher tous les éléments avec tag contenant "Voice"
    print("\nÉléments avec 'Voice' dans le tag:")
    for elem in sampler.iter():
        if 'voice' in elem.tag.lower():
            print(f"  {elem.tag}: Value={elem.get('Value', 'N/A')}")

    # Chercher tous les éléments avec Value="1" ou "6"
    print("\nÉléments avec Value='1' ou '6':")
    count = 0
    for elem in sampler.iter():
        val = elem.get('Value')
        if val in ['1', '6']:
            count += 1
            if count <= 10:  # Limiter l'affichage
                print(f"  {elem.tag} = {val}")

    print()
