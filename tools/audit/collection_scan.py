"""Scan a tracker module collection and report which features are actually used."""
import os, sys, struct, json
from collections import Counter, defaultdict

ROOT = sys.argv[1]
SKIP_DIRS = {'doubles', 'Copie de DIVERS', 'Conversions Ableton Live', 'xm2live_converted_tracks'}


def scan_xm(d):
    f = Counter()
    if not d.startswith(b'Extended Module:'):
        return None
    hs = struct.unpack_from('<I', d, 60)[0]
    songlen, restart, nch, npat, ninst, flags, speed, bpm = struct.unpack_from('<8H', d, 64)
    order = list(d[80:80 + songlen])
    f['amiga_freq_table'] = int(not (flags & 1))
    pos = 60 + hs
    pats = []
    for p in range(npat):
        hl, pt, rows, ps = struct.unpack_from('<IBHH', d, pos)
        pos += hl
        data = d[pos:pos + ps]
        pos += ps
        cells = []
        q = 0
        for r in range(rows):
            row = []
            for c in range(nch):
                if not ps or q >= len(data):
                    row.append((0, 0, 0, 0, 0)); continue
                b = data[q]; q += 1
                if b & 0x80:
                    vals = []
                    for bit in range(5):
                        if b & (1 << bit):
                            vals.append(data[q] if q < len(data) else 0); q += 1
                        else:
                            vals.append(0)
                else:
                    vals = [b] + list(data[q:q + 4]); q += 4
                    vals += [0] * (5 - len(vals))
                row.append(tuple(vals))
            cells.append(row)
        pats.append((rows, cells))
    # instruments
    used_inst = set()
    inst_info = {}
    for i in range(ninst):
        isz = struct.unpack_from('<I', d, pos)[0]
        nsmp = struct.unpack_from('<H', d, pos + 27)[0]
        info = {'nsmp': nsmp, 'multi_map': False, 'vol_env': False, 'fadeout': 0, 'smp': []}
        if nsmp:
            keymap = d[pos + 33:pos + 129]
            info['multi_map'] = len(set(keymap)) > 1
            voltype = d[pos + 233]
            info['vol_env'] = bool(voltype & 1)
            info['vol_sustain'] = bool(voltype & 2)
            info['fadeout'] = struct.unpack_from('<H', d, pos + 239)[0]
            shs = struct.unpack_from('<I', d, pos + 29)[0]
            spos = pos + isz
            total = 0
            for s in range(nsmp):
                ln, ls, ll, vol, ft, typ, pan, rel = struct.unpack_from('<IIIBbBBb', d, spos)
                info['smp'].append(dict(len=ln, ft=ft, loop=typ & 3, b16=bool(typ & 0x10), rel=rel, ls=ls, ll=ll))
                total += ln
                spos += shs
            pos = spos + total
        else:
            pos += isz
        inst_info[i + 1] = info
    # walk song in play order
    last_inst = {}
    first_cell = True
    rows_total = 0
    for oi, pn in enumerate(order):
        if pn >= len(pats):
            continue
        rows, cells = pats[pn]
        for r, row in enumerate(cells):
            rows_total += 1
            for c, (n, ins, v, e, pr) in enumerate(row):
                if ins:
                    last_inst[c] = ins
                    used_inst.add(ins)
                if 0 < n < 97:
                    f['notes'] += 1
                    if e == 0x3 or e == 0x5 or (v >> 4) == 0xF:
                        f['note_with_toneporta'] += 1
                if n == 97:
                    f['keyoff'] += 1
                if 0x10 <= v <= 0x50:
                    f['volcol_setvol'] += 1
                    if v == 0x10 and not (0 < n < 97):
                        f['volcol_vol0_nonote'] += 1
                elif v >= 0x60:
                    f['volcol_' + {6: 'volslide', 7: 'volslide', 8: 'finevol', 9: 'finevol', 0xA: 'vibrato',
                                   0xB: 'vibrato', 0xC: 'setpan', 0xD: 'panslide', 0xE: 'panslide',
                                   0xF: 'toneporta'}[v >> 4]] += 1
                if e or pr:
                    if e == 0xE:
                        k = f'E{pr >> 4:X}'
                    elif e == 0xF:
                        k = 'F_speed' if pr < 32 else 'F_bpm'
                        if not (oi == 0 and r == 0):
                            f['F_midsong'] += 1
                    elif e < 36:
                        k = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'[e]
                    else:
                        k = f'?{e}'
                    if k == '0' and pr == 0:
                        continue
                    f['fx_' + k] += 1
    f['rows'] = rows_total
    f['bpm'] = bpm
    f['speed'] = speed
    f['channels'] = nch
    for i in used_inst:
        info = inst_info.get(i)
        if not info:
            continue
        if info['nsmp'] > 1 and info['multi_map']:
            f['inst_multisample'] += 1
        if info['vol_env']:
            f['inst_vol_env'] += 1
        if info['vol_env'] and info['fadeout']:
            f['inst_fadeout'] += 1
        for s in info['smp']:
            if s['b16'] and s['loop']:
                f['smp_16bit_loop'] += 1
            if s['ft']:
                f['smp_finetune'] += 1
            if abs(s['ft']) > 64:
                f['smp_finetune_gt50c'] += 1
            if s['loop'] == 2:
                f['smp_pingpong'] += 1
            if s['loop']:
                f['smp_looped'] += 1
    f['inst_used'] = len(used_inst)
    return f


MOD_SIGS = {b'M.K.': 4, b'M!K!': 4, b'FLT4': 4, b'4CHN': 4, b'6CHN': 6, b'8CHN': 8, b'FLT8': 8, b'CD81': 8, b'OKTA': 8}


def scan_mod(d):
    f = Counter()
    sig = d[1080:1084]
    if sig in MOD_SIGS:
        nch, nsmp, hdr = MOD_SIGS[sig], 31, 1084
    elif sig[2:] == b'CH' and sig[:2].isdigit():
        nch, nsmp, hdr = int(sig[:2]), 31, 1084
    elif sig[1:] == b'CHN' and sig[:1].isdigit():
        nch, nsmp, hdr = int(sig[:1]), 31, 1084
    else:
        nch, nsmp, hdr = 4, 15, 600
        f['mod_15smp'] = 1
    so = 20 + nsmp * 30
    songlen = d[so]
    order = list(d[so + 2:so + 2 + 128])
    npat = max(order) + 1
    fts = []
    for i in range(nsmp):
        b = 20 + i * 30
        ln = struct.unpack_from('>H', d, b + 22)[0] * 2
        ft = d[b + 24] & 0xF
        if ln and ft:
            f['smp_finetune'] += 1
        if ln and struct.unpack_from('>H', d, b + 28)[0] > 1:
            f['smp_looped'] += 1
    rows_total = 0
    for oi, pn in enumerate(order[:songlen]):
        for r in range(64):
            rows_total += 1
            for c in range(nch):
                o = hdr + pn * 64 * nch * 4 + (r * nch + c) * 4
                if o + 4 > len(d):
                    continue
                b0, b1, b2, b3 = d[o:o + 4]
                period = ((b0 & 0xF) << 8) | b1
                e = b2 & 0xF
                pr = b3
                if period:
                    f['notes'] += 1
                    if e in (3, 5):
                        f['note_with_toneporta'] += 1
                if e or pr:
                    if e == 0xE:
                        k = f'E{pr >> 4:X}'
                    elif e == 0xF:
                        k = 'F_speed' if pr < 32 else 'F_bpm'
                        if not (oi == 0 and r == 0):
                            f['F_midsong'] += 1
                    else:
                        k = f'{e:X}'
                    if k == '0' and pr == 0:
                        continue
                    f['fx_' + k] += 1
    f['rows'] = rows_total
    f['channels'] = nch
    return f


results = {}
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [x for x in dns if x not in SKIP_DIRS]
    for fn in fns:
        ext = fn.lower().rsplit('.', 1)[-1]
        if ext not in ('xm', 'mod'):
            continue
        p = os.path.join(dp, fn)
        try:
            d = open(p, 'rb').read()
            r = scan_xm(d) if ext == 'xm' else scan_mod(d)
            if r is not None:
                results[os.path.relpath(p, ROOT)] = (ext, dict(r))
        except Exception as ex:
            results[os.path.relpath(p, ROOT)] = (ext, {'error': str(ex)})

json.dump(results, open(sys.argv[2], 'w'), indent=1)
for fmt in ('xm', 'mod'):
    files = {k: v for k, v in results.items() if v[0] == fmt and 'error' not in v[1]}
    errs = [k for k, v in results.items() if v[0] == fmt and 'error' in v[1]]
    n = len(files)
    print(f'\n===== {fmt.upper()}: {n} files parsed, {len(errs)} errors {errs[:5]}')
    usage = Counter(); totals = Counter()
    for k, (_, f) in files.items():
        for key, val in f.items():
            if key in ('bpm', 'speed', 'channels', 'rows'):
                continue
            if val:
                usage[key] += 1
                totals[key] += val
    for key, cnt in sorted(usage.items(), key=lambda x: -x[1]):
        print(f'{key:24s} {cnt:4d} files ({100 * cnt / n:5.1f}%)  total {totals[key]}')
