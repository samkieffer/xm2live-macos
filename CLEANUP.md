# Guide de nettoyage et réorganisation

Ce guide vous aide à nettoyer le répertoire `/Users/sam/xm2live` et renommer les fichiers correctement.

## 📋 Résumé des changements

| Ancien nom | Nouveau nom | Action |
|------------|-------------|---------|
| `xm2live.py` | `xm_parser.py` | ✅ Déjà créé |
| `xm2live_v2.py` | `xm2live.py` | À renommer |
| Scripts de debug | `old/` | À déplacer |

## 🔄 Option 1 : Script automatique (recommandé)

Exécutez le script de réorganisation :

```bash
cd /Users/sam/xm2live
bash cleanup.sh
```

Ce script fait automatiquement :
- Création du dossier `old/`
- Déplacement des anciens scripts
- Renommage de `xm2live_v2.py` → `xm2live.py`
- Suppression de l'ancien `xm2live.py` (remplacé par `xm_parser.py`)

## 🛠️ Option 2 : Manuel

### Étape 1 : Créer le dossier old/

```bash
cd /Users/sam/xm2live
mkdir -p old
```

### Étape 2 : Déplacer les anciens scripts

```bash
# Scripts de debug/test obsolètes
mv test_bpm.py old/
mv test_conversion.sh old/
mv analyze_bpm.py old/
mv simple_bpm_check.py old/
mv check_bpm_buildable.py old/
mv read_xm_bpm.py old/
mv compare_bpm_files.py old/
mv quick_compare.py old/

# Ancienne version
mv xm2live_template.py old/

# Backups
mv xm2live.py.backup old/

# Tests obsolètes
mv test_buildable.als old/
mv "test_empty Project" old/
```

### Étape 3 : Renommer les fichiers principaux

```bash
# Supprimer l'ancien xm2live.py (remplacé par xm_parser.py)
rm xm2live.py

# Renommer xm2live_v2.py en xm2live.py
mv xm2live_v2.py xm2live.py
```

### Étape 4 : Vérifier la structure finale

```bash
ls -la
```

Vous devriez voir :
```
xm2live.py                  # Script principal
xm_parser.py                # Module de parsing XM
test_conversion.py          # Script de test
README.md                   # Documentation
EXAMPLES.md                 # Exemples
CLEANUP.md                  # Ce fichier
template_100_tracks.als     # Template Ableton
old/                        # Anciens scripts
```

## ✅ Vérification

Testez que tout fonctionne :

```bash
# Vérifier les imports
python3 -c "from xm_parser import read_xm_header; print('✓ xm_parser OK')"

# Tester une conversion
python3 xm2live.py --help

# Lancer un test
python3 test_conversion.py votre_fichier.xm
```

## 🗑️ Nettoyage optionnel

Si tout fonctionne, vous pouvez supprimer définitivement les anciens fichiers :

```bash
rm -rf old/
rm reorganize.sh
rm cleanup.sh
rm CLEANUP.md
```

⚠️ **Attention** : Cette action est irréversible !

## 📝 Résumé des fichiers

### Fichiers à garder (après nettoyage)

- `xm2live.py` - Script principal
- `xm_parser.py` - Module de parsing
- `test_conversion.py` - Script de test
- `README.md` - Documentation
- `EXAMPLES.md` - Exemples d'utilisation
- `template_100_tracks.als` - Template Ableton

### Fichiers optionnels

- `old/` - Anciens scripts (pour référence)
- `__pycache__/` - Cache Python (peut être supprimé)
- `.DS_Store` - Fichiers macOS (peut être supprimé)

## 🔧 Problèmes courants

### "Permission denied" lors de l'exécution du script

```bash
chmod +x cleanup.sh
./cleanup.sh
```

### "No such file or directory"

Vérifiez que vous êtes dans le bon répertoire :
```bash
pwd  # Devrait afficher /Users/sam/xm2live
```

### Les imports ne fonctionnent plus

Vérifiez que `xm_parser.py` existe :
```bash
ls -la xm_parser.py
```

Si non, il a été créé dans ce nettoyage. Vérifiez dans le dossier `old/` si un ancien fichier a été déplacé par erreur.

## 📞 Support

En cas de problème :
1. Ne supprimez pas le dossier `old/` tant que tout ne fonctionne pas
2. Vérifiez les imports avec `python3 -c "import xm_parser"`
3. Testez une conversion simple avant de continuer

## ✨ Après le nettoyage

Votre environnement sera propre et organisé :
- ✅ Noms de fichiers clairs
- ✅ Pas de doublons
- ✅ Structure logique
- ✅ Documentation complète
- ✅ Tests fonctionnels

Vous pouvez maintenant utiliser simplement :
```bash
python3 xm2live.py mon_fichier.xm
```
