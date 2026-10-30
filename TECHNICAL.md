# Documentation Technique - XM2Live

Documentation technique approfondie pour les développeurs et mainteneurs.

## Table des matières

1. [Architecture du projet](#architecture)
2. [Format XM (FastTracker 2)](#format-xm)
3. [Format MOD (ProTracker)](#format-mod)
4. [Format ALS (Ableton Live)](#format-als)
5. [Algorithmes de conversion](#algorithmes)
6. [Structures de données](#structures)
7. [Problèmes résolus](#problèmes)
8. [Optimisations possibles](#optimisations)

---

## Architecture

### Structure des fichiers

```
xm2live/
├── xm2live.py           # Point d'entrée, orchestration
├── xm_parser.py         # Parser FastTracker 2 XM
├── mod_parser.py        # Parser Amiga ProTracker MOD
├── replayer.py          # Moteur de lecture : déroulé, tempo, longueur des notes
├── als_validator.py     # Vérification du set produit
├── batch_convert.py     # Conversion batch
└── template_100_tracks.als
```

### Flux de conversion

```
[Fichier .xm/.mod]
        ↓
   [Parser] (xm_parser.py ou mod_parser.py)
        ↓
   [samples, patterns, info]
        ↓
   [replayer.play_song : déroulé, ticks, tempo, longueur des notes]
        ↓
   [tracks_data: {channel: {instrument: [notes]}}]
        ↓
   [xm2live.py: populate_tracks]
        ↓
   [Ableton .als + Samples WAV]
```

---

## Format XM (FastTracker 2)

### Structure du fichier

```
XM File Structure:
┌────────────────────────────┐
│ Header (276 bytes)         │
│  - ID: "Extended Module:"  │
│  - Song length             │
│  - Patterns count          │
│  - Instruments count       │
│  - Default tempo (Speed)   │
│  - Default BPM             │
│  - Pattern order[256]      │
├────────────────────────────┤
│ Patterns (variable)        │
│  - Pattern header          │
│  - Packed/unpacked data    │
│  - Notes, effects          │
├────────────────────────────┤
│ Instruments (variable)     │
│  - Instrument header       │
│  - Sample headers          │
│  - Sample data             │
└────────────────────────────┘
```

### Encodage notes

- **Little-endian** (format PC)
- **Note**: 1-96 (0 = pas de note)
  - Conversion MIDI: `midi_note = xm_note + 11`
  - Exemple: XM 49 (C-4) → MIDI 60
- **Volume**: 0-64
  - Conversion velocity: `velocity = (volume / 64) * 127`

### Pattern data

**Format packed (compression):**
```
Byte 1: sssssppp  (s=flags, p=period)
  bit 7: Si 1, données packed
  bit 0: Note présente
  bit 1: Instrument présent
  bit 2: Volume présent
  bit 3: Effect type présent
  bit 4: Effect param présent
```

**Format unpacked:**
```
5 bytes par note:
  Byte 1: Note
  Byte 2: Instrument
  Byte 3: Volume
  Byte 4: Effect type
  Byte 5: Effect param
```

### Sample data

**Types:**
- 8-bit signé
- 16-bit signé

**Encodage:** Delta (différences)
```python
# Décodage delta
decoded[0] = data[0]
for i in 1..n:
    decoded[i] = decoded[i-1] + data[i]
```

**Loops:**
- Type 0: Pas de loop
- Type 1: Forward loop
- Type 2: Ping-pong loop

---

## Format MOD (ProTracker)

### Structure du fichier

```
MOD File Structure:
┌────────────────────────────┐
│ Song title (20 bytes)      │
├────────────────────────────┤
│ Sample info × 31           │
│  (30 bytes each)           │
│  - Name (22 bytes)         │
│  - Length (words)          │
│  - Finetune                │
│  - Volume                  │
│  - Repeat start/length     │
├────────────────────────────┤
│ Song length (1 byte)       │
│ Restart pos (1 byte)       │
│ Pattern order[128]         │
│ Signature (4 bytes)        │
│  "M.K." = 31 samples       │
│  "M!K!" = >64 patterns     │
│  "FLT8" = 8 channels       │
├────────────────────────────┤
│ Patterns (1024 bytes each) │
│  64 rows × channels × 4b   │
├────────────────────────────┤
│ Sample data (8-bit signed) │
└────────────────────────────┘
```

### Encodage notes

- **Big-endian** (format Amiga)
- **Period**: Valeur de période (856-113)
  - Plus le period est élevé, plus la note est basse
  - Table de conversion vers MIDI

**Format note (4 bytes):**
```
Byte 0: sssspppp  s=sample high, p=period high
Byte 1: pppppppp  period low
Byte 2: ssssehhh  s=sample low, e=effect, h=param high
Byte 3: hhhhhhhh  param low
```

### Conversion Period → MIDI

**Table standard:**
```
Period 856 (C-1) → MIDI 48 (C-3)   # +24 semitones
Period 428 (C-2) → MIDI 60 (C-4)   # +24 semitones
Period 214 (C-3) → MIDI 72 (C-5)   # +24 semitones
```

**Formule mathématique:**
```python
freq = 7093789.2 / (period * 2)  # PAL
midi = 12 * log2(freq / 440) + 69 + 24
```

### Sample data

- **Format**: 8-bit signé (-128 à 127)
- **Conversion 16-bit**: `value_16bit = value_8bit * 256`
- **Loop**: Uniquement Forward (pas de ping-pong)

---

## Format ALS (Ableton Live)

### Structure XML

```xml
<Ableton>
  <LiveSet>
    <Tracks>
      <MidiTrack Id="0">
        <DeviceChain>
          <Devices>
            <InstrumentGroupDevice>
              <Branches>
                <InstrumentBranch>
                  <DeviceChain>
                    <Devices>
                      <MultiSampler>
                        <Player>
                          <MultiSampleMap>
                            <SampleParts>
                              <MultiSamplePart>
                                <SampleRef>
                                  <FileRef>
                                    <RelativePathType Value="1"/>
                                    <RelativePath>
                                      <RelativePathElement Dir="Samples"/>
                                      <RelativePathElement Dir="sample.wav"/>
                                    </RelativePath>
                                  </FileRef>
                                </SampleRef>
                                <RootKey Value="60"/>
                                <SampleStart Value="0"/>
                                <SampleEnd Value="44100"/>
                                <SustainLoop>
                                  <LoopOn Value="true"/>
                                  <Start Value="0"/>
                                  <End Value="44100"/>
                                  <Mode Value="1"/>  <!-- 1=Forward, 2=Ping-Pong -->
                                </SustainLoop>
                                <NumVoices Value="0"/>  <!-- 0=1 voice, 5=6 voices -->
                              </MultiSamplePart>
                            </SampleParts>
                          </MultiSampleMap>
                        </Player>
                      </MultiSampler>
                    </Devices>
                  </DeviceChain>
                </InstrumentBranch>
              </Branches>
            </InstrumentGroupDevice>
          </Devices>
        </DeviceChain>
        <MidiClips>
          <MidiClip>
            <Notes>
              <KeyTracks>
                <KeyTrack MidiKey="60">
                  <Notes>
                    <MidiNoteEvent Time="0" Duration="0.25" Velocity="100"/>
                  </Notes>
                </KeyTrack>
              </KeyTracks>
            </Notes>
          </MidiClip>
        </MidiClips>
      </MidiTrack>
    </Tracks>
    <MasterTrack>
      <DeviceChain>
        <Mixer>
          <Tempo>
            <Manual Value="120"/>
          </Tempo>
        </Mixer>
      </DeviceChain>
    </MasterTrack>
  </LiveSet>
</Ableton>
```

### Éléments clés

**Tempo:**
```xml
<Manual Value="120"/>          <!-- Master tempo -->
<FloatEvent Time="0" Value="120"/>  <!-- Automation -->
```

**Loop modes:**
- 0: Off
- 1: Forward
- 2: Ping-Pong  
- 3: Backward

**NumVoices:**
- Indexé depuis 0
- 0 = 1 voix (monophonique)
- 5 = 6 voix (défaut)

---

## Algorithmes de conversion

### Calcul BPM réel

```python
# FastTracker 2 formule
BPM_réel = BPM × (6 / Speed)

# Explication:
# - Tick = 2500 / BPM millisecondes
# - Speed = ticks par row
# - Avec Speed=6, BPM calibré correctement
# - Speed ≠ 6 nécessite recalcul
```

**Exemples:**
- Speed=6, BPM=125 → 125.00 BPM
- Speed=3, BPM=125 → 250.00 BPM
- Speed=12, BPM=125 → 62.50 BPM

### Déroulé, tempo et longueur des notes (`replayer.py`)

`play_song()` parcourt `pattern_order` comme le tracker : sauts (`Bxx`, un saut en arrière termine le
morceau), arrêts de pattern (`Dxx`), boucles (`E6x`), délais de pattern (`EEx`). Chaque `Fxx` change
la vitesse (< 32) ou le BPM (>= 32) dès sa ligne et devient une automation de tempo
(BPM Live = BPM × 6 / speed). Les événements sont placés au tick près : 1 tick = 1/(4 × speed) temps.

Longueur d'une note : tant que le tracker la fait entendre, sans plafond. La note suivante du canal
la coupe (un canal = une voix) ; sinon elle s'arrête au premier de ces événements :

```python
# Fin naturelle d'un sample sans boucle (même hauteur que dans Live)
secondes = frames / (8363 * 2 ** ((note - 60 + relative_note) / 12 + cents / 1200))
# Enveloppe de volume qui retombe à 0 pour de bon, note tenue
fin = début + tick_du_premier_point_de_la_série_finale_à_0 * (0.25 / speed)
# Volume du canal à 0 pour de bon (Cxx, colonne volume, glissements, ECx, key-off),
# sauf si le volume remonte avant la note suivante (volume haché ligne par ligne)
```

Après un key-off, sans enveloppe de volume le son est coupé ; avec une enveloppe, la note s'arrête
au key-off et la fin du son FT2 (fadeout : 32768 / fadeout ticks, ou fin de l'enveloppe) devient la
release du Sampler. Un son en boucle que rien n'arrête dure jusqu'à la fin du morceau.

---

## Structures de données

### samples (retour parser)

```python
[
    {
        'instrument': 1,
        'sample': 1,
        'name': 'Kick',
        'path': '/path/to/sample.wav',
        'relative_note': 0,
        'loop_start': 0,
        'loop_length': 44100,
        'loop_type': 1,  # 0=none, 1=forward, 2=ping-pong
        'volume': 64
    },
    ...
]
```

### patterns (retour parser)

```python
[
    {
        'number': 0,
        'rows': 64,
        'data': [
            {
                'row': 0,
                'channel': 0,
                'note': 60,        # MIDI note
                'instrument': 1,
                'volume': 64,
                'effect': 0xF,
                'effect_param': 0x03
            },
            ...
        ]
    },
    ...
]
```

### tracks_data (après organize)

```python
{
    0: {  # Channel 0
        1: [  # Instrument 1
            {
                'time': 0.0,
                'note': 60,
                'velocity': 100,
                'duration': 1.5
            },
            ...
        ],
        2: [...]  # Instrument 2
    },
    1: {...}  # Channel 1
}
```

---

## Problèmes résolus

### 1. Overflow delta-decoding (XM)

**Problème:**
```python
current = np.int16(current + data[k])
# RuntimeWarning: overflow encountered in scalar add
```

**Solution:**
```python
current = 0  # int Python (pas de limite)
current = (current + int(data[k])) & 0xFFFF  # Wrapping 16-bit
if current >= 32768:
    decoded[k] = current - 65536
else:
    decoded[k] = current
```

### 2. Octave notes MOD

**Problème:** Notes 1 octave trop basses

**Cause:** Convention ProTracker vs MIDI différente

**Solution:** +24 semitones au lieu de +12
```python
PERIOD_TABLE = {
    856: 48,  # C-1 ProTracker = C-3 MIDI (+24)
    428: 60,  # C-2 ProTracker = C-4 MIDI (+24)
    214: 72,  # C-3 ProTracker = C-5 MIDI (+24)
}
```

### 3. Détection BPM (MOD)

**Problème:** BPM non détecté si effet F sans note

**Cause:** Parser ignorait les cellules sans note

**Solution:**
```python
# Aussi capturer effets F seuls
elif effect == 0xF and effect_param > 0:
    pattern_data.append({
        'row': row,
        'channel': channel,
        'note': None,
        'effect': effect,
        'effect_param': effect_param
    })
```

### 4. NumVoices Ableton

**Problème:** NumVoices non trouvé (cherchait "Voices")

**Cause:** Nom et indexation incorrects

**Solution:**
```python
num_voices = sampler.find('.//NumVoices')
num_voices.set('Value', '0')  # 0 = 1 voix, 5 = 6 voix
```

---

## Optimisations possibles

### Performance

1. **Multithreading pour batch:**
   ```python
   from concurrent.futures import ThreadPoolExecutor
   with ThreadPoolExecutor(max_workers=4) as executor:
       futures = [executor.submit(convert_xm_to_ableton, f) 
                  for f in files]
   ```

2. **Cache des samples:**
   - Détecter samples identiques (hash MD5)
   - Réutiliser fichiers WAV déjà générés

3. **Streaming patterns:**
   - Ne pas charger tous les patterns en mémoire
   - Parser à la volée

### Mémoire

1. **Générateurs au lieu de listes:**
   ```python
   def read_patterns_generator(f, num_patterns):
       for i in range(num_patterns):
           yield parse_pattern(...)
   ```

2. **Nettoyage après sample:**
   ```python
   del sample_data  # Libérer mémoire
   gc.collect()
   ```

### Code

1. **Refactoring:**
   - Séparer parsing des effets
   - Classes pour XMFile, MODFile
   - Interface commune Parser

2. **Tests unitaires:**
   ```python
   def test_period_to_midi():
       assert period_to_midi(428) == 60
       assert period_to_midi(214) == 72
   ```

---

## Références

### Spécifications formats

- **XM Format**: https://ftp.modland.com/pub/documents/format_documentation/FastTracker 2 v2.04 (.xm).html
- **MOD Format**: https://www.aes.id.au/modformat.html
- **ProTracker**: https://wiki.multimedia.cx/index.php/Protracker_Module

### Bibliothèques

- **buildable**: https://pypi.org/project/buildable/
- **numpy**: https://numpy.org/doc/
- **lxml**: https://lxml.de/

### Outils

- **FastTracker 2 Clone**: https://16-bits.org/ft2.php
- **MilkyTracker**: https://milkytracker.org/
- **OpenMPT**: https://openmpt.org/

---

**Dernière mise à jour:** Décembre 2025
**Mainteneur:** Sam + Claude (Anthropic)
