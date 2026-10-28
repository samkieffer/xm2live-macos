# Changelog - XM2Live

Historique des versions et modifications du projet.

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
