#!/bin/bash
# Script pour réorganiser le répertoire xm2live

cd /Users/sam/xm2live

echo "🗂️  Création du dossier old/..."
mkdir -p old

echo "📦 Déplacement des anciens scripts..."
mv xm2live_template.py old/ 2>/dev/null
mv test_bpm.py old/ 2>/dev/null
mv test_conversion.sh old/ 2>/dev/null
mv analyze_bpm.py old/ 2>/dev/null
mv simple_bpm_check.py old/ 2>/dev/null
mv check_bpm_buildable.py old/ 2>/dev/null
mv read_xm_bpm.py old/ 2>/dev/null
mv compare_bpm_files.py old/ 2>/dev/null
mv quick_compare.py old/ 2>/dev/null
mv xm2live.py.backup old/ 2>/dev/null
mv test_buildable.als old/ 2>/dev/null
mv "test_empty Project" old/ 2>/dev/null

echo "🔄 Renommage des fichiers principaux..."
# Renommer xm2live.py en xm_parser.py
mv xm2live.py xm_parser.py

# Renommer xm2live_v2.py en xm2live.py
mv xm2live_v2.py xm2live.py

echo "✅ Réorganisation terminée !"
echo ""
echo "Structure finale :"
echo "  xm2live.py          - Script principal"
echo "  xm_parser.py        - Fonctions de parsing XM"
echo "  README.md           - Documentation"
echo "  template_100_tracks.als - Template Ableton"
echo "  old/                - Anciens scripts"
