# FreqKnife Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplikasi desktop yang memisahkan satu file suara menjadi N file pita frekuensi, dengan slider jumlah file, preset sebaran, drag & drop, progress bar, dan tombol Batalkan.

**Architecture:** DSP murni numpy (`dsp.py`) memotong spektrum dengan STFT overlap-add sehingga semua pita saling melengkapi. `audio_io.py` satu-satunya modul yang menjalankan ffmpeg (decode ke raw f32le, encode per pita). `worker.py` menjahit keduanya di QThread dan memancarkan sinyal progress. `main.py` murni UI.

**Tech Stack:** Python 3.11+, numpy, PySide6, Pillow, pytest, PyInstaller, ffmpeg.

**Spec:** `docs/superpowers/specs/2026-10-20-freqknife-design.md`

---

## Catatan sebelum mulang

- Repo: `/Volumes/VGEN10S1T/FreqSplit` (remote `https://github.com/dkeceh/FreqKnife.git`). Jangan rename folder lokalnya.
- Semua perintah dijalankan dari root repo kecuali dinyatakan lain.
- `scipy` **tidak dipakai** — FFT numpy cukup. Jangan menambahkannya ke `requirements.txt`.
- `gh` CLI tidak terautentikasi dan tidak diperlukan. Push memakai kredensial keychain bawaan git.

## File Structure

| File | Tanggung jawab |
|---|---|
| `dsp.py` | Hitung titik cut, mask bin, STFT overlap-add. Numpy saja. |
| `audio_io.py` | Probe/decode/encode via ffmpeg, auto-rename, penamaan file. |
| `worker.py` | `process_file()` murni Python + pembungkus `SplitWorker(QThread)`. |
| `main.py` | Jendela, kontrol, drag & drop, handler progress/error, `--selftest`. |
| `tests/test_dsp.py` | Pengujian DSP (tanpa Qt, tanpa ffmpeg). |
| `tests/test_audio_io.py` | Pengujian I/O (butuh ffmpeg). |
| `tests/test_worker.py` | Pengujian orkestrasi + cancel (butuh ffmpeg). |
| `tests/test_main.py` | Fungsi murni UI (clamp) tanpa QApplication. |
| `build/make_icons.py` | SVG-nya digambar Pillow → PNG → .icns/.ico. |
| `build/build_mac.sh` | Build `.app` Mac satu perintah. |
| `.github/workflows/build.yml` | Matrix 3 OS, upload artifact, selftest binary. |

---

### Task 1: Kerangka proyek dan dependensi

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py` (kosong)
- Create: `dsp.py` (stub kosong dulu)

- [ ] **Step 1: Buat venv dan pasang dependensi**

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet "numpy>=1.26" "PySide6>=6.7" "pillow>=10.0" "pytest>=8.0" "pyinstaller>=6.0"
```

Expected: tidak ada error, `python -c "import numpy, PySide6, PIL; print('ok')"` mencetak `ok`.

- [ ] **Step 2: Tulis `requirements.txt`**

```
numpy>=1.26
PySide6>=6.7
pillow>=10.0
pytest>=8.0
pyinstaller>=6.0
```

- [ ] **Step 3: Tulis `pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = tests
addopts = -q
```

- [ ] **Step 4: Buat stub `dsp.py` dan `tests/__init__.py`**

`dsp.py`:

```python
"""Pemotongan frekuensi — numpy murni, tanpa Qt, tanpa filesystem."""
```

`tests/__init__.py`: file kosong.

- [ ] **Step 5: Verifikasi pytest jalan**

```bash
. .venv/bin/activate && pytest
```

Expected: exit code 5 ("no tests ran") — belum ada test, itu normal.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini dsp.py tests/__init__.py .gitignore
git commit -m "chore: scaffold proyek FreqKnife"
```

---

### Task 2: `compute_cutoffs`, `clamp_bands`, preset

**Files:**
- Modify: `dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Tulis test yang gagal**

`tests/test_dsp.py`:

```python
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
```

- [ ] **Step 2: Jalankan, pastikan gagal**

```bash
. .venv/bin/activate && pytest tests/test_dsp.py
```

Expected: FAIL dengan `AttributeError: module 'dsp' has no attribute 'clamp_bands'`.

- [ ] **Step 3: Tulis implementasi**

Ganti seluruh isi `dsp.py`:

```python
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
```

- [ ] **Step 4: Jalankan, pastikan lulus**

```bash
. .venv/bin/activate && pytest tests/test_dsp.py
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add dsp.py tests/test_dsp.py
git commit -m "feat: hitung titik cut frekuensi dengan preset sebaran"
```

---

### Task 3: `band_masks` — partisi bin

**Files:**
- Modify: `dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Tambahkan test yang gagal**

Tambahkan di `tests/test_dsp.py`:

```python
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
```

- [ ] **Step 2: Jalankan, pastikan gagal**

```bash
. .venv/bin/activate && pytest tests/test_dsp.py
```

Expected: FAIL `AttributeError: ... 'band_masks'`.

- [ ] **Step 3: Tambahkan implementasi**

Tambahkan di akhir `dsp.py`:

```python
def band_masks(n_fft, sample_rate, n_bands, preset=PRESET_NAMES[0]):
    """Daftar mask boolean rfft, saling bertetangga dan meliputi seluruh bin."""
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
```

- [ ] **Step 4: Jalankan, pastikan lulus**

```bash
. .venv/bin/activate && pytest tests/test_dsp.py
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add dsp.py tests/test_dsp.py
git commit -m "feat: partisi bin FFT menjadi mask pita yang saling melengkapi"
```

---

### Task 4: STFT overlap-add streaming — `iter_split` dan `split_bands`

**Files:**
- Modify: `dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Tambahkan test yang gagal**

Tambahkan di `tests/test_dsp.py`:

```python
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
        galat = float(np.abs(np.sum(bands, axis=0) - x).max())
        assert galat < 1e-3


def test_rekonstruksi_preset_lain():
    x = _acak(seed=7)
    for preset in dsp.PRESET_NAMES:
        bands = dsp.split_bands(x, 44100, 6, preset)
        galat = float(np.abs(np.sum(bands, axis=0) - x).max())
        assert galat < 1e-3, f"preset {preset}: {galat}"
```

- [ ] **Step 2: Jalankan, pastikan gagal**

```bash
. .venv/bin/activate && pytest tests/test_dsp.py
```

Expected: FAIL `AttributeError: ... 'split_bands'`.

- [ ] **Step 3: Tambahkan implementasi**

Tambahkan di akhir `dsp.py`:

```python
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
                # selalu .copy(): acc dipindah tepat setelah yield ini
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
```

- [ ] **Step 4: Jalankan, pastikan lulus**

```bash
. .venv/bin/activate && pytest tests/test_dsp.py
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add dsp.py tests/test_dsp.py
git commit -m "feat: STFT overlap-add streaming dengan rekonstruksi sempurna"
```

---

### Task 5: Isolasi nada, channel, dan kasus pinggir

**Files:**
- Modify: `dsp.py` (hanya bila ada bug)
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Tambahkan test yang gagal**

Tambahkan di `tests/test_dsp.py`:

```python
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
```

- [ ] **Step 2: Jalankan, pastikan lulus atau telusuri**

```bash
. .venv/bin/activate && pytest tests/test_dsp.py -v
```

Expected: 19 passed. Kalau `test_nada_hanya_muncul_di_pita_yang_memuatnya` gagal, **jangan longgarkan ambang tes**. Ukur dulu penyebabnya: kalau 100 Hz kebetulan jatuh persis di bin batas pita (jaraknya < 1 bin ≈ 10.8 Hz dari cut), geser pembulatan di `band_masks` — itu perbaikan nyata. Kalau penyebabnya kebocoran spektrum, laporkan NEEDS_CONTEXT beserta angkanya, jangan menebak.

- [ ] **Step 3: Commit**

```bash
git add dsp.py tests/test_dsp.py
git commit -m "test: isolasi pita, pemisahan channel, dan kasus pinggir DSP"
```

---

### Task 6: `audio_io` — probe, decode, buka raw

**Files:**
- Create: `audio_io.py`
- Test: `tests/test_audio_io.py`

- [ ] **Step 1: Tulis test yang gagal**

`tests/test_audio_io.py`:

```python
import subprocess
from pathlib import Path

import numpy as np
import pytest

import audio_io

pytestmark = pytest.mark.skipif(
    audio_io.ffmpeg_missing(), reason="ffmpeg/ffprobe tidak tersedia")


def _buat_wav(path, sr=44100, ch=2, detik=1.0):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:sample_rate={sr}:duration={detik}",
         "-ac", str(ch), str(path)], check=True)
    return path


def test_probe_mengembalikan_metadata(tmp_path):
    info = audio_io.probe(_buat_wav(tmp_path / "u.wav"))
    assert info["sample_rate"] == 44100
    assert info["channels"] == 2
    assert 0.9 < info["duration"] < 1.1


def test_decode_menghasilkan_raw_dengan_panjang_tepat(tmp_path):
    wav = _buat_wav(tmp_path / "u.wav", sr=22050, ch=1, detik=0.5)
    raw = tmp_path / "u.f32le"
    sr, ch, n = audio_io.decode_to_raw(wav, raw)
    assert (sr, ch) == (22050, 1)
    assert raw.stat().st_size == n * 4 * ch
    assert 11000 < n < 11100


def test_open_raw_membaca_sebagai_rangkaian(tmp_path):
    wav = _buat_wav(tmp_path / "u.wav", ch=2, detik=0.25)
    raw = tmp_path / "u.f32le"
    sr, ch, n = audio_io.decode_to_raw(wav, raw)
    data = audio_io.open_raw(raw, n, ch)
    assert data.shape == (n, 2)
    assert data.dtype == np.float32


def test_decode_mp3_bisa_dibuka(tmp_path):
    wav = _buat_wav(tmp_path / "u.wav")
    mp3 = tmp_path / "u.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), str(mp3)], check=True)
    sr, ch, n = audio_io.decode_to_raw(mp3, tmp_path / "u.f32le")
    assert sr == 44100 and ch == 2 and n > 40000


def test_file_rusak_melempar_error(tmp_path):
    rusak = tmp_path / "rusak.mp3"
    rusak.write_bytes(b"ini bukan audio sama sekali")
    with pytest.raises(Exception):
        audio_io.probe(rusak)


def test_ffmpeg_missing_tidak_pernah_error():
    assert isinstance(audio_io.ffmpeg_missing(), bool)
```

- [ ] **Step 2: Jalankan, pastikan gagal**

```bash
. .venv/bin/activate && pytest tests/test_audio_io.py
```

Expected: FAIL `ModuleNotFoundError: No module named 'audio_io'`.

- [ ] **Step 3: Tulis implementasi**

`audio_io.py`:

```python
"""Decode/encode audio lewat ffmpeg. Satu-satunya modul yang menjalankan subprocess."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus",
    ".aiff", ".aif", ".wma", ".mp4", ".webm",
}

CODEC_BY_EXT = {
    ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    ".flac": ["-c:a", "flac"],
    ".m4a": ["-c:a", "aac", "-b:a", "256k"],
    ".aac": ["-c:a", "aac", "-b:a", "256k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "6"],
    ".oga": ["-c:a", "libvorbis", "-q:a", "6"],
    ".opus": ["-c:a", "libopus", "-b:a", "160k"],
    ".aiff": ["-c:a", "pcm_s24le"],
    ".aif": ["-c:a", "pcm_s24le"],
    ".wav": ["-c:a", "pcm_s24le"],
}
FALLBACK_EXT = ".wav"
FALLBACK_CODEC = ["-c:a", "pcm_s16le"]


def _alat(nama):
    """Cari binary: env override → bundel PyInstaller → PATH."""
    env = os.environ.get(nama.upper() + "_BIN")
    if env:
        return env
    bundel = getattr(sys, "_MEIPASS", None)
    if bundel:
        kandidat = Path(bundel) / nama
        if kandidat.exists():
            return str(kandidat)
    return shutil.which(nama) or nama


def ffmpeg_path():
    return _alat("ffmpeg")


def ffprobe_path():
    return _alat("ffprobe")


def ffmpeg_missing():
    return shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


def probe(path):
    """Kembalikan sample_rate, channels, duration."""
    hasil = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries",
         "format=duration:stream=sample_rate,channels", "-of", "json", str(path)],
        capture_output=True, text=True)
    if hasil.returncode != 0:
        raise RuntimeError(f"ffmpeg tidak bisa membuka {Path(path).name}")
    data = json.loads(hasil.stdout)
    stream = next((s for s in data.get("streams", []) if s.get("sample_rate")), None)
    if stream is None:
        raise RuntimeError(f"{Path(path).name} tidak punya jalur audio")
    return {
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "duration": float(data.get("format", {}).get("duration") or 0.0),
    }


def decode_to_raw(path, raw_path):
    """Decode ke .f32le mentah. Return (sample_rate, channels, n_frames)."""
    info = probe(path)
    with open(raw_path, "wb") as fh:
        hasil = subprocess.run(
            [ffmpeg_path(), "-v", "error", "-y", "-i", str(path), "-vn",
             "-f", "f32le", "-acodec", "pcm_f32le", "-"],
            stdout=fh, stderr=subprocess.PIPE)
    if hasil.returncode != 0:
        raise RuntimeError(
            "ffmpeg gagal decode:\n" +
            "\n".join(hasil.stderr.decode(errors="replace").strip().splitlines()[-5:]))
    n_frames = os.path.getsize(raw_path) // (4 * info["channels"])
    return info["sample_rate"], info["channels"], n_frames


def open_raw(raw_path, n_frames, channels):
    """Baca raw sebagai memmap — hemat memori untuk file panjang."""
    return np.memmap(raw_path, dtype=np.float32, mode="r", shape=(n_frames, channels))


def output_plan(source_ext):
    """(ekstensi keluaran, argumen codec) yang mengikuti format input."""
    ext = (source_ext or "").lower()
    if ext in CODEC_BY_EXT:
        return ext, CODEC_BY_EXT[ext]
    return FALLBACK_EXT, FALLBACK_CODEC


def band_path(dest_dir, stem, index, ext):
    return Path(dest_dir) / f"{stem}_band{index:02d}{ext}"


def available_path(path):
    """Tambah suffix _2, _3, … bila nama sudah terpakai."""
    path = Path(path)
    if not path.exists():
        return path
    n = 2
    while True:
        kandidat = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not kandidat.exists():
            return kandidat
        n += 1


def encode_raw(raw_path, out_path, sample_rate, channels, codec_args):
    hasil = subprocess.run(
        [ffmpeg_path(), "-v", "error", "-y", "-f", "f32le",
         "-ar", str(sample_rate), "-ac", str(channels), "-i", str(raw_path),
         *codec_args, str(out_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if hasil.returncode != 0:
        raise RuntimeError(
            "ffmpeg gagal encode:\n" +
            "\n".join(hasil.stderr.decode(errors="replace").strip().splitlines()[-5:]))
    return Path(out_path)
```

- [ ] **Step 4: Jalankan, pastikan lulus**

```bash
. .venv/bin/activate && pytest tests/test_audio_io.py
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add audio_io.py tests/test_audio_io.py
git commit -m "feat: decode/encode ffmpeg dan penamaan file hasil"
```

---

### Task 7: Format ikut input + auto-rename

**Files:**
- Modify: `audio_io.py` (hanya bila ada bug)
- Test: `tests/test_audio_io.py`

- [ ] **Step 1: Tambahkan test yang gagal**

Tambahkan di `tests/test_audio_io.py`:

```python
@pytest.mark.parametrize("source_ext,expected_ext", [
    (".mp3", ".mp3"), (".MP3", ".mp3"), (".flac", ".flac"),
    (".m4a", ".m4a"), (".wav", ".wav"), (".aiff", ".aiff"),
    (".wma", ".wav"), (".xyz", ".wav"), ("", ".wav"),
])
def test_format_keluaran_mengikuti_input(source_ext, expected_ext):
    ext, codec = audio_io.output_plan(source_ext)
    assert ext == expected_ext
    assert codec and codec[0] == "-c:a"


def test_encode_raw_menghasilkan_file_bisa_dibuka(tmp_path):
    sr, ch, detik = 44100, 2, 0.5
    n = int(sr * detik)
    samples = (np.sin(2 * np.pi * 440 * np.arange(n) / sr) * 0.5).astype(np.float32)
    raw = tmp_path / "pita.f32le"
    raw.write_bytes(np.repeat(samples[:, None], ch, axis=1).tobytes())

    out = audio_io.encode_raw(raw, tmp_path / "pita.mp3", sr, ch,
                              audio_io.output_plan(".mp3")[1])
    assert out.exists() and out.stat().st_size > 1000
    assert audio_io.probe(out)["sample_rate"] == sr


def test_auto_rename_menambah_suffix(tmp_path):
    pertama = tmp_path / "lagu_band01.mp3"
    pertama.write_bytes(b"x")
    kedua = audio_io.available_path(pertama)
    assert kedua.name == "lagu_band01_2.mp3"
    kedua.write_bytes(b"x")
    assert audio_io.available_path(pertama).name == "lagu_band01_3.mp3"


def test_band_path_format():
    p = audio_io.band_path("/tmp", "lagu", 3, ".mp3")
    assert p.name == "lagu_band03.mp3"


def test_komposisi_tidak_pernah_menimpa_file_ada(tmp_path):
    """encode_raw punya -y dan menimpa; jaminan ada di pemanggil."""
    sr, ch, n = 44100, 1, 1000
    samples = (np.sin(2 * np.pi * 440 * np.arange(n) / sr) * 0.5).astype(np.float32)
    raw = tmp_path / "pita.f32le"
    raw.write_bytes(samples.tobytes())

    sumber = tmp_path / "lagu.wav"
    sumber.write_bytes(b"PENTING JANGAN DITIMPA")

    tujuan = audio_io.available_path(audio_io.band_path(tmp_path, "lagu", 1, ".wav"))
    assert tujuan.name == "lagu_band01.wav"
    audio_io.encode_raw(raw, tujuan, sr, ch, audio_io.output_plan(".wav")[1])

    assert sumber.read_bytes() == b"PENTING JANGAN DITIMPA"
    # berkas hasil tetap ada dan berbeda dari yang sudah ada
    kedua = audio_io.available_path(audio_io.band_path(tmp_path, "lagu", 1, ".wav"))
    assert kedua.name == "lagu_band01_2.wav"
    assert audio_io.probe(tujuan)["sample_rate"] == sr
```

- [ ] **Step 2: Jalankan dan pastikan lulus**

```bash
. .venv/bin/activate && pytest tests/test_audio_io.py
```

Expected: 21 passed (8 sebelumnya + 9 kasus parametrized + 3 + 1 komposisi). Kalau `test_format_keluaran_mengikuti_input` gagal, perbaiki `CODEC_BY_EXT` / `output_plan` di `audio_io.py`. Suite penuh harus 40 passed.

- [ ] **Step 3: Commit**

```bash
git add audio_io.py tests/test_audio_io.py
git commit -m "feat: format keluaran mengikuti input dan auto-rename"
```

---

### Task 8: `process_file` — orkestrasi, progress, cancel

**Files:**
- Create: `worker.py`
- Test: `tests/test_worker.py`

- [ ] **Step 1: Tulis test yang gagal**

`tests/test_worker.py`:

```python
import subprocess

import pytest

import audio_io
import worker

pytestmark = pytest.mark.skipif(
    audio_io.ffmpeg_missing(), reason="ffmpeg tidak tersedia")


def _buat_sumber(tmp_path, nama="lagu.wav", sr=44100, detik=2.0):
    path = tmp_path / nama
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:sample_rate={sr}:duration={detik}", path],
        check=True)
    return path


def test_menghasilkan_n_file_dengan_nama_benar(tmp_path):
    src = _buat_sumber(tmp_path)
    hasil = worker.process_file(src, tmp_path, 5, "Rata (log)")
    assert len(hasil) == 5
    assert [p.name for p in hasil] == [
        f"lagu_band0{i}.wav" for i in range(1, 6)]
    for p in hasil:
        assert p.exists() and p.stat().st_size > 0
        assert audio_io.probe(p)["sample_rate"] == 44100


def test_progress_monoton_naik_sampai_100(tmp_path):
    src = _buat_sumber(tmp_path, nama="lagu.mp3", detik=1.0)
    nilai = []
    worker.process_file(src, tmp_path, 4, "Rata (log)",
                        on_progress=nilai.append)
    assert nilai == sorted(nilai)
    assert nilai[-1] == 100
    assert all(0 <= v <= 100 for v in nilai)


def test_format_output_mengikuti_input_mp3(tmp_path):
    src = _buat_sumber(tmp_path, nama="lagu.wav")
    mp3 = tmp_path / "lagu.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), str(mp3)], check=True)
    hasil = worker.process_file(mp3, tmp_path / "keluar", 3, "Rata (log)")
    assert all(p.suffix == ".mp3" for p in hasil)
    assert audio_io.probe(hasil[0])["channels"] == 1


def test_folder_tujuan_dibuat_bila_belum_ada(tmp_path):
    src = _buat_sumber(tmp_path, detik=0.5)
    tujuan = tmp_path / "belum" / "ada"
    hasil = worker.process_file(src, tujuan, 2, "Rata (log)")
    assert all(p.exists() for p in hasil)


def test_file_band_yang_sudah_ada_tidak_pernah_ditimpa(tmp_path):
    """Jaminan \"file user tidak pernah hilang\" ada di pemanggil, bukan di ffmpeg."""
    src = _buat_sumber(tmp_path, detik=1.0)
    lama = tmp_path / "lagu_band01.wav"
    lama.write_bytes(b"PUNYA USER JANGAN DITIMPA")

    hasil = worker.process_file(src, tmp_path, 3, "Rata (log)")

    assert lama.read_bytes() == b"PUNYA USER JANGAN DITIMPA"
    assert [p.name for p in hasil] == [
        "lagu_band01_2.wav", "lagu_band02.wav", "lagu_band03.wav"]


def test_cancel_menghentikan_dan_melempar_jobcancelled(tmp_path):
    src = _buat_sumber(tmp_path, detik=3.0)
    dipanggil = []

    def batal():
        return len(dipanggil) > 0

    with pytest.raises(worker.JobCancelled):
        worker.process_file(src, tmp_path, 5, "Rata (log)",
                            on_progress=lambda p: dipanggil.append(p),
                            is_cancelled=batal)


def test_file_terlanjur_tulis_tercatat_untuk_dihapus(tmp_path):
    src = _buat_sumber(tmp_path, detik=3.0)
    ditulis = []
    panggilan = []

    def batal():
        return len(panggilan) > 3

    with pytest.raises(worker.JobCancelled):
        worker.process_file(src, tmp_path, 5, "Rata (log)",
                            on_progress=lambda p: panggilan.append(p),
                            is_cancelled=batal, written=ditulis)
    # sebelum encode tidak ada file keluaran, jadi daftar kosong
    assert ditulis == []


def test_folder_temp_dibersihkan(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    src = _buat_sumber(tmp_path, detik=0.5)
    worker.process_file(src, tmp_path, 2, "Rata (log)")
    assert list((tmp_path / "tmp").iterdir()) == []
```

- [ ] **Step 2: Jalankan, pastikan gagal**

```bash
. .venv/bin/activate && pytest tests/test_worker.py
```

Expected: FAIL `ModuleNotFoundError: No module named 'worker'`.

- [ ] **Step 3: Tulis implementasi**

`worker.py`:

```python
"""Orkestrasi pemisahan. `process_file` murni Python — bisa dites tanpa Qt."""

import shutil
import tempfile
from pathlib import Path

import audio_io
import dsp

FRAME = dsp.FRAME_DEFAULT


class JobCancelled(Exception):
    pass


def process_file(source, dest_dir, n_bands, preset,
                 on_progress=None, on_status=None, is_cancelled=None, written=None):
    """Pisahkan satu file. Kembalikan daftar Path hasil.

    `written` diisi bertahap supaya pemanggil bisa menghapus hasil parsial saat batal.
    """
    source = Path(source)
    dest_dir = Path(dest_dir)
    written = [] if written is None else written
    on_progress = on_progress or (lambda p: None)
    on_status = on_status or (lambda s: None)
    is_cancelled = is_cancelled or (lambda: False)

    def cek():
        if is_cancelled():
            raise JobCancelled()

    on_status(f"Membuka {source.name}…")
    on_progress(2)
    tmp = Path(tempfile.mkdtemp(prefix="freqknife-"))
    samples = None
    try:
        raw_in = tmp / "source.f32le"
        sr, channels, n_frames = audio_io.decode_to_raw(source, raw_in)
        samples = audio_io.open_raw(raw_in, n_frames, channels)
        cek()

        on_status("Memotong pita…")
        masks = dsp.band_masks(FRAME, sr, n_bands, preset)
        n_out = len(masks)
        if n_out != n_bands:
            on_status(f"Sebaran menyesuaikan: {n_out} file")

        ext, codec = audio_io.output_plan(source.suffix)
        raw_out = [tmp / f"band{i:02d}.f32le" for i in range(n_out)]
        handles = [open(p, "wb") for p in raw_out]
        ditulis_per_pita = [0] * n_out

        lapor = -1
        try:
            for i, chunk in dsp.iter_split(samples, sr, n_bands, preset, FRAME):
                handles[i].write(chunk.tobytes())
                ditulis_per_pita[i] += len(chunk)
                if i == n_out - 1:
                    maju = min(ditulis_per_pita[i], n_frames)
                    persen = 10 + int(20 * maju / max(n_frames, 1))
                    if persen != lapor:
                        lapor = persen
                        on_progress(persen)
                        cek()
        finally:
            for fh in handles:
                fh.close()
        cek()

        hasil = []
        for i in range(n_out):
            cek()
            on_status(f"Encoding band{i + 1:02d}{ext}")
            target = audio_io.available_path(audio_io.band_path(dest_dir, source.stem, i + 1, ext))
            # dicatat SEBELUM encode: encode gagal di tengah meninggalkan file
            # parsial, dan file itu harus ikut terhapus saat batal/gagal
            written.append(target)
            audio_io.encode_raw(raw_out[i], target, sr, channels, codec)
            hasil.append(target)
            on_progress(30 + int(70 * (i + 1) / n_out))

        on_progress(100)
        on_status("Selesai")
        return hasil
    finally:
        del samples
        shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 4: Jalankan, pastikan lulus**

```bash
. .venv/bin/activate && pytest tests/test_worker.py
```

Expected: 8 passed. Suite penuh harus 48 passed.

- [ ] **Step 5: Commit**

```bash
git add worker.py tests/test_worker.py
git commit -m "feat: orkestrasi proses dengan progress dan cancel"
```

---

### Task 9: Pembungkus QThread

**Files:**
- Modify: `worker.py`
- Test: `tests/test_worker.py`

- [ ] **Step 1: Tambahkan test import dan sinyal**

Tambahkan di `tests/test_worker.py`:

```python
def test_split_worker_punya_sinyal_yang_dibutuhkan_ui():
    for nama in ("progress", "status", "finished_ok", "failed", "cancelled"):
        assert hasattr(worker.SplitWorker, nama), nama
    assert hasattr(worker.SplitWorker, "cancel")


def test_split_worker_bisa_dibuat_tanpa_qapp():
    w = worker.SplitWorker("a.wav", "/tmp", 5, "Rata (log)")
    assert w.n_bands == 5
    assert not w._cancel
    w.cancel()
    assert w._cancel
```

- [ ] **Step 2: Jalankan, pastikan gagal**

```bash
. .venv/bin/activate && pytest tests/test_worker.py
```

Expected: FAIL `AttributeError: module 'worker' has no attribute 'SplitWorker'`.

- [ ] **Step 3: Tambahkan implementasi**

Tambahkan di akhir `worker.py`:

```python
def friendly_error(exc):
    """Pesan yang aman ditampilkan ke user."""
    import subprocess
    if isinstance(exc, subprocess.CalledProcessError):
        tail = (exc.stderr or b"").decode(errors="replace").strip().splitlines()[-5:]
        return "ffmpeg gagal:\n" + "\n".join(tail) if tail else "ffmpeg gagal."
    return str(exc) or exc.__class__.__name__


class SplitWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished_ok = Signal(list)
    failed = Signal(str)
    cancelled = Signal(list)

    def __init__(self, source, dest_dir, n_bands, preset, parent=None):
        super().__init__(parent)
        self.source, self.dest_dir = source, dest_dir
        self.n_bands, self.preset = n_bands, preset
        self._cancel = False
        self.written = []

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            hasil = process_file(
                self.source, self.dest_dir, self.n_bands, self.preset,
                on_progress=self.progress.emit,
                on_status=self.status.emit,
                is_cancelled=lambda: self._cancel,
                written=self.written,
            )
        except JobCancelled:
            self.cancelled.emit(self.written)
        except Exception as exc:
            self.failed.emit(friendly_error(exc))
        else:
            self.finished_ok.emit(hasil)
```

Tambahkan juga di ** atas file `worker.py`** (setelah import stdlib):

```python
from PySide6.QtCore import QThread, Signal
```

- [ ] **Step 4: Jalankan, pastikan lulus**

```bash
. .venv/bin/activate && pytest tests/test_worker.py
```

Expected: 10 passed. Suite penuh harus 50 passed.

- [ ] **Step 5: Commit**

```bash
git add worker.py tests/test_worker.py
git commit -m "feat: pembungkus QThread dengan sinyal progress dan error"
```

---

### Task 10: Jendela utama, drag & drop, tombol Cancel

**Files:**
- Create: `main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Tulis test fungsi murni**

`tests/test_main.py`:

```python
import main


def test_selftest_lulus():
    assert main.selftest() == 0


def test_ekstensi_audio_dikenali():
    import audio_io
    assert ".mp3" in audio_io.AUDIO_EXTENSIONS
    assert ".wav" in audio_io.AUDIO_EXTENSIONS
    assert ".txt" not in audio_io.AUDIO_EXTENSIONS
```

- [ ] **Step 2: Jalankan, pastikan gagal**

```bash
. .venv/bin/activate && pytest tests/test_main.py
```

Expected: FAIL `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Tulis `main.py`**

```python
"""Jendela utama Frequency Knife."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

import audio_io
import dsp
from worker import SplitWorker

AKAR = Path(__file__).resolve().parent
ICON = AKAR / "assets" / "icon.icns" if sys.platform == "darwin" else AKAR / "assets" / "icon.png"
FILTER = "Audio (*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.oga *.opus *.aiff *.aif *.wma *.mp4 *.webm)"


def selftest():
    """Verifikasi binary terbungkus tanpa GUI. Dipakai build dan CI."""
    import numpy as np
    rng = np.random.default_rng(0)
    x = (rng.standard_normal((8192, 2)) * 0.1).astype(np.float32)
    bands = dsp.split_bands(x, 44100, 5)
    galat = float(np.abs(np.sum(bands, axis=0) - x).max())
    print(f"selftest: {len(bands)} pita, galat rekonstruksi {galat:.2e}")
    return 0 if galat < 1e-3 else 1


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Frequency Knife")
        if ICON.exists():
            self.setWindowIcon(QIcon(str(ICON)))
        self.setMinimumWidth(470)
        self.dest_manual = False
        self.worker = None

        self.sumber = QLineEdit()
        self.sumber.setReadOnly(True)
        self.sumber.setPlaceholderText("Pilih file… atau tarik ke sini")
        self.tujuan = QLineEdit()
        self.tujuan.setPlaceholderText("Folder tujuan — default sama dengan folder sumber")

        btn_sumber = QPushButton("Pilih…")
        btn_sumber.clicked.connect(self.pilih_sumber)
        btn_tujuan = QPushButton("Pilih…")
        btn_tujuan.clicked.connect(self.pilih_tujuan)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(dsp.BANDS_SLIDER_MIN, dsp.BANDS_SLIDER_MAX)
        self.slider.setValue(dsp.BANDS_DEFAULT)
        self.spin = QSpinBox()
        self.spin.setRange(dsp.BANDS_MIN, dsp.BANDS_MAX)
        self.spin.setValue(dsp.BANDS_DEFAULT)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self._spin_berubah)
        self.hint = QLabel()

        self.preset = QComboBox()
        self.preset.addItems(dsp.PRESET_NAMES)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.status = QLabel("Pilih file suara — atau tarik file ke jendela ini.")

        self.btn_batal = QPushButton("Batalkan")
        self.btn_batal.setEnabled(False)
        self.btn_batal.clicked.connect(self.batalkan)
        self.btn_proses = QPushButton("Proses")
        self.btn_proses.setDefault(True)
        self.btn_proses.clicked.connect(this_proses := self.proses)

        isi = QWidget()
        grid = QGridLayout()
        grid.addWidget(QLabel("Sumber"), 0, 0)
        grid.addWidget(self.sumber, 0, 1)
        grid.addWidget(btn_sumber, 0, 2)
        grid.addWidget(QLabel("Tujuan"), 1, 0)
        grid.addWidget(self.tujuan, 1, 1)
        grid.addWidget(btn_tujuan, 1, 2)

        jumlah = QHBoxLayout()
        jumlah.addWidget(self.slider)
        jumlah.addWidget(self.spin)
        jumlah.addWidget(QLabel("file"))

        tombol = QHBoxLayout()
        tombol.addStretch(1)
        tombol.addWidget(self.btn_batal)
        tombol.addWidget(self.btn_proses)

        utama = QVBoxLayout(isi)
        utama.addLayout(grid)
        utama.addWidget(QLabel("Jumlah file output"))
        utama.addLayout(jumlah)
        utama.addWidget(self.hint)
        utama.addWidget(QLabel("Preset sebaran"))
        utama.addWidget(self.preset)
        utama.addWidget(self.bar)
        utama.addWidget(self.status)
        utama.addLayout(tombol)
        self.setCentralWidget(isi)

        self.setAcceptDrops(True)
        self._sinkron_hint()

    # --- drag & drop -------------------------------------------------
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in audio_io.AUDIO_EXTENSIONS:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        self.set_sumber(urls[0].toLocalFile())
        if len(urls) > 1:
            self.status.setText("Hanya file pertama yang dipakai.")
        event.acceptProposedAction()

    # --- pemilihan file ----------------------------------------------
    def pilih_sumber(self):
        jalur, _ = QFileDialog.getOpenFileName(self, "Pilih file suara", "", FILTER)
        if jalur:
            self.set_sumber(jalur)

    def set_sumber(self, jalur):
        self.sumber.setText(jalur)
        if not self.dest_manual:
            self.tujuan.setText(str(Path(jalur).parent))
        self._sinkron_hint()

    def pilih_tujuan(self):
        jalur = QFileDialog.getExistingDirectory(self, "Pilih folder tujuan", self.tujuan.text())
        if jalur:
            self.tujuan.setText(jalur)
            self.dest_manual = True

    # --- jumlah file --------------------------------------------------
    def _spin_berubah(self, nilai):
        # slider dibatasi 3–10; nilai di luar itu hanya bisa lewat spin
        if self.slider.minimum() <= nilai <= self.slider.maximum():
            self.slider.blockSignals(True)
            self.slider.setValue(nilai)
            self.slider.blockSignals(False)
        self._sinkron_hint()

    def _sinkron_hint(self):
        n = dsp.clamp_bands(self.spin.value())
        self.hint.setText(f"Akan menghasilkan {n} file")

    # --- proses --------------------------------------------------------
    def proses(self):
        sumber = self.sumber.text().strip()
        tujuan = self.tujuan.text().strip() or str(Path(sumber).parent)

        if not sumber or not Path(sumber).exists():
            QMessageBox.warning(self, "FreqKnife", "File sumber belum dipilih atau tidak ada.")
            return
        if not Path(sumber).is_file():
            QMessageBox.warning(self, "FreqKnife", "Sumber harus berupa file, bukan folder.")
            return
        if audio_io.ffmpeg_missing():
            QMessageBox.critical(self, "FreqKnife",
                                 "ffmpeg tidak ditemukan. Aplikasi memerlukan ffmpeg.")
            return
        try:
            os.makedirs(tujuan, exist_ok=True)
        except OSError:
            QMessageBox.critical(self, "FreqKnife", f"Folder tujuan tidak bisa ditulis:\n{tujuan}")
            return
        if not os.access(tujuan, os.W_OK):
            QMessageBox.critical(self, "FreqKnife", f"Folder tujuan tidak bisa ditulis:\n{tujuan}")
            return

        self.btn_proses.setEnabled(False)
        self.btn_batal.setEnabled(True)
        self.bar.setValue(0)
        self.status.setText("Menyiapkan…")

        self.worker = SplitWorker(sumber, tujuan, dsp.clamp_bands(self.spin.value()),
                                  self.preset.currentText(), self)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.status.connect(self.status.setText)
        self.worker.finished_ok.connect(self._selesai)
        self.worker.cancelled.connect(self._dibatalkan)
        self.worker.failed.connect(self._gagal)
        self.worker.start()

    def batalkan(self):
        if self.worker is not None:
            self.btn_batal.setEnabled(False)
            self.status.setText("Membatalkan…")
            self.worker.cancel()

    def _kembalikan_tombol(self):
        self.btn_proses.setEnabled(True)
        self.btn_batal.setEnabled(False)

    def _selesai(self, hasil):
        self._kembalikan_tombol()
        self.status.setText(f"Selesai — {len(hasil)} file dibuat.")
        daftar = "\n".join(p.name for p in hasil)
        box = QMessageBox(self)
        box.setWindowTitle("FreqKnife")
        box.setText(f"{len(hasil)} file berhasil dibuat.")
        box.setInformativeText(daftar)
        buka = box.addButton("Buka Folder Tujuan", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is buka and hasil:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(hasil[0].parent)))

    def _dibatalkan(self, ditulis):
        for p in ditulis:
            try:
                Path(p).unlink()
            except OSError:
                pass
        self._kembalikan_tombol()
        self.bar.setValue(0)
        self.status.setText("Dibatalkan. Hasil parsial dihapus.")

    def _gagal(self, pesan):
        self._kembalikan_tombol()
        self.status.setText("Gagal.")
        QMessageBox.critical(self, "FreqKnife", pesan)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
        event.accept()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if "--selftest" in argv:
        return selftest()
    app = QApplication(argv)
    app.setApplicationName("FreqKnife")
    app.setApplicationDisplayName("Frequency Knife")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Jalankan test, pastikan lulus**

```bash
. .venv/bin/activate && pytest
```

Expected: seluruh test lulus (28 passed).

- [ ] **Step 5: Verifikasi manual UI**

```bash
. .venv/bin/activate && python main.py
```

Checklist:
- Jendela "Frequency Knife" muncul, tidak bisa dikecilkan di bawah 470 px.
- Tarik file `.mp3` ke jendela → field Sumber terisi, Tujuan otomatis folder yang sama.
- Ubah Tujuan manual, lalu ganti Sumber → Tujuan **tidak** berubah lagi.
- Geser slider ke 3 dan 10; ketik 2 dan 30 di spin → nilai di-clamp, label hint benar.
- Pilih "Bass dominan", klik Proses → progress naik 0→100, tombol Batalkan aktif, tombol Proses nonaktif.
- Tekan Batalkan di tengah → dialog tidak muncul, status "Dibatalkan", folder tujuan bersih (tidak ada `_band*` tersisa).
- Selesai sampai 100% → dialog berisi daftar file + "Buka Folder Tujuan".
- Tarik `.txt` ke jendela → tidak diterima, Sumber tidak berubah.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: jendela utama dengan drag-drop, progress, dan cancel"
```

---

### Task 11: Icon

**Files:**
- Create: `assets/icon.svg` (sumber, dokumentasi)
- Create: `build/make_icons.py`
- Generate: `assets/icon.icns`, `assets/icon.ico`, `assets/icon.png`, `assets/icon_512.png`

- [ ] **Step 1: Tulis generator icon**

`build/make_icons.py`:

```python
"""Gambar icon FreqKnife: pisau memotong gelombang, lalu ekspor PNG/ICO/ICNS."""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

AKAR = Path(__file__).resolve().parent.parent
ASET = AKAR / "assets"


def gambar(size):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # latar rounded square gelap
    margin, radius = int(s * 0.04), int(s * 0.20)
    d.rounded_rectangle([margin, margin, s - margin, s - margin],
                        radius=radius, fill=(22, 26, 34, 255))

    # gelombang: batang vertikal simetris
    tengah = s * 0.5
    tinggi = [0.18, 0.42, 0.30, 0.52, 0.26, 0.46, 0.20]
    lebar = s * 0.055
    gap = s * 0.075
    n = len(tinggi)
    mulai = tengah - ((n - 1) * gap) / 2
    for i, h in enumerate(tinggi):
        x = mulai + i * gap
        d.rounded_rectangle(
            [x - lebar / 2, tengah - h * s * 0.62, x + lebar / 2, tengah + h * s * 0.62],
            radius=lebar / 2, fill=(90, 200, 250, 255))

    # garis pisau diagonal
    ujung = s * 0.10
    d.line([(s - ujung, ujung), (ujung, s - ujung)],
           fill=(255, 120, 90, 255), width=max(2, int(s * 0.045)))

    # mata pisau kecil di ujung
    r = s * 0.075
    d.ellipse([ujung - r, s - ujung - r, ujung + r, s - ujung + r],
              fill=(255, 120, 90, 255))
    return img


def utama():
    ASET.mkdir(exist_ok=True)
    ukuran_png = [16, 32, 64, 128, 256, 512, 1024]

    iconset = ASET / "icon.iconset"
    if iconset.exists():
        import shutil
        shutil.rmtree(iconset)
    iconset.mkdir()

    for n in ukuran_png:
        img = gambar(n)
        img.save(ASET / f"icon_{n}.png")
        if n in (16, 32, 128, 256, 512):
            img.save(iconset / f"icon_{n}x{n}.png")
            img.save(iconset / f"icon_{2 * n}x{2 * n}@2x.png") if n <= 256 else None

    gambar(256).save(ASET / "icon.png")
    gambar(512).save(ASET / "icon_512.png")
    gambar(256).save(ASET / "icon.ico",
                     sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    if sys.platform == "darwin":
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ASET / "icon.icns")],
                       check=True)
        import shutil
        shutil.rmtree(iconset)

    print("icon siap:", ", ".join(sorted(p.name for p in ASET.iterdir())))


if __name__ == "__main__":
    utama()
```

- [ ] **Step 2: Jalankan dan verifikasi**

```bash
. .venv/bin/activate && python build/make_icons.py
ls -la assets/
```

Expected: `icon.icns`, `icon.ico`, `icon.png`, `icon_512.png`, dan PNG berbagai ukuran. Buka `assets/icon_256.png` untuk memastikan gambarnya masuk akal — kalau berantakan, ubah koordinat di `gambar()` lalu jalankan ulang.

- [ ] **Step 3: Commit**

```bash
git add build/make_icons.py assets/
git commit -m "feat: icon FreqKnife (pisau memotong gelombang)"
```

---

### Task 12: Build Mac dan GitHub Actions

**Files:**
- Create: `build/build_mac.sh`
- Create: `.github/workflows/build.yml`
- Modify: `docs/superpowers/specs/2026-10-20-freqknife-design.md` (koreksi Linux)

- [ ] **Step 1: Tulis skrip build Mac**

`build/build_mac.sh`:

```bash
#!/usr/bin/env bash
# Build FreqKnife.app untuk macOS. Jalankan: bash build/build_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install --quiet -r requirements.txt

python build/make_icons.py

pyinstaller --noconfirm --clean --onefile --windowed \
  --name FreqKnife \
  --icon assets/icon.icns \
  --add-data "assets/icon.icns:assets" \
  --add-binary "$(command -v ffmpeg):." \
  --add-binary "$(command -v ffprobe):." \
  main.py

echo "Build selesai: dist/FreqKnife.app"
echo "Selftest:"
./dist/FreqKnife.app/Contents/MacOS/FreqKnife --selftest
```

```bash
chmod +x build/build_mac.sh
```

- [ ] **Step 2: Build dan jalankan selftest**

```bash
bash build/build_mac.sh
```

Expected: `dist/FreqKnife.app` terbentuk dan selftest mencetak `selftest: 5 pita, galat rekonstruksi ...e-07` dengan exit code 0.

Kalau muncul `ffmpeg`/`ffprobe` tidak ditemukan, pastikan `brew install ffmpeg` sudah jalan lalu ulangi.

- [ ] **Step 3: Verifikasi aplikasi terbungkus benar-benar jalan**

```bash
./dist/FreqKnife.app/Contents/MacOS/FreqKnife &
sleep 4
```

Checklist:
- Jendela muncul dengan icon FreqKnife di Dock dan title bar.
- Tarik sebuah `.mp3`, klik Proses, hasil muncul di folder sumber.

Tutup aplikasinya setelah selesai.

- [ ] **Step 4: Tulis workflow GitHub Actions**

`.github/workflows/build.yml`:

```yaml
name: build

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: macos-latest
            nama: FreqKnife-mac
          - os: windows-latest
            nama: FreqKnife-win
          - os: ubuntu-latest
            nama: FreqKnife-linux
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Pasang dependensi
        shell: bash
        run: |
          pip install -r requirements.txt
          python build/make_icons.py

      - name: Pasang ffmpeg
        shell: bash
        run: |
          case "$RUNNER_OS" in
            macOS)   brew install ffmpeg ;;
            Windows) choco install ffmpeg -y --no-progress ;;
            Linux)   sudo apt-get update && sudo apt-get install -y ffmpeg ;;
          esac

      - name: Build macOS
        if: runner.os == 'macOS'
        shell: bash
        run: |
          pyinstaller --noconfirm --clean --onefile --windowed --name FreqKnife \
            --icon assets/icon.icns \
            --add-data "assets/icon.icns:assets" \
            --add-binary "$(command -v ffmpeg):." \
            --add-binary "$(command -v ffprobe):." \
            main.py

      - name: Build Windows
        if: runner.os == 'Windows'
        shell: bash
        run: |
          pyinstaller --noconfirm --clean --onefile --windowed --name FreqKnife \
            --icon assets/icon.ico \
            --add-data "assets/icon.ico;assets" \
            --add-binary "$(command -v ffmpeg);." \
            --add-binary "$(command -v ffprobe);." \
            main.py

      - name: Build Linux
        if: runner.os == 'Linux'
        shell: bash
        run: |
          pyinstaller --noconfirm --clean --onefile --windowed --name FreqKnife \
            --icon assets/icon_512.png \
            --add-data "assets/icon.png:assets" \
            --add-binary "$(command -v ffmpeg):." \
            --add-binary "$(command -v ffprobe):." \
            main.py

      - name: Selftest binary
        shell: bash
        run: |
          case "$RUNNER_OS" in
            macOS)   ./dist/FreqKnife.app/Contents/MacOS/FreqKnife --selftest ;;
            Windows) ./dist/FreqKnife.exe --selftest ;;
            Linux)   ./dist/FreqKnife --selftest ;;
          esac

      - uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.nama }}
          path: dist/FreqKnife*
          if-no-files-found: error
```

- [ ] **Step 5: Koreksi spec soal Linux**

Buka `docs/superpowers/specs/2026-10-20-freqknife-design.md`, cari baris:

```
  menghasilkan `FreqKnife-mac.dmg`, `FreqKnife-win.exe`, `FreqKnife-linux.AppImage`.
```

Ganti menjadi:

```
  menghasilkan `FreqKnife.app` (macOS), `FreqKnife.exe` (Windows), dan executable
  tunggal (Linux). AppImage ditunda — butuh `appimagetool` tambahan.
```

- [ ] **Step 6: Push dan pantau Actions**

```bash
git add .github/workflows/build.yml build/build_mac.sh docs/
git commit -m "ci: build lintas platform dengan selftest binary"
git push origin main
```

Buka **https://github.com/dkeceh/FreqKnife/actions** dan tunggu ketiga job selesai. Expected: ketiga job hijau, artifact `FreqKnife-mac`, `FreqKnife-win`, `FreqKnife-linux` bisa diunduh.

Kalau job Windows gagal di `--add-binary "$(command -v ffmpeg);."` karena ffmpeg dari choco berupa wrapper `.bat`, gali binary asli dengan `where ffmpeg` lalu pakai path `.exe`-nya.

- [ ] **Step 7: Finalisasi**

```bash
. .venv/bin/activate && pytest
git status --short
```

Expected: semua test lulus, working tree bersih.

---

## Self-Review

**Cakupan spesifikasi** — §2 (keputusan terkunci) ada di Task 2/3/4/7/8/10; §3 (arsitektur) seluruh task; §4 (DSP + preset) Task 2–5; §5 (alur data + codec table) Task 6–8; §6 (UI + drag & drop) Task 10; §7 (threading/progress/cancel) Task 8–9–10; §8 (error handling) Task 6 (`RuntimeError` berisi tail stderr), Task 10 (validasi sebelum mulai), Task 11 cleanup di `finally`; §9 (pengujian) Task 2–5, 7, 8, 10; §10 (packaging) Task 11–12.

**Placeholder** — tidak ada TBD/TODO. Setiap langkah berisi kode atau perintah lengkap.

**Konsistensi tipe** — `compute_cutoffs(sample_rate, n_bands, preset)`, `band_masks(n_fft, sample_rate, n_bands, preset)`, `iter_split(samples, sample_rate, n_bands, preset, frame)`, `process_file(source, dest_dir, n_bands, preset, ...)`, `SplitWorker(source, dest_dir, n_bands, preset, parent)`, `band_path(dest_dir, stem, index, ext)` — dipakai konsisten di seluruh task.

**Dua hal yang perlu diketahui pengerja:**
1. Dedup bin bisa mengurangi jumlah pita: `band_masks(4096, 44100, 30)` mengembalikan 29 mask, bukan 30 (cut ±25 Hz dan ±31 Hz jatuh ke bin yang sama). Itu perilaku yang benar — jangan dipaksa agar jumlahnya persis. Pemanggil selalu baca `len(band_masks(...))`, bukan asumsikan `n_bands`. `worker.process_file` sudah memberi tahu UI bila jumlahnya berkurang.
2. `test_folder_temp_dibersihkan` memakai `monkeypatch.setattr(tempfile, "tempdir", ...)` — kalau gagal karena `mkdtemp` membaca `tempdir` sebelum patch, ganti dengan membandingkan `Path(tempfile.gettempdir())` sebelum/sesudah dan pastikan tidak ada direktori `freqknife-*` yang tersisa.
