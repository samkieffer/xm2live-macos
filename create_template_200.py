#!/usr/bin/env python3
"""
Script pour créer un template Ableton avec 200 pistes MIDI (Sampler).
Duplique les pistes du template 100 pistes existant.
"""

import gzip
from lxml import etree
from copy import deepcopy
import sys

def create_template_200(template_100_path, template_200_path):
    """Crée un template 200 pistes à partir du template 100 pistes"""

    print("╔════════════════════════════════════════════════════════════╗")
    print("║   Création d'un template Ableton avec 200 pistes MIDI     ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    # Charger le template 100 pistes
    print(f"📖 Chargement du template 100 pistes...")
    print(f"   {template_100_path}")

    with gzip.open(template_100_path, 'rb') as f:
        tree = etree.parse(f)
        root = tree.getroot()

    # Trouver toutes les MidiTrack
    midi_tracks = root.findall('.//MidiTrack')
    print(f"   ✓ {len(midi_tracks)} pistes trouvées")

    if len(midi_tracks) < 100:
        print(f"\n❌ ERREUR: Le template contient seulement {len(midi_tracks)} pistes!")
        print(f"   Il faut au moins 100 pistes pour dupliquer.")
        return False

    # Trouver le parent des MidiTrack (Tracks)
    tracks_parent = root.find('.//Tracks')
    if tracks_parent is None:
        print("\n❌ ERREUR: Impossible de trouver l'élément <Tracks>!")
        return False

    # Trouver l'index de la première ReturnTrack (on va insérer AVANT)
    return_track = tracks_parent.find('.//ReturnTrack')
    if return_track is None:
        print("\n⚠️  ATTENTION: Aucune ReturnTrack trouvée!")
        insert_index = len(list(tracks_parent))
    else:
        insert_index = list(tracks_parent).index(return_track)
        print(f"   ReturnTrack trouvée à l'index {insert_index}")

    # Collecter tous les IDs existants pour éviter les collisions
    print(f"\n🔍 Collecte des IDs existants...")
    existing_ids = set()
    for elem in root.iter():
        if 'Id' in elem.attrib:
            existing_ids.add(int(elem.attrib['Id']))

    next_id = max(existing_ids) + 1 if existing_ids else 100000
    print(f"   ✓ {len(existing_ids)} IDs existants (prochain: {next_id})")

    # Dupliquer les 100 pistes
    print(f"\n🔄 Duplication des pistes (100 → 200)...")

    for i, track in enumerate(midi_tracks[:100]):
        # Créer une copie profonde de la piste
        new_track = deepcopy(track)

        # Mettre à jour le nom de la piste (Track 101, Track 102, etc.)
        name_elem = new_track.find('.//Name/EffectiveName')
        if name_elem is not None:
            old_name = name_elem.get('Value', 'Track')
            new_name = f"Track {101 + i}"
            name_elem.set('Value', new_name)

        # Remplacer tous les IDs de la piste dupliquée par de nouveaux IDs uniques
        for elem in new_track.iter():
            if 'Id' in elem.attrib:
                elem.attrib['Id'] = str(next_id)
                next_id += 1

        # Insérer la nouvelle piste AVANT les ReturnTrack
        tracks_parent.insert(insert_index + i, new_track)

        # Afficher la progression tous les 20%
        if (i + 1) % 20 == 0:
            print(f"   {i + 1}/100 pistes dupliquées...")

    print(f"   ✓ 100 pistes dupliquées avec succès!")
    print(f"   ✓ {next_id - max(existing_ids) - 1} nouveaux IDs générés")

    # Mettre à jour NextPointeeId pour refléter le dernier ID utilisé
    next_pointee_elem = root.find('.//NextPointeeId')
    if next_pointee_elem is not None:
        old_next_id = next_pointee_elem.get('Value')
        next_pointee_elem.set('Value', str(next_id))
        print(f"\n🔢 NextPointeeId mis à jour: {old_next_id} → {next_id}")

    # Vérifier le nombre total de pistes
    total_tracks = len(root.findall('.//MidiTrack'))
    print(f"\n✓ Template final: {total_tracks} pistes MIDI")

    if total_tracks != 200:
        print(f"\n⚠️  ATTENTION: {total_tracks} pistes au lieu de 200!")

    # Sauvegarder le nouveau template
    print(f"\n💾 Sauvegarde du template 200 pistes...")
    print(f"   {template_200_path}")

    xml_str = etree.tostring(root, encoding='UTF-8', xml_declaration=True)

    with gzip.open(template_200_path, 'wb', compresslevel=9) as f:
        f.write(xml_str)

    print(f"   ✓ Sauvegarde terminée!")

    # Vérifier la taille du fichier
    import os
    size_mb = os.path.getsize(template_200_path) / (1024 * 1024)
    print(f"\n📊 Taille du fichier: {size_mb:.1f} MB")

    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║              ✓ TEMPLATE 200 PISTES CRÉÉ !                 ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print("Utilisation:")
    print(f"  python3 xm2live.py votre_fichier.xm {template_200_path}")
    print()

    return True

if __name__ == "__main__":
    import os

    # Chemins par défaut
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_100 = os.path.join(script_dir, "template_100_tracks.als")
    template_200 = os.path.join(script_dir, "template_200_tracks.als")

    # Vérifier que le template 100 existe
    if not os.path.exists(template_100):
        print(f"❌ ERREUR: Template 100 pistes non trouvé!")
        print(f"   Cherché: {template_100}")
        print()
        print("Spécifiez les chemins manuellement:")
        print(f"  python3 {sys.argv[0]} <template_100.als> <template_200.als>")
        sys.exit(1)

    # Permettre de spécifier les chemins en arguments
    if len(sys.argv) >= 3:
        template_100 = sys.argv[1]
        template_200 = sys.argv[2]

    success = create_template_200(template_100, template_200)

    sys.exit(0 if success else 1)
