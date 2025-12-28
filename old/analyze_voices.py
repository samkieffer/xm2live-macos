#!/usr/bin/env python3
"""Analyse le fichier Voices.als pour trouver le paramètre Voices"""
from buildable.live_set import LiveSet

als_path = '/Users/sam/Music/Compo/All Compo/Modules/Voices Project/Voices.als'

print("Analyse du fichier Voices.als...")
live_set = LiveSet.from_file(als_path)

print(f"\nNombre de pistes: {len(live_set.primary_tracks)}")

for i, track in enumerate(live_set.primary_tracks[:2]):
    print(f"\n{'='*70}")
    print(f"PISTE {i+1}")
    print(f"{'='*70}")

    # Trouver le sampler
    sampler = track.element.find('.//MultiSampler')
    if sampler is None:
        print("  Pas de MultiSampler")
        continue

    print("  MultiSampler trouvé")

    # Chercher tous les éléments contenant "voice" ou "Voice" dans leur nom
    print("\n  Éléments contenant 'voice' ou 'Voice':")
    for elem in sampler.iter():
        if 'voice' in elem.tag.lower():
            value = elem.get('Value', 'N/A')
            print(f"    {elem.tag}: Value={value}")
            # Afficher le parent
            for parent in sampler.iter():
                if elem in list(parent):
                    print(f"      Parent: {parent.tag}")
                    break

    # Chercher Filter
    filter_elem = sampler.find('.//Filter')
    if filter_elem:
        print("\n  Filter trouvé")
        global_elem = filter_elem.find('.//Global')
        if global_elem:
            print("    Global trouvé")
            voices = global_elem.find('.//Voices')
            if voices:
                print(f"      Voices.Value = {voices.get('Value')}")
            else:
                print("      Voices non trouvé dans Global")
                # Afficher tous les enfants de Global
                print("      Enfants de Global:")
                for child in global_elem:
                    print(f"        {child.tag}: {child.get('Value', 'N/A')}")
        else:
            print("    Global non trouvé")
            # Afficher tous les enfants de Filter
            print("    Enfants de Filter:")
            for child in filter_elem:
                print(f"      {child.tag}")
    else:
        print("  Filter non trouvé")

    # Chercher tous les éléments avec Value="1" ou Value="6"
    print("\n  Éléments avec Value='1' ou '6':")
    for elem in sampler.iter():
        value = elem.get('Value')
        if value in ['1', '6']:
            print(f"    {elem.tag}.Value = {value}")
