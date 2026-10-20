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
    bass = dsp.compute_cutoffs(44100, 8, "Bass-heavy")
    tinggi = dsp.compute_cutoffs(44100, 8, "Mid/High-heavy")
    assert np.median(bass) < np.median(tinggi)


def test_sample_rate_rendah_tidak_melebihi_nyquist():
    cuts = dsp.compute_cutoffs(8000, 30)
    assert all(f < 8000 * 0.5 for f in cuts)


def test_preset_tidak_dikenal_jatuh_ke_rata():
    assert dsp.compute_cutoffs(44100, 5, "ngawur") == dsp.compute_cutoffs(44100, 5)


def test_mask_saling_melengkapi_tanpa_celah_dan_tumpang_tindih():
    for n in (2, 5, 30):
        masks = dsp.band_masks(4096, 44100, n)
        total = np.sum(np.stack(masks), axis=0)
        assert np.all(total == 1), "setiap bin harus jatuh tepat satu pita"
        assert all(m.dtype == bool for m in masks)


def test_mask_jumlah_pita_sama_dengan_permintaan():
    assert len(dsp.band_masks(4096, 44100, 5)) == 5
    assert len(dsp.band_masks(4096, 44100, 2)) == 2


def test_mask_sampel_rendah_tidak_menghasilkan_pita_kosong():
    masks = dsp.band_masks(4096, 8000, 30)
    assert all(m.any() for m in masks)


def _acak(n=16384, ch=2, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal((n, ch)) * 0.1).astype(np.float32)


def test_rekonstruksi_stereo_sampai_presisi_float():
    x = _acak()
    bands = dsp.split_bands(x, 44100, 5)
    assert len(bands) == 5
    assert all(b.shape == x.shape for b in bands)
    galat = float(np.abs(np.sum(bands, axis=0) - x).max())
    assert galat < 1e-3, f"galat {galat}"


def test_rekonstruksi_mono():
    x = _acak(ch=1)[:, 0]
    bands = dsp.split_bands(x, 44100, 3)
    galat = float(np.abs(np.sum(bands, axis=0) - x).max())
    assert galat < 1e-3


def test_rekonstruksi_nol_dan_dua_pita():
    for n in (2, 30):
        x = _acak(seed=n)
        bands = dsp.split_bands(x, 44100, n)
        # jumlah bisa berkurang 1 bila dua cut jatuh ke bin FFT yang sama
        assert len(bands) == len(dsp.band_masks(dsp.FRAME_DEFAULT, 44100, n))


def test_rekonstruksi_preset_lain():
    x = _acak(seed=7)
    for preset in dsp.PRESET_NAMES:
        bands = dsp.split_bands(x, 44100, 6, preset)
        galat = float(np.abs(np.sum(bands, axis=0) - x).max())
        assert galat < 1e-3, f"preset {preset}: {galat}"


def _energi(x):
    return float(np.sum(np.square(x), dtype=np.float64))


def test_nada_hanya_muncul_di_pita_yang_memuatnya():
    sr = 44100
    n = 32768
    t = np.arange(n) / sr
    x = (0.5 * np.sin(2 * np.pi * 100.0 * t)).astype(np.float32)

    bands = dsp.split_bands(x, sr, 6)
    energi = [_energi(b) for b in bands]
    dominan = int(np.argmax(energi))

    cuts = dsp.compute_cutoffs(sr, 6)
    bawah = 0.0 if dominan == 0 else cuts[dominan - 1]
    atas = dsp.max_frequency(sr) if dominan == len(cuts) else cuts[dominan]
    assert bawah <= 100.0 <= atas, f"100 Hz jatuh di pita {dominan} ({bawah}-{atas})"

    # pita lain nyaris nol dibanding pita dominan
    for i, e in enumerate(energi):
        if i != dominan:
            assert e < energi[dominan] * 1e-3, f"pita {i} bocor: {e} vs {energi[dominan]}"


def test_kanan_dan_kiri_tidak_tercampur():
    sr = 44100
    n = 16384
    t = np.arange(n) / sr
    kiri = (0.5 * np.sin(2 * np.pi * 300.0 * t)).astype(np.float32)
    kanan = (0.5 * np.sin(2 * np.pi * 5000.0 * t)).astype(np.float32)
    x = np.stack([kiri, kanan], axis=1)

    bands = dsp.split_bands(x, sr, 5)
    for b in bands:
        assert b.shape[1] == 2
        assert b.dtype == np.float32
    # pilih pita berdasarkan titik cut, bukan asumsi indeks
    cuts = dsp.compute_cutoffs(sr, 5)
    low = bands[int(np.searchsorted(cuts, 300.0))]
    assert _energi(low[:, 0]) > _energi(low[:, 1]) * 10
    high = bands[int(np.searchsorted(cuts, 5000.0))]
    assert _energi(high[:, 1]) > _energi(high[:, 0]) * 10


def test_masukan_1d_menghasilkan_1d():
    x = np.zeros(8192, dtype=np.float32)
    bands = dsp.split_bands(x, 44100, 4)
    assert all(b.ndim == 1 for b in bands)
    # iter_split juga harus 1-D, bukan (n, 1)
    for _, chunk in dsp.iter_split(x, 44100, 4):
        assert chunk.ndim == 1
        assert chunk.dtype == np.float32


def test_iter_split_menghasilkan_seluruh_sampel():
    x = _acak(n=10000, ch=2)
    terkumpul = [0] * 5
    for i, chunk in dsp.iter_split(x, 44100, 5):
        terkumpul[i] += len(chunk)
        # bentuk chunk harus mengikuti masukan (stereo = 2-D) dan selalu float32
        assert chunk.ndim == 2 and chunk.dtype == np.float32
    # persis sepanjang sinyal — worker menulis stream ini tanpa memotong.
    # Diukur langsung dari iter_split, bukan split_bands, supaya truncation
    # [:total] di split_bands tidak bisa menyembunyikan bug kelebihan-emit.
    assert terkumpul == [len(x)] * 5


def test_split_pada_sample_rate_8000_tetap_jalan():
    x = _acak(n=8192, ch=1, seed=11)
    bands = dsp.split_bands(x, 8000, 30)
    assert len(bands) == len(dsp.band_masks(dsp.FRAME_DEFAULT, 8000, 30))
    galat = float(np.abs(np.sum(bands, axis=0) - x).max())
    assert galat < 1e-3
