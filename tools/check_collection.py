#!/usr/bin/env python3
"""
Convertit tous les modules d'un dossier (dans un dossier temporaire, effacé au fur et à mesure)
et signale les plantages et les erreurs du validateur.

Usage:
  python3 tools/check_collection.py [dossier] [--jobs 6] [--flags "--pan-automation --sample-offset"]
"""

import os
import sys
import shutil
import argparse
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOT = os.environ.get('XM2LIVE_MODULES', os.path.expanduser('~/Music/Compo/All Compo/Modules'))
SKIP_DIRS = {'doubles', 'Copie de DIVERS', 'Conversions Ableton Live', 'xm2live_converted_tracks'}


def find_modules(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith('_Ableton_Project')]
        for name in sorted(filenames):
            if name.lower().endswith(('.xm', '.mod')):
                yield os.path.join(dirpath, name)


def check(module_path, flags, work_root):
    """Convertit un module, retourne (statut, détail) ; statut = ok, validation ou plantage"""
    out_dir = tempfile.mkdtemp(dir=work_root)
    try:
        result = subprocess.run([sys.executable, os.path.join(PROJECT_DIR, 'xm2live.py'), module_path,
                                 *flags, '--output', out_dir],
                                capture_output=True, text=True, cwd=PROJECT_DIR, timeout=300)
        output = result.stdout + result.stderr
        if result.returncode != 0 or 'Traceback' in output:
            tail = [line for line in output.splitlines() if line.strip()][-3:]
            return 'plantage', ' | '.join(tail)
        errors = [line.strip() for line in output.splitlines() if line.strip().startswith('❌')]
        if errors:
            return 'validation', ' | '.join(errors[:3])
        return 'ok', ''
    except subprocess.TimeoutExpired:
        return 'plantage', 'timeout (300 s)'
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description='Conversion et validation de toute une collection')
    parser.add_argument('root', nargs='?', default=DEFAULT_ROOT)
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--flags', default='--pan-automation --sample-offset')
    args = parser.parse_args()

    modules = list(find_modules(args.root))
    work_root = tempfile.mkdtemp(prefix='xm2live_check_')
    print(f"{len(modules)} modules, {args.jobs} conversions en parallèle…")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda m: (m, *check(m, args.flags.split(), work_root)), modules))
    shutil.rmtree(work_root, ignore_errors=True)

    for status in ('plantage', 'validation'):
        failed = [(m, d) for m, s, d in results if s == status]
        for module, detail in failed:
            print(f"{'💥' if status == 'plantage' else '❌'} {os.path.relpath(module, args.root)}: {detail[:300]}")
    counts = {s: sum(1 for _, st, _ in results if st == s) for s in ('ok', 'validation', 'plantage')}
    print(f"\n{counts['ok']} OK, {counts['validation']} avec erreurs de validation, {counts['plantage']} plantage(s)")
    sys.exit(0 if counts['ok'] == len(results) else 1)


if __name__ == '__main__':
    main()
