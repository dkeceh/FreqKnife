"""Pemotongan frekuensi — numpy murni, tanpa Qt, tanpa filesystem."""

import numpy as np

PRESETS = {"Rata (log)": 1.0, "Bass dominan": 1.6, "Mid-High dominan": 0.62}
PRESET_NAMES = list(PRESETS)

F_MIN = 20.0
F_MAX = 20000.0

BANDS_DEFAULT = 5
BANDS_SLIDER_MIN, BANDS_SLIDER_MAX = 3, 10
BANDS_MIN, BANDS_MAX = 2, 30

FRAME_DEFAULT = 4096


def clamp_bands(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return BANDS_DEFAULT
    return max(BANDS_MIN, min(BANDS_MAX, value))


def max_frequency(sample_rate):
    return min(F_MAX, sample_rate * 0.5 * 0.98)


def compute_cutoffs(sample_rate, n_bands, preset=PRESET_NAMES[0]):
    """Titik cut (Hz) sebanyak n_bands - 1, merata logaritmik dengan skew preset."""
    n_bands = clamp_bands(n_bands)
    p = PRESETS.get(preset, 1.0)
    fmax = max_frequency(sample_rate)
    t = np.arange(1, n_bands, dtype=float) / n_bands
    return [float(F_MIN * (fmax / F_MIN) ** (ti ** p)) for ti in t]


def band_masks(n_fft, sample_rate, n_bands, preset=PRESET_NAMES[0]):
    """Daftar mask boolean rfft, saling bertetangga dan meliputi seluruh bin.

    Jumlah mask bisa kurang dari `n_bands` bila dua cut jatuh ke bin FFT yang
    sama; pemanggil harus membaca `len(...)` hasil fungsi ini.
    """
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sample_rate)
    cuts = compute_cutoffs(sample_rate, n_bands, preset)
    edges = sorted({0, len(freqs)} | {int(np.searchsorted(freqs, f)) for f in cuts})
    edges[0], edges[-1] = 0, len(freqs)

    masks = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi > lo:
            mask = np.zeros(len(freqs), dtype=bool)
            mask[lo:hi] = True
            masks.append(mask)
    return masks


def iter_split(samples, sample_rate, n_bands, preset=PRESET_NAMES[0], frame=FRAME_DEFAULT):
    """Yield (indeks_pita, chunk float32) sambil jalan — memori tetap kecil.

    Total chunk per pita tepat sama dengan panjang `samples`, sehingga stream
    boleh ditulis apa adanya tanpa dipotong lagi di pemanggil.
    shortcut: tiap frame menghasilkan n_bands chunk, jadi file sangat panjang
    dengan pita banyak butuh waktu; naikkan frame bila perlu.
    """
    samples = np.asarray(samples, dtype=np.float32)
    satu_dim = samples.ndim == 1
    if satu_dim:
        samples = samples[:, None]
    total, channels = samples.shape

    hop = frame // 2
    window = np.hanning(frame + 1)[:-1].astype(np.float32)
    masks = band_masks(frame, sample_rate, n_bands, preset)
    acc = np.zeros((len(masks), frame, channels), dtype=np.float32)

    # nol di depan supaya sampel pertama ikut dapat tumpang tindih penuh
    padded = np.concatenate([
        np.zeros((hop, channels), dtype=np.float32),
        samples,
        np.zeros((frame, channels), dtype=np.float32),
    ])

    keluar = 0
    for start in range(0, len(padded) - frame + 1, hop):
        spec = np.fft.rfft(padded[start:start + frame] * window[:, None], axis=0)
        for i, mask in enumerate(masks):
            acc[i] += np.fft.irfft(spec * mask[:, None], n=frame, axis=0).astype(np.float32)

        # frame 0 hanya memuat nol depan: lepas tanpa diemit, karena itu
        # bukan bagian sinyal asli
        panjang = min(hop, total - keluar) if start else 0
        for i in range(len(masks)):
            if panjang:
                potongan = acc[i][:panjang, 0] if satu_dim else acc[i][:panjang]
                yield i, potongan.copy()
            acc[i][:hop] = acc[i][hop:]
            acc[i][hop:] = 0.0

        if start:
            keluar += panjang
            if keluar >= total:
                return


def split_bands(samples, sample_rate, n_bands, preset=PRESET_NAMES[0], frame=FRAME_DEFAULT):
    """Ringkasan `iter_split` yang mengembalikan seluruh pita utuh. Untuk tes dan berkas pendek."""
    samples = np.asarray(samples, dtype=np.float32)
    satu_dim = samples.ndim == 1
    if satu_dim:
        samples = samples[:, None]
    total = len(samples)

    parts = []
    for i, chunk in iter_split(samples, sample_rate, n_bands, preset, frame):
        while len(parts) <= i:
            parts.append([])
        parts[i].append(chunk)
    hasil = [np.concatenate(p)[:total] for p in parts]
    return [b[:, 0] for b in hasil] if satu_dim else hasil
