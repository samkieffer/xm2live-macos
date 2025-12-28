# Plan Phase 2 : Paramètres Sampler et Organisation

## 🎯 Objectifs

1. **Migrer les paramètres du sampler XM → Ableton**
   - Boucles (loop start, loop end, loop mode)
   - Enveloppe de volume

2. **Organiser les conversions**
   - Créer un sous-répertoire "Conversions Ableton Live"
   - Conversion batch automatique (future)

## 📊 Analyse des données XM

### Boucles (déjà partiellement extraites)

Dans `xm_parser.py`, lignes 224-242, on extrait déjà :
- `loop_start` : Position de début (en samples)
- `loop_length` : Longueur de la boucle (en samples)
- `sample_type` : Byte contenant des flags :
  - Bit 0-1 : Type de boucle
    - `0` = Pas de boucle
    - `1` = Forward loop
    - `2` = Ping-pong loop
  - Bit 4 : 16-bit sample (déjà utilisé)

**⚠️ Problème** : Ces données ne sont PAS ajoutées au dictionnaire `samples` !

### Enveloppe de volume (non extrait actuellement)

Format XM - Instrument header (non lu actuellement) :
- 12 points d'enveloppe max
- Chaque point : (position, valeur)
- Flags : on/off, sustain, loop

**Structure à lire** :
```
Offset  Size  Description
+96     48    Volume envelope points (12 points x 4 bytes)
+144    48    Panning envelope points
+192    1     Number of volume points
+193    1     Number of panning points
+194    1     Volume sustain point
+195    1     Volume loop start point
+196    1     Volume loop end point
+197    1     Panning sustain point
+198    1     Panning loop start point
+199    1     Panning loop end point
+200    1     Volume type (flags)
+201    1     Panning type (flags)
```

## 🔧 Modifications nécessaires

### 1. Mise à jour de `xm_parser.py`

#### A. Ajouter les données de boucle au dictionnaire samples

Ligne 285-291, modifier :
```python
samples.append({
    'instrument': inst_num + 1,
    'sample': j + 1,
    'name': header['name'],
    'path': wav_path,
    'relative_note': header['relative_note'],
    # AJOUTER :
    'loop_start': header['loop_start'],
    'loop_length': header['loop_length'],
    'loop_type': header['type'] & 0x03,  # Bits 0-1
    'volume': header['volume']
})
```

#### B. Extraire l'enveloppe de volume (nouveau code)

Après la ligne 207 (`num_samples = ...`), lire l'enveloppe :

```python
if num_samples > 0:
    sample_header_size = struct.unpack('<I', f.read(4))[0]

    # Lire les données de l'instrument (96 bytes)
    instrument_data = f.read(96)

    # Lire les enveloppes (48 bytes chacune)
    vol_envelope_data = f.read(48)
    pan_envelope_data = f.read(48)

    # Lire les paramètres d'enveloppe
    num_vol_points = struct.unpack('<B', f.read(1))[0]
    num_pan_points = struct.unpack('<B', f.read(1))[0]
    vol_sustain = struct.unpack('<B', f.read(1))[0]
    vol_loop_start = struct.unpack('<B', f.read(1))[0]
    vol_loop_end = struct.unpack('<B', f.read(1))[0]
    pan_sustain = struct.unpack('<B', f.read(1))[0]
    pan_loop_start = struct.unpack('<B', f.read(1))[0]
    pan_loop_end = struct.unpack('<B', f.read(1))[0]
    vol_type = struct.unpack('<B', f.read(1))[0]
    pan_type = struct.unpack('<B', f.read(1))[0]

    # Parser les points d'enveloppe de volume
    vol_envelope_points = []
    for i in range(min(num_vol_points, 12)):
        pos = struct.unpack('<H', vol_envelope_data[i*4:i*4+2])[0]
        val = struct.unpack('<H', vol_envelope_data[i*4+2:i*4+4])[0]
        vol_envelope_points.append({'position': pos, 'value': val})

    envelope_info = {
        'enabled': bool(vol_type & 0x01),
        'sustain': bool(vol_type & 0x02),
        'loop': bool(vol_type & 0x04),
        'points': vol_envelope_points,
        'sustain_point': vol_sustain,
        'loop_start': vol_loop_start,
        'loop_end': vol_loop_end
    }
```

### 2. Mise à jour de `xm2live.py`

#### A. Modifier le répertoire de sortie

Ligne 283-284, remplacer :
```python
if not output_dir:
    xm_basename = os.path.splitext(os.path.basename(xm_path))[0]
    output_dir = os.path.join(os.path.dirname(xm_path), f"{xm_basename}_Ableton_Project")
```

Par :
```python
if not output_dir:
    xm_basename = os.path.splitext(os.path.basename(xm_path))[0]
    # Créer dans "Conversions Ableton Live"
    base_dir = os.path.dirname(xm_path)
    conversions_dir = os.path.join(base_dir, "Conversions Ableton Live")
    os.makedirs(conversions_dir, exist_ok=True)
    output_dir = os.path.join(conversions_dir, f"{xm_basename}_Ableton_Project")
```

#### B. Appliquer les boucles au sampler

Dans `update_sampler_sample()`, après la ligne 190, ajouter :

```python
# Appliquer les paramètres de boucle
if 'loop_type' in sample_info and sample_info['loop_type'] > 0:
    # Activer la boucle
    loop_on = new_sample_part.find('.//Loop/LoopOn')
    if loop_on is not None:
        loop_on.set('Value', 'true')

    # Loop start
    loop_start_elem = new_sample_part.find('.//Loop/LoopStart')
    if loop_start_elem is not None:
        loop_start_elem.set('Value', str(sample_info['loop_start']))

    # Loop end = loop_start + loop_length
    loop_end = sample_info['loop_start'] + sample_info['loop_length']
    loop_end_elem = new_sample_part.find('.//Loop/LoopEnd')
    if loop_end_elem is not None:
        loop_end_elem.set('Value', str(loop_end))

    # Loop mode
    loop_mode_elem = new_sample_part.find('.//Loop/LoopMode')
    if loop_mode_elem is not None:
        # 0 = Off, 1 = Forward, 2 = Ping-Pong
        loop_mode_elem.set('Value', str(sample_info['loop_type']))

    print(f"    → Boucle: {sample_info['loop_start']} - {loop_end} (mode {sample_info['loop_type']})")
```

#### C. Appliquer l'enveloppe de volume

Nouvelle fonction à ajouter :

```python
def apply_volume_envelope(sampler, envelope_info):
    """Applique l'enveloppe de volume XM au sampler Ableton"""

    if not envelope_info['enabled'] or not envelope_info['points']:
        return

    # Trouver l'élément VolumeEnvelope dans le sampler
    vol_env = sampler.find('.//VolumeEnvelope')
    if vol_env is None:
        return

    # Activer l'enveloppe
    enabled = vol_env.find('.//IsOn')
    if enabled is not None:
        enabled.set('Value', 'true')

    # Créer les points d'enveloppe
    # Ableton utilise un format différent, conversion nécessaire
    # XM: position en ticks, value 0-64
    # Ableton: time en ms, value 0.0-1.0

    # TODO: Mapper les points XM vers Ableton
    # Cette partie nécessite plus de recherche sur le format Ableton
```

## 🚀 Plan d'implémentation

### Étape 1 : Boucles (simple)
1. ✅ Analyser les données XM existantes
2. Modifier `xm_parser.py` pour ajouter loop_start, loop_length, loop_type
3. Modifier `xm2live.py` pour appliquer les boucles au sampler
4. Tester avec un fichier XM contenant des boucles

### Étape 2 : Répertoire de sortie (simple)
1. Modifier `xm2live.py` pour créer "Conversions Ableton Live"
2. Tester la conversion

### Étape 3 : Enveloppe de volume (complexe)
1. Modifier `xm_parser.py` pour extraire l'enveloppe
2. Analyser le format d'enveloppe Ableton
3. Créer la fonction de conversion
4. Appliquer au sampler
5. Tester

### Étape 4 : Conversion batch (future)
1. Créer un script `batch_convert.py`
2. Scanner un répertoire pour les .xm
3. Convertir tous les fichiers
4. Rapport de conversion

## 📝 Questions à clarifier

1. **Priorité** : Commencer par les boucles ou l'enveloppe ?
2. **Test** : Avez-vous un fichier .xm avec des boucles pour tester ?
3. **Enveloppe** : Format Ableton exact à déterminer (nécessite recherche)

## 🎯 Prochaine étape recommandée

Je recommande de commencer par :
1. **Boucles** (plus simple, données déjà extraites)
2. **Répertoire de sortie** (très simple)
3. **Enveloppe** (plus complexe, nécessite recherche)

Voulez-vous que je commence par implémenter les boucles et le nouveau répertoire de sortie ?
