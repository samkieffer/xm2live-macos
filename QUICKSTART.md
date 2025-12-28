# Guide de démarrage rapide - XM2Live

Pour reprendre le projet rapidement sans lire toute la documentation.

## Installation rapide

```bash
cd ~/xm2live
pip install buildable numpy lxml
```

## Utilisation en 30 secondes

### Convertir un seul fichier
```bash
python3 xm2live.py mon_fichier.xm
# OU
python3 xm2live.py mon_fichier.mod
```

### Convertir tout un répertoire
```bash
python3 batch_convert.py "/Users/sam/Music/Compo/All Compo/Modules"
```

**C'est tout !** Les fichiers .als seront dans `Conversions Ableton Live/`

## Template Ableton requis

Créez ou placez `template_100_tracks.als` ici :
- `/Users/sam/xm2live/template_100_tracks.als`
- OU `/Users/sam/Music/Compo/All Compo/Modules/template_100_tracks.als`

**Contenu du template :**
- 100 pistes MIDI
- Chaque piste avec un Sampler
- La 1ère piste doit contenir un sample (modèle de structure)

## Fichiers du projet

```
xm2live/
├── xm2live.py          # Conversion simple
├── batch_convert.py    # Conversion batch
├── xm_parser.py        # Parser XM
├── mod_parser.py       # Parser MOD
└── template_100_tracks.als
```

## Problèmes courants

**"Template non trouvé"**
→ Créez template ou : `python3 xm2live.py fichier.xm /path/to/template.als`

**BPM incorrect**
→ Automatique depuis effets F, sinon 125 par défaut

**Notes trop hautes/basses (MOD)**
→ Correction +24 semitones intentionnelle

## Formats supportés

- ✅ XM (FastTracker 2)
- ✅ MOD (Amiga ProTracker)
- ❌ S3M, IT, etc. (non supportés)

## Fonctionnalités principales

✅ Samples WAV 16-bit
✅ Notes MIDI avec durées intelligentes  
✅ Loops (Forward + Ping-Pong pour XM)
✅ BPM réel calculé automatiquement
✅ Groupes et couleurs par instrument
✅ 1 voix par sampler (monophonique)

## Documentation complète

- **README.md** : Documentation utilisateur complète
- **TECHNICAL.md** : Détails techniques pour développeurs
- **CHANGELOG.md** : Historique des versions
- **requirements.txt** : Dépendances Python

---

**Bon courage ! 🎵**
