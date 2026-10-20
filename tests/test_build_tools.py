"""Logika pengunduh ffmpeg diuji tanpa jaringan: pemetaan platform + ekstraksi."""

import sys
import tarfile
import zipfile
from pathlib import Path

import main

sys.path.insert(0, str(Path(main.__file__).resolve().parent / "build"))
import get_ffmpeg  # noqa: E402


def test_pemetaan_platform_ke_sumber():
    assert get_ffmpeg.sumber("darwin", "arm64") == ("martin", "macos/arm64")
    assert get_ffmpeg.sumber("darwin", "x86_64") == ("martin", "macos/amd64")
    assert get_ffmpeg.sumber("linux", "x86_64") == ("btbn", "linux64")
    assert get_ffmpeg.sumber("linux", "aarch64") == ("btbn", "linuxarm64")
    assert get_ffmpeg.sumber("win32", "amd64") == ("btbn", "win64")

    import pytest
    with pytest.raises(SystemExit):
        get_ffmpeg.sumber("win32", "arm64")   # sumber tidak punya build arm64
    with pytest.raises(SystemExit):
        get_ffmpeg.sumber("sunos", "sparc")


def test_ekstrak_zip_akar_dan_tar_berlapis(tmp_path):
    """Martin taruh binary di akar zip, BtbN di <paket>/bin/ — dua-duanya harus ditemukan."""
    paket = tmp_path / "ffmpeg-master-tes"
    (paket / "bin").mkdir(parents=True)
    (paket / "bin" / "ffmpeg").write_bytes(b"#sh")
    (paket / "bin" / "ffprobe").write_bytes(b"#sh")
    tar = tmp_path / "arsip.tar.xz"
    with tarfile.open(tar, "w:xz") as t:
        t.add(paket, arcname=paket.name)

    zip_ = tmp_path / "ff.zip"
    with zipfile.ZipFile(zip_, "w") as z:
        z.writestr("ffmpeg", b"biner")
        z.writestr("ffprobe", b"biner")

    tujuan = tmp_path / "keluar"
    tujuan.mkdir()
    with tarfile.open(tar) as t:
        t.extractall(tujuan, filter="data")
    get_ffmpeg._ekstrak(zip_.read_bytes(), "https://x/ff.zip", tujuan)

    ff = get_ffmpeg._cari(tujuan, "ffmpeg")
    fp = get_ffmpeg._cari(tujuan, "ffprobe")
    # yang paling dekat akar yang dipilih, bukan yang pertama ditemukan acak
    assert ff == tujuan / "ffmpeg"
    assert fp == tujuan / "ffprobe"

    # kasus hanya-bersarang: layout BtbN (Linux/Windows), akar tak punya binary
    bersarang = tmp_path / "hanya-bersarang"
    (bersarang / "paket" / "bin").mkdir(parents=True)
    (bersarang / "paket" / "bin" / "ffmpeg").write_bytes(b"#sh")
    assert get_ffmpeg._cari(bersarang, "ffmpeg") == bersarang / "paket" / "bin" / "ffmpeg"


def test_modul_memastikan_sertifikat_ssl():
    """Tanpa SSL_CERT_FILE, clone segar gagal di langkah unduh dengan TLS."""
    import os

    import pytest

    pytest.importorskip("certifi")
    assert os.environ.get("SSL_CERT_FILE"), (
        "get_ffmpeg tidak menyiapkan SSL_CERT_FILE — unduhan dingin akan gagal "
        "CERTIFICATE_VERIFY_FAILED pada kerangka Python tanpa file CA")
