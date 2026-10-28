#!/usr/bin/env python3
"""
Rendu de référence d'un module avec OpenMPT (très fidèle à FT2 et ProTracker)

Usage:
  python3 tools/render_reference.py module.xm [sortie.wav]

Par défaut, écrit <module>_openmpt.wav dans le dossier courant (jamais à côté du module).
Nécessite openmpt123 (brew install libopenmpt).
"""

import os
import sys
import struct
import shutil
import subprocess


def initial_bpm(module_path):
    """BPM initial du module (en-tête XM ; 125 par défaut pour les MOD)"""
    with open(module_path, 'rb') as f:
        header = f.read(80)
    if header.startswith(b'Extended Module:'):
        return struct.unpack_from('<H', header, 78)[0] or 125
    return 125


def exact_samplerate(bpm, target=48000):
    """Fréquence proche de target donnant un nombre entier d'échantillons par tick

    OpenMPT tronque la durée d'un tick (rate × 2.5 / BPM) à un entier : à 48 kHz et 137 BPM,
    875.9 → 875, soit 0.1 % trop rapide (~0.3 s sur 4 min 26). Avec rate = 2 × BPM × n,
    la division tombe juste (137 BPM → 47950 Hz → 875 échantillons par tick).
    """
    step = 2 * bpm
    return step * max(1, round(target / step))


def render_reference(module_path, wav_path, samplerate=None):
    """Rend le module en WAV 16 bits stéréo, une seule lecture (pas de boucle)"""
    openmpt = shutil.which('openmpt123')
    if openmpt is None:
        raise RuntimeError("openmpt123 introuvable (brew install libopenmpt)")
    samplerate = samplerate or exact_samplerate(initial_bpm(module_path))
    subprocess.run([openmpt, '--batch', '--quiet', '--samplerate', str(samplerate), '--no-float',
                    '--force', '-o', wav_path, module_path], check=True)
    return wav_path


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    module = sys.argv[1]
    stem = os.path.splitext(os.path.basename(module))[0]
    output = sys.argv[2] if len(sys.argv) > 2 else f"{stem}_openmpt.wav"
    print(f"✓ {render_reference(module, output)}")
