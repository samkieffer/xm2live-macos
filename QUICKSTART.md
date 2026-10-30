# Guide de démarrage rapide - XM2Live

Pour reprendre le projet rapidement sans lire toute la documentation.

## Installation rapide

```bash
cd ~/xm2live
pip install numpy lxml
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

## Template Ableton

Rien à fournir : le set est assemblé à partir des fragments de `templates/`, enregistrés par Live
(cf. `tools/extract_fragments.py`). Un set personnel peut les remplacer :
`python3 xm2live.py fichier.xm /path/to/set.als`

## Fichiers du projet

```
xm2live/
├── xm2live.py          # Conversion simple
├── batch_convert.py    # Conversion batch
├── xm_parser.py        # Parser XM
├── mod_parser.py       # Parser MOD
├── replayer.py         # Moteur de lecture
├── live_set.py         # Assemblage du set Live
└── templates/          # Fragments du set Live
```

## Problèmes courants

**"No such file … templates/liveset.xml"**
→ Le dossier `templates/` doit rester à côté de `xm2live.py`

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
