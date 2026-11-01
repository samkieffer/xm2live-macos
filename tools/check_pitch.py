#!/usr/bin/env python3
"""
Effets de hauteur : replayer.py comparé à libopenmpt, tick par tick, sur des modules de test

Chaque cas génère un petit module (XM table linéaire, XM table Amiga ou MOD) dont le sample est un
sinus pur, avec quelques cases d'effet sur un canal. libopenmpt le rend (BPM 32 : des ticks de 78 ms,
pour une mesure précise), la hauteur de chaque tick est mesurée par passages à zéro, puis comparée à
celle que calcule replayer.play_song() (note MIDI + pitch / pitch_moves de chaque note).

Usage: python3 tools/check_pitch.py [-v]
"""

import os
import sys
import math
import ctypes
import struct
import tempfile
import numpy as np

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TOOLS_DIR))
sys.path.insert(0, TOOLS_DIR)

from replayer import Cell, play_song  # noqa: E402
from check_timing import load_libopenmpt  # noqa: E402

RATE = 44100
BPM = 32
SPEED = 6
PERIOD_FRAMES = 16          # sinus de 16 frames : 8363 / 16 = 522,7 Hz sur la note 60
TICK_SECONDS = 2.5 / BPM
C4 = 49                      # note XM (C-4), note MIDI 60

# Cas : (nom, format, [(ligne, note XM ou None, effet, paramètre, colonne volume)])
CASES = [
    ('1xx glissement vers le haut', 'xm', [(0, C4, 0x1, 0x08, 0), (1, None, 0x1, 0x00, 0)]),
    ('2xx glissement vers le bas', 'xm', [(0, C4, 0x2, 0x10, 0)]),
    ('E1x / E2x glissements fins', 'xm', [(0, C4, 0xE, 0x18, 0), (1, None, 0xE, 0x10, 0), (2, None, 0xE, 0x2F, 0)]),
    ('X1x glissement extra fin', 'xm', [(0, C4, 33, 0x1F, 0), (1, None, 33, 0x10, 0)]),
    ('0xy arpeggio', 'xm', [(0, C4, 0x0, 0x47, 0), (1, None, 0x0, 0x47, 0)]),
    ('4xy vibrato', 'xm', [(0, C4, 0x4, 0x48, 0), (1, None, 0x4, 0x00, 0), (2, None, 0x4, 0x00, 0)]),
    ('1xx glissement, table Amiga', 'xm-amiga', [(0, C4, 0x1, 0x08, 0), (1, None, 0x1, 0x00, 0)]),
    ('0xy arpeggio, table Amiga', 'xm-amiga', [(0, C4, 0x0, 0x47, 0)]),
    ('1xx glissement MOD', 'mod', [(0, 60, 0x1, 0x04, 0), (1, None, 0x1, 0x04, 0)]),
    ('0xy arpeggio MOD', 'mod', [(0, 60, 0x0, 0x47, 0), (1, None, 0x0, 0x47, 0)]),
    ('4xy vibrato MOD', 'mod', [(0, 60, 0x4, 0x48, 0), (1, None, 0x4, 0x48, 0)]),
]
ROWS = 4


def sine_sample(frames=PERIOD_FRAMES * 4096):
    return np.round(np.sin(2 * math.pi * np.arange(frames) / PERIOD_FRAMES) * 16000).astype(np.int64)


def make_xm(path, cells, linear):
    order = bytes([0]) + bytes(255)
    header = b'Extended Module: ' + b'pitch test'.ljust(20, b'\0') + b'\x1a' + b'xm2live'.ljust(20, b'\0')
    header += struct.pack('<HIHHHHHHHH', 0x0104, 276, 1, 0, 1, 1, 1, 1 if linear else 0, SPEED, BPM) + order
    data = b''
    by_row = {row: (note, effect, param, vol) for row, note, effect, param, vol in cells}
    for row in range(ROWS):
        if row in by_row:
            note, effect, param, vol = by_row[row]
            data += bytes([note or 0, 1 if note else 0, vol, effect, param])
        else:
            data += bytes([0x80])
    pattern = struct.pack('<IBHH', 9, 0, ROWS, len(data)) + data
    sample = sine_sample()
    deltas = np.diff(np.concatenate([[0], sample])).astype(np.int16).tobytes()
    inst = struct.pack('<I', 263) + b'sine'.ljust(22, b'\0') + bytes([0]) + struct.pack('<HI', 1, 40)
    inst += bytes(96 + 96 + 14) + struct.pack('<H', 0) + bytes(22)
    smp = struct.pack('<IIIBbBBbB', len(deltas), 0, len(deltas), 64, 0, 0x11, 128, 0, 0) + b's'.ljust(22, b'\0')
    with open(path, 'wb') as f:
        f.write(header + pattern + inst + smp + deltas)


PERIODS = {60 + i: p for i, p in enumerate([428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226, 214])}


def make_mod(path, cells):
    sample = (sine_sample(PERIOD_FRAMES * 2048) // 128).astype(np.int8)
    header = b'pitch test'.ljust(20, b'\0')
    header += b'sine'.ljust(22, b'\0') + struct.pack('>HbBHH', len(sample) // 2, 0, 64, 0, len(sample) // 2)
    for _ in range(30):
        header += bytes(22) + struct.pack('>HbBHH', 0, 0, 0, 0, 1)
    header += bytes([1, 127]) + bytes([0]) + bytes(127) + b'M.K.'
    by_row = {row: (note, effect, param) for row, note, effect, param, _ in cells}
    pattern = b''
    for row in range(64):
        for channel in range(4):
            if channel == 0 and row in by_row:
                note, effect, param = by_row[row]
                period = PERIODS[note] if note else 0
                pattern += bytes([(1 & 0xF0) | (period >> 8), period & 0xFF, ((1 & 0x0F) << 4) | effect, param]) \
                    if note else bytes([0, 0, effect, param])
            else:
                pattern += bytes(4)
    # Fxx en première ligne : speed 6, puis BPM 32 (canal 2)
    pattern = pattern[:4] + bytes([0, 0, 0xF, BPM]) + pattern[8:]
    with open(path, 'wb') as f:
        f.write(header + pattern + sample.tobytes())


def openmpt_pitches(path, ticks, mod=False):
    """Hauteur (demi-tons au-dessus de la note 60) de chaque tick du rendu libopenmpt

    MOD : ProTracker n'applique le nouveau BPM (F20 en première ligne) qu'au tick suivant, et OpenMPT
    joue les MOD à la fréquence PAL de l'Amiga (période 428 → 8287 Hz, et non 8363 Hz : -0,16 demi-ton).
    """
    lib = load_libopenmpt()
    lib.openmpt_module_set_render_param.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int32]
    lib.openmpt_module_read_mono.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16)]
    data = open(path, 'rb').read()
    module = lib.openmpt_module_create_from_memory2(data, len(data), None, None, None, None, None, None, None)
    lib.openmpt_module_set_render_param(module, 4, 0)  # pas de rampe de volume
    frames = int(ticks * TICK_SECONDS * RATE)
    buffer = (ctypes.c_int16 * frames)()
    lib.openmpt_module_read_mono(module, RATE, frames, buffer)
    lib.openmpt_module_destroy(module)
    x = np.array(buffer[:frames], dtype=float)
    base = (3546895.0 / 428 if mod else 8363.0) / PERIOD_FRAMES
    first_tick = 2.5 / 125 if mod else TICK_SECONDS
    pitches = []
    for tick in range(ticks):
        start = 0 if tick == 0 else first_tick + (tick - 1) * TICK_SECONDS
        length = first_tick if tick == 0 else TICK_SECONDS
        a, b = int((start + 0.15 * length) * RATE), int((start + 0.85 * length) * RATE)
        crossings = np.nonzero(np.diff(np.signbit(x[a:b])))[0]
        if len(crossings) < 4:
            pitches.append(None)
            continue
        freq = (len(crossings) - 1) / 2 / ((crossings[-1] - crossings[0]) / RATE)
        pitches.append(12 * math.log2(freq / base))
    return pitches


def replayer_pitches(cells, file_format, linear, ticks):
    """Hauteur de chaque tick selon replayer.play_song (même module, cases construites ici)"""
    rows = []
    by_row = {row: (note, effect, param, vol) for row, note, effect, param, vol in cells}
    for row in range(ROWS):
        if row in by_row:
            note, effect, param, vol = by_row[row]
            midi = (note - 1 + 12) if note and file_format != 'mod' else note
            rows.append([Cell(midi, 1 if note else None, None, effect, param, vol or None)])
        else:
            rows.append([None])
    samples = [{'instrument': 1, 'length': 1 << 20, 'loop_type': 1, 'relative_note': 0, 'finetune': 0,
                'volume': 64, 'panning': 128}]
    song = play_song([{'rows': ROWS, 'cells': rows}], [0], SPEED, BPM, file_format, samples,
                     linear_frequencies=linear)
    tick_beats = 0.25 / SPEED
    pitches = [None] * ticks
    for note in song['tracks'][0][1]:
        moves = [(note['time'], note['pitch'])] + note['pitch_moves']
        for tick in range(ticks):
            time = (tick + 0.5) * tick_beats
            if note['time'] <= time < note['time'] + note['duration']:
                current = [value for t, value in moves if t <= time + 1e-9]
                pitches[tick] = note['note'] - 60 + current[-1]
    return pitches


def main():
    verbose = '-v' in sys.argv
    ticks = ROWS * SPEED
    failures = 0
    work = tempfile.mkdtemp(prefix='xm2live_pitch_')
    for name, file_format, cells in CASES:
        path = os.path.join(work, 'test.mod' if file_format == 'mod' else 'test.xm')
        if file_format == 'mod':
            make_mod(path, cells)
        else:
            make_xm(path, cells, linear=(file_format == 'xm'))
        reference = openmpt_pitches(path, ticks, mod=(file_format == 'mod'))
        ours = replayer_pitches(cells, 'mod' if file_format == 'mod' else 'xm', file_format == 'xm', ticks)
        errors = [abs(a - b) for a, b in zip(reference, ours) if a is not None and b is not None]
        worst = max(errors) if errors else None
        ok = worst is not None and worst < 0.05
        failures += not ok
        print(f"{'=' if ok else '≠'} {name:32s} écart max {worst if worst is None else round(worst, 3)} demi-ton")
        if verbose or not ok:
            print('    OpenMPT :', ' '.join(f"{p:+.2f}" if p is not None else '  ?  ' for p in reference))
            print('    replayer:', ' '.join(f"{p:+.2f}" if p is not None else '  ?  ' for p in ours))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
