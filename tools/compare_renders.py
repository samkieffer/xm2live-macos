#!/usr/bin/env python3
"""
Compare deux rendus audio d'un même morceau (référence tracker vs export Ableton)

Mesure, fenêtre par fenêtre : décalage temporel (ms), écart de hauteur (cents),
écart de niveau (dB, relatif à l'écart médian).

Usage:
  python3 tools/compare_renders.py reference.wav export_live.wav [--window 10] [--start 0] [--end 0]

Nécessite librosa (pip install librosa).
"""

import argparse
import numpy as np
import librosa

SR = 22050
HOP = 64                 # résolution temporelle de l'enveloppe d'attaques (~2.9 ms)
CQT_HOP = 512
BINS_PER_OCTAVE = 120    # 10 cents par bin (affiné par interpolation)
CQT_FMIN = 40.0
CQT_OCTAVES = 6


def best_lag(ref, test, start, end, max_lag):
    """Décalage (en trames) de test[start:end] qui maximise la corrélation avec ref[start:end]"""
    segment_ref = ref[start:end] - ref[start:end].mean()
    best, best_score = 0, -np.inf
    for lag in range(-max_lag, max_lag + 1):
        if start + lag < 0 or end + lag > len(test):
            continue
        segment = test[start + lag:end + lag]
        segment = segment - segment.mean()
        score = np.dot(segment_ref, segment) / (np.linalg.norm(segment_ref) * np.linalg.norm(segment) + 1e-12)
        if score > best_score:
            best, best_score = lag, score
    return best, best_score


def pitch_shift_cents(ref_spec, test_spec, max_bins=12):
    """Écart de hauteur (cents) entre deux spectres log-fréquence moyens, interpolé"""
    margin = max_bins + 1
    scores = []
    for k in range(-max_bins, max_bins + 1):
        a = ref_spec[margin:-margin]
        b = np.roll(test_spec, -k)[margin:-margin]
        scores.append(np.corrcoef(a, b)[0, 1])
    scores = np.nan_to_num(np.array(scores), nan=-1.0)
    i = int(np.argmax(scores))
    shift = float(i - max_bins)
    if 0 < i < len(scores) - 1:
        denom = scores[i - 1] - 2 * scores[i] + scores[i + 1]
        if denom != 0:
            shift += 0.5 * (scores[i - 1] - scores[i + 1]) / denom
    return shift * 1200 / BINS_PER_OCTAVE, float(scores[i])


def main():
    parser = argparse.ArgumentParser(description='Compare deux rendus audio')
    parser.add_argument('reference')
    parser.add_argument('test')
    parser.add_argument('--window', type=float, default=10.0, help='taille des fenêtres (s)')
    parser.add_argument('--start', type=float, default=0.0)
    parser.add_argument('--end', type=float, default=0.0, help='0 = jusqu\'à la fin')
    args = parser.parse_args()

    ref, _ = librosa.load(args.reference, sr=SR, mono=True)
    test, _ = librosa.load(args.test, sr=SR, mono=True)
    print(f"Durées: référence {len(ref) / SR:.2f} s, test {len(test) / SR:.2f} s "
          f"(écart {(len(test) - len(ref)) / SR:+.2f} s)")

    # Alignement global sur les 60 premières secondes (décalage de démarrage de l'export)
    onset_ref = librosa.onset.onset_strength(y=ref, sr=SR, hop_length=HOP)
    onset_test = librosa.onset.onset_strength(y=test, sr=SR, hop_length=HOP)
    fps = SR / HOP
    global_lag, _ = best_lag(onset_ref, onset_test, int(2 * fps), int(60 * fps), int(2 * fps))
    print(f"Décalage global du test: {global_lag / fps * 1000:+.1f} ms (compensé ci-dessous)")
    shift = global_lag * HOP
    test = test[shift:] if shift >= 0 else np.concatenate([np.zeros(-shift), test])
    onset_test = librosa.onset.onset_strength(y=test, sr=SR, hop_length=HOP)

    # Spectres log-fréquence pour la hauteur
    def cqt(y):
        return np.abs(librosa.cqt(y, sr=SR, hop_length=CQT_HOP, fmin=CQT_FMIN,
                                  n_bins=BINS_PER_OCTAVE * CQT_OCTAVES,
                                  bins_per_octave=BINS_PER_OCTAVE, filter_scale=2))
    cqt_ref, cqt_test = cqt(ref), cqt(test)
    cqt_fps = SR / CQT_HOP

    end = args.end or min(len(ref), len(test)) / SR
    rows = []
    print(f"\n{'fenêtre':>13}  {'décalage':>9}  {'hauteur':>9}  {'niveau':>7}  corr")
    t = args.start
    while t + args.window / 2 <= end:
        t_end = min(t + args.window, end)
        lag, corr = best_lag(onset_ref, onset_test, int(t * fps), int(t_end * fps), int(0.1 * fps))
        ca, cb = int(t * cqt_fps), int(t_end * cqt_fps)
        spec_ref = np.log1p(100 * cqt_ref[:, ca:cb].mean(axis=1))
        spec_test = np.log1p(100 * cqt_test[:, ca:cb].mean(axis=1))
        cents, pitch_corr = pitch_shift_cents(spec_ref, spec_test)
        rms_ref = np.sqrt(np.mean(ref[int(t * SR):int(t_end * SR)] ** 2)) + 1e-9
        rms_test = np.sqrt(np.mean(test[int(t * SR):int(t_end * SR)] ** 2)) + 1e-9
        rows.append((t, t_end, lag / fps * 1000, cents, 20 * np.log10(rms_test / rms_ref), corr))
        t += args.window

    gain_median = np.median([r[4] for r in rows])
    for t0, t1, ms, cents, db, corr in rows:
        flags = []
        if abs(ms) > 20:
            flags.append('TIMING')
        if abs(cents) > 10:
            flags.append('HAUTEUR')
        if abs(db - gain_median) > 3:
            flags.append('NIVEAU')
        print(f"{t0:6.0f}-{t1:4.0f} s  {ms:+7.1f} ms  {cents:+6.1f} ct  {db - gain_median:+5.1f} dB  {corr:.2f}  {' '.join(flags)}")

    offsets = np.array([r[2] for r in rows])
    times = np.array([(r[0] + r[1]) / 2 for r in rows])
    drift = np.polyfit(times / 60, offsets, 1)[0] if len(rows) > 2 else 0.0
    cents_all = np.array([r[3] for r in rows])
    print(f"\nRésumé: hauteur médiane {np.median(cents_all):+.1f} cents "
          f"(pire {cents_all[np.argmax(np.abs(cents_all))]:+.1f}), "
          f"dérive {drift:+.1f} ms/min, gain médian {gain_median:+.1f} dB, "
          f"{sum(1 for r in rows if abs(r[2]) > 20 or abs(r[3]) > 10)} fenêtre(s) signalée(s) sur {len(rows)}")


if __name__ == '__main__':
    main()
