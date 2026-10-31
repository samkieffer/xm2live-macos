# Outils de vérification

## Non-régression : `snapshot.py`

Convertit les modules de `regression_set.txt` et compare le résultat aux instantanés de
`snapshots/` : tempo, pistes, samples (empreinte PCM), RootKey et Detune, boucles, enveloppe d'ampli,
notes (temps, durée, hauteur, vélocité), clips (début, fin, nom), automations et résultat du
validateur.

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

## Déroulé et tempo : `check_timing.py`

Compare, ligne par ligne, le parcours du morceau calculé par `replayer.py` à celui de libopenmpt
(ordre, ligne, speed, BPM de chaque ligne jouée). La référence est tracée en lisant la position de
libopenmpt pendant un rendu (bibliothèque installée avec `brew install libopenmpt`, appelée par
`ctypes`). Environ 25 s pour la collection.

```bash
python3 tools/check_timing.py --jobs 8               # toute la collection
python3 tools/check_timing.py "/chemin/BDTN.XM"      # un module
```

État au 30/10/2026 : 393 modules identiques sur 394 (`esfe.xm` n'est pas un module). Un ordre
pointant vers un pattern absent du fichier est retiré de la comparaison : FT2 (et `replayer.py`)
jouent 64 lignes vides, OpenMPT saute l'ordre (FRONT.XM : 46 s dans FT2).
`openmpt123 --info` n'est pas une bonne référence : sa durée inclut les ordres jamais atteints
(BAM_BAM.XM : 249,6 s annoncées pour 224,0 s réellement jouées).

## Fragments du set Live : `extract_fragments.py`

Le set est assemblé à partir des fragments de `templates/` (`../live_set.py`). À chaque nouvelle
version de Live, les régénérer depuis un set enregistré par cette version :

1. `python3 xm2live.py "/chemin/DISCOTEC.XM" --sample-offset --output /tmp/ref` (groupes et Simpler)
2. ouvrir `/tmp/ref/DISCOTEC.als` dans Live et l'enregistrer ;
3. `python3 tools/extract_fragments.py /tmp/ref/DISCOTEC.als`, puis `python3 tools/snapshot.py diff`.

Seuls les fragments présents dans le set sont remplacés (`--only` pour en choisir). Ils sont nettoyés :
ni nom, ni chemin de sample, ni note, ni automation.

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
