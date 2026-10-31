#!/usr/bin/env python3
"""
Module de parsing de fichiers Amiga ProTracker Module (.mod)
Extrait les samples, patterns et notes MIDI
"""

import sys
import os
import struct
import wave
import numpy as np
from pathlib import Path

from xm_parser import decode_name
from replayer import Cell


# Table de conversion Period → Note MIDI
# Basée sur les periods standards ProTracker (PAL)
# Note: +24 semitones pour corriger l'octave (C-1 ProTracker = C-3 MIDI)
PERIOD_TABLE = {
    # Octave 1 (C-1 à B-1 ProTracker) → C-3 à B-3 MIDI
    856: 48, 808: 49, 762: 50, 720: 51, 678: 52, 640: 53,
    604: 54, 570: 55, 538: 56, 508: 57, 480: 58, 453: 59,
    # Octave 2 (C-2 à B-2 ProTracker) → C-4 à B-4 MIDI
    428: 60, 404: 61, 381: 62, 360: 63, 339: 64, 320: 65,
    302: 66, 285: 67, 269: 68, 254: 69, 240: 70, 226: 71,
    # Octave 3 (C-3 à B-3 ProTracker) → C-5 à B-5 MIDI
    214: 72, 202: 73, 190: 74, 180: 75, 170: 76, 160: 77,
    151: 78, 143: 79, 135: 80, 127: 81, 120: 82, 113: 83,
    # Octave 4 (extension) → C-6 à B-6 MIDI
    107: 84, 101: 85, 95: 86, 90: 87, 85: 88, 80: 89,
    76: 90, 71: 91, 67: 92, 64: 93, 60: 94, 57: 95,
}


def period_to_midi(period):
    """Convertit une valeur de period ProTracker en note MIDI

    La formule exacte est basée sur la fréquence:
    freq = 7093789.2 / (period * 2) (PAL)
    MIDI = 12 * log2(freq / 440) + 69

    Mais on utilise une table de lookup pour les valeurs standards
    """
    if period == 0:
        return None

    # Chercher la valeur la plus proche dans la table
    closest_period = min(PERIOD_TABLE.keys(), key=lambda x: abs(x - period))

    # Si la différence est trop grande, calculer via la formule
    if abs(closest_period - period) > 10:
        # Formule: freq = 7093789.2 / (period * 2)
        freq = 7093789.2 / (period * 2)
        # MIDI = 12 * log2(freq / 440) + 69 + 24 (correction octave)
        import math
        midi_note = 12 * math.log2(freq / 440.0) + 69 + 24
        return int(round(midi_note))

    return PERIOD_TABLE[closest_period]


def read_mod_header(filepath):
    """Lit le header d'un fichier MOD et détermine le format"""
    with open(filepath, 'rb') as f:
        # Lire le titre (20 bytes)
        title = decode_name(f.read(20))

        # Chercher la signature à l'offset 1080 pour déterminer le format
        f.seek(1080)
        signature = f.read(4).decode('ascii', errors='ignore')

        # Déterminer le nombre de samples
        if signature in ['M.K.', 'M!K!', 'FLT4', 'FLT8', '4CHN', '6CHN', '8CHN']:
            num_samples = 31
        else:
            num_samples = 15

        # Déterminer le nombre de canaux
        if signature == 'FLT8' or signature == '8CHN':
            num_channels = 8
        elif signature == '6CHN':
            num_channels = 6
        else:
            num_channels = 4  # Standard MOD

        return {
            'title': title,
            'num_samples': num_samples,
            'num_channels': num_channels,
            'signature': signature
        }


def read_mod_samples_info(f, num_samples):
    """Lit les informations des samples (headers seulement, pas les données)"""
    samples_info = []

    for i in range(num_samples):
        # Lire les 30 bytes de sample info
        name = decode_name(f.read(22))
        length = struct.unpack('>H', f.read(2))[0] * 2  # En words -> bytes
        finetune = struct.unpack('B', f.read(1))[0]
        # Finetune est signé sur 4 bits
        if finetune > 7:
            finetune = finetune - 16
        volume = struct.unpack('B', f.read(1))[0]
        repeat_start = struct.unpack('>H', f.read(2))[0] * 2  # En words -> bytes
        repeat_length = struct.unpack('>H', f.read(2))[0] * 2  # En words -> bytes

        samples_info.append({
            'name': name,
            'length': length,
            'finetune': finetune,
            'volume': volume,
            'repeat_start': repeat_start,
            'repeat_length': repeat_length,
        })

    return samples_info


def read_mod_patterns(f, num_patterns, num_channels):
    """Lit les patterns du MOD

    Chaque pattern = 64 rows
    Chaque row = num_channels notes
    Chaque note = 4 bytes
    """
    patterns = []

    for pattern_num in range(num_patterns):
        cells = []

        for row in range(64):  # Toujours 64 rows dans MOD
            row_cells = []
            cells.append(row_cells)
            for channel in range(num_channels):
                # Lire 4 bytes pour cette note
                data = f.read(4)
                if len(data) < 4:
                    row_cells.append(None)
                    continue

                # Décoder les 4 bytes
                # Byte 0: sssspppp  s=sample high nibble, p=period high nibble
                # Byte 1: pppppppp  p=period low byte
                # Byte 2: ssssehhh  s=sample low nibble, e=effect, h=effect param high
                # Byte 3: hhhhhhhh  h=effect param low byte

                sample_high = (data[0] & 0xF0) >> 4
                period_high = (data[0] & 0x0F) << 8
                period_low = data[1]
                period = period_high | period_low

                sample_low = (data[2] & 0xF0) >> 4
                sample = (sample_high << 4) | sample_low

                effect = data[2] & 0x0F
                effect_param = data[3]

                # Case normalisée (même format que XM) ; sans numéro de sample, le canal
                # rejoue son dernier sample. Effet Cxx = volume de la ligne
                midi_note = period_to_midi(period) if period > 0 else None
                volume = min(effect_param, 64) if effect == 0xC else None
                if midi_note is None and not sample and volume is None and not effect and not effect_param:
                    row_cells.append(None)
                else:
                    row_cells.append(Cell(midi_note, sample or None, volume, effect, effect_param))

        patterns.append({
            'number': pattern_num,
            'rows': 64,
            'cells': cells
        })

    return patterns


def save_sample_as_wav(sample_data, output_path, sample_rate=8363):
    """Sauvegarde les données d'un sample en WAV (8-bit signé → 16-bit)"""
    if len(sample_data) == 0:
        return False

    # Convertir de 8-bit signé à 16-bit signé
    # Les samples MOD sont 8-bit signé (-128 à 127)
    # D'abord convertir bytes en uint8, puis réinterpréter comme int8
    sample_8bit = np.frombuffer(sample_data, dtype=np.uint8).astype(np.int8)
    sample_16bit = sample_8bit.astype(np.int16) * 256

    with wave.open(output_path, 'w') as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(sample_16bit.tobytes())

    return True


def extract_samples_and_patterns(mod_path, samples_dir):
    """Extrait les samples ET les patterns d'un fichier MOD

    Retourne: (samples, patterns, mod_info)
    Compatible avec la signature de xm_parser.py
    """
    samples = []
    patterns = []
    mod_info = None

    with open(mod_path, 'rb') as f:
        # Lire le titre (20 bytes)
        title = decode_name(f.read(20))

        # Lire les infos des samples (31 samples, même si format 15)
        samples_info = read_mod_samples_info(f, 31)

        # Lire song length et pattern order
        song_length = struct.unpack('B', f.read(1))[0]
        restart_pos = struct.unpack('B', f.read(1))[0]  # Ignoré généralement
        pattern_order = list(f.read(128))[:song_length]

        # Déterminer le nombre de patterns uniques
        num_patterns = max(pattern_order) + 1 if pattern_order else 0

        # Lire la signature pour déterminer le format
        signature = f.read(4).decode('ascii', errors='ignore')

        # Déterminer le nombre de samples et canaux
        if signature in ['M.K.', 'M!K!', 'FLT4', 'FLT8', '4CHN', '6CHN', '8CHN']:
            num_samples = 31
        else:
            num_samples = 15
            # Pas de signature, reculer de 4 bytes
            f.seek(-4, 1)

        # Déterminer le nombre de canaux
        if signature == 'FLT8' or signature == '8CHN':
            num_channels = 8
        elif signature == '6CHN':
            num_channels = 6
        else:
            num_channels = 4

        print(f"\nInfos: {num_samples} samples, {num_patterns} patterns, {num_channels} canaux")
        print(f"Signature: '{signature}' (format {'31-sample' if num_samples == 31 else '15-sample'})")

        # Lire les patterns
        print("\nLecture des patterns...")
        patterns = read_mod_patterns(f, num_patterns, num_channels)

        for i, pattern in enumerate(patterns):
            num_notes = sum(1 for row in pattern['cells'] for cell in row if cell and cell.note is not None)
            print(f"  Pattern {i+1}/{num_patterns}: 64 rows, {num_notes} notes")

        # Lire les données des samples
        print("\nLecture des samples...")
        for i in range(num_samples):
            sample_info = samples_info[i]

            if sample_info['length'] == 0:
                continue

            print(f"\nSample {i+1}: '{sample_info['name']}', {sample_info['length']} bytes")

            # Lire les données du sample (8-bit signé)
            sample_data = f.read(sample_info['length'])

            if len(sample_data) > 0:
                # Sauvegarder en WAV
                sample_name = sample_info['name'] if sample_info['name'] else f'Sample_{i+1:02d}'
                # Nettoyer le nom pour le filesystem
                safe_name = "".join(c for c in sample_name if c.isalnum() or c in (' ', '-', '_')).strip()
                if not safe_name:
                    safe_name = f'Sample_{i+1:02d}'

                # Nom fixe préfixé par le numéro de sample (hexa, comme dans ProTracker) :
                # unique par construction, une reconversion écrase au lieu d'empiler
                wav_name = f'{i+1:02X} {safe_name}.wav'
                wav_path = os.path.join(samples_dir, wav_name)

                if save_sample_as_wav(sample_data, wav_path):
                    print(f"    ✓ {wav_name}")

                    # Déterminer le type de loop
                    loop_type = 0  # Pas de loop par défaut
                    loop_start = 0
                    loop_length = 0

                    # Loop actif si > 1 word, et ramené dans le sample (valeurs parfois corrompues)
                    if sample_info['repeat_length'] > 2 and sample_info['repeat_start'] < len(sample_data):
                        loop_type = 1  # Forward loop (MOD n'a pas de ping-pong)
                        loop_start = sample_info['repeat_start']
                        loop_length = min(sample_info['repeat_length'], len(sample_data) - loop_start)

                    samples.append({
                        'instrument': i + 1,
                        'sample': 1,  # MOD n'a qu'un sample par instrument
                        'name': sample_info['name'].strip(),  # vide si le sample n'a pas de nom
                        'path': wav_path,
                        'relative_note': 0,  # MOD utilise finetune, pas relative_note
                        # Finetune MOD (-8..+7, en 1/8 de demi-ton) → échelle XM (1/128 de demi-ton)
                        'finetune': sample_info['finetune'] * 16,
                        'loop_start': loop_start,
                        'loop_length': loop_length,
                        'loop_type': loop_type,
                        'volume': sample_info['volume'],
                        'length': sample_info['length']  # Longueur en samples (pour effet 9xx)
                    })

        # Speed et BPM par défaut de ProTracker : les effets Fxx sont appliqués par
        # replayer.py là où ils apparaissent (y compris en cours de morceau)
        default_speed = 6
        default_bpm = 125

        mod_info = {
            'name': title,
            'channels': num_channels,
            'tempo': default_speed,
            'bpm': default_bpm,
            'pattern_order': pattern_order,
            'song_length': song_length
        }

    return samples, patterns, mod_info


# Fonction principale pour test
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 mod_parser.py <fichier.mod>")
        sys.exit(1)

    mod_path = sys.argv[1]
    samples_dir = './mod_samples_test'
    os.makedirs(samples_dir, exist_ok=True)

    print(f"Parsing de {mod_path}...")
    samples, patterns, mod_info = extract_samples_and_patterns(mod_path, samples_dir)

    print(f"\n{'='*60}")
    print(f"MODULE: {mod_info['name']}")
    print(f"Samples extraits: {len(samples)}")
    print(f"Patterns: {len(patterns)}")
    print(f"Canaux: {mod_info['channels']}")
    print(f"{'='*60}")
