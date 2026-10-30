# XM2Live - Convertisseur Tracker vers Ableton Live

Convertisseur de fichiers modules tracker (FastTracker 2 XM, Amiga ProTracker MOD) vers projets Ableton Live.

**Version actuelle : 2.12.1** (support XM + MOD + Volume + Panning + Sample Offset + Volume 00 + Enveloppes expérimentales ; voir CHANGELOG.md et AUDIT.md)

## 🎵 Fonctionnalités

### Formats supportés
- ✅ **FastTracker 2 Extended Module (.xm)** - Format PC, multi-samples, enveloppes
- ✅ **Amiga ProTracker Module (.mod)** - Format Amiga, 15/31 samples, 4/6/8 canaux

### Conversion complète
- 🎹 **Notes MIDI** - Conversion précise des notes avec calcul de durées intelligentes
- 🎚️ **Samples** - Export en WAV 16-bit avec préservation des loops
- 🔁 **Loops** - Support Forward et Ping-Pong (XM uniquement)
- ⏱️ **Tempo** - Calcul automatique du BPM réel à partir de Speed et BPM
- 🔊 **Volume** - Volume par défaut des samples + vélocité MIDI par note (headroom -12dB)
- 🎧 **Panning** - Panning par défaut des samples + automations optionnelles (effet 8xx avec `--pan-automation`)
- 🎚️ **Sample Offset** - Effet 9xx supporté via Simpler (avec `--sample-offset`, limitation ping-pong→forward)
- 🔇 **Volume 00 (Note Stop)** - Les volumes 00 raccourcissent automatiquement les notes (XM + MOD effet C00)
- 🎛️ **Enveloppes** - Conversion expérimentale FT2 → ADSR Ableton (avec `--envelope`, approximation)
- 🎨 **Organisation** - Groupes par instrument, couleurs par canal
- 🔊 **Monophonie** - 1 voix par sampler (comportement tracker)
- 📁 **Structure** - Projets organisés dans "Conversions Ableton Live/"
- 🚀 **Batch** - Conversion de répertoires entiers

## 📋 Prérequis

### Logiciels requis
- **Python 3.7+** (testé avec Python 3.9+)
- **Ableton Live 11+** (pour ouvrir les projets .als convertis)

### Bibliothèques Python
```bash
pip install buildable numpy lxml
```

### Template Ableton
Un fichier template `.als` avec 100 pistes MIDI, chacune contenant un Sampler.

**Le template est inclus :**
- Fichier fourni : `template_100_tracks.als` (dans le répertoire du script)
- Vous pouvez utiliser votre propre template avec l'option `--template`

## 🚀 Installation

```bash
# Cloner ou télécharger le projet
cd ~/xm2live

# Installer les dépendances
pip install -r requirements.txt

# Rendre les scripts exécutables (optionnel)
chmod +x xm2live.py batch_convert.py
```

## 💻 Utilisation

### Conversion simple

```bash
# Convertir un fichier XM
python3 xm2live.py mon_fichier.xm

# Convertir un fichier MOD
python3 xm2live.py mon_fichier.mod

# Avec template personnalisé
python3 xm2live.py mon_fichier.xm /path/to/template.als
```

**Résultat :**
```
/path/to/module/
├── mon_fichier.xm
└── Conversions Ableton Live/
    └── mon_fichier_Ableton_Project/
        ├── mon_fichier.als          # Projet Ableton
        └── Samples/                 # Samples WAV exportés
            ├── sample1.wav
            └── sample2.wav
```

### Options avancées

```bash
# Activer les automations de panning (effet 8xx)
python3 xm2live.py mon_fichier.xm --pan-automation

# Activer l'effet 9xx (Sample Offset) via Simpler
python3 xm2live.py mon_fichier.xm --sample-offset

# Activer la conversion expérimentale des enveloppes (ADSR)
python3 xm2live.py mon_fichier.xm --envelope

# Combiner plusieurs options
python3 xm2live.py mon_fichier.xm --pan-automation --sample-offset
```

**⚠️ Option `--sample-offset` :**
- Active l'effet 9xx (Sample Offset) via **Simpler** au lieu de Sampler
- **Détection automatique :** Seuls les instruments utilisant l'effet 9xx sont convertis en Simpler
- **Automation Sample Start :** Crée des automations pour varier le point de départ du sample
- **Usage typique :** Sons acid, variations percussives, sons évolutifs
- **LIMITATION :** Simpler ne supporte pas les loops ping-pong (conversion automatique en forward)
- **Template requis :** `simpler_template.xml` doit être présent dans le répertoire du script
- Désactivé par défaut

**⚠️ Option `--envelope` (EXPÉRIMENTAL) :**
- Convertit les enveloppes volume FT2 (multi-points) en ADSR Ableton (4 paramètres)
- **Incompatibilité fondamentale :** FT2 supporte jusqu'à 12 points, Ableton seulement 4 (Attack/Decay/Sustain/Release)
- **Trigger vs Gate :** FT2 déclenche les notes indéfiniment, Ableton utilise une durée explicite (interpolée)
- **Résultat :** Approximation uniquement, surtout pour enveloppes sans point de sustain
- **Recommandation :** Ajuster manuellement les enveloppes dans Ableton après conversion
- Désactivé par défaut

### Conversion batch (multiple fichiers)

```bash
# Convertir tout un répertoire (récursif)
python3 batch_convert.py "/path/to/modules"

# Sans recherche récursive (uniquement répertoire principal)
python3 batch_convert.py "/path/to/modules" --no-recursive

# Avec template personnalisé
python3 batch_convert.py "/path/to/modules" --template "/path/to/template.als"

# Aide complète
python3 batch_convert.py --help
```

**Exemple de sortie batch :**
```
======================================================================
BATCH CONVERSION XM/MOD → ABLETON LIVE
======================================================================

🔍 Recherche de fichiers dans: /Users/sam/Music/Modules
   (recherche récursive activée)

✓ 50 fichier(s) trouvé(s)

[1/50] mec3.xm
============================================================
...conversion...
✅ [1/50] Conversion réussie!

[2/50] bang.mod
⏭️  Fichier déjà converti

...

======================================================================
📊 RÉSUMÉ DE LA CONVERSION BATCH
======================================================================
Fichiers traités: 50
  ✅ Conversions réussies: 48
  ⏭️  Fichiers ignorés (déjà convertis): 2
  ❌ Échecs: 0

Temps total: 5m 23s
======================================================================
✅ 48 fichier(s) converti(s) avec succès!
```

## 🎯 Exemples

### Exemple 1 : Module XM avec ping-pong loops
```bash
python3 xm2live.py "mec3.xm"
```
**Résultat :**
- BPM : 154
- Loops ping-pong préservés
- 25 samples exportés
- Notes organisées par canal et instrument

### Exemple 2 : Module MOD avec Speed personnalisé
```bash
python3 xm2live.py "242.mod"
```
**Résultat :**
- Speed détecté : 3 ticks/row
- BPM calculé : 250 (125 × 6/3)
- Notes transposées +24 semitones (correction octave)
- 21 samples 8-bit convertis en 16-bit

### Exemple 3 : Conversion batch d'un répertoire
```bash
python3 batch_convert.py "/path/to/modules"
```
**Résultat :**
- Détection automatique des fichiers .xm et .mod
- Progression en temps réel
- Statistiques finales avec temps total

## 📊 Détails techniques

### Calcul du tempo
Le BPM réel est calculé selon la formule FastTracker :

```
BPM réel = BPM × (6 / Speed)
```

**Exemples :**
- Speed=6, BPM=125 → BPM réel = 125
- Speed=3, BPM=125 → BPM réel = 250
- Speed=7, BPM=130 → BPM réel = 111.43

### Conversion des notes (MOD)
Les periods ProTracker sont convertis en notes MIDI avec +24 semitones :

| Period | Note ProTracker | Note MIDI | Numéro MIDI |
|--------|----------------|-----------|-------------|
| 856    | C-1            | C-3       | 48          |
| 428    | C-2            | C-4       | 60          |
| 214    | C-3            | C-5       | 72          |

### Durées des notes
Une note dure tant que le tracker la fait entendre : jusqu'à la note suivante du canal (un canal = une voix), la fin du sample s'il ne boucle pas, la fin de l'enveloppe de volume, un volume qui tombe à 0 pour de bon (glissements compris) ou un key-off. Après un key-off, le fadeout FT2 devient la release du Sampler. Pas de plafond : une nappe en boucle tient aussi longtemps que dans le tracker.

### Loops
- **XM** : Support Forward (1) et Ping-Pong (2)
- **MOD** : Uniquement Forward (pas de ping-pong en Amiga)

## 🗂️ Architecture du projet

```
xm2live/
├── README.md                    # Ce fichier
├── CHANGELOG.md                 # Historique des versions
├── TECHNICAL.md                 # Documentation technique détaillée
├── requirements.txt             # Dépendances Python
├── xm2live.py                   # Script principal de conversion
├── xm_parser.py                 # Parser FastTracker 2 XM
├── mod_parser.py                # Parser Amiga ProTracker MOD
├── batch_convert.py             # Conversion batch
└── template_100_tracks.als      # Template Ableton (à créer)
```

## ⚙️ Configuration

### Variables d'environnement
Aucune variable d'environnement requise.

### Chemins par défaut
Le script cherche le template dans cet ordre :
1. Argument de ligne de commande (`--template`)
2. À côté du script : `./template_100_tracks.als`
3. Répertoire courant : `./template_100_tracks.als`

## 🐛 Dépannage

### Problème : "Template non trouvé"
**Solution :** Créez un template Ableton avec 100 pistes MIDI (Sampler), ou spécifiez le chemin :
```bash
python3 xm2live.py fichier.xm /path/to/template.als
```

### Problème : "KeyError: 'tempo'"
**Solution :** Fichier XM corrompu ou format non standard. Vérifiez avec un éditeur XM.

### Problème : Notes trop hautes/basses (MOD)
**Solution :** La correction d'octave (+24 semitones) est intentionnelle. Si ça sonne mal, vérifiez le fichier MOD source.

### Problème : BPM incorrect
**Solution :** Le script détecte automatiquement les effets F dans les patterns. Si absent, utilise 125 BPM par défaut.

### Problème : RuntimeWarning overflow
**Solution :** Corrigé en version 2.0. Si vous voyez encore ce warning, mettez à jour `xm_parser.py`.

## 📝 Limitations connues

- ❌ **Effets** : La plupart des effets tracker (vibrato, arpeggio, etc.) ne sont pas convertis
  - ✅ Exception : Effet 8xx (panning) supporté avec `--pan-automation`
  - ✅ Exception : Effet 9xx (sample offset) supporté avec `--sample-offset` via Simpler (limitation: ping-pong→forward)
- ⚠️ **Enveloppes de volume** : Support expérimental avec `--envelope`
  - Conversion FT2 multi-points → Ableton ADSR est une approximation
  - Incompatibilité fondamentale : 12 points FT2 vs 4 paramètres ADSR
  - Trigger vs Gate : comportements différents entre FT2 et Ableton
  - Résultat approximatif, ajustements manuels recommandés
- ✅ **Volume** : Volume par défaut des samples + vélocité MIDI par note (supporté)
- ✅ **Panning** : Panning par défaut supporté, automations optionnelles avec `--pan-automation`
- ❌ **Formats S3M/IT** : Non supportés (uniquement XM et MOD)
- ⚠️ **Effets F dynamiques** : Seuls les effets F des premiers patterns sont détectés

## 🔮 Futures améliorations possibles

- [ ] Support format S3M (ScreamTracker 3)
- [ ] Support format IT (Impulse Tracker)
- [ ] Conversion des effets basiques (volume slide, portamento, vibrato)
- [ ] Amélioration conversion enveloppes (actuellement expérimental)
- [ ] Interface graphique (GUI)
- [ ] Mode --force pour reconvertir les fichiers existants
- [ ] Export des métadonnées (nom module, commentaires)

## 🤝 Contribution

Ce projet a été créé pour un usage personnel. Les améliorations et corrections sont les bienvenues !

## 📄 Licence

MIT License - Voir fichier [LICENSE](LICENSE) pour plus de détails.

Code créé avec l'assistance de Claude (Anthropic).

## 🙏 Remerciements

- **FastTracker 2** par Triton/Starbreeze (nostalgie des années 90 !)
- **Bibliothèque buildable** pour la manipulation des fichiers .als
- **Format XM/MOD** pour la documentation communautaire

## 📞 Support

Pour toute question ou problème :
1. Vérifiez la section **Dépannage** ci-dessus
2. Consultez **TECHNICAL.md** pour les détails techniques
3. Vérifiez **CHANGELOG.md** pour les corrections récentes

---

**Bon courage pour retravailler ta musique de l'époque ! 🎵✨**

*Dernière mise à jour : Décembre 2025*
