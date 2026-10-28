#!/usr/bin/env python3
"""
Lecteur d'enveloppes volume pour fichiers XM (séparé du parser principal)
REWRITE: Copie exacte de la structure xm_parser.py pour éviter les bugs
"""

import struct


def read_xm_envelopes(xm_path):
    """Lit les enveloppes volume des instruments XM

    Returns:
        dict {instrument_num: envelope_info}
        où envelope_info = {'enabled', 'sustain_enabled', 'num_points', 'sustain_point', 'points'}
    """

    envelopes = {}

    try:
        with open(xm_path, 'rb') as f:
            # Skip header principal (60 bytes)
            f.read(60)

            # Lire les métadonnées
            header_size = struct.unpack('<I', f.read(4))[0]
            song_length = struct.unpack('<H', f.read(2))[0]
            f.read(2)  # restart pos
            num_channels = struct.unpack('<H', f.read(2))[0]
            num_patterns = struct.unpack('<H', f.read(2))[0]
            num_instruments = struct.unpack('<H', f.read(2))[0]
            f.read(2 + 2 + 2 + 256)  # flags, tempo, bpm, pattern order

            # Skip patterns (COPIE EXACTE de xm_parser.py)
            for i in range(num_patterns):
                pattern_header_len = struct.unpack('<I', f.read(4))[0]
                f.read(1)  # packing type
                num_rows = struct.unpack('<H', f.read(2))[0]
                packed_size = struct.unpack('<H', f.read(2))[0]

                remaining_header = pattern_header_len - 9
                if remaining_header > 0:
                    f.read(remaining_header)
                if packed_size > 0:
                    f.read(packed_size)

            # Lire les instruments (COPIE EXACTE de xm_parser.py)
            for inst_num in range(num_instruments):
                try:
                    inst_header_size = struct.unpack('<I', f.read(4))[0]

                    if inst_header_size < 29:
                        continue

                    inst_name = f.read(22).decode('ascii', errors='ignore').strip('\x00')
                    inst_type = struct.unpack('<B', f.read(1))[0]
                    num_samples = struct.unpack('<H', f.read(2))[0]

                    envelope_info = {
                        'enabled': False,
                        'sustain_enabled': False,
                        'num_points': 0,
                        'sustain_point': 0,
                        'points': []
                    }

                    if num_samples > 0 and num_samples < 256:
                        sample_header_size = struct.unpack('<I', f.read(4))[0]

                        # Lire les données d'enveloppe
                        note_map = f.read(96)  # Note-to-sample mapping

                        # Volume envelope points (12 points × 4 bytes)
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

                        # Vibrato + fadeout
                        f.read(6)

                        # Reserved (2 bytes)
                        f.read(2)

                        # Skip remaining instrument header
                        # bytes_read = TOUT ce qui est dans le header (inst_header_size S'INCLUT)
                        # inst_header_size (4) + inst_name (22) + inst_type (1) + num_samples (2)
                        # + sample_header_size (4) + note_map (96) + vol_env (48) + pan_env (48)
                        # + envelope_params (10) + vibrato+fadeout (6) + reserved (2)
                        bytes_read = 4 + 22 + 1 + 2 + 4 + 96 + 48 + 48 + 10 + 6 + 2  # = 243
                        remaining = inst_header_size - bytes_read
                        if remaining > 0:
                            f.read(remaining)

                        # Créer envelope_info
                        vol_enabled = vol_type & 0x01
                        vol_sustain_enabled = vol_type & 0x02

                        envelope_info = {
                            'enabled': bool(vol_enabled),
                            'sustain_enabled': bool(vol_sustain_enabled),
                            'num_points': num_vol_points,
                            'sustain_point': vol_sustain_point,
                            'points': vol_env_points[:num_vol_points] if vol_enabled else []
                        }

                        # Lire les headers de samples (COPIE EXACTE de xm_parser.py)
                        sample_headers = []
                        for j in range(num_samples):
                            sample_len = struct.unpack('<I', f.read(4))[0]
                            f.read(36)  # Skip le reste du header (36 bytes)
                            sample_headers.append({'length': sample_len})

                        # Skip les données des samples (COPIE EXACTE de xm_parser.py)
                        for j, header in enumerate(sample_headers):
                            if header['length'] > 0 and header['length'] < 10000000:
                                f.read(header['length'])

                    else:
                        # Pas de samples, skip tout le header
                        remaining = inst_header_size - 29
                        if remaining > 0:
                            f.read(remaining)

                    # Stocker l'enveloppe
                    envelopes[inst_num + 1] = envelope_info

                except Exception as e:
                    # En cas d'erreur, continuer silencieusement
                    continue

    except Exception as e:
        print(f"    ⚠️  Erreur lecture enveloppes: {e}")

    return envelopes
