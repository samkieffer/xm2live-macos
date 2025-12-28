#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sam/xm2live')
from xm2live import read_xm_header

xm_file = '/Users/sam/Music/Compo/All Compo/Modules/censor.xm'

print(f"Lecture de: {xm_file}")
info = read_xm_header(xm_file)

if info:
    print(f"\nModule: {info['name']}")
    print(f"BPM: {info['bpm']}")
    print(f"Tempo: {info['tempo']}")
else:
    print("Erreur de lecture")
