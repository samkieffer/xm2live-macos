#!/usr/bin/env python3
"""
Calibrage du Sampler de Live : un set de mesure, puis l'analyse de son export audio

  python3 tools/live_calibration.py make  <dossier>   # crée <dossier>/calibration.als
  (ouvrir le set dans Live, exporter le Main en WAV : <dossier>/calibration.wav)
  python3 tools/live_calibration.py measure <dossier>/calibration.wav

Le set joue à 120 BPM, une section après l'autre, zone au niveau du convertisseur (ZONE_GAIN :
à zone 1.0 et vélocité 127, le Sampler sort ~23 dB au-dessus du sample et l'export sature) :
  1. vélocité → volume à 100 % : 12 notes de vélocité 127 à 1 (sinus constant, device à 0 dB)
  2. volume de la zone : 4 notes à ZONE_GAIN × 1, 1/2, 1/4, 1/16
  3. volume du device en automation : une note tenue, paliers 0, -6, -12, -24, -36 dB
  4. vélocité → volume à 35 % (réglage jusqu'à la v2.13) : mêmes vélocités qu'en 1
  5. Glide : PortamentoMode 1 puis 2 ; Do tenu, Ré qui le chevauche, Sol séparé (son qui décroît,
     pour voir si la note qui glisse redémarre le sample)
  6. Pitch bend (enveloppe de clip), plage 48 : une note tenue, paliers 0, +12, -12, +24, -24, +36, +47
     demi-tons d'un temps chacun, puis alternance 0 / +7 toutes les 20 ms (comme un arpeggio)
     (mesuré : Live joue la moitié, sa plage plafonne à 24 ; l'alternance n'est pas lissée)
  7. Pitch bend, plage 12 : paliers 0, +6, +12, -12

Mesures du 31/10/2026 (Live 12.4.16), reprises dans xm2live.py : vélocité à 100 % = 0,4 dB par pas
(droite en dB) ; Vel → Vol à a % ajoute a × (22,7 dB - 0,4 dB × (127 - vélocité)) au gain 1 du
Sampler (à 35 %, la vélocité 127 est donc 14,8 dB sous celle à 100 %) ; zone linéaire ;
PortamentoMode 2 glisse sans redémarrer le sample (1 le redémarre), aucun des deux ne glisse entre
notes séparées. Mesures du 01/11/2026 : PitchBendRange plafonne à 24 demi-tons (48 → 24, 12 exact),
marches de pitch bend de 20 ms rendues sans lissage.
"""

import os
import sys
import math
import wave
import argparse
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from live_set import LiveSetBuilder, set_value  # noqa: E402
from xm2live import ZONE_GAIN  # noqa: E402

TEMPO = 120.0
RATE = 44100
VELOCITIES = [127, 112, 96, 80, 64, 48, 32, 24, 16, 8, 4, 1]
ZONE_VOLUMES = [ZONE_GAIN, ZONE_GAIN / 2, ZONE_GAIN / 4, ZONE_GAIN / 16]
DEVICE_DB = [0, -6, -12, -24, -36]
# Débuts des sections (beats) ; une note dure 1 temps, une toutes les 2 temps
VEL100_AT, ZONE_AT, DEVICE_AT, VEL35_AT, GLIDE_AT, BEND48_AT, BEND12_AT = 0, 26, 36, 48, 74, 88, 102
BEND48_STEPS = [0, 12, -12, 24, -24, 36, 47]
BEND12_STEPS = [0, 6, 12, -12]
FAST_STEP = 0.04  # temps (20 ms à 120 BPM)
GLIDE_NOTES = [(0.0, 1.5, 60), (1.0, 1.0, 62), (3.0, 1.0, 67)]  # (début, durée, note) : Ré chevauche Do


def write_wav(path, samples):
    with wave.open(path, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())


def make(out_dir):
    from xm2live import update_sampler_sample, update_midi_clip_notes, add_automation_envelope, \
        add_float_event, write_tempo, update_track_name, add_clip_envelope, pitch_bend_value
    samples_dir = os.path.join(out_dir, 'Samples')
    os.makedirs(samples_dir, exist_ok=True)
    t = np.arange(2 * RATE) / RATE
    tone = os.path.join(samples_dir, 'tone.wav')        # 1 kHz constant, 2 s en boucle
    write_wav(tone, 0.5 * np.sin(2 * math.pi * 1000 * t))
    pluck = os.path.join(samples_dir, 'pluck.wav')      # 440 Hz qui décroît (sans boucle)
    write_wav(pluck, 0.5 * np.sin(2 * math.pi * 440 * t) * np.exp(-t * 1.5))

    builder = LiveSetBuilder()
    base = {'relative_note': 0, 'finetune': 0, 'volume': 64, 'panning': 128, 'loop_type': 0,
            'loop_start': 0, 'loop_length': 0}
    tone_info = dict(base, path=tone, loop_type=1, loop_start=0, loop_length=2 * RATE - 1)
    pluck_info = dict(base, path=pluck)

    def track(name, info, notes, zone=ZONE_GAIN, device_db=0.0, vel_scale=1.0, portamento=0):
        element = builder.add_track('midi_track')
        update_track_name(element, name)
        update_sampler_sample(element, info, out_dir, builder.sample_part)
        sampler = element.find('DeviceChain/DeviceChain/Devices/MultiSampler')
        set_value(sampler, 'Player/MultiSampleMap/SampleParts/MultiSamplePart/Volume', zone)
        set_value(sampler, 'VolumeAndPan/Volume/Manual', device_db)
        set_value(sampler, 'VolumeAndPan/VolumeVelScale/Manual', vel_scale)
        set_value(sampler, 'Globals/PortamentoMode/Manual', portamento)
        set_value(sampler, 'Globals/PortamentoTime/Manual', 200)
        update_midi_clip_notes(element, [{'time': t0, 'duration': d, 'note': n, 'velocity': v}
                                         for t0, d, n, v in notes])
        return sampler

    track('1 vel 100%', tone_info, [(VEL100_AT + 2 * i, 1, 72, v) for i, v in enumerate(VELOCITIES)])
    for i, zone in enumerate(ZONE_VOLUMES):
        track(f'2 zone {zone}', tone_info, [(ZONE_AT + 2 * i, 1, 72, 127)], zone=zone)
    sampler = track('3 device dB', tone_info, [(DEVICE_AT, 2 * len(DEVICE_DB), 72, 127)])
    events = add_automation_envelope(builder.tracks.findall('MidiTrack')[-1],
                                     sampler.find('VolumeAndPan/Volume/AutomationTarget').get('Id'))
    add_float_event(events, '0.0', DEVICE_DB[0])
    for i in range(1, len(DEVICE_DB)):
        add_float_event(events, DEVICE_AT + 2 * i, DEVICE_DB[i - 1])
        add_float_event(events, DEVICE_AT + 2 * i, DEVICE_DB[i])
    track('4 vel 35%', tone_info, [(VEL35_AT + 2 * i, 1, 72, v) for i, v in enumerate(VELOCITIES)], vel_scale=0.35)
    for mode in (1, 2):
        start = GLIDE_AT + (mode - 1) * 6
        track(f'5 glide mode {mode}', pluck_info, [(start + t0, d, n, 127) for t0, d, n in GLIDE_NOTES], portamento=mode)

    def bend_track(name, start, bend_range, steps, fast_until=None):
        sampler = track(name, tone_info, [(start, len(steps) + (3 if fast_until else 1), 48, 127)])
        element = builder.tracks.findall('MidiTrack')[-1]
        sampler.find('Globals/PitchBendRange').set('Value', str(bend_range))
        clip = element.find('DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events/MidiClip')
        target = element.find('DeviceChain/MainSequencer/MidiControllers/ControllerTargets.0').get('Id')
        events = add_clip_envelope(clip, target, 0)
        for i, semitones in enumerate(steps[1:], 1):
            add_float_event(events, start + i, pitch_bend_value(steps[i - 1], bend_range))
            add_float_event(events, start + i, pitch_bend_value(semitones, bend_range))
        if fast_until:
            t, value, last = start + len(steps), 0, pitch_bend_value(steps[-1], bend_range)
            while t < fast_until:
                new = pitch_bend_value(7 if value == 0 else 0, bend_range)
                add_float_event(events, t, last)
                add_float_event(events, t, new)
                last, value, t = new, 7 if value == 0 else 0, round(t + FAST_STEP, 6)

    bend_track('6 pitch bend 48', BEND48_AT, 48, BEND48_STEPS, fast_until=BEND48_AT + len(BEND48_STEPS) + 2)
    bend_track('7 pitch bend 12', BEND12_AT, 12, BEND12_STEPS)

    write_tempo(builder.live_set, [(0.0, TEMPO)])
    path = os.path.join(out_dir, 'calibration.als')
    builder.save(path)
    print(f"{path} : ouvrir dans Live, exporter le Main en WAV ({os.path.join(out_dir, 'calibration.wav')})")


def read_mono(path):
    with wave.open(path) as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        data = wav.readframes(wav.getnframes())
    if width == 3:
        raw = np.frombuffer(data, np.uint8).reshape(-1, 3).astype(np.int32)
        x = raw[:, 0] | raw[:, 1] << 8 | raw[:, 2] << 16
        x = np.where(x >= 1 << 23, x - (1 << 24), x) / float(1 << 23)
    elif width == 4:
        x = np.frombuffer(data, np.int32) / float(1 << 31)
    else:
        x = np.frombuffer(data, np.int16) / 32768.0
    return x.reshape(-1, channels).mean(axis=1), rate


def measure(path):
    x, rate = read_mono(path)
    sec = 60.0 / TEMPO

    def level_db(beat, length=0.5):
        """Niveau RMS (dB) au milieu d'une note : de beat + 0.25 à beat + 0.25 + length"""
        a, b = int((beat + 0.25) * sec * rate), int((beat + 0.25 + length) * sec * rate)
        rms = np.sqrt(np.mean(x[a:b] ** 2))
        return 20 * math.log10(rms) if rms > 0 else -200.0

    reference = level_db(VEL100_AT)
    clipped = np.mean(np.abs(x) > 0.999)
    if clipped > 0.001:
        print(f"⚠️  Export saturé ({clipped:.1%} des échantillons à pleine échelle) : mesures faussées en haut de l'échelle")
    print(f"Référence (vélocité 127, zone {ZONE_GAIN}, device 0 dB) : {reference:.1f} dBFS\n")
    print("Vélocité   100 %     35 %")
    for i, v in enumerate(VELOCITIES):
        print(f"{v:8d}  {level_db(VEL100_AT + 2 * i) - reference:+7.2f}  {level_db(VEL35_AT + 2 * i) - reference:+7.2f} dB")
    print("\nZone      mesuré   attendu (linéaire)")
    for i, zone in enumerate(ZONE_VOLUMES):
        print(f"{zone:7.5f}  {level_db(ZONE_AT + 2 * i) - reference:+7.2f}  {20 * math.log10(zone / ZONE_GAIN):+7.2f} dB")
    print("\nDevice    mesuré")
    for i, db in enumerate(DEVICE_DB):
        print(f"{db:+4d} dB  {level_db(DEVICE_AT + 2 * i, 1.0) - reference:+7.2f} dB")

    print("\nGlide (hauteur en Hz et niveau, par 50 ms)")
    for mode in (1, 2):
        start = GLIDE_AT + (mode - 1) * 6
        print(f"  mode {mode} :")
        for k in range(int(4.5 * sec / 0.05)):
            a = int((start * sec + k * 0.05) * rate)
            chunk = x[a:a + int(0.05 * rate)]
            crossings = np.count_nonzero(np.diff(np.signbit(chunk)))
            rms = np.sqrt(np.mean(chunk ** 2))
            if rms > 1e-4:
                print(f"    {k * 0.05:5.2f} s  {crossings / 2 / 0.05:6.0f} Hz  {20 * math.log10(rms):6.1f} dB")
    measure_pitch(x, rate, sec)


def measure_pitch(x, rate, sec):
    """Sections 6 et 7 : hauteur mesurée (demi-tons par rapport au Do 48 à 500 Hz) par palier"""
    def semitones(start_beat, length_beats):
        a, b = int(start_beat * sec * rate), int((start_beat + length_beats) * sec * rate)
        chunk = x[a:b]
        crossings = np.nonzero(np.diff(np.signbit(chunk)))[0]
        if len(crossings) < 3:
            return None
        freq = (len(crossings) - 1) / 2 / ((crossings[-1] - crossings[0]) / rate)
        return 12 * math.log2(freq / 500.0)

    print("\nPitch bend, plage 48 (demi-tons attendus → mesurés)")
    for i, expected in enumerate(BEND48_STEPS):
        print(f"  {expected:+4d} → {semitones(BEND48_AT + i + 0.25, 0.5):+7.2f}")
    fast = BEND48_AT + len(BEND48_STEPS)
    values = [semitones(fast + k * FAST_STEP + 0.005, FAST_STEP - 0.01) for k in range(20)]
    print("  alternance 0 / +7 toutes les 20 ms :", ' '.join(f"{v:+.1f}" if v is not None else '?' for v in values))
    print("Pitch bend, plage 12")
    for i, expected in enumerate(BEND12_STEPS):
        print(f"  {expected:+4d} → {semitones(BEND12_AT + i + 0.25, 0.5):+7.2f}")


def main():
    parser = argparse.ArgumentParser(description='Calibrage du Sampler de Live')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('make').add_argument('dir')
    sub.add_parser('measure').add_argument('wav')
    args = parser.parse_args()
    if args.command == 'make':
        os.makedirs(args.dir, exist_ok=True)
        make(os.path.abspath(args.dir))
    else:
        measure(args.wav)


if __name__ == '__main__':
    main()
