# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XM2Live converts 1990s tracker music files (FastTracker 2 XM, Amiga ProTracker MOD) to Ableton Live projects. The goal is to preserve the original compositions while enabling modern reworking in Ableton Live.

**Status:** Production-ready (Version 2.3.0)

**Recent additions (v2.1-v2.3):**
- Volume support (default sample volume + per-note velocity)
- Panning support (default sample panning + optional 8xx automations)
- Headroom management (-12 dB) to prevent clipping

## Essential Commands

### Single File Conversion
```bash
# Convert XM file
python3 xm2live.py path/to/file.xm

# Convert MOD file
python3 xm2live.py path/to/file.mod

# With custom template
python3 xm2live.py file.xm /path/to/template.als

# With panning automations (effect 8xx)
python3 xm2live.py file.xm --pan-automation
```

### Batch Conversion
```bash
# Convert entire directory (recursive)
python3 batch_convert.py "/Users/sam/Music/Compo/All Compo/Modules"

# Non-recursive (current directory only)
python3 batch_convert.py /path/to/modules --no-recursive

# With custom template
python3 batch_convert.py /path/to/modules --template /path/to/template.als

# With panning automations
python3 batch_convert.py /path/to/modules --pan-automation
```

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Dependencies: buildable, numpy, lxml
```

### Testing
```bash
# Test files used during development
python3 xm2live.py "/Users/sam/Music/Compo/All Compo/Modules/mec3.xm"
python3 xm2live.py "/Users/sam/Music/Compo/All Compo/Modules/BANG.MOD"
python3 xm2live.py "/Users/sam/Music/Compo/All Compo/Modules/242.mod"
```

## Architecture

### Core Design Principle

The converter is **parser-based**, not library-based. It reads binary tracker formats at the byte level and generates Ableton Live XML projects by manipulating the .als file structure.

### Data Flow

```
Input File (.xm/.mod)
    ↓
Parser (xm_parser.py or mod_parser.py)
    ↓
[samples, patterns, metadata]
    ↓
organize_tracks_by_channel()
    ↓
{channel: {instrument: [notes]}}
    ↓
populate_tracks() in xm2live.py
    ↓
Output (.als + WAV samples)
```

### Parser Architecture

**xm_parser.py (FastTracker 2 XM):**
- Little-endian binary parsing
- Delta-decoding for 16-bit samples (wrapping arithmetic required)
- Packed/unpacked pattern formats
- Loops: Forward (type 1) + Ping-Pong (type 2)
- Returns: `(samples, patterns, xm_info)`

**mod_parser.py (Amiga ProTracker):**
- Big-endian binary parsing
- Period-to-MIDI conversion with +24 semitone offset
- 8-bit to 16-bit sample conversion
- Effect F detection for Speed/BPM
- Loops: Forward only (no ping-pong on Amiga)
- Returns: `(samples, patterns, mod_info)`

**Both parsers share identical output structure:**
```python
samples = [{
    'instrument': int,
    'sample': int,
    'name': str,
    'path': str,  # WAV file path
    'relative_note': int,
    'finetune': int,  # -128 to +127 (cents)
    'loop_start': int,
    'loop_length': int,
    'loop_type': int,  # 0=none, 1=forward, 2=ping-pong
    'volume': int,  # 0-64 (64=100%)
    'panning': int  # 0-255 (0=left, 128=center, 255=right)
}]

patterns = [{
    'number': int,
    'rows': int,
    'data': [{
        'row': int,
        'channel': int,
        'note': int,  # MIDI note number
        'instrument': int,
        'volume': int,
        'effect': int,
        'effect_param': int
    }]
}]

info = {
    'name': str,
    'channels': int,
    'tempo': int,  # Speed (ticks/row)
    'bpm': int,
    'pattern_order': list,
    'song_length': int
}
```

### Ableton Live XML Manipulation

The project uses the `buildable` library to load/save .als files, but directly manipulates XML elements via `lxml` for precise control:

**Key XML structures:**
- `MultiSampler/Player/MultiSampleMap/SampleParts/MultiSamplePart` - Sample configuration
- `NumVoices` - Voice count (0=1 voice, 5=6 voices) - indexed from 0
- `SustainLoop` - Loop settings (LoopOn, Start, End, Mode)
- `RootKey` - Root note adjustment based on XM relative_note
- `Manual` and `FloatEvent` - Tempo settings

**Template requirement:**
- 100 MIDI tracks with Sampler
- First track MUST contain a sample (used as template for all other tracks)
- Located at: `./template_100_tracks.als` or `/Users/sam/Music/Compo/All Compo/Modules/template_100_tracks.als`

## Critical Implementation Details

### 1. BPM Calculation (NEVER change this)

```python
# FastTracker 2 formula
real_bpm = bpm * (6.0 / speed)
```

- Speed = ticks per row (default 6)
- BPM is calibrated for Speed=6
- Example: Speed=3, BPM=125 → real BPM = 250

### 2. MOD Period to MIDI Conversion (NEVER change this)

```python
# +24 semitones, NOT +12
PERIOD_TABLE = {
    856: 48,  # C-1 ProTracker → C-3 MIDI
    428: 60,  # C-2 ProTracker → C-4 MIDI
    214: 72,  # C-3 ProTracker → C-5 MIDI
}
```

ProTracker uses different octave conventions than MIDI. The +24 offset is correct.

### 3. Delta Decoding Overflow Fix (XM samples)

```python
# CORRECT: Use Python int with manual wrapping
current = 0  # Python int (unlimited)
current = (current + int(data[k])) & 0xFFFF  # 16-bit wrapping
if current >= 32768:
    decoded[k] = current - 65536
else:
    decoded[k] = current

# WRONG: np.int16 causes RuntimeWarning
current = np.int16(current + data[k])  # ❌ DO NOT USE
```

### 4. Effect F Detection (Speed/BPM)

Effect F commands can exist **without notes** in a cell. The parser must capture these:

```python
# Capture effect F even when note is None
elif effect == 0xF and effect_param > 0:
    pattern_data.append({
        'note': None,  # Important: can be None
        'effect': effect,
        'effect_param': effect_param
    })
```

Search in `pattern_order` (play order), not pattern numbers.

### 5. Note Duration Calculation

```python
# Interval-based duration (max 4 beats)
for i, note in enumerate(notes):
    if i + 1 < len(notes):
        interval = notes[i+1]['time'] - note['time']
        note['duration'] = min(interval, 4.0)
    else:
        note['duration'] = 4.0
```

This simulates monophonic tracker behavior where each channel has one voice.

### 6. NumVoices Configuration

```python
# Set to monophonic (1 voice)
num_voices = sampler.find('.//NumVoices')
num_voices.set('Value', '0')  # 0 = 1 voice, 5 = 6 voices
```

Element name is `NumVoices` (not `Voices`), indexed from 0.

### 7. Volume Support (v2.1-v2.2)

**Sample default volume:**
```python
# XM volume: 0-64 (64 = 100%)
# Ableton Volume: 0.0-1.0 (1.0 = 0 dB)
# With -12 dB headroom to prevent clipping
ableton_volume = (xm_volume / 64.0) * 0.25
```

**Per-note volume (velocity):**
- XM volume column (0-64) → MIDI velocity (0-127)
- Conversion: `velocity = min(127, xm_volume * 2)`
- Ableton: `VolumeVelScale` (Vol-Vel) set to **35%** (Ableton default)
- This makes velocity affect volume without saturation

### 8. Panning Support (v2.3)

**Sample default panning:**
```python
# XM panning: 0-255 (0=left, 128=center, 255=right)
# Ableton Panorama: -1.0 to +1.0 (0=center)
ableton_pan = (xm_panning - 128) / 128.0
```
Element: `MultiSamplePart > Panorama`

**Per-note panning (effect 8xx) - OPTIONAL:**
- Activated with `--pan-automation` flag
- Creates automation on `Mixer > Pan > AutomationTarget`
- **2 points per note** (plateau to prevent interpolation)
- **Returns to default** panning when no effect 8xx
- Point at time 0 with sample's default panning
- Includes `AutomationTransformViewState` (required by Ableton)

Example automation behavior:
```
Sample default pan = 128 (center)
Note with 8FF → Pan jumps to right, stays during note
Note with 800 → Pan jumps to left, stays during note
Note without 8xx → Pan returns to center (default)
```

## Known Limitations (Accepted, Do Not Fix)

- **Effects:** Most effects (vibrato, arpeggio, etc.) are NOT converted - too complex
  - Exception: Effect 8xx (panning) IS supported with `--pan-automation`
  - Effect 9xx (sample offset): NOT supported - Ableton Sampler's Sample Start parameter is not automatable (technical limitation of Ableton Live, not fixable)
- **Volume envelopes (ADSR):** EXPERIMENTAL support with `--envelope` flag
  - **Fundamental incompatibility:** FT2 multi-point envelopes (up to 12 points) cannot be accurately converted to Ableton ADSR (4 parameters)
  - **Trigger vs Gate:** FT2 notes trigger indefinitely (until next note), Ableton notes have explicit duration (interpolated from note spacing)
  - **Result:** Approximation only, especially for envelopes without sustain point
  - **Recommendation:** Musicians should manually adjust envelopes in Ableton after conversion
  - Available with `--envelope` flag (disabled by default)
- **Panning:** Sample default panning IS supported. Effect 8xx automations available with flag
- **S3M/IT formats:** NOT supported - only XM and MOD
- **Dynamic BPM changes:** NOT detected - only first patterns scanned

## File Organization

```
xm2live/
├── xm2live.py          # Main conversion orchestrator
├── xm_parser.py        # XM format parser
├── mod_parser.py       # MOD format parser
├── batch_convert.py    # Batch conversion script
├── RESUME_SESSION.md   # Complete session context (READ THIS FIRST)
├── TECHNICAL.md        # Technical details and specifications
├── README.md           # User documentation
└── requirements.txt    # Python dependencies
```

## Important Documentation

Before making any changes, read these files in order:

1. **MODIFICATIONS_LOG.md** - Complete version history with detailed changes (v2.0 → v2.3.0)
2. **CLAUDE.md** (this file) - Quick reference and critical implementation details
3. **README.md** - User-facing documentation

## Project Philosophy

- **Authenticity over features** - Faithful conversion, not enhancement
- **Simple over clever** - Straightforward code
- **Functional over optimal** - It works, ship it
- **Real tests over unit tests** - Test with actual tracker files

## User Context

- **User:** Sam
- **Use case:** Personal (reworking 30-year-old music)
- **Technical level:** High (understands Python, git, binary formats)
- **Preferences:** Technical documentation, no excessive emojis, concrete examples

## Common Pitfalls

1. **DO NOT** change the +24 semitone offset for MOD files to +12
2. **DO NOT** use `np.int16` for delta decoding - use Python int with wrapping
3. **DO NOT** ignore effect F commands that lack notes
4. **DO NOT** search patterns by number - use `pattern_order`
5. **DO NOT** look for `Voices` element - it's `NumVoices`
6. **DO NOT** add features not explicitly requested
7. **DO NOT** rewrite working code without a specific bug report

## When Debugging

Test files that demonstrate specific features:
- `mec3.xm` - Ping-pong loops, volume variations (v2.2.0)
- `MEC-pan.xm` - Panning automations (v2.3.0 - created for testing)
- `242.mod` - Speed=3, BPM=250 calculation
- `BANG.MOD` - BPM=160 detection
- `CHURCH22.MOD` - 31 samples format
- `divers/` directory - 21 files for batch testing

## Version History Summary

**v2.3.0 (Current)** - Panning support (static + optional automations)
**v2.2.0** - Volume per note via velocity (Vol-Vel 35%, -12dB headroom)
**v2.1.0** - Sample default volume support
**v2.0.0** - Initial stable version (samples, patterns, notes, loops, tempo)
