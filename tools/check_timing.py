#!/usr/bin/env python3
"""
Compare le déroulé de chaque module, ligne par ligne, entre replayer.py et OpenMPT

Pour chaque ligne jouée : (ordre, ligne, speed, BPM). Une séquence identique garantit le même
déroulé (Bxx, Dxx, E6x, EEx) et les mêmes changements de tempo (Fxx) qu'OpenMPT, lui-même calé
sur FT2. La référence est tracée en lisant la position de libopenmpt pendant la lecture.

Usage:
  python3 tools/check_timing.py [dossier ou fichier] [--jobs 8]
"""

import io
import os
import sys
import ctypes
import ctypes.util
import shutil
import argparse
import tempfile
import contextlib
from concurrent.futures import ProcessPoolExecutor

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from replayer import play_song  # noqa: E402
from xm_parser import extract_samples_and_patterns as extract_xm  # noqa: E402
from mod_parser import extract_samples_and_patterns as extract_mod  # noqa: E402
from check_collection import DEFAULT_ROOT, find_modules  # noqa: E402

TRACE_RATE = 8000  # fréquence de rendu de la trace : seule la position compte, pas le son
TRACE_CHUNK = 8    # 1 ms entre deux lectures de position


def load_libopenmpt():
    path = ctypes.util.find_library('openmpt') or '/opt/homebrew/lib/libopenmpt.dylib'
    lib = ctypes.CDLL(path)
    lib.openmpt_module_create_from_memory2.restype = ctypes.c_void_p
    lib.openmpt_module_create_from_memory2.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_void_p, ctypes.c_void_p]
    for name in ('get_current_order', 'get_current_row', 'get_current_speed'):
        getattr(lib, f'openmpt_module_{name}').argtypes = [ctypes.c_void_p]
        getattr(lib, f'openmpt_module_{name}').restype = ctypes.c_int32
    lib.openmpt_module_get_current_tempo2.argtypes = [ctypes.c_void_p]
    lib.openmpt_module_get_current_tempo2.restype = ctypes.c_double
    lib.openmpt_module_read_mono.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_size_t,
                                             ctypes.POINTER(ctypes.c_int16)]
    lib.openmpt_module_read_mono.restype = ctypes.c_size_t
    lib.openmpt_module_destroy.argtypes = [ctypes.c_void_p]
    return lib


def openmpt_rows(module_path):
    """Lignes jouées par libopenmpt : [(ordre, ligne, speed, bpm)], ou None si illisible"""
    lib = load_libopenmpt()
    data = open(module_path, 'rb').read()
    error = ctypes.c_int(0)
    module = lib.openmpt_module_create_from_memory2(data, len(data), None, None, None, None,
                                                    ctypes.byref(error), None, None)
    if not module:
        return None
    buffer = (ctypes.c_int16 * TRACE_CHUNK)()
    rows, last = [], None
    # Position lue après chaque bloc rendu ; vitesse et tempo retenus sont ceux de la fin de la
    # ligne (ProTracker n'applique un nouveau BPM qu'au tick suivant le Fxx)
    while lib.openmpt_module_read_mono(module, TRACE_RATE, TRACE_CHUNK, buffer):
        position = (lib.openmpt_module_get_current_order(module), lib.openmpt_module_get_current_row(module))
        current = position + (lib.openmpt_module_get_current_speed(module),
                              round(lib.openmpt_module_get_current_tempo2(module)))
        if position != last:
            rows.append(current)
            last = position
        else:
            rows[-1] = current
    lib.openmpt_module_destroy(module)
    # Le dernier bloc peut déjà pointer sur la position de bouclage du morceau
    if len(rows) > 1 and rows[-1][:2] in {r[:2] for r in rows[:-1]}:
        rows.pop()
    return rows


def replayer_rows(module_path):
    """Lignes jouées par replayer.play_song : ([(ordre, ligne, speed, bpm)], secondes), ou None"""
    work_dir = tempfile.mkdtemp(prefix='xm2live_timing_')
    is_mod = module_path.lower().endswith('.mod')
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            samples, patterns, info = (extract_mod if is_mod else extract_xm)(module_path, work_dir)
        if info is None:
            return None
        song = play_song(patterns, info['pattern_order'], info['tempo'], info['bpm'], 'mod' if is_mod else 'xm')
        # Un ordre pointant vers un pattern absent : FT2 (et replayer.py) jouent 64 lignes vides,
        # OpenMPT saute l'ordre. Ces lignes sont retirées de la comparaison
        rows = [r for r in song['played_rows'] if info['pattern_order'][r[0]] < len(patterns)]
        return rows, song['duration_seconds']
    except Exception:
        return None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def compare(module_path):
    """Retourne (module, statut, détail) ; statut = ok, différent ou illisible"""
    ours, reference = replayer_rows(module_path), openmpt_rows(module_path)
    if ours is None or reference is None:
        return module_path, 'illisible', ''
    rows, seconds = ours
    if rows == reference:
        return module_path, 'ok', f"{len(rows)} lignes, {seconds:.1f} s"
    index = next((i for i, (a, b) in enumerate(zip(rows, reference)) if a != b), min(len(rows), len(reference)))
    ours_at = rows[index] if index < len(rows) else 'fin'
    theirs_at = reference[index] if index < len(reference) else 'fin'
    return module_path, 'différent', (f"ligne jouée n° {index} : replayer {ours_at}, OpenMPT {theirs_at} "
                                      f"(précédente {rows[index - 1] if index else '-'}) ; "
                                      f"{len(rows)} lignes contre {len(reference)}")


def main():
    parser = argparse.ArgumentParser(description='Déroulé ligne par ligne : replayer vs OpenMPT')
    parser.add_argument('root', nargs='?', default=DEFAULT_ROOT)
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()

    modules = [args.root] if os.path.isfile(args.root) else list(find_modules(args.root))
    base = os.path.dirname(args.root) if os.path.isfile(args.root) else args.root
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(compare, modules))

    for status in ('différent', 'illisible'):
        for module, st, detail in results:
            if st == status:
                print(f"{'≠' if status == 'différent' else '?'} {os.path.relpath(module, base)}: {detail}")
    counts = {s: sum(1 for _, st, _ in results if st == s) for s in ('ok', 'différent', 'illisible')}
    if len(results) == 1 and counts['ok']:
        print(f"= {results[0][2]}")
    print(f"\n{counts['ok']} identiques, {counts['différent']} différents, {counts['illisible']} illisibles"
          f" (sur {len(results)})")
    sys.exit(0 if counts['différent'] == 0 else 1)


if __name__ == '__main__':
    main()
