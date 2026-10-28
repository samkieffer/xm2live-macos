#!/usr/bin/env python3
"""
Module de parsing de fichiers FastTracker 2 Extended Module (.xm)
Extrait les samples, patterns et notes MIDI
"""

import sys
import os
import struct
import wave
import numpy as np
from pathlib import Path

from replayer import Cell, KEY_OFF


def decode_name(raw):
    """Texte lisible d'un champ nom du module (sans octets nuls ni caractères de contrôle,
    que le XML d'Ableton refuse)"""
    return ''.join(c for c in raw.decode('ascii', errors='ignore') if c.isprintable())


def read_xm_header(filepath):
    """Lit les infos de base du fichier XM"""
    with open(filepath, 'rb') as f:
        id_text = f.read(17).decode('ascii', errors='ignore')
        if not id_text.startswith("Extended Module"):
            return None

        module_name = f.read(20).decode('ascii', errors='ignore').strip('\x00')
        f.read(1)  # 0x1a
        tracker_name = f.read(20).decode('ascii', errors='ignore').strip('\x00')

        f.read(2)  # version
        f.read(4)  # header size

        song_length = int.from_bytes(f.read(2), 'little')
        restart_pos = int.from_bytes(f.read(2), 'little')
        num_channels = int.from_bytes(f.read(2), 'little')
        num_patterns = int.from_bytes(f.read(2), 'little')
        num_instruments = int.from_bytes(f.read(2), 'little')
        flags = int.from_bytes(f.read(2), 'little')
        default_tempo = int.from_bytes(f.read(2), 'little')
        default_bpm = int.from_bytes(f.read(2), 'little')

        pattern_order = list(f.read(256))[:song_length]

        return {
            'name': module_name,
            'tracker': tracker_name,
            'song_length': song_length,
            'channels': num_channels,
            'patterns': num_patterns,
            'instruments': num_instruments,
            'tempo': default_tempo,
            'bpm': default_bpm,
            'pattern_order': pattern_order
        }


def parse_pattern_data(data, num_rows, num_channels):
    """Parse les données d'un pattern XM en grille de cases (Cell, ou None si la case est vide)

    L'interprétation musicale (instrument du canal, délais, sauts, tempo) est faite par replayer.py.
    """
    rows = []
    pos = 0

    for row in range(num_rows):
        row_cells = []
        rows.append(row_cells)
        for channel in range(num_channels):
            if pos >= len(data):
                row_cells.append(None)
                continue

            # Lire le premier byte
            note_byte = data[pos]
            pos += 1

            note = None
            instrument = None
            volume = None
            effect_type = None
            effect_param = None

            if note_byte & 0x80:  # Packed note
                if note_byte & 0x01:  # Note présente
                    if pos < len(data):
                        note = data[pos]
                        pos += 1

                if note_byte & 0x02:  # Instrument présent
                    if pos < len(data):
                        instrument = data[pos]
                        pos += 1

                if note_byte & 0x04:  # Volume présent
                    if pos < len(data):
                        volume = data[pos]
                        pos += 1

                if note_byte & 0x08:  # Effect type présent
                    if pos < len(data):
                        effect_type = data[pos]
                        pos += 1

                if note_byte & 0x10:  # Effect param présent
                    if pos < len(data):
                        effect_param = data[pos]
                        pos += 1
            else:  # Unpacked note (5 bytes)
                note = note_byte
                if pos + 3 < len(data):
                    instrument = data[pos]
                    volume = data[pos + 1]
                    effect_type = data[pos + 2]
                    effect_param = data[pos + 3]
                    pos += 4

            # Décoder la colonne volume XM (0x10-0x50 = volume 0-64)
            decoded_volume = None
            if volume is not None:
                if 0x10 <= volume <= 0x50:
                    decoded_volume = volume - 0x10  # 0x10 -> 0, 0x50 -> 64
                # Ignorer les autres valeurs (0x00-0x0F, 0x60+ sont des commandes spéciales)

            # Effet Cxx (Set Volume) : FT2 l'applique après la colonne volume, il est donc prioritaire
            if effect_type == 0x0C:
                decoded_volume = min(effect_param or 0, 64)

            # Convertir la note XM (1-96) en MIDI : note 1 = C-0, note 49 = C-4 → MIDI 60 ; 97 = key-off
            midi_note = None
            if note == 97:
                midi_note = KEY_OFF
            elif note and 0 < note < 97:
                midi_note = note - 1 + 12

            effect, param = effect_type or 0, effect_param or 0
            if midi_note is None and not instrument and decoded_volume is None and not effect and not param:
                row_cells.append(None)
            else:
                row_cells.append(Cell(midi_note, instrument or None, decoded_volume, effect, param))

    return rows


def read_patterns(f, num_patterns, num_channels):
    """Lit tous les patterns du XM"""
    patterns = []

    for i in range(num_patterns):
        try:
            pattern_header_len = struct.unpack('<I', f.read(4))[0]
            packing_type = struct.unpack('<B', f.read(1))[0]
            num_rows = struct.unpack('<H', f.read(2))[0]
            packed_size = struct.unpack('<H', f.read(2))[0]

            # Skip reste du header
            remaining_header = pattern_header_len - 9
            if remaining_header > 0:
                f.read(remaining_header)

            # Lire les données du pattern (packed_size 0 = pattern vide)
            cells = []
            if packed_size > 0:
                data = f.read(packed_size)
                cells = parse_pattern_data(data, num_rows, num_channels)

            patterns.append({
                'number': i,
                'rows': num_rows,
                'cells': cells
            })

            num_notes = sum(1 for row in cells for cell in row if cell and cell.note is not None)
            print(f"  Pattern {i+1}/{num_patterns}: {num_rows} rows, {num_notes} notes")

        except Exception as e:
            print(f"  Erreur pattern {i+1}: {e}")
            patterns.append({'number': i, 'rows': 64, 'cells': []})

    return patterns


def extract_samples_and_patterns(xm_path, samples_dir):
    """Extrait les samples ET les patterns du XM"""
    samples = []
    patterns = []
    xm_info = None

    with open(xm_path, 'rb') as f:
        # Lire le header principal
        id_text = f.read(17)
        if not id_text.startswith(b'Extended Module'):
            print(f"❌ Ce n'est pas un fichier FastTracker 2 XM (en-tête: {id_text[:16]!r})")
            return samples, patterns, xm_info
        module_name = decode_name(f.read(20))
        f.read(1)  # 0x1a
        tracker_name = f.read(20)
        version = struct.unpack('<H', f.read(2))[0]

        header_size = struct.unpack('<I', f.read(4))[0]
        song_length = struct.unpack('<H', f.read(2))[0]
        restart_pos = struct.unpack('<H', f.read(2))[0]
        num_channels = struct.unpack('<H', f.read(2))[0]
        num_patterns = struct.unpack('<H', f.read(2))[0]
        num_instruments = struct.unpack('<H', f.read(2))[0]
        flags = struct.unpack('<H', f.read(2))[0]
        default_tempo = struct.unpack('<H', f.read(2))[0]
        default_bpm = struct.unpack('<H', f.read(2))[0]
        pattern_order = list(f.read(256))[:song_length]

        xm_info = {
            'name': module_name,
            'channels': num_channels,
            'tempo': default_tempo or 6,  # Speed (ticks par row) ; 0 invalide → défaut FT2
            'bpm': default_bpm or 125,
            'pattern_order': pattern_order,
            'song_length': song_length
        }

        print(f"\nInfos: {num_instruments} instruments, {num_patterns} patterns, {num_channels} canaux")

        # Lire les patterns
        print("\nLecture des patterns...")
        patterns = read_patterns(f, num_patterns, num_channels)

        # Lire les instruments et samples
        print("\nLecture des instruments...")
        for inst_num in range(num_instruments):
            try:
                inst_header_size = struct.unpack('<I', f.read(4))[0]

                if inst_header_size < 29:
                    continue

                inst_name = decode_name(f.read(22))
                inst_type = struct.unpack('<B', f.read(1))[0]
                num_samples = struct.unpack('<H', f.read(2))[0]

                print(f"\nInstrument {inst_num+1}: '{inst_name}', {num_samples} samples")

                if num_samples > 0 and num_samples < 256:
                    sample_header_size = struct.unpack('<I', f.read(4))[0]

                    remaining = inst_header_size - 33
                    if remaining > 0:
                        f.read(remaining)

                    # Lire les headers de samples
                    sample_headers = []
                    for j in range(num_samples):
                        sample_len = struct.unpack('<I', f.read(4))[0]
                        loop_start = struct.unpack('<I', f.read(4))[0]
                        loop_len = struct.unpack('<I', f.read(4))[0]
                        volume = struct.unpack('<B', f.read(1))[0]
                        finetune = struct.unpack('<b', f.read(1))[0]
                        sample_type = struct.unpack('<B', f.read(1))[0]
                        panning = struct.unpack('<B', f.read(1))[0]
                        relative_note = struct.unpack('<b', f.read(1))[0]
                        reserved = struct.unpack('<B', f.read(1))[0]
                        sample_name = decode_name(f.read(22))

                        sample_headers.append({
                            'length': sample_len,
                            'loop_start': loop_start,
                            'loop_length': loop_len,
                            'volume': volume,
                            'type': sample_type,
                            'name': sample_name or inst_name or f"Sample_{inst_num+1}_{j+1}",
                            'relative_note': relative_note,
                            'finetune': finetune,  # -128 à +127 (1/128 de demi-ton)
                            'panning': panning  # 0-255 (0=gauche, 128=centre, 255=droite)
                        })

                    # Lire les données des samples
                    for j, header in enumerate(sample_headers):
                        if header['length'] > 0 and header['length'] < 10000000:
                            sample_data = f.read(header['length'])

                            is_16bit = header['type'] & 0x10

                            if is_16bit:
                                data = np.frombuffer(sample_data, dtype=np.int16)
                            else:
                                data = np.frombuffer(sample_data, dtype=np.int8).astype(np.int16) * 256

                            # Delta decode (avec gestion naturelle du wrapping)
                            if len(data) > 0:
                                decoded = np.zeros(len(data), dtype=np.int16)
                                current = 0  # Utiliser int natif pour éviter overflow warning
                                for k in range(len(data)):
                                    current = (current + int(data[k])) & 0xFFFF  # Wrapping 16-bit
                                    # Convertir en int16 signé
                                    if current >= 32768:
                                        decoded[k] = current - 65536
                                    else:
                                        decoded[k] = current

                                # Save as WAV
                                # Nom fixe préfixé par le numéro d'instrument (hexa, comme dans FT2) :
                                # unique par construction, une reconversion écrase au lieu d'empiler
                                safe_name = "".join(c for c in header['name'] if c.isalnum() or c in (' ', '_', '-', ',')).strip()
                                prefix = f"{inst_num+1:02X}" if num_samples == 1 else f"{inst_num+1:02X}-{j+1}"
                                safe_name = f"{prefix} {safe_name or 'Sample'}"

                                wav_path = os.path.join(samples_dir, f"{safe_name}.wav")

                                with wave.open(wav_path, 'w') as wav:
                                    wav.setnchannels(1)
                                    wav.setsampwidth(2)
                                    wav.setframerate(8363)
                                    wav.writeframes(decoded.tobytes())

                                # Le XM stocke les boucles en octets : /2 pour obtenir des frames en 16-bit
                                loop_start = header['loop_start'] // 2 if is_16bit else header['loop_start']
                                loop_length = header['loop_length'] // 2 if is_16bit else header['loop_length']
                                loop_type = header['type'] & 0x03  # Bits 0-1: 0=off, 1=forward, 2=ping-pong
                                # Comme FT2 : boucle ramenée dans le sample, désactivée si vide
                                loop_length = min(loop_length, len(decoded) - loop_start)
                                if loop_length <= 0:
                                    loop_type, loop_start, loop_length = 0, 0, 0

                                samples.append({
                                    'instrument': inst_num + 1,
                                    'sample': j + 1,
                                    'name': header['name'],
                                    'path': wav_path,
                                    'relative_note': header['relative_note'],
                                    'finetune': header['finetune'],  # -128 à +127 (1/128 de demi-ton)
                                    'loop_start': loop_start,
                                    'loop_length': loop_length,
                                    'loop_type': loop_type,
                                    'volume': header['volume'],
                                    'panning': header['panning'],  # 0-255 (0=gauche, 128=centre, 255=droite)
                                    'length': len(decoded)  # Longueur en samples (pour effet 9xx)
                                })

                                print(f"    ✓ {safe_name}")
                else:
                    remaining = inst_header_size - 29
                    if remaining > 0:
                        f.read(remaining)

            except Exception as e:
                print(f"  Erreur instrument {inst_num+1}: {e}")
                continue

    return samples, patterns, xm_info

