# Changelog - XM2Live

Historique des versions et modifications du projet.

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
