#!/usr/bin/env python3
"""
Vérification de cohérence d'un set Ableton (.als) généré par xm2live

Détecte les erreurs que Live tolère mal ou signale mal : IDs d'automation en double,
automations orphelines, samples manquants, boucles hors du sample, Detune hors plage, etc.

Usage: python3 als_validator.py projet.als [autre.als ...]
"""

import os
import sys
import gzip
import wave
from collections import Counter
from lxml import etree


def load_als(als_path):
    """Charge un .als (XML gzippé) et retourne l'élément racine"""
    with gzip.open(als_path, 'rb') as f:
        return etree.fromstring(f.read(), etree.XMLParser(huge_tree=True))


def is_global_id_element(elem):
    """Éléments dont l'Id doit être unique dans tout le set (cibles référencées par PointeeId)"""
    return isinstance(elem.tag, str) and 'Id' in elem.attrib and (
        elem.tag.endswith('Target') or elem.tag == 'Pointee')


def sample_frames(wav_path):
    """Nombre de frames d'un WAV, ou None si illisible"""
    try:
        with wave.open(wav_path, 'rb') as wav:
            return wav.getnframes()
    except (wave.Error, OSError, EOFError):
        return None


def validate_als(als_path):
    """Valide un set Ableton

    Returns:
        Liste de tuples (niveau, message), niveau = 'erreur' ou 'avertissement'
    """
    issues = []
    root = load_als(als_path)
    live_set = root.find('LiveSet')
    project_dir = os.path.dirname(os.path.abspath(als_path))

    # 1. IDs globaux uniques et NextPointeeId au-delà du plus grand
    global_ids = Counter(int(e.get('Id')) for e in root.iter() if is_global_id_element(e))
    duplicates = sorted(i for i, n in global_ids.items() if n > 1)
    if duplicates:
        issues.append(('erreur', f"{len(duplicates)} ID d'automation en double (ex. {duplicates[:5]})"))

    next_pointee = live_set.find('NextPointeeId')
    if next_pointee is not None and global_ids:
        if int(next_pointee.get('Value')) <= max(global_ids):
            issues.append(('erreur', f"NextPointeeId={next_pointee.get('Value')} ≤ plus grand ID ({max(global_ids)})"))

    # 2. Chaque automation pointe vers une cible existante
    for pointee in root.iter('PointeeId'):
        if int(pointee.get('Value')) not in global_ids:
            issues.append(('erreur', f"Automation orpheline (PointeeId {pointee.get('Value')} introuvable)"))

    # 3. Pistes : Id uniques, groupes existants
    tracks = live_set.find('Tracks')
    track_ids = Counter(t.get('Id') for t in tracks)
    duplicate_tracks = [i for i, n in track_ids.items() if n > 1]
    if duplicate_tracks:
        issues.append(('erreur', f"Id de piste en double: {duplicate_tracks[:5]}"))

    group_ids = {t.get('Id') for t in tracks if t.tag == 'GroupTrack'}
    for track in tracks:
        group = track.find('TrackGroupId')
        if group is not None and group.get('Value') != '-1' and group.get('Value') not in group_ids:
            issues.append(('erreur', f"Piste rattachée à un groupe inexistant (TrackGroupId {group.get('Value')})"))

    # 4. Tempo dans la plage de Live
    tempo = live_set.find('MainTrack/DeviceChain/Mixer/Tempo/Manual')
    if tempo is None:
        tempo = live_set.find('MasterTrack/DeviceChain/Mixer/Tempo/Manual')
    if tempo is None:
        issues.append(('erreur', "Tempo introuvable"))
    elif not 20 <= float(tempo.get('Value')) <= 999:
        issues.append(('erreur', f"Tempo hors plage Live (20-999): {tempo.get('Value')}"))

    # 5. Samples et notes, piste par piste
    for track in tracks:
        if track.tag != 'MidiTrack':
            continue
        name = track.find('Name/EffectiveName').get('Value')

        for part in track.iter('MultiSamplePart'):
            rel_path = part.find('.//SampleRef/FileRef/RelativePath').get('Value')
            wav_path = os.path.join(project_dir, rel_path)
            frames = sample_frames(wav_path)
            if frames is None:
                issues.append(('erreur', f"{name}: sample introuvable ou illisible ({rel_path})"))
                continue

            root_key = int(part.find('RootKey').get('Value'))
            if not 0 <= root_key <= 127:
                issues.append(('erreur', f"{name}: RootKey hors plage ({root_key})"))

            detune = float(part.find('Detune').get('Value'))
            if not -50 <= detune <= 50:
                issues.append(('erreur', f"{name}: Detune hors plage ±50 cents ({detune})"))

            sample_end = int(part.find('SampleEnd').get('Value'))
            if sample_end >= frames:
                issues.append(('erreur', f"{name}: SampleEnd {sample_end} ≥ longueur du sample ({frames})"))

            loop_mode = part.find('SustainLoop/Mode')
            if loop_mode is not None and loop_mode.get('Value') != '0':
                loop_start = int(part.find('SustainLoop/Start').get('Value'))
                loop_end = int(part.find('SustainLoop/End').get('Value'))
                if not 0 <= loop_start < loop_end <= frames:
                    issues.append(('erreur', f"{name}: boucle {loop_start}-{loop_end} hors du sample ({frames} frames)"))

        bad_notes = 0
        for note in track.iter('MidiNoteEvent'):
            if (float(note.get('Duration')) <= 0 or float(note.get('Time')) < 0
                    or not 0 <= int(note.get('Velocity')) <= 127):
                bad_notes += 1
        if bad_notes:
            issues.append(('erreur', f"{name}: {bad_notes} note(s) invalide(s) (durée ≤ 0, temps < 0 ou vélocité hors 0-127)"))

    return issues


def print_report(als_path, issues):
    """Affiche le résultat de la validation, retourne True si aucune erreur"""
    errors = [msg for level, msg in issues if level == 'erreur']
    warnings = [msg for level, msg in issues if level == 'avertissement']
    if not issues:
        print(f"   ✓ Validation OK: {os.path.basename(als_path)}")
    else:
        print(f"   {'❌' if errors else '⚠️ '} Validation: {len(errors)} erreur(s), {len(warnings)} avertissement(s)")
        for msg in errors[:20]:
            print(f"   ❌ {msg}")
        for msg in warnings[:20]:
            print(f"   ⚠️  {msg}")
    return not errors


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    ok = True
    for path in sys.argv[1:]:
        ok = print_report(path, validate_als(path)) and ok
    sys.exit(0 if ok else 1)
