# Log des Modifications - XM2Live V2

## Session du 27 Décembre 2025

### Version v2.0.0 - Initialisation
**Date:** 27/12/2025 13:20

**Changements:**
- Création d'une copie du projet xm2live fonctionnel dans xm2live_v2
- Préservation de la version stable originale dans /Users/sam/xm2live
- Template copié dans le répertoire du projet : template_100_tracks.als (723KB)
- Fichier de test prioritaire : MEC3.XM (823KB)

**Fichiers du projet:**
- xm2live.py (36KB) - Script principal de conversion
- xm_parser.py (15.5KB) - Parser pour fichiers XM
- mod_parser.py (16.2KB) - Parser pour fichiers MOD
- batch_convert.py (9.5KB) - Conversion en batch
- template_100_tracks.als (723KB) - Template Ableton Live

**État:** ✅ Version stable de référence

---

## Version v2.1.0 - Support du Volume des Samples
**Date:** 27/12/2025 14:11

**Objectif:** Implémenter le support du volume par défaut des samples (valeur 0-64 dans les fichiers XM).

**Analyse effectuée:**
1. **Fichier exemple analysé:** `/Users/sam/xm2live_v2/pan + vol examples Project/pan + vol examples.als`
   - Piste 1: Volume 0dB (1.0), Pan full left (-1)
   - Piste 2: Volume 0dB (1.0), Pan full right (+1)
   - Piste 3: Volume -3dB (0.7060804963), Pan center (0)

2. **Encodage Ableton découvert:**
   - Élément XML: `MultiSamplePart > Volume`
   - Plage: 0.0 à 1.0 (linéaire)
   - 1.0 = 0 dB (volume par défaut)
   - Formule: dB = 20 * log10(value)

3. **Encodage XM:**
   - Plage: 0 à 64 (64 = 100%)
   - Conversion: `ableton_volume = xm_volume / 64.0`

**Modifications du code:**

1. **xm2live.py** (ligne 11):
   - Ajout: `import math` pour le calcul des dB

2. **xm2live.py** (lignes 193-210):
   - Nouvelle fonctionnalité: Lecture du volume depuis `sample_info['volume']`
   - Conversion XM → Ableton: `ableton_volume = xm_volume / 64.0`
   - Mise à jour de l'élément `MultiSamplePart > Volume`
   - Affichage des valeurs en dB quand différent du maximum

**Tests effectués:**
- Fichier de test: MEC3.XM (823 KB)
- Résultat: ✅ Sample avec volume 41/64 correctement converti en 0.641 (-3.9 dB)
- Validation: Fichier .als valide et s'ouvre correctement

**Backup créé:**
- `backups/v2.1.0_volume_support_20251227_141135.tar.gz` (503 KB)

**État:** ✅ Version stable - Volume de base fonctionnel

---

## Version v2.2.0 - Automations de Volume par Note
**Date:** 27/12/2025 16:44

**Objectif:** Implémenter les automations de volume au niveau de la piste basées sur la colonne Volume des notes FastTracker (0-64).

**Analyse effectuée:**
1. **Fichier exemple analysé:** `/Users/sam/xm2live_v2/pan + vol examples Project/pan + vol examples.als`
   - Piste 5: Automation de volume (track-level) de -∞ à +6 dB
   - Structure: `Track > AutomationEnvelopes > AutomationEnvelope`
   - Points: `Time` en beats, `Value` 0.0-1.0+
   - PointeeId: Référence à `Mixer > Volume > AutomationTarget > Id`

2. **Encodage découvert:**
   - Temps: Directement en beats (Time=8.0 = 8 beats)
   - PointeeId: Doit correspondre à l'Id de l'AutomationTarget
   - Events: FloatEvent avec Time et Value

3. **Modification des parsers:**
   - Volume par note déjà extrait dans xm_parser.py et mod_parser.py
   - Ajout de `'volume_xm'` dans la structure des notes pour conserver le volume original (0-64)

**Modifications du code:**

1. **xm_parser.py** (lignes 357, 386):
   - Ajout de `'volume_xm': note_event['volume']` dans notes_by_channel
   - Passage du volume XM à la structure finale des tracks

2. **mod_parser.py** (lignes 392, 417):
   - Même modification que xm_parser.py pour garder la cohérence

3. **xm2live.py** (lignes 347-420):
   - **Nouvelle fonction:** `create_volume_automation(track, notes, next_id)`
   - Vérifie s'il y a des variations de volume (optimisation)
   - Crée AutomationEnvelope pointant vers le Volume du Mixer
   - Génère des points d'automation (FloatEvent) pour chaque note
   - Conversion: `ableton_volume = volume_xm / 64.0`

4. **xm2live.py** (lignes 562-564, 582):
   - Initialisation de `global_next_id = 100000` avant la boucle de création des pistes
   - Appel de `create_volume_automation()` pour chaque piste créée
   - Suppression de l'ancienne initialisation redondante (ligne 629-631)

**Tests effectués:**
- Fichier de test: MEC3.XM (823 KB)
- Résultat: ✅ Conversion réussie sans automations (toutes les notes ont le même volume)
- Validation: Fichier .als valide, NextPointeeId=100006
- **Note:** MEC3.XM n'utilise pas de variations de volume par note (cas courant)

**Comportement:**
- Si toutes les notes ont le même volume → Pas d'automation créée (optimisation)
- Si des variations existent → Automation créée avec un point par note
- Affichage: "→ Automation volume: X points" dans les logs

**Backup créé:**
- `backups/v2.2.0_volume_automation_20251227_164437.tar.gz` (504 KB)

**État:** ✅ Version stable - Automations de volume implémentées

**Note pour tests futurs:** Pour valider visuellement les automations, il faudrait un fichier XM utilisant activement la colonne Volume avec des variations.

---

## Version v2.2.0 - Support du Volume par Note via Velocity
**Date:** 27/12/2025 18:00

**Objectif:** Implémenter le support des variations de volume par note (colonne Volume FastTracker) via la velocity MIDI et le paramètre Vol-Vel d'Ableton.

**Découverte importante:**
- Les parsers xm_parser.py et mod_parser.py convertissent déjà le volume XM (0-64) en velocity MIDI (0-127)
- Pour que la velocity affecte le volume dans Ableton, il suffit de configurer le paramètre **Vol-Vel** du Sampler
- Cette approche est beaucoup plus simple et performante que les automations de piste

**Analyse effectuée:**
1. Test avec fichier XM contenant des variations de volume
2. Découverte que la velocity MIDI est déjà présente dans les clips
3. Recherche web confirmant que **35% est la valeur par défaut d'Ableton** pour Vol-Vel
4. Problème de saturation identifié : combinaison velocity + Vol-Vel 35% dépassait 0 dB
5. Solution : réduction du volume du sample de -12 dB (standard Ableton)

**Modifications du code:**

**xm2live.py** (lignes 212-217):
- Ajout de la configuration `VolumeVelScale` (Vol-Vel) à 35%
- Élément XML: `VolumeAndPan/VolumeVelScale/Manual`
- Valeur: 0.35 (35% - valeur par défaut Ableton)

**xm2live.py** (lignes 196-202):
- Réduction du volume du sample : multiplication par 0.25 (-12 dB)
- Formule: `ableton_volume = (xm_volume / 64.0) * 0.25`
- Conforme aux standards Ableton pour éviter le clipping

**Tests effectués:**
- Fichier de test: MEC.XM (avec variations de volume)
- Résultat: ✅ Volumes correctement reproduits, pas de saturation
- Validation: Son équilibré avec headroom suffisant

**Avantages de cette approche:**
- Pas d'automations volumineuses à générer
- Fichiers .als plus légers
- Performance optimale dans Ableton
- Respect des standards de mixing (-12 dB headroom)

**Backup créé:**
- `backups/v2.2.0_velocity_volume_20251227_180000.tar.gz`

**État:** ✅ Version stable - Volume par note fonctionnel

---

## Version v2.3.0 - Support du Panning (Sampler + Automations)
**Date:** 27/12/2025 19:30

**Objectif:** Implémenter le support complet du panning : panning par défaut du sample ET automations pour l'effet 8xx (FastTracker).

**Analyse effectuée:**
1. Étude du fichier exemple `pan + vol examples.als`
2. Découverte de la structure d'automation : `Mixer > Pan > AutomationTarget` (pas "Panorama" !)
3. Identification du besoin de créer des "plateaux" (2 points par note)
4. Gestion du retour au panning par défaut (comportement FastTracker)

**Modifications du code:**

**xm_parser.py** (lignes 245, 303):
- Ajout du champ `'panning'` dans le dictionnaire sample_headers
- Stockage du panning par défaut (0-255) du sample XM

**xm_parser.py** (lignes 352-356, 393):
- Détection de l'effet 8xx (Set Panning)
- Extraction du paramètre panning (0-255)
- Stockage dans `'panning_xm'` pour chaque note avec effet 8xx

**xm2live.py** (lignes 220-237):
- Ajout du mapping panning du sample vers `MultiSamplePart > Panorama`
- Conversion: `ableton_pan = (xm_panning - 128) / 128.0`
- Affichage si différent du centre

**xm2live.py** (lignes 374-510):
- **Nouvelle fonction:** `create_pan_automation(track, notes, sample_default_pan, next_id)`
- Point initial à temps 0 avec le panning par défaut du sample
- Pour chaque note avec effet 8xx : **2 points** (début + fin) = plateau
- Retour au panning par défaut si note sans effet après une note avec effet
- Inclut `AutomationTransformViewState` (leçon apprise du crash volume)

**xm2live.py** (lignes 512-520, 1007-1028):
- Ajout du paramètre `enable_pan_automation` (défaut: False)
- Argument CLI `--pan-automation` pour activer les automations
- Documentation dans l'aide : "Par défaut désactivé car rare dans les modules"

**batch_convert.py** (lignes 56, 160-161, 275-279):
- Ajout du support `--pan-automation` pour la conversion en batch
- Transmission du paramètre à `convert_xm_to_ableton()`

**Tests effectués:**
- Fichier de test: MEC-pan.xm (créé avec effets 8xx pour validation)
- Sans `--pan-automation`: ✅ Panning statique uniquement (-0.12 gauche)
- Avec `--pan-automation`: ✅ 9 points d'automation créés
- Validation Ableton: ✅ Plateaux corrects, retour au défaut, pas de crash

**Comportement:**
- **Par défaut (sans --pan-automation):** Seul le panning statique du sample est appliqué
- **Avec --pan-automation:** Automations complètes avec:
  - Point initial au temps 0 (panning par défaut du sample)
  - 2 points par note avec effet 8xx (plateau)
  - Retour au panning par défaut si note sans effet 8xx

**Formules de conversion:**
- Panning sample: `ableton_pan = (xm_pan - 128) / 128.0` (-1.0 à +1.0)
- Effet 8xx: même formule, appliquée dans l'automation

**Backup créé:**
- `backups/v2.3.0_panning_support_20251227_193000.tar.gz`

**État:** ✅ Version stable - Panning complet (méga chanmax !)

---

## Prochaines modifications

*(Les nouvelles modifications seront ajoutées ici)*

