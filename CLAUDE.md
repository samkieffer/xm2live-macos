# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XM2Live converts 1990s tracker music files (FastTracker 2 XM, Amiga ProTracker MOD) to Ableton Live projects. The goal is to preserve the original compositions while enabling modern reworking in Ableton Live.

**Status:** Production-ready (Version 2.10.0 — single source: `__version__` in xm2live.py, read by the app build scripts)

**v2.10.0 (2026-10-28):** finetune and 16-bit loop fixes, notes without instrument, Cxx volume,
volume-0 notes as stops, deterministic sample file names, `--envelope` restored, `.als` validator
run after every conversion, regression tools in `tools/`. Roadmap: AUDIT.md.

**Earlier additions (v2.1-v2.5):**
- Volume support (default sample volume + per-note velocity)
- Panning support (default sample panning + optional 8xx automations)
- Sample Offset support (effect 9xx via Simpler, optional)
- Volume 00 support (note stop via volume column decoding)
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

# With sample offset support (effect 9xx)
python3 xm2live.py file.xm --sample-offset
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

# With sample offset support
python3 batch_convert.py /path/to/modules --sample-offset
```

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Dependencies: buildable, numpy, lxml

# Enable the git hooks (once per clone)
git config core.hooksPath .githooks
```

### Git and GitHub
- Remote: `origin` = git@github.com:samkieffer/xm2live-macos.git (**public** repository)
- `.githooks/post-commit` and `post-merge` push the current branch right after every commit or
  merge: **a commit is a publication**. Never commit secrets or private data.
- No force push: after an amend or rebase of published commits, the hook warns and the push has
  to be done by hand. Skip publishing once with `XM2LIVE_NO_PUSH=1 git commit ...`

### Testing (run before and after every converter change)
```bash
# Regression: convert the reference modules (tools/regression_set.txt) and diff
# against the stored snapshots (tools/snapshots/*.json)
python3 tools/snapshot.py diff
# After checking that every difference is intended, store the new state
python3 tools/snapshot.py save

# Convert + validate the whole collection (~390 modules, ~1.5 min): catches crashes
python3 tools/check_collection.py --jobs 8

# Validate any generated set (also runs automatically at the end of each conversion)
python3 als_validator.py path/to/project.als

# Audio check: reference render with OpenMPT (matches FT2 to 0 ms / 0 cent),
# then compare with a WAV exported from Live
python3 tools/render_reference.py module.xm reference.wav
python3 tools/compare_renders.py reference.wav live_export.wav
```
Tool details: tools/README.md.

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
    'finetune': int,  # -128 to +127 (1/128 semitone, XM scale; MOD nibble × 16)
    'loop_start': int,  # frames (XM 16-bit: header bytes / 2)
    'loop_length': int,  # frames
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
        'note': int,  # XM note 1-96 / MIDI note for MOD; None for non-note events
        'instrument': int,  # None (XM) or 'sample': 0 (MOD) = reuse the channel's last instrument
        'volume': int,  # 0-64 from vol column or Cxx; None = not set on this row
        'effect': int,
        'effect_param': int
        # Also: 'is_volume_stop' (vol 00 / C00), 'is_instrument_only' (instrument without note).
        # organize_tracks_by_channel() resolves instrument and volume per channel in play order.
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
  - Exception: Effect 9xx (sample offset) IS supported with `--sample-offset` via Simpler
    - Uses Simpler instead of Sampler (Sample Start is automatable in Simpler)
    - LIMITATION: Simpler doesn't support ping-pong loops (auto-converted to forward)
    - LIMITATION: Multi-sample not supported (loads only first sample)
    - Template required: `simpler_template.xml` (65KB, included in repository)
- **Volume envelopes (ADSR):** EXPERIMENTAL support with `--envelope` flag
  - **Fundamental incompatibility:** FT2 multi-point envelopes (up to 12 points) cannot be accurately converted to Ableton ADSR (4 parameters)
  - **Trigger vs Gate:** FT2 notes trigger indefinitely (until next note), Ableton notes have explicit duration (interpolated from note spacing)
  - **Result:** Approximation only, especially for envelopes without sustain point
  - **Recommendation:** Musicians should manually adjust envelopes in Ableton after conversion
  - Available with `--envelope` flag (disabled by default)
- **Panning:** Sample default panning IS supported. Effect 8xx automations available with flag
- **S3M/IT formats:** NOT supported - only XM and MOD
- **Song flow and timing (lot 1 of AUDIT.md):** Dxx/Bxx/E6x/EEx, mid-song Fxx, EDx and ECx are
  NOT handled yet - only the initial tempo is used and patterns are laid end to end
- **Volume 0 notes:** a note played at volume 0 (vol column 0x10, Cxx C00) becomes a stop event,
  not a MIDI note (silent in the tracker; Live would raise velocity 0 to 1). Revisit when
  volume slides are converted (lot 4)

## File Organization

```
xm2live/
├── xm2live.py          # Main conversion orchestrator (+ __version__)
├── xm_parser.py        # XM format parser
├── mod_parser.py       # MOD format parser
├── envelope_reader.py  # XM volume envelopes (for --envelope)
├── als_validator.py    # .als consistency checks (run after each conversion)
├── batch_convert.py    # Batch conversion script
├── tools/              # snapshot.py, render_reference.py, compare_renders.py, audit/
├── AUDIT.md            # Measured state + roadmap (lots 0-4)
├── TECHNICAL.md        # Technical details and specifications
├── README.md           # User documentation
└── requirements.txt    # Python dependencies
```

## Important Documentation

Before making any changes, read these files in order:

1. **AUDIT.md** (2026-10-28) - Measured state of the converter and the prioritized roadmap (lots 0-4)
2. **CLAUDE.md** (this file) - Quick reference and critical implementation details
3. **CHANGELOG.md** and git history - Version history
4. **README.md** - User-facing documentation

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
8. **DO NOT** use XM loop points as frames for 16-bit samples - they are in bytes
9. **DO NOT** scale finetune to fit ±50 cents - carry whole semitones into RootKey

### 9. Sample Offset Support (v2.4.0)

**Effect 9xx (Sample Offset):**
- XM effect: 9xx sets the sample playback start offset
- Value range: 0x00-0xFF (0-255 in decimal)
- Usage: Acid sounds, percussive variations, evolving textures

**Implementation:**
```python
# Detection phase (pre-scan patterns)
instruments_with_9xx = detect_effect_9xx_per_instrument(patterns, pattern_order, file_format)

# Device selection (per track)
if instrument in instruments_with_9xx:
    populate_track_with_simpler()  # Use Simpler (Sample Start automatable)
else:
    update_sampler_sample()  # Use Sampler (normal)

# Automation creation (after notes)
create_sample_offset_automation(track, notes, next_id)
```

**Key functions:**
- `detect_effect_9xx_per_instrument()` - Scans patterns, returns set of instrument numbers with effect 9xx
- `get_simpler_template()` - Loads simpler_template.xml (65KB), returns ElementTree copy
- `populate_track_with_simpler()` - Configures Simpler (similar to update_sampler_sample but for Simpler device)
- `create_sample_offset_automation()` - Creates Sample Start automation with plateau pattern (2 points per note)

**XML structure (Simpler):**
- Device: `OriginalSimpler` (not MultiSampler)
- Sample Start: `LoopModulators/SampleStart/AutomationTarget`
- Loop: `LoopModulators/LoopOn` (true/false only, no ping-pong mode)
- SNAP: `Snap/Manual` (true if loop, false otherwise)
- ADSR: `VolumeAndPan/Envelope` (same as Sampler)

**Conversion:**
- XM offset (0-255) → Ableton Sample Start (0.0-1.0)
- Approximation: `sample_start = offset_xm / 255.0`
- Not pixel-perfect but good enough for most use cases
- Users can adjust manually if needed

**Limitations:**
- Ping-pong loops → forward (Simpler doesn't support ping-pong)
- Multi-sample not supported (Simpler limitation, loads first sample only)
- Conversion is approximative (not sample-accurate)

**Parser changes:**
- xm_parser.py: Extracts `effect_type == 0x09` → `sample_offset_xm` field
- mod_parser.py: Extracts `effect == 0x09` → `sample_offset_xm` field

**Template:**
- `simpler_template.xml` - 65KB XML file, extracted from user-provided example
- Must be present in script directory or current directory
- Contains pre-configured OriginalSimpler with all necessary structure

### 10. Volume 00 Support (v2.5.0)

**Volume 00 (Note Stop):**
- XM: Volume column value 00 stops the currently playing note on that channel
- MOD: Effect C00 (Set Volume 00) stops the currently playing note
- Effect: Shortens the duration of the previous note in Ableton
- Per-channel: Volume 00 on Ch1 only affects Ch1, not other channels

**XM Volume Column Encoding (CRITICAL):**
```python
# FastTracker 2 volume column uses special encoding:
# 0x00-0x0F: No volume command
# 0x10-0x50: Set volume (0x10 = vol 0, 0x50 = vol 64)
# 0x60+: Other commands (slides, panning, etc.)

# MUST decode before using:
if 0x10 <= volume_raw <= 0x50:
    decoded_volume = volume_raw - 0x10  # 0x10 → 0, 0x50 → 64
```

**Implementation:**
```python
# 1. Capture volume 00 events (xm_parser.py:108-145)
decoded_volume = None
if volume is not None:
    if 0x10 <= volume <= 0x50:
        decoded_volume = volume - 0x10

# Capture volume stop events
if decoded_volume is not None and decoded_volume == 0:
    notes.append({'is_volume_stop': True, ...})

# 2. Use volume stops for duration calculation (xm_parser.py:411-438)
for note in channel_notes:
    if note.get('is_volume_stop'):
        continue  # Skip, used only for calculation

    # Find next event (note OR volume stop)
    for next_event in remaining_notes:
        if next_event.get('is_volume_stop'):
            note['duration'] = next_event['time'] - note['time']
            break
        if not next_event.get('is_volume_stop'):
            note['duration'] = next_event['time'] - note['time']
            break

# 3. Filter volume stops before MIDI creation
# (automatic via 'continue' in step 2)
```

**MOD Effect C00:**
```python
# mod_parser.py:191-204
elif effect == 0xC and effect_param == 0x00:
    pattern_data.append({
        'is_volume_stop': True,
        'volume': 0,
        ...
    })
```

**Key Bug Fixed:**
```python
# WRONG (0 evaluates to False in Python):
'volume': volume if volume else 64  # ❌ Converts vol 0 → 64!

# CORRECT:
'volume': 64 if decoded_volume is None else decoded_volume  # ✓
```

**Test file:**
- `test-vol00.xm` - 3 volume stop events, demonstrates note shortening

### 11. Finetune and 16-bit Loops (fixed 2026-10-28)

**Finetune → RootKey + Detune** (`finetune_to_root_key_and_detune()` in xm2live.py):
```python
# XM finetune: 1/128 semitone, FT2 keeps 16 steps per semitone (finetune >> 3)
cents = (finetune >> 3) * 6.25          # -128 → -100 cents, +127 → +93.75
semitones = round(cents / 100)          # Ableton Detune is limited to ±50 cents
detune = cents - semitones * 100
root_key = 60 - relative_note - semitones
```
- Old formula `finetune / 2.56` clamped to ±50 halved every finetune. Measured on
  DISCOTEC.XM: Baxs.wav (finetune -117) was +48 cents sharp, so the long loop ran 2.8% fast
  and drifted up to ~50 ms ahead within each bar (heard as a "BPM problem").
- MOD finetune (-8..+7, 1/8 semitone) is scaled ×16 in mod_parser.py to share this formula.

**16-bit loops:** XM sample headers store length, loop start and loop length in **bytes**.
xm_parser.py divides loop points by 2 for 16-bit samples (otherwise loops start too late
and end beyond the sample end).

## When Debugging

Test files that demonstrate specific features (the regression set is tools/regression_set.txt):
- `DISCOTEC.XM` - Finetune up to -128, 16-bit ping-pong loops, EDx, 8xx (FT2 render: ~/Desktop/DISCOTEC-FT2.wav)
- `mec3.xm` - Ping-pong loops, volume variations (v2.2.0)
- `MEC-pan.xm` - Panning automations (v2.3.0 - created for testing)
- `MEC.XM` - Volume envelopes (`--envelope`), key-offs, EDx
- `AMIGA/SARCOPHA.XM` - Notes without instrument number (61% of its notes)
- `BDTN.XM` - Pattern breaks (Dxx), volume-0 notes
- `242 DEMO/242.mod` - Speed=3, BPM=250 calculation
- `BANG.MOD` - BPM=160 detection
- `CHURCH22.MOD`, `KEEPCOOL.MOD`, `BLOOD3.MOD` - 31 samples, heavy Cxx volume use
- `test-vol00.xm` - not found on disk any more

## Version History Summary

**v2.10.0 (Current)** - Lot 0 of AUDIT.md: tuning/loop fixes, notes without instrument, Cxx, validator, tools
**v2.6.0-v2.9.0** - Template-less conversion, --merge-tracks, --output (see git history)
**v2.5.0** - Volume 00 support (note stop via volume column decoding, XM + MOD)
**v2.4.0** - Sample Offset support (effect 9xx via Simpler, optional)
**v2.3.0** - Panning support (static + optional automations)
**v2.2.0** - Volume per note via velocity (Vol-Vel 35%, -12dB headroom)
**v2.1.0** - Sample default volume support
**v2.0.0** - Initial stable version (samples, patterns, notes, loops, tempo)
