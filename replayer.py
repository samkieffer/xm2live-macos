#!/usr/bin/env python3
"""
Moteur de lecture commun XM / MOD : parcourt le morceau comme le tracker

Suit l'ordre de lecture réel (Bxx saut, Dxx arrêt de pattern, E6x boucle, EEx délai de pattern),
applique les changements de vitesse et de tempo (Fxx) là où ils apparaissent, et place les
événements au tick près (EDx note delay, ECx note cut, key-off).

Unités : le temps est en temps Ableton (beats). Une ligne vaut toujours 1/4 de temps et un tick
1/(4 × speed) de temps ; le tempo Live suit donc la vitesse : BPM Live = BPM × 6 / speed
(formule FT2), écrit en automation de tempo à chaque changement.

Longueur des notes : une note dure tant que le tracker la fait entendre, sans plafond. Elle s'arrête
au prochain événement de son canal (un canal = une voix), à la fin du sample s'il ne boucle pas,
quand l'enveloppe de volume retombe à 0 pour de bon, ou quand le volume du canal tombe à 0 (Cxx,
colonne volume, glissements, ECx, key-off). Après un key-off, la fin du son (fadeout, fin de
l'enveloppe) devient la release du Sampler (instruments listés dans 'released_instruments').
"""

import math
from bisect import bisect_right
from collections import defaultdict, namedtuple

# Une case de pattern, identique pour XM et MOD (une case vide vaut None)
#   note          : note MIDI, KEY_OFF ou None
#   instrument    : numéro d'instrument (XM) ou de sample (MOD), None = instrument du canal
#   volume        : 0-64 (colonne volume ou Cxx), None = pas de volume sur cette ligne
#   effect, param : effet et paramètre (numérotation commune XM / MOD pour 0-F)
#   volume_effect : commande de la colonne volume XM (octet brut 0x60-0xFF), None sinon
Cell = namedtuple('Cell', 'note instrument volume effect param volume_effect', defaults=(None,))
KEY_OFF = -1

MAX_ROWS = 100000      # garde-fou contre une boucle de patterns sans fin
BASE_RATE = 8363       # fréquence des WAV extraits : vitesse de lecture de la note 60 (C-4 XM, C-2 MOD)
FADEOUT_START = 32768  # FT2 : après un key-off, le fadeout part de 32768 et perd `fadeout` par tick


def live_tempo(bpm, speed):
    """Tempo Ableton équivalent, à 4 lignes par temps : BPM × 6 / speed"""
    return bpm * 6.0 / speed


def sample_seconds(sample, note):
    """Durée de lecture d'un sample sans boucle sur cette note, en secondes (None s'il boucle)

    Même hauteur que dans Live : RootKey et Detune viennent de relative_note et du finetune FT2
    (16 pas par demi-ton), cf. xm2live.finetune_to_root_key_and_detune().
    """
    if sample.get('loop_type'):
        return None
    cents = (sample.get('finetune', 0) >> 3) * 6.25
    rate = BASE_RATE * 2 ** ((note - 60 + sample.get('relative_note', 0)) / 12 + cents / 1200)
    return sample['length'] / rate


def envelope_flags(envelope):
    """(sustain, boucle) effectifs : FT2 ignore un point de sustain ou une fin de boucle hors des points"""
    num_points = envelope['num_points']
    sustain = envelope['sustain_enabled'] and envelope['sustain_point'] < num_points
    loop = envelope['loop_enabled'] and envelope['loop_start'] <= envelope['loop_end'] < num_points
    return sustain, loop


def zero_tail(points):
    """Indice du premier point de la série finale de points à 0 (None si le dernier point n'est pas à 0)"""
    start = None
    for i in range(len(points) - 1, -1, -1):
        if points[i][1]:
            break
        start = i
    return start


def envelope_silence(envelope):
    """Tick, depuis le début de la note, où l'enveloppe de volume s'éteint pour de bon (note tenue)

    None si elle ne s'éteint pas : pas d'enveloppe, dernier point non nul, ou sustain / boucle qui
    la retient avant les points à 0.
    """
    if not envelope or not envelope['enabled']:
        return None
    zero = zero_tail(envelope['points'])
    if zero is None:
        return None
    sustain, loop = envelope_flags(envelope)
    if (sustain and envelope['sustain_point'] < zero) or (loop and envelope['loop_start'] < zero):
        return None
    return envelope['points'][zero][0]


def release_ticks(envelope, fadeout):
    """Ticks entre un key-off et le silence, comme FT2

    0 sans enveloppe de volume (FT2 coupe aussitôt), sinon le plus court du fadeout (32768 / fadeout
    ticks) et de la fin de l'enveloppe ; None si le son continue (fadeout nul et enveloppe qui ne
    retombe pas à 0).
    """
    if not envelope or not envelope['enabled']:
        return 0
    candidates = []
    if fadeout:
        candidates.append(math.ceil(FADEOUT_START / fadeout))
    points = envelope['points']
    zero = zero_tail(points)
    if zero is not None:
        sustain, loop = envelope_flags(envelope)
        # Le key-off relâche le sustain ; une boucle continue, sauf si elle finit sur le point de sustain
        if loop and sustain and envelope['loop_end'] == envelope['sustain_point']:
            loop = False
        if not (loop and envelope['loop_start'] < zero):
            # Position au key-off : le point de sustain (note tenue), sinon le début (majorant)
            start = points[envelope['sustain_point']][0] if sustain else 0
            candidates.append(max(0, points[zero][0] - start))
    return min(candidates) if candidates else None


def beats_after(tempo_changes, start, seconds):
    """Temps (beats) atteint `seconds` secondes après `start`, en suivant les changements de tempo"""
    i = max(0, bisect_right(tempo_changes, (start, math.inf)) - 1)
    time = start
    while i + 1 < len(tempo_changes):
        segment = (tempo_changes[i + 1][0] - time) * 60.0 / tempo_changes[i][1]
        if seconds <= segment:
            break
        seconds -= segment
        time = tempo_changes[i + 1][0]
        i += 1
    return time + seconds * tempo_changes[i][1] / 60.0


def volume_commands(cell, sub_effect, file_format, memory):
    """Changements de volume d'une case : (fin, colonne par tick, effet par tick)

    Colonne volume XM : 6x / 7x glissement par tick, 8x / 9x glissement fin. Effets : Axy, 5xy et
    6xy glissent de +x par tick (sinon -y), EAx / EBx sont des glissements fins (tick de la note).
    En XM un paramètre nul reprend le précédent (mémoire commune à A, 5 et 6, séparée pour EA et
    EB) ; en MOD il ne fait rien.
    """
    fine, column, slide = 0, 0, 0
    if cell.volume_effect is not None:
        kind, value = cell.volume_effect >> 4, cell.volume_effect & 0xF
        if kind == 0x6:
            column = -value
        elif kind == 0x7:
            column = value
        elif kind == 0x8:
            fine = -value
        elif kind == 0x9:
            fine = value
    if cell.effect in (0x5, 0x6, 0xA):
        param = cell.param
        if file_format == 'xm':
            param = param or memory['slide']
            memory['slide'] = param
        slide = param >> 4 if param & 0xF0 else -(param & 0xF)
    elif sub_effect in (0xA, 0xB):
        value = cell.param & 0xF
        key = 'fine_up' if sub_effect == 0xA else 'fine_down'
        if file_format == 'xm':
            value = value or memory[key]
            memory[key] = value
        fine += value if sub_effect == 0xA else -value
    return fine, column, slide


def play_song(patterns, pattern_order, speed, bpm, file_format, samples=()):
    """Joue le morceau et produit les notes par canal et par instrument

    Args:
        patterns: [{'rows': int, 'cells': [[Cell ou None, ...] par ligne]}]
        pattern_order: ordre de lecture (numéros de patterns)
        speed, bpm: vitesse (ticks par ligne) et tempo initiaux
        file_format: 'xm' ou 'mod' (formule de vélocité, mémoire des effets, panning 8xx en XM)
        samples: samples des parsers (longueur, boucle, accordage, volume, enveloppe, fadeout) ;
            sans eux, les notes durent jusqu'à l'événement suivant de leur canal

    Returns:
        dict avec 'tracks' {canal: {instrument: [notes]}}, 'tempo_changes' [(temps, BPM Live)],
        'end_time' (temps), 'duration_seconds', 'released_instruments' (instruments dont un key-off
        lance une release : {instrument: ticks}) et 'played_rows' [(ordre, ligne, speed, bpm)]
        (déroulé ligne par ligne, comparé à OpenMPT par tools/check_timing.py)
    """
    # Son de chaque instrument : son dernier sample, comme les pistes Live (xm2live.py)
    instrument_samples = {s['instrument']: s for s in samples}
    default_volume = {i: min(s.get('volume', 64), 64) for i, s in instrument_samples.items()}
    silence = {i: envelope_silence(s.get('envelope')) for i, s in instrument_samples.items()}
    release = {i: release_ticks(s.get('envelope'), s.get('fadeout', 0)) for i, s in instrument_samples.items()}

    # Événements de chaque canal, dans l'ordre du temps : notes, silences (le volume tombe à 0) et
    # reprises (le volume remonte sans nouvelle note : glissement, numéro d'instrument seul...)
    events = defaultdict(list)

    # État de chaque canal. Une note sans instrument rejoue le dernier instrument du canal et garde
    # son volume. Deux volumes : `channel_volume` donne la vélocité (64 = volume par défaut du
    # sample, que porte le Sampler) et `level` le volume réel 0-64, qui dit si on entend quelque chose
    channel_instrument = {}
    channel_volume = {}
    level = {}
    playing = {}  # instrument de la dernière note jouée (pour le key-off)
    fading_in = {}  # note partie à volume 0 : elle prendra la vélocité du volume le plus haut atteint
    memory = defaultdict(lambda: {'slide': 0, 'fine_up': 0, 'fine_down': 0})
    loop_start = defaultdict(int)  # E6x : ligne de début de boucle, par canal
    loop_count = defaultdict(int)
    released_instruments = {}

    tempo_changes = [(0.0, live_tempo(bpm, speed))]
    time = 0.0      # début de la ligne courante, en temps
    seconds = 0.0
    order_index, row = 0, 0
    played_rows = []

    def velocity(volume):
        return min(127, volume * 2) if file_format == 'xm' else int(volume / 64.0 * 127)

    def set_level(channel, value, at):
        """Volume réel du canal : passer à 0 rend le canal muet, en repartir le fait réentendre"""
        old = level.get(channel, 64)
        level[channel] = value
        if old and not value:
            events[channel].append({'time': at, 'kind': 'silence'})
        elif value and not old:
            events[channel].append({'time': at, 'kind': 'resume'})
        if value and channel in fading_in:
            note = fading_in[channel]
            note['peak'] = max(note['peak'], velocity(channel_volume.get(channel, 64)))

    def slide_volume(channel, delta, at):
        """Glissement : les deux volumes bougent de `delta`, bornés à 0-64"""
        if delta:
            channel_volume[channel] = max(0, min(64, channel_volume.get(channel, 64) + delta))
            set_level(channel, max(0, min(64, level.get(channel, 64) + delta)), at)

    def key_off(channel, at):
        instrument = playing.get(channel)
        ticks = release.get(instrument, 0)
        if ticks is None:
            return  # fadeout nul et enveloppe qui ne retombe pas à 0 : le son continue
        if ticks:
            released_instruments[instrument] = ticks
        else:
            channel_volume[channel] = 0  # FT2 : sans enveloppe de volume, le key-off met le volume à 0
        # La note s'arrête au key-off (la fin du son, s'il y en a une, devient la release du Sampler) ;
        # un numéro d'instrument seul relance l'enveloppe et fait réentendre le son, comme dans FT2
        set_level(channel, 0, at)

    while order_index < len(pattern_order) and len(played_rows) < MAX_ROWS:
        pattern_number = pattern_order[order_index]
        if pattern_number >= len(patterns):
            # Pattern référencé mais absent du fichier : sauté, comme le fait OpenMPT
            order_index += 1
            row = 0
            continue
        num_rows = patterns[pattern_number]['rows']
        cells = patterns[pattern_number]['cells']
        row_cells = cells[row] if row < len(cells) else []

        # 1. Vitesse et tempo (Fxx) : effectifs dès cette ligne ; délai de pattern (EEx)
        pattern_delay = 0
        for cell in row_cells:
            if cell and cell.effect == 0xF and cell.param:
                if cell.param < 32:
                    speed = cell.param
                else:
                    bpm = cell.param
            elif cell and cell.effect == 0xE and cell.param >> 4 == 0xE:
                pattern_delay = cell.param & 0xF
        tempo = live_tempo(bpm, speed)
        if tempo != tempo_changes[-1][1]:
            if tempo_changes[-1][0] == time:
                tempo_changes[-1] = (time, tempo)
            else:
                tempo_changes.append((time, tempo))
        tick = 0.25 / speed
        row_ticks = speed * (1 + pattern_delay)  # EEx répète la ligne (sans rejouer les notes)
        played_rows.append((order_index, row, speed, bpm))

        # 2. Notes, volumes et arrêts de chaque canal, effets de déroulé
        jump_order, break_row, loop_row = None, None, None
        for channel, cell in enumerate(row_cells):
            if cell is None:
                continue
            effect, param = cell.effect, cell.param
            sub_effect = param >> 4 if effect == 0xE else None

            if effect == 0xB:
                jump_order = param
            elif effect == 0xD:
                break_row = (param >> 4) * 10 + (param & 0xF)  # paramètre en décimal codé
            elif sub_effect == 0x6:
                count = param & 0xF
                if count == 0:
                    loop_start[channel] = row
                elif loop_count[channel] == 0:
                    loop_count[channel] = count
                    loop_row = loop_start[channel]
                else:
                    loop_count[channel] -= 1
                    if loop_count[channel]:
                        loop_row = loop_start[channel]

            # EDx : la case entière est retardée ; au-delà de la ligne, FT2 ne la joue pas
            delay = param & 0xF if sub_effect == 0xD else 0
            if delay >= speed:
                continue
            at = time + delay * tick
            fine, column_slide, effect_slide = volume_commands(cell, sub_effect, file_format, memory[channel])
            # ECx : volume à 0 au tick x (FT2 et ProTracker coupent le son en mettant le volume à 0)
            cut = param & 0xF if sub_effect == 0xC and (param & 0xF) < speed else None

            def run_ticks(first, last):
                """Glissements par tick (sauf le tick 0 de chaque répétition de la ligne) et ECx"""
                if not (column_slide or effect_slide or cut is not None):
                    return
                for t in range(first, last):
                    if t % speed:
                        slide_volume(channel, column_slide, time + t * tick)
                        slide_volume(channel, effect_slide, time + t * tick)
                    if t == cut:
                        channel_volume[channel] = 0
                        set_level(channel, 0, time + t * tick)

            run_ticks(1, delay)  # avant une note retardée, les glissements agissent sur la précédente

            # Tick de la case : instrument, volume, note
            new_level = level.get(channel, 64)
            if cell.instrument:
                channel_instrument[channel] = cell.instrument
                channel_volume[channel] = 64  # un numéro d'instrument remet le volume par défaut
                new_level = default_volume.get(cell.instrument, 64)
            if cell.volume is not None:
                channel_volume[channel] = new_level = cell.volume

            if cell.note == KEY_OFF:
                set_level(channel, new_level, at)
                key_off(channel, at)
            elif cell.note is not None:
                instrument = cell.instrument or channel_instrument.get(channel)
                if instrument is None:
                    continue  # aucun instrument encore choisi sur ce canal : rien ne joue
                level[channel] = new_level
                playing[channel] = instrument
                note = {
                    'kind': 'note',
                    'time': at,
                    'tick': tick,
                    'note': cell.note,
                    'instrument': instrument,
                    # Note à volume 0 : muette tant que le volume ne remonte pas (Live ferait d'une
                    # vélocité 0 une vélocité 1). Si elle remonte (fondu d'entrée), la note prend la
                    # vélocité du volume le plus haut atteint ; la forme du fondu est pour le lot 4
                    'velocity': velocity(channel_volume.get(channel, 64)) if new_level else None,
                    'peak': 0,
                    'panning_xm': param if file_format == 'xm' and effect == 0x8 else None,
                    'sample_offset_xm': param if effect == 0x9 else None,
                }
                events[channel].append(note)
                fading_in.pop(channel, None)
                if not new_level:
                    fading_in[channel] = note
            else:
                set_level(channel, new_level, at)  # volume 00 / C00 sans note : la note se tait

            if fine:
                slide_volume(channel, fine, at)
            run_ticks(delay, row_ticks)

        # 3. Avancer
        seconds += speed * (1 + pattern_delay) * 2.5 / bpm
        time += 0.25 * (1 + pattern_delay)

        if loop_row is not None:
            row = loop_row
        elif jump_order is not None or break_row is not None:
            if jump_order is not None and jump_order <= order_index:
                break  # saut en arrière : le morceau reboucle, c'est sa fin
            order_index = jump_order if jump_order is not None else order_index + 1
            row = break_row or 0
            if order_index < len(pattern_order):
                target = pattern_order[order_index]
                if target >= len(patterns) or row >= patterns[target]['rows']:
                    row = 0
            loop_start.clear()
            loop_count.clear()
        else:
            row += 1
            if row >= num_rows:
                order_index += 1
                row = 0
                loop_start.clear()
                loop_count.clear()

    def natural_end(note):
        """Fin du son sans autre événement : fin du sample, ou extinction de l'enveloppe (None : jamais)"""
        sample = instrument_samples.get(note['instrument'])
        if sample is None:
            return None
        ends = []
        sample_length = sample_seconds(sample, note['note'])
        if sample_length is not None:
            ends.append(beats_after(tempo_changes, note['time'], sample_length))
        if silence.get(note['instrument']) is not None:
            ends.append(note['time'] + silence[note['instrument']] * note['tick'])
        return min(ends) if ends else None

    # Durées. Un canal = une voix : la note suivante coupe la précédente. Sinon une note dure
    # jusqu'à la fin naturelle de son son ou jusqu'au dernier silence qu'aucune reprise ne suit (les
    # silences passagers, comme un volume haché ligne par ligne, ne coupent pas la note). Un son
    # sans fin (boucle) en fin de canal tient jusqu'à la fin du morceau.
    tracks = defaultdict(lambda: defaultdict(list))
    for channel, channel_events in events.items():
        channel_events.sort(key=lambda e: e['time'])
        for i, event in enumerate(channel_events):
            if event['kind'] != 'note':
                continue
            note_velocity = event['velocity']
            silent_since = None if note_velocity else event['time']
            natural = natural_end(event)
            end = natural if natural is not None else time
            for j in range(i + 1, len(channel_events)):
                following = channel_events[j]
                if following['time'] >= end:
                    break
                if following['kind'] == 'note':
                    end = following['time']
                    break
                if following['kind'] == 'silence':
                    if silent_since is None:
                        silent_since = following['time']
                elif silent_since is not None:
                    silent_since = None
                    note_velocity = note_velocity or event['peak']
            if silent_since is not None:
                end = min(end, silent_since)
            duration = end - event['time']
            if duration <= 0 or not note_velocity:
                continue  # coupée sur le tick où elle commence (EC0), ou jamais audible
            tracks[channel][event['instrument']].append({
                'time': event['time'],
                'note': event['note'],
                'velocity': note_velocity,
                'duration': duration,
                'panning_xm': event['panning_xm'],
                'sample_offset_xm': event['sample_offset_xm'],
            })

    return {
        'tracks': tracks,
        'tempo_changes': tempo_changes,
        'end_time': time,
        'duration_seconds': seconds,
        'released_instruments': released_instruments,
        'played_rows': played_rows,
    }
