"""Unduh ffmpeg + ffprobe statis ke vendor/ffmpeg/ untuk platform ini.

Pemakaian:
    python build/get_ffmpeg.py           # dua baris: jalur ffmpeg, lalu ffprobe
    python build/get_ffmpeg.py --env     # FFMPEG_FF= / FFMPEG_FP= untuk $GITHUB_ENV

shortcut: verifikasi = kedua binary benar-benar bisa dijalankan (`-version`),
bukan penguncian hash — itu yang menjamin aplikasi jalan di mesin lain. Pin
sha256 per versi ditambahkan bila kelak butuh rantai pasokan yang kukuh.
Lisensi dari arsip unduhan tidak ikut dibundel: rilis masih internal.
"""

import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

AKAR = Path(__file__).resolve().parent.parent
KELUAR = AKAR / "vendor" / "ffmpeg"
BTBN = "BtbN/FFmpeg-Builds"
MARTIN = "https://ffmpeg.martin-riedl.de"


def sumber(plat=None, mesin=None):
    """(jenis sumber, target) untuk platform ini — murni, bisa diuji tanpa jaringan."""
    plat = sys.platform if plat is None else plat
    mesin = platform.machine().lower() if mesin is None else mesin
    arm = mesin in ("arm64", "aarch64")

    if plat == "darwin":
        return "martin", f"macos/{'arm64' if arm else 'amd64'}"
    if plat.startswith("linux"):
        return "btbn", "linuxarm64" if arm else "linux64"
    if plat == "win32":
        if arm:
            raise SystemExit("sumber BtbN tidak menyediakan build statis Windows arm64")
        return "btbn", "win64"
    raise SystemExit(f"platform {plat} tidak didukung pengunduh ffmpeg")


def _unduh(url):
    req = Request(url, headers={"User-Agent": "FreqKnife-build"})
    with urlopen(req, timeout=180) as r:
        return r.read()


def _tautan(jenis, target, nama):
    if jenis == "btbn":
        # tag "latest" di GitHub = URL stabil, isinya ffmpeg + ffprobe
        return f"https://github.com/{BTBN}/releases/latest/download/{nama}"
    # direktori rilis martin-riedl membawa stempel waktu+versi (…_9.0.2) yang
    # berganti tiap rilis, dan tidak ada endpoint "latest" (indeksnya 403) —
    # jadi tautannya dibaca dari halaman utama
    html = _unduh(MARTIN + "/").decode("utf-8", "replace")
    pola = re.compile(r'"(/download/' + re.escape(target) + r'/[^"]*/' +
                      re.escape(nama) + r')"')
    cocok = pola.findall(html)
    if not cocok:
        raise SystemExit(f"tautan {nama} untuk {target} tidak ditemukan di {MARTIN}")
    return MARTIN + cocok[0]


def _arsip(jenis, target):
    if jenis == "martin":
        return [_tautan(jenis, target, "ffmpeg.zip"),
                _tautan(jenis, target, "ffprobe.zip")]
    # Varian gpl tanpa akhiran "-shared": build BtbN ber-"shared" justru
    # bergantung .so di sekitarnya — persis kesalahan yang sama dengan binary
    # brew. gpl (bukan lgpl) dipilih sebagai superset encoder, jadi tidak mungkin
    # kehilangan libmp3lame/libvorbis yang dipakai audio_io.CODEC_BY_EXT.
    if target == "win64":
        return [_tautan(jenis, target, "ffmpeg-master-latest-win64-gpl.zip")]
    return [_tautan(jenis, target, f"ffmpeg-master-latest-{target}-gpl.tar.xz")]


def _ekstrak(data, url, tujuan):
    nama = url.rsplit("/", 1)[-1]
    if nama.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(tujuan)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as t:
            # filter="data" menolak jalur absolut dan tautan keluar arsip
            t.extractall(tujuan, filter="data")


def _cari(akar, nama):
    kandidat = [p for p in akar.rglob(nama) if p.is_file()]
    if not kandidat:
        raise SystemExit(f"{nama} tidak ada di dalam arsip setelah ekstrak")
    # struktur arsip beda per sumber: martin taruh di akar, BtbN di <paket>/bin
    return min(kandidat, key=lambda p: len(p.parts))


def _uji(p):
    hasil = subprocess.run([str(p), "-version"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    baris = hasil.stdout.decode(errors="replace").splitlines()
    if hasil.returncode != 0:
        raise SystemExit(f"{p} tidak bisa dijalankan (kode {hasil.returncode}):\n"
                         + "\n".join(baris))
    return baris[0] if baris else ""


def utama(env=False):
    jenis, target = sumber()
    d = KELUAR / f"{jenis}-{target.replace('/', '-')}"
    akhiran = ".exe" if sys.platform == "win32" else ""
    ff, fp = d / f"ffmpeg{akhiran}", d / f"ffprobe{akhiran}"

    if not (ff.is_file() and fp.is_file()):
        if d.exists():
            shutil.rmtree(d)      # ekstraksi gagal setengah jalan dari run lalu
        d.mkdir(parents=True)
        for url in _arsip(jenis, target):
            print(f"unduh {url}", file=sys.stderr)
            _ekstrak(_unduh(url), url, d)
        for p in (ff, fp):
            if not p.is_file():
                shutil.move(str(_cari(d, p.name)), str(p))
        if akhiran == "":
            os.chmod(ff, 0o755)   # zip tidak menyimpan bit eksekusi
            os.chmod(fp, 0o755)

    for p in (ff, fp):
        print(f"periksa {p.name}: {_uji(p)}", file=sys.stderr)

    if env:
        print(f"FFMPEG_FF={ff.as_posix()}")
        print(f"FFMPEG_FP={fp.as_posix()}")
    else:
        print(ff.as_posix())
        print(fp.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(utama("--env" in sys.argv[1:]))
