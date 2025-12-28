# Guide de reprise de session - XM2Live

**Pour Claude (ou un autre assistant IA) : Ce fichier contient le contexte complet du projet.**

## Contexte du projet

### Objectif
Convertir des fichiers tracker des années 90 (FastTracker 2 XM, Amiga ProTracker MOD) vers Ableton Live pour pouvoir retravailler cette musique avec des outils modernes.

### Historique personnel
- Musique créée il y a ~30 ans avec FastTracker 2
- Objectif : Retravailler ces morceaux dans Ableton Live
- Besoin de préserver : samples, notes, tempo, loops

## État actuel du projet

**Version** : 2.0 (complète et fonctionnelle)  
**Date** : Décembre 2025  
**Statut** : ✅ Production-ready

### Fonctionnalités implémentées
- ✅ Support XM (FastTracker 2)
- ✅ Support MOD (ProTracker)
- ✅ Conversion batch
- ✅ Calcul BPM réel (Speed/BPM)
- ✅ Loops (Forward + Ping-Pong)
- ✅ Notes MIDI avec durées intelligentes
- ✅ 1 voix par sampler (monophonique)
- ✅ Organisation automatique (groupes, couleurs)

### Tests validés
- ✅ mec3.xm (loops ping-pong)
- ✅ 242.mod (Speed=3, BPM=250)
- ✅ BANG.MOD (BPM=160 détecté)
- ✅ CHURCH22.MOD (format 31 samples)
- ✅ Répertoire "divers" (21 fichiers batch)

## Problèmes résolus (NE PAS réintroduire)

### 1. Octave notes MOD
❌ **Erreur** : +12 semitones  
✅ **Correct** : +24 semitones  
**Raison** : Convention ProTracker vs MIDI

### 2. Détection BPM
❌ **Erreur** : Ignorer effets F sans notes  
✅ **Correct** : Capturer effets F seuls  
**Raison** : Effet F peut être seul dans une cellule

### 3. RuntimeWarning overflow
❌ **Erreur** : `np.int16(current + data[k])`  
✅ **Correct** : int Python + wrapping manuel  
**Raison** : Delta-decoding intentionnel

### 4. NumVoices Ableton
❌ **Erreur** : Chercher "Voices" ou "Filter/Global/Voices"  
✅ **Correct** : Élément `NumVoices` directement dans MultiSampler  
**Indexation** : 0=1 voix, 5=6 voix

### 5. Calcul BPM réel
✅ **Formule** : `BPM_réel = BPM × (6 / Speed)`  
**Exemples** :
- Speed=6, BPM=125 → 125.00 BPM
- Speed=3, BPM=125 → 250.00 BPM

## Structure du code

### Fichiers principaux
1. **xm2live.py** - Orchestration principale
   - Détection format (.xm vs .mod)
   - Chargement template Ableton
   - Population des pistes
   - Application BPM réel

2. **xm_parser.py** - Parser XM
   - Little-endian
   - Delta-decoding samples
   - Patterns packed/unpacked
   - Loops type 1/2

3. **mod_parser.py** - Parser MOD
   - Big-endian
   - Conversion period → MIDI
   - Détection effets F
   - Samples 8-bit → 16-bit

4. **batch_convert.py** - Conversion batch
   - Recherche récursive
   - Statistiques
   - Gestion erreurs

### Points d'entrée
```python
# xm_parser.py
extract_samples_and_patterns(xm_path, samples_dir)
  → (samples, patterns, xm_info)

# mod_parser.py  
extract_samples_and_patterns(mod_path, samples_dir)
  → (samples, patterns, mod_info)

# xm2live.py
convert_xm_to_ableton(file_path, template_path)
  → True/False
```

### Structures de données clés

**samples** :
```python
[{
    'instrument': 1,
    'sample': 1,
    'name': 'Kick',
    'path': '/path/to/sample.wav',
    'relative_note': 0,
    'loop_start': 0,
    'loop_length': 44100,
    'loop_type': 1,  # 0=none, 1=forward, 2=ping-pong
    'volume': 64
}]
```

**mod_info / xm_info** :
```python
{
    'name': 'module_name',
    'channels': 4,
    'tempo': 6,      # Speed (ticks/row)
    'bpm': 125,      # BPM XM/MOD
    'pattern_order': [0, 1, 2, ...],
    'song_length': 10
}
```

## Dépendances critiques

```python
buildable>=0.2.0  # Manipulation .als
numpy>=1.20.0     # Traitement samples
lxml>=4.6.0       # Parser XML
```

## Template Ableton requis

**Emplacement** :
- `/Users/sam/xm2live/template_100_tracks.als`
- OU `/Users/sam/Music/Compo/All Compo/Modules/template_100_tracks.als`

**Contenu** :
- 100 pistes MIDI avec Sampler
- 1ère piste doit avoir un sample (modèle MultiSamplePart)

## Commandes de test rapide

```bash
# Test simple
python3 xm2live.py "/Users/sam/Music/Compo/All Compo/Modules/mec3.xm"

# Test MOD
python3 xm2live.py "/Users/sam/Music/Compo/All Compo/Modules/BANG.MOD"

# Test batch
python3 batch_convert.py "/Users/sam/Music/Compo/All Compo/Modules/divers" --no-recursive
```

## Philosophie du projet

### Préserver l'authenticité
- ❌ Ne pas ajouter d'effets modernes
- ✅ Conversion fidèle notes + samples
- ✅ Préserver tempo et loops
- ✅ Comportement monophonique tracker

### Simplicité
- ❌ Pas de GUI (CLI suffit)
- ✅ Scripts autonomes
- ✅ Dépendances minimales
- ✅ Sorties prévisibles

### Utilisabilité
- ✅ Projets prêts à ouvrir dans Ableton
- ✅ Organisation automatique
- ✅ Noms de fichiers propres
- ✅ Documentation complète

## Limitations acceptées

- ❌ Effets tracker non convertis (OK : trop complexe)
- ❌ Enveloppes de volume (OK : trop complexe)
- ❌ Panning (OK : peut être ajouté manuellement)
- ❌ Formats S3M/IT (OK : non prioritaires)

## Pour ajouter une fonctionnalité

1. Lire TECHNICAL.md section "Optimisations possibles"
2. Vérifier CHANGELOG.md pour historique
3. Tester avec fichiers de référence
4. Mettre à jour CHANGELOG.md
5. Documenter dans README.md si user-facing

## Contact utilisateur

**Utilisateur** : Sam  
**Usage** : Personnel (musique années 90)  
**Niveau technique** : Bon (comprend Python, git, etc.)  
**Préférences** :
- Pas d'emojis excessifs
- Documentation claire et technique
- Exemples concrets

## Si quelque chose ne marche pas

1. **Vérifier version Python** : `python3 --version` (doit être 3.7+)
2. **Réinstaller dépendances** : `pip install -r requirements.txt --force-reinstall`
3. **Tester avec fichier connu** : mec3.xm, BANG.MOD
4. **Consulter section Dépannage** dans README.md
5. **Vérifier TECHNICAL.md** → Problèmes résolus

## Philosophie de développement

- ✅ Code simple > code clever
- ✅ Documentation > commentaires
- ✅ Fonctionnel > optimal
- ✅ Tests réels > tests unitaires théoriques

---

**Message pour la prochaine session Claude :**

Ce projet est **complet et fonctionnel**. Ne pas tout réécrire, seulement :
- Corriger bugs reportés
- Ajouter fonctionnalités demandées explicitement
- Améliorer performance si nécessaire

**La documentation est exhaustive. Lis-la avant de coder !**

---

Dernière session : Décembre 2025  
Prochaine session : ?  
Version actuelle : 2.0 ✅
