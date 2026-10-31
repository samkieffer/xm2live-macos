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
from bisect import bisect_left, bisect_right
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
# Ordre pointant vers un pattern absent du fichier : FT2 joue 64 lignes vides (FRONT.XM dure 46 s
# dans FT2), là où OpenMPT saute l'ordre (cf. tools/check_timing.py)
MISSING_PATTERN_ROWS = 64
AMIGA_C2_PERIOD = 428      # période ProTracker de la note 60 (MOD)
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


def envelope_curve(envelope, length, max_points=256):
    """Points (tick, valeur 0-64) de l'enveloppe de volume sur `length` ticks, note tenue

    À relier par des segments. Le sustain tient sa valeur jusqu'au bout (la note s'arrête au
    key-off), une boucle est déroulée (au plus `max_points` points, puis la valeur est tenue).
    """
    points = envelope['points']
    sustain, loop = envelope_flags(envelope)
    curve, offset, i = [], 0, 0
    while len(curve) < max_points:
        tick, value = points[i][0] + offset, points[i][1]
        if tick >= length:
            if curve:  # valeur interpolée à la fin de la note
                (t0, v0) = curve[-1]
                curve.append((length, v0 + (value - v0) * (length - t0) / max(tick - t0, 1)))
            else:
                curve.append((0, value))
            break
        curve.append((tick, value))
        if sustain and i == envelope['sustain_point']:
            break
        if loop and i == envelope['loop_end']:
            if envelope['loop_start'] == envelope['loop_end']:
                break  # boucle d'un seul point : tenue
            # Retour au début de la boucle : la valeur saute à celle du point de départ (marche)
            offset += points[i][0] - points[envelope['loop_start']][0]
            curve.append((tick, points[envelope['loop_start']][1]))
            i = envelope['loop_start'] + 1
            continue
        i += 1
        if i >= len(points):
            break
    return curve


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


def pan_commands(cell, file_format, memory):
    """Panoramique d'une case : (valeur fixée au tick de la case ou None, colonne par tick, effet par tick)

    XM seulement : colonne volume Cx fixe x × 16 et Dx / Ex glissent de -x / +x par tick ; l'effet
    8xx fixe xx et Pxy glisse de +x par tick (sinon -y), un paramètre nul reprenant le précédent.
    8xx est appliqué après la colonne volume, comme dans FT2.
    """
    if file_format != 'xm':
        return None, 0, 0
    value, column, slide = None, 0, 0
    if cell.volume_effect is not None:
        kind, amount = cell.volume_effect >> 4, cell.volume_effect & 0xF
        if kind == 0xC:
            value = amount << 4
        elif kind == 0xD:
            column = -amount
        elif kind == 0xE:
            column = amount
    if cell.effect == 0x8:
        value = cell.param
    elif cell.effect == 0x19:
        param = cell.param or memory['pan_slide']
        memory['pan_slide'] = param
        slide = param >> 4 if param & 0xF0 else -(param & 0xF)
    return value, column, slide


def tone_portamento(cell, file_format, memory):
    """Vitesse brute du tone portamento d'une case, None si la case n'en fait pas

    3xx (et 5xy, qui continue à la vitesse mémorisée), colonne volume Fx en XM (vitesse x × 16) ;
    un paramètre nul reprend la vitesse précédente. Unité : en XM, 1/16 de demi-ton par tick ; en
    MOD, unités de période Amiga par tick (cf. glide_ticks).
    """
    column = file_format == 'xm' and cell.volume_effect is not None and cell.volume_effect >> 4 == 0xF
    if not (cell.effect in (0x3, 0x5) or column):
        return None
    if column and cell.volume_effect & 0xF:
        memory['porta'] = (cell.volume_effect & 0xF) << 4
    if cell.effect == 0x3 and cell.param:
        memory['porta'] = cell.param
    return memory['porta']


def glide_ticks(speed, from_note, to_note, file_format):
    """Durée (ticks) du glissement de from_note à to_note à la vitesse brute `speed` (tone_portamento)"""
    if not speed:
        return None
    if file_format == 'xm':
        semitones_per_tick = speed / 16.0
    else:
        # Un demi-ton vaut environ 5,6 % de la période, celle de la note de départ
        period = AMIGA_C2_PERIOD * 2 ** (-(from_note - 60) / 12.0)
        semitones_per_tick = speed / (period * (1 - 2 ** (-1 / 12.0)))
    return abs(to_note - from_note) / semitones_per_tick


def sample_offset(cell, memory):
    """Offset 9xx de la case (en unités de 256 frames), None sans 9xx ; 900 reprend le précédent"""
    if cell.effect != 0x9:
        return None
    memory['offset'] = cell.param or memory['offset']
    return memory['offset']


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
        dict avec 'tracks' {canal: {instrument: [notes]}} (une note : time, duration, note, tick (durée
        d'un tick en temps), volume 0-64 au début de la note (fondu d'entrée : le plus haut atteint),
        volume_moves [(temps, volume)] et pan 0-255 / pan_moves [(temps, pan)] : changements pendant
        la note, legato et glide_ms (tone portamento : la note prolonge le son de la précédente en
        glissant vers sa hauteur, durée du glissement en ms), sample_offset_xm),
        'tempo_changes' [(temps, BPM Live)],
        'end_time' (temps), 'segments' [(début, fin, numéro de pattern)] (chaque passage d'un ordre de
        lecture, dans l'ordre joué), 'duration_seconds', 'released_instruments' (instruments dont un key-off
        lance une release : {instrument: ticks}) et 'played_rows' [(ordre, ligne, speed, bpm)]
        (déroulé ligne par ligne, comparé à OpenMPT par tools/check_timing.py)
    """
    # Son de chaque instrument : son dernier sample, comme les pistes Live (xm2live.py)
    instrument_samples = {s['instrument']: s for s in samples}
    default_volume = {i: min(s.get('volume', 64), 64) for i, s in instrument_samples.items()}
    default_pan = {i: s.get('panning', 128) for i, s in instrument_samples.items()}
    silence = {i: envelope_silence(s.get('envelope')) for i, s in instrument_samples.items()}
    release = {i: release_ticks(s.get('envelope'), s.get('fadeout', 0)) for i, s in instrument_samples.items()}

    # Événements de chaque canal, dans l'ordre du temps : notes, silences (le volume tombe à 0) et
    # reprises (le volume remonte sans nouvelle note : glissement, numéro d'instrument seul...)
    events = defaultdict(list)

    # État de chaque canal. Une note sans instrument rejoue le dernier instrument du canal et garde
    # son volume. `level` : volume réel 0-64 (défaut du sample à chaque numéro d'instrument)
    channel_instrument = {}
    level = {}
    volume_moves = defaultdict(list)  # canal -> [(temps, volume)] à chaque changement
    playing = {}  # instrument de la dernière note jouée (pour le key-off et le tone portamento)
    last_note = {}  # hauteur visée sur le canal (départ d'un tone portamento)
    fading_in = {}  # note partie à volume 0 : elle prendra le volume le plus haut atteint
    # Panoramique du canal (FT2) : un numéro d'instrument le remet au défaut du sample, Cx et 8xx le
    # fixent jusqu'au prochain numéro d'instrument, les glissements le déplacent tick par tick
    pan = {}
    pan_moves = defaultdict(list)  # canal -> [(temps, panoramique)] à chaque changement
    memory = defaultdict(lambda: {'slide': 0, 'fine_up': 0, 'fine_down': 0, 'pan_slide': 0, 'porta': 0,
                                  'offset': 0})
    loop_start = defaultdict(int)  # E6x : ligne de début de boucle, par canal
    loop_count = defaultdict(int)
    released_instruments = {}

    tempo_changes = [(0.0, live_tempo(bpm, speed))]
    time = 0.0      # début de la ligne courante, en temps
    seconds = 0.0
    order_index, row = 0, 0
    played_rows = []
    segments = []  # passages successifs dans l'ordre de lecture : [début, fin, numéro de pattern]

    def set_level(channel, value, at):
        """Volume réel du canal : passer à 0 rend le canal muet, en repartir le fait réentendre"""
        value = max(0, min(64, value))
        old = level.get(channel, 64)
        level[channel] = value
        if value != old:
            volume_moves[channel].append((at, value))
        if old and not value:
            events[channel].append({'time': at, 'kind': 'silence'})
        elif value and not old:
            events[channel].append({'time': at, 'kind': 'resume'})
        if value and channel in fading_in:
            fading_in[channel]['peak'] = max(fading_in[channel]['peak'], value)

    def set_pan(channel, value, at):
        value = max(0, min(255, value))
        if pan.get(channel, 128) != value:
            pan[channel] = value
            pan_moves[channel].append((at, value))

    def slide_volume(channel, delta, at):
        """Glissement de volume de `delta` (borné à 0-64)"""
        if delta:
            set_level(channel, level.get(channel, 64) + delta, at)

    def key_off(channel, at):
        instrument = playing.get(channel)
        ticks = release.get(instrument, 0)
        if ticks is None:
            return  # fadeout nul et enveloppe qui ne retombe pas à 0 : le son continue
        if ticks:
            released_instruments[instrument] = ticks
        # La note s'arrête au key-off (la fin du son, s'il y en a une, devient la release du Sampler ;
        # sans enveloppe de volume, FT2 met le volume à 0) ; un numéro d'instrument seul relance
        # l'enveloppe et fait réentendre le son, comme dans FT2
        set_level(channel, 0, at)

    def pattern_rows(number):
        """Nombre de lignes d'un pattern ; un pattern absent du fichier vaut 64 lignes vides dans FT2"""
        return patterns[number]['rows'] if number < len(patterns) else MISSING_PATTERN_ROWS

    while order_index < len(pattern_order) and len(played_rows) < MAX_ROWS:
        pattern_number = pattern_order[order_index]
        num_rows = pattern_rows(pattern_number)
        cells = patterns[pattern_number]['cells'] if pattern_number < len(patterns) else []
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
        if not segments or played_rows[-2][0] != order_index:
            if segments:
                segments[-1][1] = time
            segments.append([time, None, pattern_number])

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
            pan_value, pan_column_slide, pan_effect_slide = pan_commands(cell, file_format, memory[channel])
            # ECx : volume à 0 au tick x (FT2 et ProTracker coupent le son en mettant le volume à 0)
            cut = param & 0xF if sub_effect == 0xC and (param & 0xF) < speed else None

            def run_ticks(first, last):
                """Glissements par tick (sauf le tick 0 de chaque répétition de la ligne) et ECx"""
                if not (column_slide or effect_slide or pan_column_slide or pan_effect_slide or cut is not None):
                    return
                for t in range(first, last):
                    if t % speed:
                        slide_volume(channel, column_slide, time + t * tick)
                        slide_volume(channel, effect_slide, time + t * tick)
                        if pan_column_slide or pan_effect_slide:
                            set_pan(channel, pan.get(channel, 128) + pan_column_slide + pan_effect_slide,
                                    time + t * tick)
                    if t == cut:
                        set_level(channel, 0, time + t * tick)

            run_ticks(1, delay)  # avant une note retardée, les glissements agissent sur la précédente

            # Tick de la case : instrument, volume, note
            new_level = level.get(channel, 64)
            if cell.instrument:
                channel_instrument[channel] = cell.instrument
                new_level = default_volume.get(cell.instrument, 64)  # remis au défaut du sample
                set_pan(channel, default_pan.get(cell.instrument, 128), at)
            if cell.volume is not None:
                new_level = cell.volume
            if pan_value is not None:
                set_pan(channel, pan_value, at)

            if cell.note == KEY_OFF:
                set_level(channel, new_level, at)
                key_off(channel, at)
            elif cell.note is not None:
                instrument = cell.instrument or channel_instrument.get(channel)
                if instrument is None:
                    continue  # aucun instrument encore choisi sur ce canal : rien ne joue
                # Tone portamento : le son en cours glisse vers la note sans redémarrer (même sample)
                porta = tone_portamento(cell, file_format, memory[channel])
                glide_ms = None
                if porta is not None and channel in playing and channel in last_note:
                    instrument = playing[channel]
                    ticks = glide_ticks(porta, last_note[channel], cell.note, file_format)
                    glide_ms = ticks * 2500.0 / bpm if ticks is not None else None
                if glide_ms == 0:
                    set_level(channel, new_level, at)  # déjà à cette hauteur : la note continue
                    if fine:
                        slide_volume(channel, fine, at)
                    run_ticks(delay, row_ticks)
                    continue
                if new_level != level.get(channel, 64):
                    volume_moves[channel].append((at, new_level))
                level[channel] = new_level
                playing[channel] = instrument
                last_note[channel] = cell.note
                note = {
                    'kind': 'note',
                    'time': at,
                    'tick': tick,
                    'note': cell.note,
                    'instrument': instrument,
                    # Note à volume 0 : muette tant que le volume ne remonte pas. Si elle remonte
                    # (fondu d'entrée), son volume de référence est le plus haut atteint
                    'volume': new_level or None,
                    'peak': 0,
                    'pan': pan.get(channel, 128),
                    'glide_ms': glide_ms,
                    'sample_offset_xm': sample_offset(cell, memory[channel]),
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
            if order_index < len(pattern_order) and row >= pattern_rows(pattern_order[order_index]):
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
        moves = sorted(pan_moves[channel], key=lambda m: m[0])
        move_times = [m[0] for m in moves]
        volumes = sorted(volume_moves[channel], key=lambda m: m[0])
        volume_times = [m[0] for m in volumes]
        legato = {}  # index d'une note en tone portamento -> fin naturelle du son qu'elle prolonge
        for i, event in enumerate(channel_events):
            if event['kind'] != 'note':
                continue
            note_volume = event['volume']
            silent_since = None if note_volume else event['time']
            natural = legato[i] if i in legato else natural_end(event)
            end = natural if natural is not None else time
            for j in range(i + 1, len(channel_events)):
                following = channel_events[j]
                if following['time'] >= end:
                    break
                if following['kind'] == 'note':
                    end = following['time']
                    if following['glide_ms'] and silent_since is None:
                        legato[j] = natural  # le son glisse vers la note suivante, qui le prolonge
                    break
                if following['kind'] == 'silence':
                    if silent_since is None:
                        silent_since = following['time']
                elif silent_since is not None:
                    silent_since = None
                    note_volume = note_volume or event['peak']
            if silent_since is not None:
                end = min(end, silent_since)
            duration = end - event['time']
            if duration <= 0 or not note_volume:
                continue  # coupée sur le tick où elle commence (EC0), ou jamais audible
            # Changements de volume et de panoramique pendant la note (après le tick où elle commence)
            first, last = bisect_right(move_times, event['time']), bisect_left(move_times, end)
            first_volume = bisect_right(volume_times, event['time'])
            last_volume = bisect_left(volume_times, end)
            start_moves = [(event['time'], 0)] if not event['volume'] else []  # fondu d'entrée
            tracks[channel][event['instrument']].append({
                'time': event['time'],
                'tick': event['tick'],
                'note': event['note'],
                'volume': note_volume,
                'volume_moves': start_moves + volumes[first_volume:last_volume],
                'duration': duration,
                'pan': event['pan'],
                'pan_moves': moves[first:last],
                'legato': i in legato,
                'glide_ms': event['glide_ms'] if i in legato else None,
                'sample_offset_xm': event['sample_offset_xm'],
            })

    return {
        'tracks': tracks,
        'tempo_changes': tempo_changes,
        'end_time': time,
        'segments': [(start, end if end is not None else time, number) for start, end, number in segments],
        'duration_seconds': seconds,
        'released_instruments': released_instruments,
        'played_rows': played_rows,
    }
