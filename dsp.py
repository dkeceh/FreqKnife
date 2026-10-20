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
