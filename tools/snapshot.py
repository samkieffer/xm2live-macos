#!/usr/bin/env python3
"""
Instantanés de non-régression : convertit les modules de référence et compare
le résultat (.als + samples) à un instantané enregistré.

Usage:
  python3 tools/snapshot.py save              # enregistre l'état actuel comme référence
  python3 tools/snapshot.py diff              # compare l'état actuel à la référence
  python3 tools/snapshot.py diff discotec bang  # seulement certains modules

Options:
  --root DIR   dossier des modules (défaut: $XM2LIVE_MODULES ou ~/Music/Compo/All Compo/Modules)
  --dir DIR    dossier des instantanés (défaut: tools/snapshots)
  --keep DIR   conserve les projets convertis dans DIR (sinon dossier temporaire)
"""

import os
import sys
import json
import hashlib
import argparse
import tempfile
import subprocess
from collections import Counter

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, PROJECT_DIR)

from als_validator import load_als, validate_als, is_global_id_element  # noqa: E402

DEFAULT_ROOT = os.environ.get('XM2LIVE_MODULES', os.path.expanduser('~/Music/Compo/All Compo/Modules'))


def read_regression_set(path):
    """Lit la liste des modules : [(id, chemin relatif, [options])]"""
    entries = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            ident, rel_path, flags = [part.strip() for part in line.split('|')]
            entries.append((ident, rel_path, flags.split()))
    return entries


def convert(module_path, flags, output_dir):
    """Lance xm2live.py, retourne (chemin du .als, sortie console)"""
    cmd = [sys.executable, os.path.join(PROJECT_DIR, 'xm2live.py'), module_path, *flags, '--output', output_dir]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_DIR)
    stem = os.path.splitext(os.path.basename(module_path))[0]
    als_path = os.path.join(output_dir, f"{stem}.als")
    if result.returncode != 0 or not os.path.exists(als_path):
        return None, result.stdout + result.stderr
    return als_path, result.stdout


def wav_md5(path):
    """Empreinte des données PCM d'un WAV (indépendante du nom de fichier)"""
    import wave
    with wave.open(path, 'rb') as wav:
        return hashlib.md5(wav.readframes(wav.getnframes())).hexdigest()[:12], wav.getnframes()


def value(elem, path, cast=str):
    found = elem.find(path)
    return cast(found.get('Value')) if found is not None else None


def summarize(als_path):
    """Résumé comparable d'un set : tempo, pistes, samples, notes, automations"""
    root = load_als(als_path)
    live_set = root.find('LiveSet')
    project_dir = os.path.dirname(als_path)

    # Nom lisible de chaque cible d'automation (ex. "Mixer/Pan")
    target_names = {}
    for elem in root.iter():
        if is_global_id_element(elem):
            parent = elem.getparent()
            grand_parent = parent.getparent() if parent is not None else None
            target_names[elem.get('Id')] = f"{grand_parent.tag if grand_parent is not None else ''}/{parent.tag}"

    tempo = live_set.find('MainTrack/DeviceChain/Mixer/Tempo/Manual')
    tracks = live_set.find('Tracks')
    group_names = {t.get('Id'): value(t, 'Name/EffectiveName') for t in tracks if t.tag == 'GroupTrack'}

    summary = {'tempo': round(float(tempo.get('Value')), 4) if tempo is not None else None, 'tracks': []}
    name_counts = Counter()
    for track in tracks:
        name = value(track, 'Name/EffectiveName')
        name_counts[name] += 1
        entry = {
            'key': f"{name} #{name_counts[name]}" if name_counts[name] > 1 else name,
            'type': track.tag,
            'group': group_names.get(value(track, 'TrackGroupId')),
        }
        if track.tag == 'MidiTrack':
            devices = track.find('DeviceChain/DeviceChain/Devices')
            entry['device'] = devices[0].tag if devices is not None and len(devices) else None
            envelope = devices[0].find('.//VolumeAndPan/Envelope') if entry['device'] else None
            if envelope is not None:
                entry['amp_envelope'] = {
                    param: round(value(envelope, f'{param}/Manual', float), 4)
                    for param in ('AttackTime', 'DecayTime', 'SustainLevel', 'ReleaseTime')
                    if envelope.find(f'{param}/Manual') is not None
                }
            entry['parts'] = []
            for part in track.iter('MultiSamplePart'):
                rel_path = value(part, './/SampleRef/FileRef/RelativePath')
                md5, frames = wav_md5(os.path.join(project_dir, rel_path))
                entry['parts'].append({
                    'sample': md5, 'frames': frames,
                    'root_key': value(part, 'RootKey', int),
                    'detune': round(value(part, 'Detune', float), 4),
                    'volume': round(value(part, 'Volume', float), 4),
                    'panorama': round(value(part, 'Panorama', float), 4),
                    'loop': [value(part, 'SustainLoop/Mode', int), value(part, 'SustainLoop/Start', int),
                             value(part, 'SustainLoop/End', int)],
                })
            notes = []
            for key_track in track.iter('KeyTrack'):
                key = value(key_track, 'MidiKey', int)
                for note in key_track.iter('MidiNoteEvent'):
                    notes.append([round(float(note.get('Time')), 6), round(float(note.get('Duration')), 6),
                                  key, int(note.get('Velocity'))])
            entry['notes'] = sorted(notes)
            automations = {}
            for envelope in track.iter('AutomationEnvelope'):
                target = target_names.get(value(envelope, 'EnvelopeTarget/PointeeId'), '?')
                events = [(e.get('Time'), e.get('Value')) for e in envelope.iter('FloatEvent')]
                automations[target] = [len(events), hashlib.md5(repr(events).encode()).hexdigest()[:12]]
            entry['automations'] = automations
        summary['tracks'].append(entry)

    summary['validation'] = [f"{level}: {msg}" for level, msg in validate_als(als_path)]
    return summary


def diff_notes(old, new):
    """Décrit les différences entre deux listes de notes"""
    old_map = {(n[0], n[2]): n for n in old}
    new_map = {(n[0], n[2]): n for n in new}
    added = [new_map[k] for k in new_map.keys() - old_map.keys()]
    removed = [old_map[k] for k in old_map.keys() - new_map.keys()]
    changed = [(old_map[k], new_map[k]) for k in old_map.keys() & new_map.keys() if old_map[k] != new_map[k]]
    lines = []
    if added:
        lines.append(f"+{len(added)} notes (ex. {sorted(added)[:3]})")
    if removed:
        lines.append(f"-{len(removed)} notes (ex. {sorted(removed)[:3]})")
    if changed:
        dur = sum(1 for a, b in changed if a[1] != b[1])
        vel = sum(1 for a, b in changed if a[3] != b[3])
        example = sorted(changed)[0]
        lines.append(f"{len(changed)} notes modifiées (durée: {dur}, vélocité: {vel}; ex. {example[0]} → {example[1]})")
    return lines


def diff_summaries(old, new):
    """Liste lisible des différences entre deux résumés ([temps, durée, note, vélocité] pour les notes)"""
    lines = []
    if old['tempo'] != new['tempo']:
        lines.append(f"tempo: {old['tempo']} → {new['tempo']}")
    old_tracks = {t['key']: t for t in old['tracks']}
    new_tracks = {t['key']: t for t in new['tracks']}
    for key in old_tracks.keys() - new_tracks.keys():
        lines.append(f"piste supprimée: {key}")
    for key in new_tracks.keys() - old_tracks.keys():
        lines.append(f"piste ajoutée: {key} ({len(new_tracks[key].get('notes', []))} notes)")
    for key in sorted(old_tracks.keys() & new_tracks.keys()):
        a, b = old_tracks[key], new_tracks[key]
        track_lines = []
        for field in ('type', 'group', 'device', 'amp_envelope'):
            # Un champ absent de la référence (ancien format d'instantané) n'est pas comparé
            if field in a and a[field] != b.get(field):
                track_lines.append(f"{field}: {a.get(field)} → {b.get(field)}")
        for i, (pa, pb) in enumerate(zip(a.get('parts', []), b.get('parts', []))):
            for field in pa:
                if pa[field] != pb.get(field):
                    track_lines.append(f"sample {i + 1} {field}: {pa[field]} → {pb.get(field)}")
        if len(a.get('parts', [])) != len(b.get('parts', [])):
            track_lines.append(f"nombre de samples: {len(a['parts'])} → {len(b['parts'])}")
        track_lines += diff_notes(a.get('notes', []), b.get('notes', []))
        if a.get('automations') != b.get('automations'):
            track_lines.append(f"automations: {a.get('automations')} → {b.get('automations')}")
        lines += [f"{key}: {line}" for line in track_lines]
    if old['validation'] != new['validation']:
        lines.append(f"validation: {old['validation'] or 'OK'} → {new['validation'] or 'OK'}")
    return lines


def main():
    parser = argparse.ArgumentParser(description='Instantanés de non-régression xm2live')
    parser.add_argument('action', choices=['save', 'diff'])
    parser.add_argument('only', nargs='*', help='identifiants à traiter (défaut: tous)')
    parser.add_argument('--root', default=DEFAULT_ROOT)
    parser.add_argument('--dir', default=os.path.join(TOOLS_DIR, 'snapshots'))
    parser.add_argument('--set', default=os.path.join(TOOLS_DIR, 'regression_set.txt'))
    parser.add_argument('--keep', help='conserver les projets convertis dans ce dossier')
    args = parser.parse_args()

    entries = [e for e in read_regression_set(args.set) if not args.only or e[0] in args.only]
    os.makedirs(args.dir, exist_ok=True)
    work_dir = args.keep or tempfile.mkdtemp(prefix='xm2live_snapshot_')

    failures = 0
    for ident, rel_path, flags in entries:
        module_path = os.path.join(args.root, rel_path)
        als_path, log = convert(module_path, flags, os.path.join(work_dir, ident))
        if als_path is None:
            print(f"❌ {ident}: conversion échouée\n" + '\n'.join(log.splitlines()[-15:]))
            failures += 1
            continue
        summary = summarize(als_path)
        snapshot_path = os.path.join(args.dir, f"{ident}.json")

        if args.action == 'save':
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, separators=(',', ':'))
            n_notes = sum(len(t.get('notes', [])) for t in summary['tracks'])
            status = 'OK' if not summary['validation'] else f"{len(summary['validation'])} problème(s) de validation"
            print(f"💾 {ident}: {len(summary['tracks'])} pistes, {n_notes} notes, validation {status}")
        else:
            if not os.path.exists(snapshot_path):
                print(f"⚠️  {ident}: pas d'instantané de référence (lancer 'save')")
                failures += 1
                continue
            with open(snapshot_path, encoding='utf-8') as f:
                reference = json.load(f)
            lines = diff_summaries(reference, summary)
            if lines:
                failures += 1
                print(f"≠ {ident}: {len(lines)} différence(s)")
                for line in lines[:40]:
                    print(f"    {line}")
                if len(lines) > 40:
                    print(f"    … {len(lines) - 40} autres")
            else:
                print(f"= {ident}: identique")

    if not args.keep:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
