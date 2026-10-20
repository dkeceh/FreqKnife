import subprocess
from pathlib import Path

import numpy as np
import pytest

import audio_io

pytestmark = pytest.mark.skipif(
    audio_io.ffmpeg_missing(), reason="ffmpeg/ffprobe tidak tersedia")


def _buat_wav(path, sr=44100, ch=2, detik=1.0):
    subprocess.run(
        [audio_io.ffmpeg_path(), "-v", "error", "-y", "-f", "lavfi",
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
    subprocess.run([audio_io.ffmpeg_path(), "-v", "error", "-y", "-i", str(wav), str(mp3)], check=True)
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
    # lewat ffmpeg_path() agar tetap jalan di CI, yang menyetel FFMPEG_BIN
    # tanpa menaruh ffmpeg di PATH
    asli_ffmpeg = audio_io.ffmpeg_path()
    asli_ffprobe = audio_io.ffprobe_path()

    # mode bundel: PATH kosong, _alat menemukan binary
    monkeypatch.setattr(audio_io.shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(audio_io, "_alat",
                        lambda nama: asli_ffmpeg if nama == "ffmpeg" else asli_ffprobe)
    assert audio_io.ffmpeg_missing() is False

    # binary hilang sama sekali
    monkeypatch.setattr(audio_io, "_alat",
                        lambda nama: f"/tmp/tidak-ada-{nama}")
    assert audio_io.ffmpeg_missing() is True


def test_alat_menghormati_env_ffmpeg_bin(tmp_path, monkeypatch):
    """CI menyetel FFMPEG_BIN/FFPROBE_BIN lewat $GITHUB_ENV. Tanpa ini
    ffmpeg_missing() mengabaikan binary yang baru terunduh, sehingga selftest
    gagal dan seluruh test audio ter-skip walau ffmpeg sudah ada."""
    ff = tmp_path / "ffmpeg"
    ff.write_bytes(b"#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("FFMPEG_BIN", str(ff))
    assert audio_io._alat("ffmpeg") == str(ff), "env harus mengalahkan PATH"

    fp = tmp_path / "ffprobe"
    fp.write_bytes(b"#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("FFPROBE_BIN", str(fp))
    assert audio_io.ffmpeg_missing() is False


def test_alat_menemukan_binary_berekstensi_exe_di_bundel(tmp_path, monkeypatch):
    import types

    # pakai stand-in modul sys: hanya sys._MEIPASS yang dibaca _alat,
    # jadi global sys tidak perlu disentuh sama sekali
    def set_bundel(path):
        # cabang env harus dimatikan dulu: CI menyetel FFMPEG_BIN, dan env
        # memang sengaja didahulukan di atas bundel
        monkeypatch.delenv("FFMPEG_BIN", raising=False)
        monkeypatch.delenv("FFPROBE_BIN", raising=False)
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
