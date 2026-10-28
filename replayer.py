#!/usr/bin/env python3
"""
Moteur de lecture commun XM / MOD : parcourt le morceau comme le tracker

Suit l'ordre de lecture réel (Bxx saut, Dxx arrêt de pattern, E6x boucle, EEx délai de pattern),
applique les changements de vitesse et de tempo (Fxx) là où ils apparaissent, et place les
événements au tick près (EDx note delay, ECx note cut, key-off).

Unités : le temps est en temps Ableton (beats). Une ligne vaut toujours 1/4 de temps et un tick
1/(4 × speed) de temps ; le tempo Live suit donc la vitesse : BPM Live = BPM × 6 / speed
(formule FT2), écrit en automation de tempo à chaque changement.
"""

from collections import defaultdict, namedtuple

# Une case de pattern, identique pour XM et MOD (une case vide vaut None)
#   note       : note MIDI, KEY_OFF ou None
#   instrument : numéro d'instrument (XM) ou de sample (MOD), None = instrument du canal
#   volume     : 0-64 (colonne volume ou Cxx), None = pas de volume sur cette ligne
#   effect, param : effet et paramètre (numérotation commune XM / MOD pour 0-F)
Cell = namedtuple('Cell', 'note instrument volume effect param')
KEY_OFF = -1

MAX_ROWS = 100000        # garde-fou contre une boucle de patterns sans fin
MAX_DURATION = 4.0       # durée maximale d'une note, en temps (lisibilité ; cf. AUDIT.md, lot 2)


def live_tempo(bpm, speed):
    """Tempo Ableton équivalent, à 4 lignes par temps : BPM × 6 / speed"""
    return bpm * 6.0 / speed


def play_song(patterns, pattern_order, speed, bpm, file_format):
    """Joue le morceau et produit les notes par canal et par instrument

    Args:
        patterns: [{'rows': int, 'cells': [[Cell ou None, ...] par ligne]}]
        pattern_order: ordre de lecture (numéros de patterns)
        speed, bpm: vitesse (ticks par ligne) et tempo initiaux
        file_format: 'xm' ou 'mod' (formule de vélocité, panning 8xx en XM seulement)

    Returns:
        dict avec 'tracks' {canal: {instrument: [notes]}}, 'tempo_changes' [(temps, BPM Live)],
        'end_time' (temps), 'duration_seconds' et 'played_rows' [(ordre, ligne, speed, bpm)]
        (déroulé ligne par ligne, comparé à OpenMPT par tools/check_timing.py)
    """
    events = defaultdict(list)  # canal -> notes et arrêts, dans l'ordre du temps

    # État de chaque canal : une note sans instrument rejoue le dernier instrument du canal
    # et garde son volume courant
    channel_instrument = {}
    channel_volume = {}
    loop_start = defaultdict(int)  # E6x : ligne de début de boucle, par canal
    loop_count = defaultdict(int)

    tempo_changes = [(0.0, live_tempo(bpm, speed))]
    time = 0.0      # début de la ligne courante, en temps
    seconds = 0.0
    order_index, row = 0, 0
    played_rows = []

    def stop(channel, at):
        events[channel].append({'time': at, 'is_stop': True})

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

        # 1. Vitesse et tempo (Fxx) : effectifs dès cette ligne
        for cell in row_cells:
            if cell and cell.effect == 0xF and cell.param:
                if cell.param < 32:
                    speed = cell.param
                else:
                    bpm = cell.param
        tempo = live_tempo(bpm, speed)
        if tempo != tempo_changes[-1][1]:
            if tempo_changes[-1][0] == time:
                tempo_changes[-1] = (time, tempo)
            else:
                tempo_changes.append((time, tempo))
        tick = 0.25 / speed
        played_rows.append((order_index, row, speed, bpm))

        # 2. Notes et arrêts de chaque canal, effets de déroulé
        jump_order, break_row, loop_row, pattern_delay = None, None, None, 0
        for channel, cell in enumerate(row_cells):
            if cell is None:
                continue
            effect, param = cell.effect, cell.param
            sub_effect = param >> 4 if effect == 0xE else None

            if effect == 0xB:
                jump_order = param
            elif effect == 0xD:
                break_row = (param >> 4) * 10 + (param & 0xF)  # paramètre en décimal codé
            elif sub_effect == 0xE:
                pattern_delay = param & 0xF
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

            if cell.instrument:
                channel_instrument[channel] = cell.instrument
                channel_volume[channel] = 64  # un numéro d'instrument remet le volume par défaut

            if cell.note == KEY_OFF:
                stop(channel, at)
            elif cell.note is not None:
                instrument = cell.instrument or channel_instrument.get(channel)
                if instrument is None:
                    continue  # aucun instrument encore choisi sur ce canal : rien ne joue
                volume = cell.volume if cell.volume is not None else channel_volume.get(channel, 64)
                channel_volume[channel] = volume
                if volume == 0:
                    # Note à volume 0 : inaudible dans le tracker (tant que les glissements de volume
                    # ne sont pas convertis), Live remonterait une vélocité 0 à 1 → simple arrêt
                    stop(channel, at)
                else:
                    events[channel].append({
                        'time': at,
                        'note': cell.note,
                        'instrument': instrument,
                        'velocity': min(127, volume * 2) if file_format == 'xm' else int(volume / 64.0 * 127),
                        'panning_xm': param if file_format == 'xm' and effect == 0x8 else None,
                        'sample_offset_xm': param if effect == 0x9 else None,
                    })
            elif cell.volume is not None:
                channel_volume[channel] = cell.volume
                if cell.volume == 0:
                    stop(channel, at)  # volume 00 / C00 sans note : la note en cours s'arrête

            # ECx : coupe la note du canal au tick x
            if sub_effect == 0xC and (param & 0xF) < speed:
                stop(channel, time + (param & 0xF) * tick)

        # 3. Avancer : EEx répète la ligne (sans rejouer les notes)
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

    # Durées : jusqu'au prochain événement du canal (note ou arrêt), un canal = une voix
    tracks = defaultdict(lambda: defaultdict(list))
    for channel, channel_events in events.items():
        channel_events.sort(key=lambda e: e['time'])
        for i, event in enumerate(channel_events):
            if event.get('is_stop'):
                continue
            if i + 1 < len(channel_events):
                duration = min(channel_events[i + 1]['time'] - event['time'], MAX_DURATION)
            else:
                duration = MAX_DURATION
            if duration <= 0:
                continue  # coupée sur le même tick (EC0) : inaudible
            tracks[channel][event['instrument']].append({
                'time': event['time'],
                'note': event['note'],
                'velocity': event['velocity'],
                'duration': duration,
                'panning_xm': event['panning_xm'],
                'sample_offset_xm': event['sample_offset_xm'],
            })

    return {
        'tracks': tracks,
        'tempo_changes': tempo_changes,
        'end_time': time,
        'duration_seconds': seconds,
        'played_rows': played_rows,
    }
