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


def test_ffmpeg_missing_menghormati_resolusi_alat(monkeypatch):
    """Bundel PyInstaller: binary ada tapi tidak ada di PATH."""
    import shutil as _sh

    asli_ffmpeg = _sh.which("ffmpeg")
    asli_ffprobe = _sh.which("ffprobe")
    assert asli_ffmpeg and asli_ffprobe, "tes ini butuh ffmpeg asli di PATH"

    # mode bundel: PATH kosong, _alat menemukan binary
    monkeypatch.setattr(audio_io.shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(audio_io, "_alat",
                        lambda nama: asli_ffmpeg if nama == "ffmpeg" else asli_ffprobe)
    assert audio_io.ffmpeg_missing() is False

    # binary hilang sama sekali
    monkeypatch.setattr(audio_io, "_alat",
                        lambda nama: f"/tmp/tidak-ada-{nama}")
    assert audio_io.ffmpeg_missing() is True


def test_alat_menemukan_binary_berekstensi_exe_di_bundel(tmp_path, monkeypatch):
    import types

    # pakai stand-in modul sys: hanya sys._MEIPASS yang dibaca _alat,
    # jadi global sys tidak perlu disentuh sama sekali
    def set_bundel(path):
        monkeypatch.setattr(
            audio_io, "sys", types.SimpleNamespace(_MEIPASS=str(path)))

    bundel_exe = tmp_path / "bundle_exe"
    bundel_exe.mkdir()
    exe = bundel_exe / "ffmpeg.exe"
    exe.write_bytes(b"#!/bin/sh\nexit 0\n")
    set_bundel(bundel_exe)
    assert audio_io._alat("ffmpeg") == str(exe)

    bundel_plt = tmp_path / "bundle_plt"
    bundel_plt.mkdir()
    polos = bundel_plt / "ffmpeg"
    polos.write_bytes(b"#!/bin/sh\nexit 0\n")
    set_bundel(bundel_plt)
    assert audio_io._alat("ffmpeg") == str(polos)

    bundel_kosong = tmp_path / "bundle_kosong"
    bundel_kosong.mkdir()
    set_bundel(bundel_kosong)
    hasil = audio_io._alat("ffmpeg")
    assert not hasil.startswith(str(bundel_kosong))
