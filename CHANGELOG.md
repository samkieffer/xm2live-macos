# Changelog - XM2Live

Historique des versions et modifications du projet.

## [2.14.0] - 2026-10-31

Lot 4 de AUDIT.md : expression.

### Ajouté
- 🔊 **Automation du volume du Sampler** pour les changements de volume pendant les notes : `Cxx` et
  colonne volume sans note, glissements, volume haché, fondus d'entrée (226 XM sur 303 et 71 MOD sur 91
  en ont). L'automation part de 0 dB à chaque note et descend au plus à -36 dB (minimum du paramètre).
  Le mixer reste libre.
- 🎛️ **`--envelope`** (option « Enveloppes » de l'app) met désormais la **forme exacte** de l'enveloppe
  de volume FT2 dans cette automation (sustain tenu, boucles déroulées), au lieu de l'approximation ADSR.
- 🎢 **Tone portamento** (`3xx`, `5xy`, colonne volume `Fx`) : la note ne redémarre plus le sample, elle
  prolonge le son précédent qui glisse vers sa hauteur (notes en legato et glide du Sampler, durée de
  glissement typique de la piste). 75 XM concernés.
- 🧪 `tools/live_calibration.py` : set de mesure à exporter depuis Live, puis analyse (courbe
  vélocité → volume, niveaux, glide).

### Modifié
- 🎚️ **Vélocité calibrée** sur la réponse mesurée du Sampler (Vel → Vol à 100 %, 0,4 dB par pas) :
  `vélocité = 127 + 50·log10(volume/64)`. Le volume par défaut du sample passe dans la vélocité ; la
  zone porte une marge fixe (-38,8 dB) qui garde le niveau d'avant à volume plein (Vel → Vol à 100 %
  ajoute jusqu'à +22,7 dB, contre +7,9 dB à 35 % : sans cette marge, tout saturait). Avant, `2 × volume`
  à 35 % plaçait le volume 1 à -17,5 dB au lieu de -36 dB et comprimait toute la dynamique.

### Corrigé
- ✂️ **Les clips coupaient la dernière note de chaque piste** au-delà de 4 temps (fin du clip calculée
  comme « dernière note + 4 temps », héritage du plafond supprimé en v2.12). Le validateur le vérifie
  désormais, ainsi que l'ordre des points d'automation.

## [2.13.0] - 2026-10-30

Lot 3 de AUDIT.md : construction du set Ableton.

### Modifié
- 🧩 **Set assemblé à partir de fragments enregistrés par Live** (`templates/` : `liveset.xml`,
  `midi_track.xml`, `group_track.xml`, `simpler.xml`), lisibles et comparables dans git, régénérables
  avec `tools/extract_fragments.py` à chaque version de Live. `live_set.py` les copie et écrit le set
  en une fois avec gzip et lxml : **`buildable` n'est plus nécessaire**, plus de fichier temporaire
  par conversion, plus de second passage pour les automations Sample Start.
- 📁 Les **pistes de groupe** viennent d'un groupe enregistré par Live (295 éléments) au lieu des
  ~30 éléments écrits à la main.
- 🔢 **Identifiants** : seuls ceux que Live garde uniques dans le set sont renumérotés (cibles
  d'automation et de modulation, Pointee, ControllerTargets, pistes) ; les index locaux restent comme
  Live les écrit. Chaque note a un **`NoteId`** unique dans son clip (tous valaient 0).
- ⚡ Conversion plus rapide : 0,53 s au lieu de 0,77 s pour DISCOTEC.

### Corrigé
- 🎧 **Panoramique** (signalé sur DISCOTEC : les deux pistes Baxs jouaient du même côté). Le
  panoramique suit désormais l'état du canal comme dans FT2 : un numéro d'instrument le remet au défaut
  du sample, la colonne volume `Cx` (ignorée jusqu'ici, 15 900 cases dans 68 XM) et `8xx` le fixent
  jusqu'au numéro d'instrument suivant, `Dx`/`Ex` et `Pxy` le font glisser. Une piste au panoramique
  constant le reçoit sur la zone du Sampler, même sans `--pan-automation` ; une piste au panoramique
  variable reçoit une automation en escalier du mixer, zone au centre (avant : défaut du sample sur la
  zone plus 8xx sur le mixer, qui ne pouvait pas ramener à gauche un son placé à droite). Vérifié note
  par note contre libopenmpt (DISCOTEC, BDTN, MEC-pan).
- 🏷️ Les pistes gardent leur nom dans Live (« Ch10 - Ramada.wav ») : seul `EffectiveName` était
  écrit, et Live renommait la piste d'après son sample (« 10 05 Ramada »).
- 🎚️ Sur une piste Simpler, l'automation Sample Start effaçait l'automation de panoramique (8xx).
- 🗂️ `batch_convert.py` n'exige plus `template_100_tracks.als` (au-delà de 100 pistes, il échouait).
- 🧹 Le Simpler ne référence plus un fichier de ta bibliothèque de samples.

### Supprimé
- `minimal_template.py`, `create_template_200.py`, `template_100_tracks.als`, `template_200_tracks.als`,
  `simpler_template.xml` (remplacé par `templates/simpler.xml`) et le code de clonage associé.

### Vérification
- `als_validator.py` contrôle aussi les `NoteId` (uniques, sous le compteur du clip), un emplacement de
  clip par scène, et compte `ControllerTargets.N` parmi les identifiants globaux.

## [2.12.1] - 2026-10-30

### Corrigé
- ⏱️ Un ordre pointant vers un pattern absent du fichier joue 64 lignes vides, comme FT2, au lieu
  d'être sauté (comportement d'OpenMPT). Vérifié dans FT2 sur FRONT.XM : 46 s, contre 40 s avant.
  28 XM concernés, souvent en milieu de morceau : la musique qui suit était avancée.
- 🎯 `tools/check_timing.py` retire ces lignes de la comparaison, puisque OpenMPT les saute
  (393 modules sur 394 toujours identiques).

## [2.12.0] - 2026-10-28

Lot 2 de AUDIT.md : longueur des notes.

### Modifié
- 🎹 **Plus de plafond de 4 temps** : une note dure tant que le tracker la fait entendre. Elle s'arrête
  à la note suivante du canal, à la fin du sample s'il ne boucle pas (calculée avec la hauteur jouée
  et les changements de tempo), quand l'enveloppe de volume retombe à 0, ou quand le volume du canal
  tombe à 0 pour de bon. Sur la collection : 500 000 notes raccourcies (batteries à la longueur du
  sample) et 25 000 rallongées, dont 11 000 nappes en boucle qui étaient coupées à 4 temps.
- 🔉 **Glissements de volume** (`Axy`, `5xy`, `6xy`, `EAx`/`EBx`, colonne volume `6x`-`9x`) suivis au
  tick près, avec la mémoire des effets FT2 : un fondu jusqu'à 0 termine la note (90 fichiers). Un
  silence suivi d'une reprise avant la note suivante (volume haché ligne par ligne, numéro
  d'instrument seul qui remet le volume) ne coupe pas la note.
- 🔑 **Key-off et fadeout** : sans enveloppe, coupure immédiate ; avec enveloppe, la note s'arrête au
  key-off et la fin du son FT2 (fadeout, fin de l'enveloppe) devient la **release du Sampler** de
  l'instrument (103 instruments dans 38 fichiers). Avec un fadeout nul et une enveloppe qui ne
  retombe pas à 0, le key-off est ignoré, comme dans FT2 (164 key-offs).
- 🔇 Une note jouée à volume 0 puis remontée (fondu d'entrée, `C00` suivi de `Cxx`) existe désormais,
  avec la vélocité du volume le plus haut atteint (368 notes). Les notes jouées sur un sample à volume
  0 sans remontée disparaissent (654 notes, déjà muettes dans Live).

### Technique
- `xm_parser.py` lit l'enveloppe de volume et le fadeout de chaque instrument et garde les commandes
  de la colonne volume (`Cell.volume_effect`) ; `envelope_reader.py` est supprimé (`--envelope`
  utilise l'enveloppe du parser, mêmes valeurs ADSR).

## [2.11.0] - 2026-10-28

Lot 1 de AUDIT.md : moteur de lecture.

### Ajouté
- ▶️ **`replayer.py`**, commun au XM et au MOD : le morceau est parcouru comme dans le tracker au lieu
  de mettre les patterns bout à bout.
  - Déroulé : `Bxx` (saut ; un saut en arrière termine le morceau), `Dxx` (arrêt de pattern),
    `E6x` (boucle), `EEx` (délai de pattern). Un ordre pointant vers un pattern absent est sauté.
  - Tempo : chaque `Fxx` (speed ou BPM) s'applique là où il apparaît et devient une **automation de
    tempo** en escalier dans Live (BPM Live = BPM × 6 / speed).
  - Au tick près : `EDx` (note delay ; au-delà de la ligne la note n'est pas jouée), `ECx` (note cut),
    **key-off** (la note s'arrête).
- 🎯 `tools/check_timing.py` : compare le déroulé ligne par ligne (ordre, ligne, speed, BPM) à
  libopenmpt. **393 modules sur 394 identiques** (le dernier n'est pas un module).

### Corrigé
- ⏱️ Timeline : environ 50 modules étaient décalés de plus de 5 % (patterns coupés par `Dxx`, sauts,
  changements de tempo ignorés). BDTN.XM durait 66 % de trop.
- 🎵 MOD : le tempo initial ne lisait que le premier `Fxx` d'un pattern. KEEPCOOL.MOD (speed 4,
  130 BPM) sortait à 130 BPM au lieu de 195.
- 🎚️ Tempo écrit par chemins explicites dans le set au lieu de chercher la valeur « 120 ».

## [2.10.0] - 2026-10-28

Lot 0 de AUDIT.md : filet de sécurité et corrections rapides.

### Corrigé
- 🎚️ **Finetune** : il était divisé par deux (`finetune / 2.56` plafonné à ±50 cents). Calcul FT2
  (16 pas par demi-ton) avec report du demi-ton entier sur RootKey. Sur DISCOTEC.XM, `Baxs.wav` était
  48 cents trop haut et sa boucle 2,8 % trop rapide. Le finetune MOD (-8..+7) est pris en compte (×16).
- 🔁 **Boucles des samples 16 bits** : les points de boucle XM sont en octets, désormais divisés par 2
  (avant : boucles décalées, fin au-delà du sample).
- 🎹 **Notes sans numéro d'instrument** (XM et MOD) : elles rejouent le dernier instrument du canal
  au lieu d'être ignorées (SARCOPHA.XM : 61 % de notes récupérées).
- 🔊 **Effet Cxx** (Set Volume) : devient la vélocité de la note, en XM comme en MOD.
- 🔇 **Note à volume 0** : traitée comme un arrêt (silencieuse dans le tracker ; Live remonte une vélocité 0 à 1).
- ⏱️ MOD : un `Fxx` sans note ne coupe plus la note en cours du canal.
- 🎚️ MOD : `--sample-offset` détecte enfin l'effet 9xx (la détection lisait une clé inexistante).
- 🎛️ `--envelope` fonctionne de nouveau : `envelope_reader.py` avait été supprimé par erreur le 1er janvier.
- 📁 Les samples ont des noms fixes préfixés par le numéro d'instrument (`08 Baxswav.wav`) : une
  reconversion écrase au lieu d'empiler des `_1`, `_2`…
- 🔏 App Mac : la signature ad hoc échouait silencieusement (attributs Finder sur les templates).
- 💥 Plantages trouvés en convertissant toute la collection : noms de samples contenant des octets
  nuls ou des caractères de contrôle (8 XM), speed 0 dans l'en-tête (2 XM), boucles vides ou hors
  du sample (3 XM, 1 MOD), fichier qui n'est pas un XM (message clair au lieu d'un parsing aberrant).

### Ajouté
- ✅ `als_validator.py` : vérification du set à la fin de chaque conversion (IDs, automations, samples,
  boucles, accordage, notes).
- 🧪 `tools/snapshot.py` : instantanés de non-régression sur 13 modules de référence.
- 🗂️ `tools/check_collection.py` : conversion et validation de toute la collection (~390 modules).
- 🎧 `tools/render_reference.py` (rendu OpenMPT calé sur FT2) et `tools/compare_renders.py`
  (hauteur, timing et niveau, fenêtre par fenêtre).
- 🔢 Version unique dans `xm2live.py` (`__version__`, `--version`), reprise par l'app et le DMG.

Les versions 2.1 à 2.9 sont décrites dans CLAUDE.md et l'historique git.

## [2.0.0] - 2025-12-25

### Ajouté
- 🎉 **Support format MOD** (Amiga ProTracker)
  - Parser MOD complet (`mod_parser.py`)
  - Détection automatique 15 vs 31 samples
  - Support multi-canaux (4, 6, 8 canaux)
  - Conversion period → MIDI avec table de lookup
  - Samples 8-bit → 16-bit WAV
  - Support loops Forward (pas de ping-pong en MOD)
  
- 🚀 **Conversion batch** (`batch_convert.py`)
  - Recherche récursive de tous les .xm et .mod
  - Détection automatique des doublons
  - Progression en temps réel ([1/50], [2/50], etc.)
  - Statistiques finales (réussites, échecs, temps)
  - Gestion robuste des erreurs
  - Support Ctrl+C avec statistiques intermédiaires
  
- 🎵 **Calcul BPM réel**
  - Formule : `BPM réel = BPM × (6 / Speed)`
  - Détection automatique Speed et BPM depuis effets F
  - Recherche dans pattern_order (ordre de lecture réel)
  - Capture des effets F même sans notes

- 🎹 **Durées de notes intelligentes**
  - Calcul basé sur l'intervalle jusqu'à la prochaine note
  - Maximum 4 beats pour lisibilité visuelle
  - Comportement monophonique par canal
  
- 🔁 **Support loops amélioré**
  - Loops Forward (type 1)
  - Loops Ping-Pong (type 2, XM uniquement)
  - Extraction depuis headers samples
  - Application correcte dans Ableton Sampler

- 📁 **Organisation améliorée**
  - Sous-répertoire "Conversions Ableton Live/"
  - Groupes automatiques par instrument
  - Couleurs par instrument (1-69)
  - 1 voix par sampler (monophonique)

### Corrigé
- 🐛 **Octave notes MOD** : +24 semitones au lieu de +12
  - Period 428 (C-2 ProTracker) → MIDI 60 (C-4) ✅
  - Period 214 (C-3 ProTracker) → MIDI 72 (C-5) ✅
  
- 🐛 **Détection BPM** : Capture des effets F sans notes
  - Effets F peuvent exister seuls dans une cellule
  - Ajout de pattern_data même sans note si effet F présent
  
- 🐛 **RuntimeWarning overflow** : Delta-decoding samples XM
  - Utilisation d'int Python au lieu de np.int16
  - Wrapping manuel 16-bit pour éviter le warning
  
- 🐛 **NumVoices** : Passage de 6 à 1 voix
  - Élément correct : `NumVoices` (pas `Voices`)
  - Indexé depuis 0 : NumVoices="0" = 1 voix

### Modifié
- 📝 Détection format automatique (.xm vs .mod)
- 📝 Messages d'usage mis à jour
- 📝 Support des deux formats dans un seul script

## [1.5.0] - Phase 2 (XM uniquement)

### Ajouté
- 🔁 Support loops (Forward, Ping-Pong)
- 📁 Sous-répertoire "Conversions Ableton Live"
- 🔊 Configuration voix monophoniques (1 voix)
- ⏱️ Durées de notes basées sur intervalles

### Corrigé
- 🐛 IndexError dans création de groupes
- 🐛 Script se bloquant indéfiniment
- 🐛 BPM toujours à 120 au lieu de la valeur XM

## [1.0.0] - Phase 1 (XM uniquement)

### Ajouté
- 🎹 Conversion basique XM → Ableton
- 🎚️ Extraction samples en WAV
- 🎵 Extraction notes MIDI
- 🎨 Couleurs par instrument
- 📁 Groupes par instrument
- ⏱️ Application BPM
- 🎼 Transposition (relative_note)

### Format du fichier
- Type: Fichiers Markdown (.md)
- Encoding: UTF-8
- Nouveau: Ajout au début du fichier
- Format: [Version] - Date

---

**Convention de versionnage :**
- Version Majeure : Nouveaux formats supportés
- Version Mineure : Nouvelles fonctionnalités
- Version Patch : Corrections de bugs

**Légende des emojis :**
- 🎉 Fonctionnalité majeure
- ✨ Nouvelle fonctionnalité
- 🐛 Correction de bug
- 📝 Documentation
- 🔧 Maintenance
- ⚡ Performance
- 🔒 Sécurité
