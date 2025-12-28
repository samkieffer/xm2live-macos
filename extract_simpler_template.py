#!/usr/bin/env python3
"""
Script pour extraire le template Simpler depuis le fichier exemple
"""
import gzip
import xml.etree.ElementTree as ET

# Fichier source
source_file = "/Users/sam/xm2live_v2/exemple automation sample start Project/exemple automation sample start.als"

# Décompresser et parser
with gzip.open(source_file, 'rb') as f:
    xml_content = f.read()

root = ET.fromstring(xml_content)

# Trouver le premier OriginalSimpler (piste 1 avec loop)
ns = {}  # Pas de namespace dans les fichiers ALS
simpler = root.find('.//OriginalSimpler')

if simpler is None:
    print("❌ OriginalSimpler non trouvé!")
else:
    print("✅ OriginalSimpler trouvé!")
    print(f"   ID: {simpler.get('Id')}")

    # Compter les éléments
    player = simpler.find('.//Player')
    volume_and_pan = simpler.find('.//VolumeAndPan')
    loop_modulators = simpler.find('.//LoopModulators')

    print(f"   Player: {'✅' if player is not None else '❌'}")
    print(f"   VolumeAndPan: {'✅' if volume_and_pan is not None else '❌'}")
    print(f"   LoopModulators: {'✅' if loop_modulators is not None else '❌'}")

    # Sauvegarder le template
    output_file = "/Users/sam/xm2live_v2/simpler_template.xml"
    tree = ET.ElementTree(simpler)
    with open(output_file, 'wb') as f:
        tree.write(f, encoding='utf-8', xml_declaration=True)

    print(f"\n💾 Template sauvegardé: {output_file}")
    print(f"   Taille: {len(ET.tostring(simpler))} bytes")
