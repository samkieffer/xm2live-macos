# XM2Live — État des lieux (28 octobre 2026)

Audit du convertisseur (Python) et de l'app Mac, avec des mesures faites sur ta collection
(`/Users/sam/Music/Compo/All Compo/Modules`, sans `doubles/` ni `Copie de DIVERS/`) :
**~300 XM et 91 MOD**. Les chiffres se reproduisent avec les scripts de [`tools/audit/`](tools/audit/).

## Résumé

1. **La vitesse n'est pas le problème.** Une conversion de DISCOTEC prend 0,8 s. L'effort doit
   porter sur la fidélité musicale et sur la robustesse du fichier Ableton.
2. **Le principal défaut est le modèle de temps.** Aujourd'hui, une ligne = 1/4 de temps, le
   tempo est fixe et les patterns sont mis bout à bout. Le convertisseur ne connaît ni les ticks ni
   le déroulé réel de la lecture (sauts, arrêts de pattern, changements de tempo). C'est pour ça
   que `EDx` n'a pas abouti la dernière fois : le niveau de détail nécessaire n'existe pas. Un petit
   « moteur de lecture » qui parcourt le morceau comme le fait le tracker règle d'un coup `EDx`,
   `ECx`, `Dxx`/`Bxx`, les changements de tempo, le key-off et les notes sans instrument.
3. **Les problèmes mesurés les plus graves :** notes perdues dans 14 XM (jusqu'à 61 % des notes),
   timeline décalée de plus de 5 % dans ~50 fichiers, volumes `Cxx` ignorés dans 88 % des MOD,
   enveloppes de volume (62 % des XM) non converties, option `--envelope` cassée depuis janvier.
4. **Le template fonctionne mais il est fragile :** clonage avec renumérotation aveugle des ID,
   tempo réglé en cherchant la valeur « 120 », piste de groupe écrite à la main.
5. **Il manque un filet de sécurité automatique.** `openmpt123` est déjà installé : il peut produire
   la version de référence d'un module sans passer par FT2 à la main.

## 1. Constats mesurés

| # | Problème | Fichiers touchés | Effet à l'écoute | Effort |
|---|---|---|---|---|
| 1 | Notes sans numéro d'instrument ignorées (le tracker rejoue le dernier instrument du canal) | 14 XM (15 920 notes), 2 MOD | **Notes manquantes** : SARCOPHA, LEP 61 %, CRYSTALH, CRYSTAL 56 %, DEMO3 53 % | Faible |
| 2 | Déroulé de lecture ignoré : `Dxx` (arrêt de pattern), `Bxx` (saut) | 43 XM, 16 MOD | Lignes jamais jouées dans le tracker mais présentes dans Live ; décalage de la structure | Moyen |
| 3 | Changements de tempo en cours de morceau (`Fxx`) ignorés | 78 XM, 63 MOD (dont des réglages redondants) | Avec le n° 2 : timeline décalée de plus de 5 % dans 26 XM et 25 MOD, de plus de 20 % dans 10 XM et 8 MOD | Moyen |
| 4 | `EDx` (note delay) ignoré | 92 XM (31 %), 10 281 occurrences | Groove, flam, effets de doublure (comme sur DISCOTEC) | Faible une fois le n° 2 fait |
| 5 | Volume `Cxx` ignoré (vélocité fixe à 64 en MOD) | 84 XM (28 %), **80 MOD (88 %)** | Pas de dynamique dans les MOD | Faible |
| 6 | Enveloppes de volume non converties | 188 XM (62 %) | Les sons « pluck » ou à decay tiennent au lieu de s'éteindre | Moyen |
| 7 | `--envelope` ne fait rien : `envelope_reader.py` supprimé par erreur dans le commit `277dee8` (1er janvier), alors que l'app propose l'option | — | Option sans effet | Faible (récupérable dans git) |
| 8 | Notes coupées à 4 temps | 277 fichiers sur 299 ; 2,2 % des notes, dont 10 618 nappes en boucle | Nappes et sons longs coupés | Faible |
| 9 | Key-off (note 97) ignoré | 61 XM, 1 878 notes | La note tient jusqu'à la note suivante | Faible une fois le n° 2 fait |
| 10 | Tone portamento (`3xx`, `5xx`, colonne `Fx`) rejoué comme une nouvelle note | 76 XM (11 067 notes), 22 MOD | Ré-attaque au lieu d'un glissé | Moyen (à valider dans Live) |
| 11 | Glissements de volume (`Axx`, colonne volume) ignorés | 95 XM (32 %), 44 MOD (48 %) | Fade-ins et fade-outs absents | Moyen |
| 12 | ✅ (30/10, v2.13.0) Panoramique de la colonne volume (`Cx`) absent des automations | 68 XM (23 %) | Placement stéréo partiel | Faible |
| 13 | Instruments multi-samples (seul le dernier sample est gardé) | **1 seul fichier** | — | Pas prioritaire |

**Corrigé aujourd'hui :** finetune (76 % des XM, 46 % des MOD ; dont 102 XM au-delà de ±50 cents)
et boucles 16 bits (42 % des XM).

**Ne pose pas de problème :** les XM en table de fréquences Amiga (37 %) ont la même hauteur de note
que la table linéaire, seuls les portamentos diffèrent. Le C-2 MOD à 8363 Hz suit la convention FT2 et
OpenMPT : c'est le bon choix, puisque tes références sont des rendus FT2.

## 2. EDx et le modèle de temps

**Aujourd'hui** (`organize_tracks_by_channel`, en double dans `xm_parser.py` et `mod_parser.py`) :
`temps = cumul des patterns / 4 + ligne / 4`. La vitesse (ticks par ligne) n'est connue nulle part
à ce stade. On ne peut donc pas placer un événement à « ligne + 2 ticks », ni suivre un saut.

**Proposition : un module `replayer.py` partagé par XM et MOD**, qui :
- parcourt `pattern_order` comme le tracker : `Dxx` passe au pattern suivant à la ligne indiquée,
  `Bxx` saute, `E6x` fait une boucle, `EEx` retarde le pattern, et la fin du morceau est détectée
  quand un saut revient en arrière ;
- garde l'état de chaque canal : dernier instrument, note en cours, volume, panoramique ;
- garde l'état global : vitesse et BPM, modifiés par `Fxx` au moment où ils apparaissent ;
- produit une liste d'événements datés en temps : `note_on`, `note_off`, `volume`, `pan`, `tempo`.

Conversion du temps : on garde la grille 4 lignes = 1 temps et
`temps = lignes / 4 + tick / (vitesse × 4)`. Le tempo devient une **automation de tempo** sur la piste
Master (`BPM × 6 / vitesse`) à chaque changement. Les mesures restent donc alignées sur les patterns.

Avec ce socle, chaque effet tient en quelques lignes :
- `EDx` : la note est décalée de x ticks ; si x ≥ vitesse, la note n'est pas jouée (comportement FT2) ;
- `ECx` : `note_off` au tick x ;
- key-off : `note_off` (immédiat sans enveloppe, release avec enveloppe, voir §3) ;
- note sans instrument : utilise l'état du canal ;
- `Cxx` : vélocité de la note, ou `note_off` si 00.

Ce module remplace les deux `organize_tracks_by_channel` dupliqués. Le code qui écrit le fichier
Ableton ne change presque pas, puisqu'il reçoit toujours des notes avec temps, durée et vélocité.

## 3. Longueur des notes

**Aujourd'hui :** `durée = min(écart jusqu'à la note suivante ou au volume 00, 4 temps)`.

**Quand FT2 arrête-t-il réellement un son ?**
- à la note suivante sur le canal, sauf tone portamento ;
- au key-off : coupure immédiate sans enveloppe ; avec enveloppe, l'enveloppe se poursuit et le
  fadeout s'applique, soit environ 32768 / fadeout ticks ;
- à `ECx`, ou quand le volume passe à 0 ;
- à la fin du sample s'il ne boucle pas ;
- à la fin de l'enveloppe si son dernier point est à 0 (sons percussifs sans sustain).

**Mesuré sur les XM :**
- le plafond de 4 temps coupe un son encore audible dans **2,2 % des notes, mais dans 277 fichiers
  sur 299**. Ce sont surtout des nappes en boucle, donc des notes peu nombreuses mais très audibles ;
- **19 % des notes MIDI** durent plus longtemps que le sample lui-même : un coup de caisse claire
  apparaît comme une note de 4 temps. C'est le défaut de lisibilité que le plafond essayait de limiter.

**Proposition :**
`durée = min(événement suivant, key-off (+ release), cut, fin naturelle du sample, fin de l'enveloppe)`,
**sans plafond arbitraire**. La fin naturelle d'un sample sans boucle se calcule exactement :
`frames / (8363 × 2^((note + relative_note − 49)/12 + cents/1200))` secondes.
On gagne sur les deux plans : les batteries deviennent des notes courtes (lisibles) et les nappes durent
aussi longtemps qu'elles sonnent (fidèles). On peut garder le plafond en option pour l'affichage.

**Enveloppes (n° 6 et 7) :** récupérer `envelope_reader.py` depuis git (`git show 277dee8^:envelope_reader.py`),
puis procéder en deux temps :
- (a) pour les enveloppes **sans sustain** qui tombent à 0 (plucks, percussions), raccourcir la note et
  approximer le decay dans l'ADSR du Sampler. C'est mesurable et fiable ;
- (b) pour les autres, garder l'approximation ADSR déjà présente (`configure_envelope_adsr`).

**Tone portamento (n° 10)** : piste à tester dans Live. Ne pas ré-attaquer, faire chevaucher les notes
(legato) et régler le Sampler en mono avec Glide en mode Portamento. Je ne l'ai pas vérifié dans Live.

## 4. Template Ableton

**Comment c'est construit aujourd'hui :**
- Base : un set d'une piste (Sampler avec un sample) enregistré par **Live 12.3.2**, embarqué en
  base64 gzip dans `minimal_template.py`. C'est illisible et impossible à comparer dans git.
- La piste est clonée N fois et **tous** les attributs `Id` sont renumérotés, y compris les index
  locaux (`ClipSlot`, `KeyTrack`, `ControllerTargets.N`…). Live le tolère, mais ce n'est pas son format.
- Le `MultiSamplePart` vient de la première piste ; Simpler vient de `simpler_template.xml` ;
  la **piste de groupe est écrite à la main** avec environ 25 éléments, alors qu'un vrai groupe en
  contient bien plus. C'est le point le plus exposé à une future version de Live.
- Le tempo est réglé en remplaçant tout `Manual` ou `FloatEvent` dont la valeur vaut `"120"`. Ça marche
  parce que seul le tempo vaut 120 dans le template actuel, pas par construction.
- `buildable` ne sert qu'à charger, enregistrer et lister les pistes. Il impose en plus de rouvrir le
  fichier après coup pour ajouter les automations Sample Start (« buildable ne persiste pas… »).
- Toutes les notes ont `NoteId="0"`, alors que Live 11+ attend un identifiant unique par clip.
- Restes inutilisés : `get_or_create_template`, `create_template_with_n_tracks`, `update_all_ids`,
  `create_template_200.py`, `template_100_tracks.als` et `template_200_tracks.als` (2 Mo embarqués
  dans l'app pour rien), et le dossier `template_200_tracks Project/` suivi par git.
- Chaque conversion laisse un `.als` temporaire dans `/var/folders/…/T` (14 fichiers, 5 Mo aujourd'hui).

**Une méthode plus solide : fragments, puis assemblage, puis validation**
1. **Un set de référence enregistré par Live** (`templates/reference.als`) contenant une piste MIDI
   avec Sampler et sample, une piste avec Simpler, un groupe avec une piste, et une automation.
   Un script `tools/extract_fragments.py` en extrait des **fragments XML lisibles** :
   `liveset.xml`, `midi_track.xml`, `group_track.xml`, `simpler.xml`. Ils sont comparables dans git et
   **régénérables en une commande** à chaque nouvelle version de Live. Plus aucun XML écrit à la main.
2. **Un seul allocateur d'ID** qui ne renumérote que ce qui doit être unique dans tout le set
   (`AutomationTarget`, cibles de modulation, `Pointee`, `Id` des pistes) et laisse les index
   locaux tels quels. Le set de référence servira à confirmer cette liste. `NextPointeeId` = max + 1.
3. **Des chemins explicites** au lieu de chercher des valeurs : tempo via `MasterTrack/…/Tempo/Manual`,
   et automation de tempo pour les `Fxx`.
4. **Supprimer `buildable`** : `gzip` et `lxml` suffisent, et le second passage sur le fichier disparaît.
5. **Un validateur lancé à la fin de chaque conversion** (c'est la vérification faite aujourd'hui) :
   ID globaux uniques, chaque `PointeeId` pointe vers une cible existante, `NextPointeeId` supérieur au
   plus grand ID, samples présents, boucles dans les limites du sample, Detune entre −50 et +50,
   RootKey entre 0 et 127, `NoteId` uniques.

**Idée pour plus tard, côté retravail :** ✅ (v2.15.0, un clip par suite de patterns) un clip par
pattern (nommé « Pattern 0C ») plutôt qu'un seul clip par piste, et éventuellement les scènes de la vue Session dans l'ordre des patterns. La structure
du morceau d'origine resterait visible dans Live.

## 5. Vérification automatique (filet de sécurité)

- **Rendu de référence automatique :** `openmpt123 --render module.xm` est installé. OpenMPT reproduit
  très fidèlement FT2, ce qui évite les exports manuels.
- **Comparaison de rendus** (méthode d'aujourd'hui) dans `tools/compare_renders.py ref.wav live.wav` :
  écart de hauteur en cents et décalage temporel par section.
- **Instantanés de non-régression :** `tools/snapshot.py` produit un résumé JSON par module (pistes,
  notes, RootKey, Detune, boucles, tempo) pour une dizaine de modules de référence, à comparer avant
  et après chaque modification. C'est la comparaison ancien/nouveau faite aujourd'hui.
- **Plus tard :** un petit moteur de rendu du `.als` (simulation du Sampler, validée aujourd'hui sur
  l'intro de DISCOTEC), à comparer au rendu OpenMPT sans ouvrir Live.

## 6. App Mac, dépôt et documentation

- **Option « Enveloppe »** dans l'app : sans effet (voir n° 7). À corriger ou à masquer.
- **Sample Offset activé par défaut dans l'app :** les instruments qui utilisent `9xx` passent sur Simpler,
  qui perd le ping-pong et le multi-sample. À garder si c'est un choix délibéré.
- **Dépendances Python :** l'app utilise le `python3` du système, qui doit avoir numpy, lxml et buildable,
  et rien n'est vérifié avant de lancer. Ajouter un contrôle avec un message clair. Sans buildable
  (§4), il ne reste que lxml et numpy, et numpy pourrait être remplacé.
- **Le dossier `Samples/` s'accumule à chaque reconversion** : 90 fichiers pour 24 samples dans
  DISCOTEC. Repartir d'un dossier propre et utiliser des noms fixes préfixés par le numéro
  d'instrument (`08 Baxs.wav`). Cela distinguerait aussi les cinq « NTX PATCH ».
- **Versions incohérentes :** CLAUDE.md dit 2.5.0, la bannière CLI v2.9.0, le DMG 2.6.0,
  Info.plist 1.0, et CHANGELOG s'arrête à 2.0.0. Il faudrait une seule source de version.
- **Git :** `__pycache__/*.pyc` et `.DS_Store` sont suivis malgré le `.gitignore`.
  **`Controls.swift` et `make_dmg.sh` ne sont pas commités**, tout comme les modifications de l'app
  2.6.0 : risque de perte.
- **Documentation :** CLAUDE.md renvoie à `MODIFICATIONS_LOG.md` et `RESUME_SESSION.md`, qui n'existent
  pas, et la section « Known Limitations » ne reflète plus l'état du code.
- **Structure du code :** `xm2live.py` fait 2 544 lignes, dont 650 pour `convert_xm_to_ableton`, et les
  chemins Sampler et Simpler sont presque en double (~250 lignes chacun). À découper au fil des lots
  (`replayer.py`, `ableton_writer.py`, `templates/`), pas dans une réécriture à part.
- **Performance :** 0,83 s et 130 Mo pour DISCOTEC (2,6 Mo, 57 pistes), dont 30 % de compression gzip
  et 25 % de décodage des samples. Un décodage delta vectorisé (`cumsum` + masque 16 bits, résultat
  exact) gagnerait ~0,15 s par fichier, soit environ une minute sur toute la collection. Ce n'est pas
  une priorité.

## 7. Feuille de route proposée

| Lot | Contenu | Pourquoi dans cet ordre |
|---|---|---|
| **0. Filet de sécurité et corrections rapides** ✅ fait le 28/10/2026 (v2.10.0) | snapshot + validateur + rendu OpenMPT ; notes sans instrument (n° 1) ; `Cxx` en vélocité (n° 5) ; dossier `Samples/` ; restaurer `envelope_reader.py` ; hygiène git, versions, docs | Chaque changement suivant sera mesuré. Gros gain pour peu d'effort |
| **1. Moteur de lecture** ✅ fait le 28/10/2026 (v2.11.0, vérifié ligne par ligne contre libopenmpt : 393/394) | `replayer.py` : `Dxx`/`Bxx`/`E6x`/`EEx`, `Fxx` en automation de tempo, `EDx`, `ECx`, key-off, état des canaux | Socle commun à `EDx` et à la longueur des notes |
| **2. Longueur des notes** ✅ fait le 28/10/2026 (v2.12.0) | fin naturelle du sample, suppression du plafond de 4 temps (ou option), key-off et fadeout, enveloppes sans sustain | A besoin du temps au tick et des key-off du lot 1 |
| **3. Template** ✅ fait le 30/10/2026 (v2.13.0) | fragments extraits d'un set Live, allocateur d'ID, suppression de buildable, `NoteId`, nettoyage des fichiers temporaires | Indépendant ; peut passer avant le lot 1 si tu préfères |
| **4. Expression** ✅ fait le 31/10/2026 (v2.14.0) | glissements de volume et panoramique de la colonne volume en automations, tone portamento en glide (à tester dans Live), calibrage de la courbe vélocité → volume (mesure dans Live) | Le plus subjectif ; à faire une fois la base fiable |

Pistes pour plus tard : un clip par pattern et scènes en Session ; instruments multi-samples (un seul fichier concerné).

## Méthode et limites

- Scan octet par octet de chaque module (cellules, en-têtes d'instruments et de samples) dans l'ordre
  de lecture. Scripts : `tools/audit/collection_scan.py`, `timing_scan.py` et `length_scan.py`
  (`python3 -I <script> <dossier>`).
- La simulation du déroulé de lecture est approximative : `E6x` est ignoré et un saut en arrière est
  traité comme la fin du morceau. Les pourcentages donnent un ordre de grandeur.
- Le calcul des durées ignore les enveloppes et les changements de tempo, et utilise le premier sample
  de chaque instrument.
- Profilage : `cProfile` sur une conversion complète de DISCOTEC avec `--pan-automation`.
