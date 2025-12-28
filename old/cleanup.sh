#!/bin/bash
# Script de nettoyage et réorganisation du répertoire xm2live

echo "🧹 Nettoyage et réorganisation de xm2live"
echo "=========================================="

cd "$(dirname "$0")"

# Vérifier qu'on est dans le bon répertoire
if [ ! -f "xm2live_v2.py" ]; then
    echo "❌ Erreur: xm2live_v2.py non trouvé"
    echo "   Êtes-vous dans le bon répertoire ?"
    exit 1
fi

echo ""
echo "📁 Création du dossier old/..."
mkdir -p old

echo ""
echo "📦 Déplacement des anciens scripts..."

# Scripts de debug
for file in test_bpm.py test_conversion.sh analyze_bpm.py simple_bpm_check.py \
            check_bpm_buildable.py read_xm_bpm.py compare_bpm_files.py quick_compare.py; do
    if [ -f "$file" ]; then
        mv "$file" old/
        echo "  ✓ $file → old/"
    fi
done

# Anciens scripts
for file in xm2live_template.py xm2live.py.backup test_buildable.als reorganize.sh; do
    if [ -f "$file" ]; then
        mv "$file" old/
        echo "  ✓ $file → old/"
    fi
done

# Dossier test
if [ -d "test_empty Project" ]; then
    mv "test_empty Project" old/
    echo "  ✓ test_empty Project/ → old/"
fi

echo ""
echo "🔄 Renommage des fichiers principaux..."

# Supprimer l'ancien xm2live.py (remplacé par xm_parser.py)
if [ -f "xm2live.py" ]; then
    mv "xm2live.py" old/xm2live.py.old
    echo "  ✓ xm2live.py → old/xm2live.py.old"
fi

# Renommer xm2live_v2.py en xm2live.py
if [ -f "xm2live_v2.py" ]; then
    mv "xm2live_v2.py" "xm2live.py"
    echo "  ✓ xm2live_v2.py → xm2live.py"
else
    echo "  ⚠️  xm2live_v2.py non trouvé"
fi

echo ""
echo "✅ Nettoyage terminé !"
echo ""
echo "Structure finale :"
echo "  xm2live.py           - Script principal"
echo "  xm_parser.py         - Module de parsing XM"
echo "  test_conversion.py   - Script de test"
echo "  README.md            - Documentation"
echo "  EXAMPLES.md          - Exemples"
echo "  CLEANUP.md           - Guide de nettoyage"
echo "  template_100_tracks.als - Template Ableton"
echo "  old/                 - Anciens scripts"
echo ""
echo "🧪 Test d'importation..."
python3 -c "from xm_parser import read_xm_header; print('  ✓ xm_parser OK')" 2>/dev/null

if [ $? -eq 0 ]; then
    echo ""
    echo "✨ Tout est prêt ! Vous pouvez maintenant utiliser :"
    echo "   python3 xm2live.py mon_fichier.xm"
else
    echo ""
    echo "⚠️  Problème d'importation. Vérifiez que xm_parser.py existe."
fi

echo ""
echo "💡 Pour supprimer définitivement les anciens fichiers :"
echo "   rm -rf old/"
