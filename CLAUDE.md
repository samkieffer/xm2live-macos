# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XM2Live converts 1990s tracker music files (FastTracker 2 XM, Amiga ProTracker MOD) to Ableton Live projects. The goal is to preserve the original compositions while enabling modern reworking in Ableton Live.

**Status:** Production-ready (Version 2.15.0 — single source: `__version__` in xm2live.py, read by the app build scripts)

**v2.15.0 (2026-10-31):** one arrangement clip per run of patterns where a track plays (named after
the patterns), instead of one clip from bar 1 to the last note.

**v2.14.0 (2026-10-31):** expression (lot 4 of AUDIT.md): calibrated velocity, Sampler volume
automation for volume changes during notes (FT2 volume envelopes in it with `--envelope`, ADSR
removed), tone portamento as legato notes + Sampler glide; clips no longer cut long last notes.

**v2.13.0 (2026-10-30):** the .als is assembled from fragments saved by Live (`templates/`,
`live_set.py`), lot 3 of AUDIT.md: no more buildable or 100/200-track templates, IDs renumbered only
where they must be unique, unique NoteIds, track names kept in Live (UserName), written in one pass.

**v2.12.1 (2026-10-30):** an order pointing to a missing pattern plays 64 empty rows, as in FT2
(28 XM files; FRONT.XM lasts 46 s in FT2).

**v2.12.0 (2026-10-28):** real note length (lot 2 of AUDIT.md): no 4-beat cap, notes end with
the sample, the volume envelope, a volume falling to 0 for good (slides included), key-off; the
FT2 fadeout after a key-off becomes the Sampler release.

**v2.11.0 (2026-10-28):** playback engine `replayer.py` (lot 1 of AUDIT.md): real song flow
(Bxx/Dxx/E6x/EEx), Fxx speed/BPM changes as tempo automation, EDx/ECx/key-off at tick level.

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

# With a personal set saved by Live (replaces the fragments it contains, see live_set.py)
python3 xm2live.py file.xm /path/to/set.als

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

# Dependencies: numpy, lxml

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

# Song flow and tempo, row by row, against libopenmpt (~25 s for the collection)
python3 tools/check_timing.py --jobs 8

# Validate any generated set (also runs automatically at the end of each conversion)
python3 als_validator.py path/to/project.als

# Regenerate templates/ after a new Live version: convert DISCOTEC.XM with --sample-offset,
# open the set in Live, save it, then
python3 tools/extract_fragments.py path/to/DISCOTEC.als

# Live's Sampler response (velocity curve, levels, glide): set to export from Live, then analysis
python3 tools/live_calibration.py make /tmp/calib
python3 tools/live_calibration.py measure /tmp/calib/calibration.wav

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
[samples, patterns (grid of Cell), metadata]
    ↓
replayer.play_song()  ← walks the song like the tracker (flow, ticks, tempo)
    ↓
{channel: {instrument: [notes]}} + tempo changes
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
    'panning': int,  # 0-255 (0=left, 128=center, 255=right)
    'length': int,  # frames
    'envelope': dict,  # XM only: volume envelope of the instrument (points, sustain, loop)
    'fadeout': int  # XM only: volume decrease per tick after a key-off (out of 32768)
}]

patterns = [{
    'number': int,
    'rows': int,
    'cells': [[Cell or None, ...], ...]  # one list per row, one entry per channel (None = empty)
}]
# replayer.Cell(note, instrument, volume, effect, param, volume_effect), same for XM and MOD:
#   note: MIDI note, KEY_OFF (-1) or None; instrument: None = channel's last instrument
#   volume: 0-64 from the XM volume column or Cxx, None = not set; effect/param: shared 0-F numbering
#   volume_effect: raw XM volume column command (0x60-0xFF: slides, panning...), None otherwise

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

`live_set.py` assembles the set with `lxml` and `gzip` only, from fragments saved by Live
(`templates/`): `liveset.xml` (the set without MIDI/group tracks), `midi_track.xml` (MIDI track with a
Sampler and an empty arrangement clip), `group_track.xml`, `simpler.xml`. Each track is a copy of a
fragment (`LiveSetBuilder.add_track()`), inserted before the return tracks; the set is written once.

**IDs (`LiveSetBuilder.renumber()`):** only the IDs Live keeps unique across the set are renumbered
on each copy: elements ending in `Target` (AutomationTarget, ModulationTarget), `Pointee`,
`ControllerTargets.N`, plus track Ids (small consecutive numbers). Local indexes (ClipSlot, KeyTrack,
MidiClip, AutomationEnvelope, FloatEvent, TrackSendHolder) stay as Live writes them. Notes get a
`NoteId` unique in their clip (1..N) and `NoteIdGenerator/NextId` = N + 1. Each track gets one clip
slot per scene (`fit_slots()`). Track names go in `UserName` (otherwise Live renames the track after
its instrument) and `EffectiveName`.

**Fragments:** extracted and cleaned by `tools/extract_fragments.py` (no names, sample paths, notes
or automations). Current sources: the set and MIDI track from a Live 12.3.2 set, the group track from
a Live 12.3.2 set, the Simpler from a user example.

**Key XML structures:**
- `MultiSampler/Player/MultiSampleMap/SampleParts/MultiSamplePart` - Sample configuration
- `NumVoices` - Voice count (0=1 voice, 5=6 voices) - indexed from 0
- `SustainLoop` - Loop settings (LoopOn, Start, End, Mode)
- `RootKey` - Root note adjustment based on XM relative_note
- `MainTrack/DeviceChain/Mixer/Tempo` - Tempo (`Manual`) and its automation envelope in
  `MainTrack/AutomationEnvelopes` (step = two FloatEvents at the same time), see `write_tempo()`


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

### 4. Playback Engine (replayer.py, v2.11.0)

`play_song()` walks `pattern_order` like the tracker instead of laying patterns end to end:
- Flow: Bxx jump (a backward jump = end of song), Dxx break (decimal row), E6x pattern loop
  (per channel), EEx pattern delay, an order pointing to a missing pattern plays 64 empty rows
  (FT2, checked on FRONT.XM: 46 s; OpenMPT skips it, so check_timing.py leaves those rows out)
- Fxx: speed (< 32) or BPM (>= 32) from the row where it appears, written as a tempo automation
- Time: 1 row = 1/4 beat always, 1 tick = 1/(4 × speed) beat, so Live BPM = BPM × 6 / speed
- Ticks: EDx delays the whole cell (x >= speed: not played), ECx sets the volume to 0 at tick x,
  key-off, volume slides (per tick, with the FT2 effect memory in XM)
- Channel state: a note without instrument replays the channel's instrument and keeps its volume
- Verified row by row against libopenmpt with `tools/check_timing.py` (393/394 identical)

### 5. Note Duration Calculation (replayer.py, v2.12.0)

A note lasts as long as the tracker makes it heard, with no cap. Each channel is one voice, so the
next note on the channel ends it. Otherwise it ends at the first of:
- the natural end of a sample without loop: `frames / (8363 × 2^((note - 60 + relative_note)/12 + cents/1200))`
  seconds, converted to beats through the tempo changes (`sample_seconds()`, `beats_after()`)
- the volume envelope reaching 0 for good while the note is held (`envelope_silence()`)
- the channel volume falling to 0 **for good**: Cxx/volume column 0, slides (Axy, 5xy, 6xy, EAx/EBx,
  volume column 6x-9x), ECx, key-off. A silence followed by a resume before the next note (volume
  back up, or an instrument number alone, which resets the volume in FT2) does not end the note:
  gated pads stay one note (the gate is lot 4)
- a looped sound that nothing stops lasts until the end of the song

Key-off (`release_ticks()`): without volume envelope FT2 cuts at once; with an envelope the note-off is
at the key-off and the end of the sound (min of fadeout `32768 / fadeout` ticks and the envelope
falling to 0) becomes the Sampler/Simpler `ReleaseTime` of that instrument (`configure_release()`,
only for instruments a key-off actually releases); with fadeout 0 and an envelope that stays above
0 the key-off is ignored (the sound goes on in FT2).

Velocity comes from the volume when the note starts. A note started at volume 0 is silent: it is
dropped unless its volume comes back up (fade-in), then it takes the velocity of the highest volume
reached. Notes cut on the tick they start (EC0) are dropped. The sample offset (9xx) is not taken
into account in the length.

### 5b. Clips (v2.15.0)

`replayer.play_song()` returns `segments`: each passage of an order entry, in played order
(start, end, pattern number). `clip_runs()` in xm2live.py cuts each track into clips: a clip starts at
the start of the pattern of its first note and ends at the first pattern boundary where nothing sounds
(a held note extends it: Live cuts notes at the clip end); patterns where the track does not play get
no clip. Names: `clip_name()` ("Pattern 0C", "Patterns 21-22-21", "Patterns 0C…1F", hex as in FT2).
Like the clips Live splits, notes keep song time and each clip shows its window: `Time` =
`CurrentStart` = `Loop/LoopStart` = clip start, `StartRelative` 0, `LoopEnd` = `OutMarker` =
`CurrentEnd`. The validator checks notes inside their clip window and clips that do not overlap.

### 6. NumVoices Configuration

```python
# Set to monophonic (1 voice)
num_voices = sampler.find('.//NumVoices')
num_voices.set('Value', '0')  # 0 = 1 voice, 5 = 6 voices
```

Element name is `NumVoices` (not `Voices`), indexed from 0.

### 7. Volume (v2.14.0)

FT2 plays a sample at the channel volume (0-64, linear amplitude): the sample's default volume on
each instrument number, then Cxx / volume column / slides / ECx / key-off. `replayer.py` gives each
note `volume` (at its start; the highest reached for a fade-in) and `volume_moves` (changes during
the note). In Live (`set_levels()`, `velocity_for()`, `create_volume_automation()` in xm2live.py):
- zone `MultiSamplePart > Volume` = `ZONE_GAIN` 0.0115 (-38.8 dB), device `VolumeAndPan/Volume` = 0 dB,
  Vel → Vol (`VolumeVelScale`) = 100 %. Measured: at Vel → Vol 0 % the Sampler has unity gain, and
  a % adds a × (22.7 dB - 0.4 dB × (127 - velocity)); the zone brings a full-volume note back to the
  pre-2.14 level (-16.1 dB of the sample: zone -12 dB, device -12 dB, 35 %), which did not clip
- velocity = the volume at the note start, through Live's measured curve (0.4 dB per velocity step at
  100 %, linear in dB): `velocity = 127 + 50·log10(v/64)` (64 → 127, 32 → 112, 1 → 37)
- changes during the note → automation of the device volume (dB relative to the note's start,
  back to 0 dB at each note, floor -36 dB = the parameter's minimum), only on tracks that need it
- `--envelope`: the FT2 volume envelope (`replayer.envelope_curve()`: sustain held, loops unrolled)
  is multiplied into that automation, note by note

Measurements: `tools/live_calibration.py` (set to open in Live, export, analysis), 2026-10-31 on Live
12.4.16. Redo them after a Live update.

### 7b. Tone Portamento (v2.14.0)

A note played with 3xx, 5xy or volume column Fx while the channel sounds does not retrigger: it
continues the sound (`legato`, same instrument as the playing note; to the same pitch, the note just
goes on). In Live the previous note overlaps it by `LEGATO_OVERLAP` (1/64 beat, added when writing
the MIDI notes only) and the Sampler/Simpler glides: `PortamentoMode` = 2 (measured: 2 glides without
restarting the sample, 1 restarts it, neither glides between separate notes), `PortamentoTime` = the
track's median slide duration (`glide_ms`: 3xx = xx/16 semitone per tick, Fx = x semitones per tick,
MOD = Amiga period units per tick).

### 8. Panning Support (v2.13.0)

```python
# XM panning: 0-255 (0=left, 128=center, 255=right)
# Ableton Panorama: -1.0 to +1.0 (0=center)
ableton_pan = (xm_panning - 128) / 128.0   # pan_to_ableton()
```

**Channel panning (replayer.py, XM only, like FT2):** an instrument number resets the channel
panning to the sample's default; volume column `Cx` (x × 16) and effect `8xx` set it until the next
instrument number (a note without instrument keeps it); volume column `Dx`/`Ex` and effect `Pxy` slide
it per tick. Each note gets `pan` (at its start) and `pan_moves` (changes during the note).

**In Live (`track_panning()` in xm2live.py), per track:**
- constant panning → `MultiSamplePart > Panorama` of the Sampler/Simpler zone, no automation
- varying panning with `--pan-automation` → zone at center and a stepped automation on
  `Mixer > Pan` (`create_pan_automation()`: two points at the same time per change). The zone must
  stay centered: the mixer pan is a balance, it cannot move a sound panned hard in the zone
- varying panning without the flag → the zone takes the panning heard longest

Checked against libopenmpt's channel VU meters (left/right) on DISCOTEC, BDTN and MEC-pan: every
note agrees except short notes (meter falloff) and instruments with a panning envelope.

## Known Limitations (Accepted, Do Not Fix)

- **Effects:** Most effects (vibrato, arpeggio, etc.) are NOT converted - too complex
  - Exception: panning (8xx, volume column Cx/Dx/Ex, Pxy) IS converted (section 8)
  - Exception: Effect 9xx (sample offset) IS supported with `--sample-offset` via Simpler
    - Uses Simpler instead of Sampler (Sample Start is automatable in Simpler)
    - LIMITATION: Simpler doesn't support ping-pong loops (auto-converted to forward)
    - LIMITATION: Multi-sample not supported (loads only first sample)
    - Simpler fragment: `templates/simpler.xml`
- **Volume envelopes:** only with `--envelope` (in the volume automation); the part after a key-off
  is the Sampler release (fadeout), not the envelope's tail
- **Volume floor:** the device volume stops at -36 dB below the note's start: fades and gates dip to
  -36 dB, not to silence (a note still ends at its last silence)
- **Panning envelopes (instrument):** not converted (MEC-pan, ESSAI5); the panning stays the channel's
- **S3M/IT formats:** NOT supported - only XM and MOD
- **Tone portamento:** one glide time per track (Live has one per device); the slide speed varies in FT2
- **Key-off with an instrument number on the same cell (41 cells in the collection):** treated as a
  key-off; FT2 might reset the volume instead
- **Kxx (key-off at tick xx):** not handled (unused in the collection)

## File Organization

```
xm2live/
├── xm2live.py          # Main conversion orchestrator (+ __version__)
├── xm_parser.py        # XM format parser
├── mod_parser.py       # MOD format parser
├── replayer.py         # Playback engine shared by XM and MOD (flow, ticks, tempo, note length)
├── live_set.py         # .als assembly from the fragments of templates/ (IDs, gzip)
├── templates/          # Fragments saved by Live: liveset, midi_track, group_track, simpler
├── als_validator.py    # .als consistency checks (run after each conversion)
├── batch_convert.py    # Batch conversion script
├── tools/              # snapshot.py, check_collection.py, check_timing.py, render_reference.py,
│                       # compare_renders.py, extract_fragments.py, audit/
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
4. **DO NOT** search patterns by number or lay them end to end - use `replayer.play_song()`
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
# Detection phase (notes played by replayer.play_song)
instruments_with_9xx = detect_effect_9xx_per_instrument(tracks_data)

# Device selection (per track)
if instrument in instruments_with_9xx:
    populate_track_with_simpler()  # Use Simpler (Sample Start automatable)
else:
    update_sampler_sample()  # Use Sampler (normal)

# Automation creation (after notes)
create_sample_offset_automation(track, notes, sample_start_id, sample_length)
```

**Key functions:**
- `detect_effect_9xx_per_instrument()` - Scans the played notes, returns set of instrument numbers with effect 9xx
- `LiveSetBuilder.copy_fragment('simpler')` - Copy of templates/simpler.xml with renumbered IDs
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

**Notes:** `replayer.play_song()` copies the 9xx parameter of each note into `sample_offset_xm`

**Template:** `templates/simpler.xml` (OriginalSimpler from a user example, cleaned by
`tools/extract_fragments.py`)

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

**Implementation (since v2.12.0):**
- The parsers decode the volume column (above) and Cxx (which wins, FT2 applies it after the
  volume column) into `Cell.volume`, MOD C00 included
- `replayer.play_song()` follows the real channel volume: a volume of 0 makes the channel silent,
  and the current note ends there unless the volume comes back before the next note (section 5)

**Key Bug Fixed:**
```python
# WRONG (0 evaluates to False in Python):
'volume': volume if volume else 64  # ❌ Converts vol 0 → 64!

# CORRECT: test against None
volume = cell.volume if cell.volume is not None else channel_volume.get(channel, 64)  # ✓
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

**v2.15.0 (Current)** - One clip per run of patterns
**v2.14.0** - Lot 4 of AUDIT.md: calibrated velocity, volume automation, envelopes, tone portamento glide
**v2.13.0** - Lot 3 of AUDIT.md: .als assembled from Live-saved fragments, buildable removed
**v2.12.1** - Missing patterns play 64 empty rows (FT2)
**v2.12.0** - Lot 2 of AUDIT.md: real note length (sample end, envelope, volume, key-off release)
**v2.11.0** - Lot 1 of AUDIT.md: replayer.py (song flow, Fxx tempo automation, EDx, ECx, key-off)
**v2.10.0** - Lot 0 of AUDIT.md: tuning/loop fixes, notes without instrument, Cxx, validator, tools
**v2.6.0-v2.9.0** - Template-less conversion, --merge-tracks, --output (see git history)
**v2.5.0** - Volume 00 support (note stop via volume column decoding, XM + MOD)
**v2.4.0** - Sample Offset support (effect 9xx via Simpler, optional)
**v2.3.0** - Panning support (static + optional automations)
**v2.2.0** - Volume per note via velocity (Vol-Vel 35%, -12dB headroom)
**v2.1.0** - Sample default volume support
**v2.0.0** - Initial stable version (samples, patterns, notes, loops, tempo)
