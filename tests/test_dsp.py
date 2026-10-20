import numpy as np
import pytest

import dsp


def test_clamp_bands_mengecek_batas():
    assert dsp.clamp_bands(5) == 5
    assert dsp.clamp_bands(1) == 2
    assert dsp.clamp_bands(99) == 30
    assert dsp.clamp_bands("7") == 7
    assert dsp.clamp_bands("bukan-angka") == dsp.BANDS_DEFAULT


def test_cutoff_jumlah_sama_dengan_n_bands_minus_satu():
    cuts = dsp.compute_cutoffs(44100, 5)
    assert len(cuts) == 4


def test_cutoff_monoton_naik_dan_di_dalam_rentang():
    for n in (2, 5, 10, 30):
        cuts = dsp.compute_cutoffs(44100, n)
        assert cuts == sorted(cuts)
        fmax = dsp.max_frequency(44100)
        assert all(20.0 < f < fmax for f in cuts)


def test_cutoff_batas_2_pita_tepat_satu_garis():
    cuts = dsp.compute_cutoffs(44100, 2)
    assert len(cuts) == 1
    assert 20.0 < cuts[0] < dsp.max_frequency(44100)


def test_preset_bass_menumpukkan_cut_di_bawah():
    bass = dsp.compute_cutoffs(44100, 8, "Bass dominan")
    tinggi = dsp.compute_cutoffs(44100, 8, "Mid-High dominan")
    assert np.median(bass) < np.median(tinggi)


def test_sample_rate_rendah_tidak_melebihi_nyquist():
    cuts = dsp.compute_cutoffs(8000, 30)
    assert all(f < 8000 * 0.5 for f in cuts)


def test_preset_tidak_dikenal_jatuh_ke_rata():
    assert dsp.compute_cutoffs(44100, 5, "ngawur") == dsp.compute_cutoffs(44100, 5)
