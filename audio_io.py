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
