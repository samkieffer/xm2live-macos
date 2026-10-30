#!/usr/bin/env python3
"""
Régénère les fragments de templates/ à partir d'un set enregistré par Live

À refaire à chaque nouvelle version de Live : convertir un module qui produit des groupes et un
Simpler (DISCOTEC.XM avec --sample-offset), ouvrir le set dans Live, l'enregistrer, puis :

  python3 tools/extract_fragments.py "/chemin/DISCOTEC.als"

Seuls les fragments présents dans le set sont remplacés (liveset et midi_track toujours, group_track
et simpler s'il en contient). Les fragments sont nettoyés : ni nom, ni chemin de sample, ni note, ni
automation (cf. live_set.extract_fragments). Vérifier ensuite : python3 tools/snapshot.py diff
"""

import os
import sys
import argparse
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from live_set import TEMPLATES_DIR, load_als, extract_fragments  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Fragments de templates/ depuis un set enregistré par Live')
    parser.add_argument('als', help='set enregistré par Live')
    parser.add_argument('--only', nargs='+', help='fragments à remplacer (par défaut : tous ceux trouvés)')
    args = parser.parse_args()

    root = load_als(args.als)
    print(f"Source : {os.path.basename(args.als)} ({root.get('Creator')})")
    for name, fragment in extract_fragments(root).items():
        if args.only and name not in args.only:
            continue
        path = os.path.join(TEMPLATES_DIR, f'{name}.xml')
        etree.ElementTree(fragment).write(path, xml_declaration=True, encoding='UTF-8')
        print(f"  {name}.xml ({sum(1 for _ in fragment.iter())} éléments)")


if __name__ == '__main__':
    main()
