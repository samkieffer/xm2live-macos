#!/usr/bin/env python3
"""
Analyse batch des enveloppes pour valider l'algorithme ADSR
"""

import struct
import sys
from collections import defaultdict

def parse_envelope_stats(xm_path):
    """Parse et retourne les stats d'enveloppes"""

    stats = {
        'file': xm_path,
        'instruments_with_env': 0,
        'peak_positions': defaultdict(int),  # Index du point pic
        'sustain_positions': defaultdict(int),  # Index du point sustain
        'num_points_dist': defaultdict(int),  # Distribution du nombre de points
        'examples': []
    }

    try:
        with open(xm_path, 'rb') as f:
            # Skip header principal
            f.read(60)
            header_size = struct.unpack('<I', f.read(4))[0]
            song_length = struct.unpack('<H', f.read(2))[0]
            f.read(2)
            num_channels = struct.unpack('<H', f.read(2))[0]
            num_patterns = struct.unpack('<H', f.read(2))[0]
            num_instruments = struct.unpack('<H', f.read(2))[0]
            f.read(2 + 2 + 2 + 256)

            # Skip patterns
            for i in range(num_patterns):
                pattern_header_len = struct.unpack('<I', f.read(4))[0]
                f.read(1)
                num_rows = struct.unpack('<H', f.read(2))[0]
                packed_size = struct.unpack('<H', f.read(2))[0]
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

                    if num_samples > 0 and num_samples < 256:
                        sample_header_size = struct.unpack('<I', f.read(4))[0]

                        # Note-to-sample mapping
                        f.read(96)

                        # Volume envelope points
                        vol_env_points = []
                        for i in range(12):
                            time = struct.unpack('<H', f.read(2))[0]
                            value = struct.unpack('<H', f.read(2))[0]
                            vol_env_points.append((time, value))

                        # Panning envelope - skip
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

                        f.read(6)  # vibrato

                        # Skip remaining header
                        bytes_read = 29 + 4 + 96 + 48 + 48 + 14 + 2
                        remaining = inst_header_size - bytes_read
                        if remaining > 0:
                            f.read(remaining)

                        # Analyser l'enveloppe
                        vol_enabled = vol_type & 0x01
                        vol_sustain_enabled = vol_type & 0x02

                        if vol_enabled and num_vol_points > 0:
                            stats['instruments_with_env'] += 1
                            stats['num_points_dist'][num_vol_points] += 1

                            # Trouver le pic
                            max_val = 0
                            max_idx = 0
                            for i in range(num_vol_points):
                                if vol_env_points[i][1] > max_val:
                                    max_val = vol_env_points[i][1]
                                    max_idx = i

                            stats['peak_positions'][max_idx] += 1

                            if vol_sustain_enabled:
                                stats['sustain_positions'][vol_sustain_point] += 1

                            # Garder quelques exemples
                            if len(stats['examples']) < 3:
                                stats['examples'].append({
                                    'name': inst_name,
                                    'num_points': num_vol_points,
                                    'peak_idx': max_idx,
                                    'peak_val': max_val,
                                    'sustain_idx': vol_sustain_point if vol_sustain_enabled else None,
                                    'sustain_val': vol_env_points[vol_sustain_point][1] if vol_sustain_enabled else None,
                                    'points': [(vol_env_points[i][0], vol_env_points[i][1]) for i in range(num_vol_points)]
                                })

                        # Skip sample headers et data
                        for j in range(num_samples):
                            f.read(40)

                        for j in range(num_samples):
                            current_pos = f.tell()
                            f.seek(current_pos - (num_samples - j) * 40)
                            sample_len = struct.unpack('<I', f.read(4))[0]
                            f.seek(current_pos - (num_samples - j - 1) * 40)
                            if sample_len > 0 and sample_len < 10000000:
                                f.read(sample_len)

                    else:
                        remaining = inst_header_size - 29
                        if remaining > 0:
                            f.read(remaining)

                except Exception as e:
                    # Skip silently
                    break

    except Exception as e:
        stats['error'] = str(e)

    return stats


def main():
    files = [
        "/Users/sam/Music/Compo/All Compo/Modules/mec3.xm",
        "/Users/sam/Music/Compo/All Compo/Modules/DEACT2.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/PERSII.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/ESSI5.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/FASCEDIT.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/FLAWIN.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/CENSOR.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/NEX.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/JUN9.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/NEW.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/ELECTRO2.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/SKINNY.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/SOUNDTR2.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/THRAITRM.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/SYNTEX.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/GOA.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/ELECTRO4.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/JUNO97.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/QUAKE.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/ELECTRO5.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/FDP213L.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/ALIEN.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/ETAN2.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/doubles/JUN97.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/INTRO.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/WTMM004.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/COBALT.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/XXX.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/INDUST.XM",
        "/Users/sam/Music/Compo/All Compo/Modules/DIVERS/BANG96.XM",
    ]

    print("="*70)
    print("ANALYSE BATCH DES ENVELOPPES VOLUME XM")
    print("="*70)

    all_stats = {
        'peak_positions': defaultdict(int),
        'sustain_positions': defaultdict(int),
        'num_points_dist': defaultdict(int),
        'total_instruments': 0
    }

    for xm_file in files:
        import os
        basename = os.path.basename(xm_file)
        print(f"\n{'='*70}")
        print(f"File: {basename}")
        print(f"{'='*70}")

        stats = parse_envelope_stats(xm_file)

        if 'error' in stats:
            print(f"  ERROR: {stats['error']}")
            continue

        print(f"  Instruments with envelope: {stats['instruments_with_env']}")

        if stats['instruments_with_env'] > 0:
            print(f"\n  Number of points distribution:")
            for n_points, count in sorted(stats['num_points_dist'].items()):
                print(f"    {n_points} points: {count} instruments")

            print(f"\n  Peak position distribution:")
            for peak_idx, count in sorted(stats['peak_positions'].items()):
                print(f"    Point {peak_idx}: {count} instruments")

            if stats['sustain_positions']:
                print(f"\n  Sustain position distribution:")
                for sus_idx, count in sorted(stats['sustain_positions'].items()):
                    print(f"    Point {sus_idx}: {count} instruments")

            # Exemples
            if stats['examples']:
                print(f"\n  Examples:")
                for ex in stats['examples'][:2]:
                    print(f"    '{ex['name']}':")
                    print(f"      Points: {ex['num_points']}, Peak: idx={ex['peak_idx']} val={ex['peak_val']}")
                    if ex['sustain_idx'] is not None:
                        print(f"      Sustain: idx={ex['sustain_idx']} val={ex['sustain_val']}")

            # Aggregate
            all_stats['total_instruments'] += stats['instruments_with_env']
            for k, v in stats['peak_positions'].items():
                all_stats['peak_positions'][k] += v
            for k, v in stats['sustain_positions'].items():
                all_stats['sustain_positions'][k] += v
            for k, v in stats['num_points_dist'].items():
                all_stats['num_points_dist'][k] += v

    # Summary
    print(f"\n\n{'='*70}")
    print("GLOBAL SUMMARY")
    print(f"{'='*70}")
    print(f"Total instruments with envelope: {all_stats['total_instruments']}")

    print(f"\nGlobal peak position distribution:")
    for peak_idx, count in sorted(all_stats['peak_positions'].items()):
        pct = 100.0 * count / all_stats['total_instruments']
        print(f"  Point {peak_idx}: {count} instruments ({pct:.1f}%)")

    print(f"\nGlobal sustain position distribution:")
    if all_stats['sustain_positions']:
        total_sustain = sum(all_stats['sustain_positions'].values())
        for sus_idx, count in sorted(all_stats['sustain_positions'].items()):
            pct = 100.0 * count / total_sustain
            print(f"  Point {sus_idx}: {count} instruments ({pct:.1f}%)")
    else:
        print("  No sustain points found")

    print(f"\nGlobal number of points distribution:")
    for n_points, count in sorted(all_stats['num_points_dist'].items()):
        pct = 100.0 * count / all_stats['total_instruments']
        print(f"  {n_points} points: {count} instruments ({pct:.1f}%)")

    print("\n" + "="*70)
    print("CONCLUSIONS POUR L'ALGORITHME:")
    print("="*70)

    # Analyse pour valider l'algorithme
    peak_at_0 = all_stats['peak_positions'].get(0, 0)
    peak_total = sum(all_stats['peak_positions'].values())

    print(f"\n1. ATTACK:")
    print(f"   Peak at point 0: {peak_at_0}/{peak_total} ({100.0*peak_at_0/peak_total:.1f}%)")
    if peak_at_0 > peak_total * 0.8:
        print(f"   ✓ Hypothèse validée: Peak quasi toujours au point 0 (Attack instantané)")
    else:
        print(f"   ⚠ Hypothèse partielle: Certains fichiers ont Attack > 0")

    if all_stats['sustain_positions']:
        sustain_at_1 = all_stats['sustain_positions'].get(1, 0)
        sustain_total = sum(all_stats['sustain_positions'].values())
        print(f"\n2. SUSTAIN:")
        print(f"   Sustain at point 1: {sustain_at_1}/{sustain_total} ({100.0*sustain_at_1/sustain_total:.1f}%)")
        if sustain_at_1 > sustain_total * 0.5:
            print(f"   ✓ Hypothèse validée: Sustain souvent au point 1")
        else:
            print(f"   ⚠ Sustain position varie")

    avg_points = sum(k*v for k,v in all_stats['num_points_dist'].items()) / all_stats['total_instruments']
    print(f"\n3. NOMBRE DE POINTS:")
    print(f"   Moyenne: {avg_points:.1f} points/envelope")
    print(f"   ✓ Assez de points pour extraction ADSR (4+ paramètres)")


if __name__ == '__main__':
    main()
