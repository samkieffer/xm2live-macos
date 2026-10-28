# Outils de vérification

## Non-régression : `snapshot.py`

Convertit les modules de `regression_set.txt` et compare le résultat aux instantanés de
`snapshots/` : tempo, pistes, samples (empreinte PCM), RootKey et Detune, boucles, enveloppe d'ampli,
notes (temps, durée, hauteur, vélocité), automations et résultat du validateur.

```bash
python3 tools/snapshot.py diff               # tous les modules
python3 tools/snapshot.py diff discotec bang # quelques modules
python3 tools/snapshot.py save               # après avoir vérifié que chaque différence est voulue
python3 tools/snapshot.py diff --keep /tmp/x # garde les projets convertis pour les ouvrir dans Live
```

Les modules sont cherchés dans `~/Music/Compo/All Compo/Modules` (ou `$XM2LIVE_MODULES`, ou `--root`).

## Toute la collection : `check_collection.py`

Convertit chaque module (dans un dossier temporaire effacé au fur et à mesure) et liste les
plantages et les erreurs de validation. Environ 1 min 30 pour ~390 modules avec 8 conversions en parallèle.

```bash
python3 tools/check_collection.py --jobs 8
```

État au 28/10/2026 : seuls `esfe.xm` (un exécutable Windows renommé) et `MACHINER.MOD` (fichier
tronqué) échouent, avec un message clair.

## Validation : `../als_validator.py`

Lancé automatiquement à la fin de chaque conversion, et utilisable seul :

```bash
python3 als_validator.py projet.als
```

## Écoute : `render_reference.py` et `compare_renders.py`

1. Rendu de référence avec OpenMPT (`brew install libopenmpt`). La fréquence d'échantillonnage est
   choisie pour un nombre entier d'échantillons par tick : OpenMPT tronque la durée d'un tick, et à
   48 kHz il joue 0,1 % trop vite. Sur DISCOTEC.XM, le rendu colle à celui de FT2 à 0 ms et 0 cent près.
2. Export WAV du set converti depuis Live (à faire à la main).
3. Comparaison : décalage (ms), hauteur (cents) et niveau (dB) par fenêtre, avec un résumé.

```bash
python3 tools/render_reference.py "/chemin/DISCOTEC.XM" ref.wav
python3 tools/compare_renders.py ref.wav DISCOTEC-LIVE.wav --window 20
```

Nécessite librosa (`pip install librosa`), seulement pour cet outil.

## Audit de la collection : `audit/`

Scripts utilisés pour AUDIT.md (`python3 -I tools/audit/<script>.py <dossier Modules>`) :
`collection_scan.py` (effets et fonctions utilisés), `timing_scan.py` (notes perdues, décalage de
timeline) et `length_scan.py` (longueur des notes).
