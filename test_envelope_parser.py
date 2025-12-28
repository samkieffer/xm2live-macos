#!/usr/bin/env python3
"""
Script de test pour parser les enveloppes volume des instruments XM
"""

import struct
import sys

def parse_xm_envelopes(xm_path):
    """Parse et affiche les enveloppes volume des instruments XM"""

    with open(xm_path, 'rb') as f:
        # Skip header principal
        f.read(60)  # ID + module info
        header_size = struct.unpack('<I', f.read(4))[0]
        song_length = struct.unpack('<H', f.read(2))[0]
        f.read(2)  # restart pos
        num_channels = struct.unpack('<H', f.read(2))[0]
        num_patterns = struct.unpack('<H', f.read(2))[0]
        num_instruments = struct.unpack('<H', f.read(2))[0]
        f.read(2)  # flags
        default_tempo = struct.unpack('<H', f.read(2))[0]
        default_bpm = struct.unpack('<H', f.read(2))[0]
        f.read(256)  # pattern order

        print(f"XM File: {num_instruments} instruments, {num_patterns} patterns")
        print("="*70)

        # Skip patterns (lecture rapide)
        for i in range(num_patterns):
            pattern_header_len = struct.unpack('<I', f.read(4))[0]
            f.read(1)  # packing type
            num_rows = struct.unpack('<H', f.read(2))[0]
            packed_size = struct.unpack('<H', f.read(2))[0]

            # Skip reste du header + données
            remaining_header = pattern_header_len - 9
            if remaining_header > 0:
                f.read(remaining_header)
            if packed_size > 0:
                f.read(packed_size)

        # Lire les instruments
        for inst_num in range(num_instruments):
            try:
                inst_header_size = struct.unpack('<I', f.read(4))[0]

                if inst_header_size < 29:
                    continue

                inst_name = f.read(22).decode('ascii', errors='ignore').strip('\x00')
                inst_type = struct.unpack('<B', f.read(1))[0]
                num_samples = struct.unpack('<H', f.read(2))[0]

                print(f"\n{'='*70}")
                print(f"Instrument {inst_num+1}: '{inst_name}'")
                print(f"  Samples: {num_samples}")
                print(f"  Header size: {inst_header_size} bytes")

                if num_samples > 0 and num_samples < 256:
                    sample_header_size = struct.unpack('<I', f.read(4))[0]

                    # LIRE LES DONNÉES D'ENVELOPPE (au lieu de les skip)
                    # Note-to-sample mapping (96 bytes)
                    note_map = f.read(96)

                    # Volume envelope points (12 points × 4 bytes)
                    vol_env_points = []
                    for i in range(12):
                        time = struct.unpack('<H', f.read(2))[0]
                        value = struct.unpack('<H', f.read(2))[0]
                        vol_env_points.append((time, value))

                    # Panning envelope points (12 points × 4 bytes) - skip pour l'instant
                    f.read(48)

                    # Envelope parameters
                    num_vol_points = struct.unpack('<B', f.read(1))[0]
                    num_pan_points = struct.unpack('<B', f.read(1))[0]
                    vol_sustain_point = struct.unpack('<B', f.read(1))[0]
                    vol_loop_start = struct.unpack('<B', f.read(1))[0]
                    vol_loop_end = struct.unpack('<B', f.read(1))[0]
                    pan_sustain_point = struct.unpack('<B', f.read(1))[0]
                    pan_loop_start = struct.unpack('<B', f.read(1))[0]
                    pan_loop_end = struct.unpack('<B', f.read(1))[0]
                    vol_type = struct.unpack('<B', f.read(1))[0]
                    pan_type = struct.unpack('<B', f.read(1))[0]

                    # Vibrato + fadeout
                    vibrato_type = struct.unpack('<B', f.read(1))[0]
                    vibrato_sweep = struct.unpack('<B', f.read(1))[0]
                    vibrato_depth = struct.unpack('<B', f.read(1))[0]
                    vibrato_rate = struct.unpack('<B', f.read(1))[0]
                    volume_fadeout = struct.unpack('<H', f.read(2))[0]

                    # Reserved (2 bytes) - mais seulement si header_size le permet
                    bytes_read = 29 + 4 + 96 + 48 + 48 + 14 + 2  # = 241
                    remaining = inst_header_size - bytes_read
                    if remaining > 0:
                        f.read(remaining)

                    # Afficher les infos d'enveloppe
                    vol_enabled = vol_type & 0x01
                    vol_sustain_enabled = vol_type & 0x02
                    vol_loop_enabled = vol_type & 0x04

                    print(f"\n  Volume Envelope:")
                    print(f"    Enabled: {bool(vol_enabled)}")
                    print(f"    Sustain: {bool(vol_sustain_enabled)} (point #{vol_sustain_point})")
                    print(f"    Loop: {bool(vol_loop_enabled)} (points {vol_loop_start}-{vol_loop_end})")
                    print(f"    Num points: {num_vol_points}")
                    print(f"    Fadeout: {volume_fadeout}")

                    if vol_enabled and num_vol_points > 0:
                        print(f"\n  Envelope Points (first {num_vol_points}):")
                        for i in range(num_vol_points):
                            time, value = vol_env_points[i]
                            marker = ""
                            if i == vol_sustain_point and vol_sustain_enabled:
                                marker = " ← SUSTAIN"
                            if i == vol_loop_start and vol_loop_enabled:
                                marker += " ← LOOP START"
                            if i == vol_loop_end and vol_loop_enabled:
                                marker += " ← LOOP END"
                            print(f"    Point {i}: time={time:5d} ticks, value={value:3d}/64{marker}")

                        # Analyser pour ADSR
                        print(f"\n  Analysis pour ADSR:")

                        # Trouver le pic (valeur max)
                        max_val = 0
                        max_idx = 0
                        for i in range(num_vol_points):
                            if vol_env_points[i][1] > max_val:
                                max_val = vol_env_points[i][1]
                                max_idx = i

                        print(f"    Peak: Point {max_idx} (time={vol_env_points[max_idx][0]}, val={max_val})")

                        if vol_sustain_enabled:
                            sustain_time = vol_env_points[vol_sustain_point][0]
                            sustain_val = vol_env_points[vol_sustain_point][1]
                            print(f"    Sustain: Point {vol_sustain_point} (time={sustain_time}, val={sustain_val})")
                        else:
                            print(f"    Sustain: Not defined")

                        last_point_idx = num_vol_points - 1
                        last_time = vol_env_points[last_point_idx][0]
                        last_val = vol_env_points[last_point_idx][1]
                        print(f"    Last: Point {last_point_idx} (time={last_time}, val={last_val})")

                    # Skip sample headers et data
                    for j in range(num_samples):
                        f.read(40)  # sample header

                    for j in range(num_samples):
                        # Relire le header pour connaître la taille
                        current_pos = f.tell()
                        f.seek(current_pos - (num_samples - j) * 40)
                        sample_len = struct.unpack('<I', f.read(4))[0]
                        f.seek(current_pos - (num_samples - j - 1) * 40)

                        # Skip sample data
                        if sample_len > 0 and sample_len < 10000000:
                            f.read(sample_len)

                else:
                    # Pas de samples, skip le reste du header
                    remaining = inst_header_size - 29
                    if remaining > 0:
                        f.read(remaining)

            except Exception as e:
                print(f"\n  ERROR parsing instrument {inst_num+1}: {e}")
                import traceback
                traceback.print_exc()
                break

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 test_envelope_parser.py <file.xm>")
        sys.exit(1)

    parse_xm_envelopes(sys.argv[1])
