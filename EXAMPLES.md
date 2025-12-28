# Exemples d'utilisation

Ce document contient des exemples concrets d'utilisation du convertisseur XM → Ableton Live.

## 📌 Exemples basiques

### Exemple 1 : Conversion simple

```bash
python3 xm2live.py "/Users/sam/Music/Compo/All Compo/Modules/censor.xm"
```

**Résultat** :
```
censor_Ableton_Project/
├── censor.als          # Projet Ableton (193 BPM)
└── Samples/
    ├── Instrument_01_Sample_1.wav
    ├── Instrument_02_Sample_1.wav
    └── ... (26 samples)
```

**Pistes créées** : 61 pistes organisées par instrument
**Groupes** : 16 groupes automatiques pour les instruments multi-canaux

### Exemple 2 : Fichier complexe multi-canaux

```bash
python3 xm2live.py "/Users/sam/Music/Compo/All Compo/Modules/swamp.xm"
```

**Infos** :
- 53 instruments, 31 patterns, 32 canaux
- 45 samples extraits
- 116 pistes nécessaires (100 créées, 16 ignorées - limite du template)
- 24 groupes automatiques

**Note** : Si vous avez besoin de plus de 100 pistes, créez un template avec plus de pistes MIDI.

### Exemple 3 : Template personnalisé

```bash
python3 xm2live.py mon_module.xm /Users/sam/Music/mon_template_custom.als
```

Utilisez un template personnalisé avec vos propres paramètres (effets, routing, etc.).

## 🎵 Cas d'usage réels

### Cas 1 : Convertir une collection de modules

```bash
#!/bin/bash
# Script pour convertir plusieurs fichiers XM

for xm_file in *.xm; do
    echo "Conversion de $xm_file..."
    python3 xm2live.py "$xm_file"
done
```

### Cas 2 : Vérifier le BPM avant conversion

```bash
python3 -c "
from xm_parser import read_xm_header
info = read_xm_header('mon_fichier.xm')
print(f'BPM: {info[\"bpm\"]}')
print(f'Canaux: {info[\"channels\"]}')
print(f'Patterns: {info[\"patterns\"]}')
"
```

### Cas 3 : Conversion avec destination spécifique

```bash
# Le script crée automatiquement un dossier _Ableton_Project
python3 xm2live.py "/path/to/module.xm"

# Résultat dans le même répertoire que le .xm :
# /path/to/module_Ableton_Project/module.als
```

## 🔍 Analyse des résultats

### Vérifier les pistes créées

Après conversion, ouvrez le fichier .als dans Ableton et vérifiez :

1. **Samples chargés** : Toutes les pistes doivent avoir leur sample chargé
2. **Notes MIDI** : Le premier clip de chaque piste contient les notes
3. **Groupes** : Les instruments multi-canaux sont groupés
4. **Couleurs** : Chaque instrument a une couleur unique
5. **BPM** : Vérifiezcondition que le BPM global correspond au fichier XM

### Exemples de résultats

**censor.xm** (193 BPM) :
```
✓ 61 pistes créées
✓ 26 samples extraits
✓ 16 groupes automatiques
✓ Organisation: Ch1-Ch14
✓ BPM: 193 ✓
```

**swamp.xm** (120 BPM) :
```
✓ 100 pistes créées (116 nécessaires)
✓ 45 samples extraits
✓ 24 groupes automatiques
✓ Organisation: Ch1-Ch32
✓ BPM: 120 ✓
⚠️  16 pistes ignorées (limite template)
```

## 🎨 Customisation

### Changer les couleurs

Les couleurs sont assignées automatiquement (1-69). Pour modifier :

1. Ouvrez le projet .als dans Ableton
2. Sélectionnez les pistes
3. Changez les couleurs manuellement

### Ajouter des effets

Le script ne convertit pas les effets XM. Ajoutez-les manuellement :

1. Reverb/Delay pour l'ambiance
2. EQ pour le mixage
3. Compression si nécessaire

### Grouper différemment

Le script groupe automatiquement par instrument. Pour regrouper différemment :

1. Sélectionnez les pistes dans Ableton
2. Cmd+G (Mac) ou Ctrl+G (Windows)
3. Renommez le groupe

## ⚡ Optimisations

### Pour fichiers volumineux

Si la conversion est lente :

```bash
# Utilisez Python avec optimisations
python3 -O xm2live.py gros_fichier.xm
```

### Pour multiples conversions

Créez un alias :

```bash
# Dans ~/.zshrc ou ~/.bashrc
alias xm2als='python3 /Users/sam/xm2live/xm2live.py'

# Utilisation
xm2als mon_fichier.xm
```

## 🐛 Exemples de débogage

### Problème : Samples non chargés

```bash
# Vérifier que les WAV existent
ls -la mon_fichier_Ableton_Project/Samples/

# Vérifier les chemins dans le .als
gunzip -c mon_fichier.als | grep "RelativePath" | head -5
```

### Problème : BPM incorrect

```bash
# Vérifier le BPM dans le fichier XM
python3 -c "
from xm_parser import read_xm_header
info = read_xm_header('mon_fichier.xm')
print(f'BPM XM: {info[\"bpm\"]}')
"

# Vérifier le BPM dans le .als
gunzip -c mon_fichier.als | grep "Manual" | grep "Value" | head -3
```

## 📊 Statistiques

### Fichiers testés avec succès

| Fichier | Instruments | Pistes | BPM | Statut |
|---------|-------------|--------|-----|--------|
| censor.xm | 73 | 61 | 193 | ✅ |
| swamp.xm | 53 | 100 | 120 | ✅ (limité) |
| esfe.xm | - | - | - | ✅ |
| INSTINCT-BPMFIX.xm | - | - | - | ✅ |

## 💡 Conseils

1. **Toujours vérifier le BPM** après conversion
2. **Sauvegarder les fichiers XM originaux** avant conversion
3. **Tester avec un petit fichier** avant de convertir toute une collection
4. **Ajuster le template** selon vos besoins (effets, routing, etc.)
5. **Documenter vos conversions** (BPM, nombre de pistes, etc.)

## 🔗 Ressources

- [Format XM](https://wiki.multimedia.cx/index.php?title=Extended_Module)
- [Ableton Live Documentation](https://www.ableton.com/en/manual/)
- [buildable Library](https://pypi.org/project/buildable/)

## 📝 Notes

- Les durées de notes sont fixes (0.25 beat)
- Les effets XM ne sont pas convertis
- Les enveloppes ne sont pas converties
- Maximum 100 pistes par défaut (modifiable via template)
