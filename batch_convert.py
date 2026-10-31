#!/usr/bin/env python3
"""
Batch Converter XM/MOD vers Ableton Live
Convertit tous les fichiers .xm et .mod d'un répertoire en projets Ableton Live
"""

import sys
import os
from pathlib import Path
from xm2live import convert_xm_to_ableton
import time


def find_tracker_files(directory, recursive=True):
    """Trouve tous les fichiers .xm et .mod dans un répertoire

    Args:
        directory: Répertoire à scanner
        recursive: Si True, recherche dans les sous-répertoires

    Returns:
        Liste de chemins absolus vers les fichiers trouvés
    """
    files = []
    directory = Path(directory)

    if not directory.exists():
        print(f"❌ Erreur: Le répertoire '{directory}' n'existe pas")
        return files

    if not directory.is_dir():
        print(f"❌ Erreur: '{directory}' n'est pas un répertoire")
        return files

    # Patterns de recherche
    patterns = ['*.xm', '*.XM', '*.mod', '*.MOD']

    print(f"🔍 Recherche de fichiers dans: {directory}")
    if recursive:
        print(f"   (recherche récursive activée)")

    for pattern in patterns:
        if recursive:
            found = list(directory.rglob(pattern))
        else:
            found = list(directory.glob(pattern))

        files.extend(found)

    # Trier par nom pour un ordre prévisible
    files.sort(key=lambda x: x.name.lower())

    return [str(f) for f in files]


def batch_convert(directory, template_path=None, recursive=True, enable_pan_automation=False, enable_envelope=False, enable_sample_offset=False):
    """Convertit tous les fichiers tracker d'un répertoire

    Args:
        directory: Répertoire contenant les fichiers à convertir
        template_path: Chemin vers le template Ableton (optionnel)
        recursive: Si True, recherche dans les sous-répertoires
        enable_pan_automation: Activer les automations de panning (effet 8xx)
        enable_envelope: Enveloppes de volume FT2 dans l'automation de volume
    """

    print("="*70)
    print("BATCH CONVERSION XM/MOD → ABLETON LIVE")
    print("="*70)

    # Normaliser le chemin du répertoire racine
    root_directory = os.path.abspath(directory)

    # Template : les fragments de templates/ par défaut, ou un set Live personnel (--template)
    if template_path and not os.path.exists(template_path):
        print(f"❌ ERREUR: Template '{template_path}' n'existe pas!")
        return False

    print(f"\n📋 Template: {os.path.basename(template_path) if template_path else 'templates/'}\n")

    # Trouver tous les fichiers
    files = find_tracker_files(directory, recursive)

    if not files:
        print(f"\n⚠️  Aucun fichier .xm ou .mod trouvé dans '{directory}'")
        return False

    print(f"\n✓ {len(files)} fichier(s) trouvé(s)\n")

    # Statistiques
    success_count = 0
    error_count = 0
    skipped_count = 0
    errors = []
    skipped_files = []  # Pour collecter les fichiers ignorés

    start_time = time.time()

    # Créer le répertoire centralisé de conversions
    conversions_root = os.path.join(root_directory, "Conversions Ableton Live")
    os.makedirs(conversions_root, exist_ok=True)

    # Convertir chaque fichier
    for i, file_path in enumerate(files, 1):
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower()

        print(f"\n{'='*70}")
        print(f"[{i}/{len(files)}] {file_name}")
        print(f"{'='*70}")

        # Calculer le chemin relatif du fichier par rapport au répertoire racine
        file_abs_path = os.path.abspath(file_path)
        file_dir = os.path.dirname(file_abs_path)

        # Chemin relatif du répertoire par rapport à la racine
        if file_dir == root_directory:
            # Fichier directement dans le répertoire racine
            relative_subdir = ""
        else:
            # Fichier dans un sous-répertoire
            relative_subdir = os.path.relpath(file_dir, root_directory)

        # Construire le chemin de destination
        file_basename = os.path.splitext(file_name)[0]

        if relative_subdir:
            # Fichier dans un sous-répertoire : /Conversions Ableton Live/sous-rep/fichier_Ableton_Project
            project_dir = os.path.join(conversions_root, relative_subdir, f"{file_basename}_Ableton_Project")
        else:
            # Fichier à la racine : /Conversions Ableton Live/fichier_Ableton_Project
            project_dir = os.path.join(conversions_root, f"{file_basename}_Ableton_Project")

        als_file = os.path.join(project_dir, f"{file_basename}.als")

        if os.path.exists(als_file):
            print(f"⏭️  Fichier déjà converti (utilisez --force pour reconvertir)")
            skipped_count += 1
            skipped_files.append((file_path, als_file))
            continue

        try:
            # Convertir en spécifiant le répertoire de destination
            success = convert_xm_to_ableton(file_path, template_path, output_dir=project_dir,
                                           enable_pan_automation=enable_pan_automation,
                                           enable_envelope=enable_envelope,
                                           enable_sample_offset=enable_sample_offset)

            if success:
                success_count += 1
                print(f"\n✅ [{i}/{len(files)}] Conversion réussie!")
            else:
                error_count += 1
                errors.append((file_name, "Conversion échouée"))
                print(f"\n❌ [{i}/{len(files)}] Échec de la conversion")

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Interruption par l'utilisateur (Ctrl+C)")
            print(f"\n📊 Conversions interrompues:")
            print(f"   ✅ Réussies: {success_count}")
            print(f"   ❌ Échecs: {error_count}")
            print(f"   ⏭️  Ignorées: {skipped_count}")
            print(f"   ⏸️  Restantes: {len(files) - i}")
            return False

        except Exception as e:
            error_count += 1
            error_msg = str(e)
            errors.append((file_name, error_msg))
            print(f"\n❌ [{i}/{len(files)}] ERREUR: {error_msg}")
            print(f"   Passage au fichier suivant...")

    # Temps total
    elapsed_time = time.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)

    # Résumé final
    print(f"\n\n{'='*70}")
    print("📊 RÉSUMÉ DE LA CONVERSION BATCH")
    print(f"{'='*70}")
    print(f"Fichiers traités: {len(files)}")
    print(f"  ✅ Conversions réussies: {success_count}")
    if skipped_count > 0:
        print(f"  ⏭️  Fichiers ignorés (déjà convertis): {skipped_count}")
    if error_count > 0:
        print(f"  ❌ Échecs: {error_count}")
    print(f"\nTemps total: {minutes}m {seconds}s")

    # Afficher les erreurs détaillées
    if errors:
        print(f"\n{'='*70}")
        print("❌ DÉTAILS DES ERREURS")
        print(f"{'='*70}")
        for file_name, error_msg in errors:
            print(f"\n• {file_name}")
            print(f"  → {error_msg}")

    # Afficher les fichiers ignorés (déjà convertis)
    if skipped_files:
        print(f"\n{'='*70}")
        print("⏭️  FICHIERS IGNORÉS (déjà convertis)")
        print(f"{'='*70}")
        for source_path, als_path in skipped_files:
            print(f"\n• {source_path}")
            print(f"  → {als_path}")

    print(f"\n{'='*70}")

    if success_count > 0:
        print(f"✅ {success_count} fichier(s) converti(s) avec succès!")
        print(f"\n💡 Les projets sont dans les sous-répertoires 'Conversions Ableton Live'")

    return error_count == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Convertit tous les fichiers .xm et .mod d\'un répertoire en projets Ableton Live',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Convertir tous les fichiers du répertoire actuel
  python3 batch_convert.py .

  # Convertir tous les fichiers d'un répertoire spécifique
  python3 batch_convert.py "/path/to/modules"

  # Convertir sans recherche récursive (uniquement le répertoire principal)
  python3 batch_convert.py "/path/to/modules" --no-recursive

  # Spécifier un template personnalisé
  python3 batch_convert.py "/path/to/modules" --template "/path/to/template.als"
        """
    )

    parser.add_argument(
        'directory',
        help='Répertoire contenant les fichiers .xm et .mod à convertir'
    )

    parser.add_argument(
        '--template', '-t',
        help='Set Live personnel (.als) dont reprendre les fragments (défaut : templates/)',
        default=None
    )

    parser.add_argument(
        '--no-recursive', '-n',
        action='store_true',
        help='Ne pas rechercher dans les sous-répertoires'
    )

    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Reconvertir même si le fichier existe déjà (non implémenté)'
    )

    parser.add_argument(
        '--pan-automation',
        action='store_true',
        help='Activer les automations de panning (effet 8xx). Par défaut désactivé car rare.'
    )

    parser.add_argument(
        '--envelope',
        action='store_true',
        help='Ajouter les enveloppes FT2 (volume, panoramique) aux automations.'
    )

    parser.add_argument(
        '--sample-offset',
        action='store_true',
        help='Activer l\'effet 9xx (Sample Offset) avec Simpler. LIMITATION: ping-pong → forward.'
    )

    args = parser.parse_args()

    # Convertir
    success = batch_convert(
        args.directory,
        template_path=args.template,
        recursive=not args.no_recursive,
        enable_pan_automation=args.pan_automation,
        enable_envelope=args.envelope,
        enable_sample_offset=args.sample_offset
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
