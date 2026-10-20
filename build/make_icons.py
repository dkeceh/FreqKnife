"""Gambar icon FreqKnife: pisau memotong gelombang, lalu ekspor PNG/ICO/ICNS."""

import shutil
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
        shutil.rmtree(iconset)
    iconset.mkdir()

    for n in ukuran_png:
        img = gambar(n)
        img.save(ASET / f"icon_{n}.png")
        if n in (16, 32, 128, 256):
            img.save(iconset / f"icon_{n}x{n}.png")
            img.save(iconset / f"icon_{2 * n}x{2 * n}@2x.png")
        elif n == 512:
            img.save(iconset / "icon_512x512.png")

    gambar(256).save(ASET / "icon.png")
    gambar(512).save(ASET / "icon_512.png")
    gambar(256).save(ASET / "icon.ico",
                     sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    if sys.platform == "darwin":
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ASET / "icon.icns")],
                       check=True)
        shutil.rmtree(iconset)

    # verifikasi sendiri: setiap aset yang dijanjikan harus ada dan bisa dibuka
    wajib = ["icon.icns", "icon.ico", "icon.png", "icon_512.png"]
    wajib += [f"icon_{n}.png" for n in ukuran_png]
    for nama in wajib:
        p = ASET / nama
        assert p.exists() and p.stat().st_size > 0, f"aset hilang: {nama}"
    for nama, ukuran in [("icon.png", 256), ("icon_512.png", 512)]:
        with Image.open(ASET / nama) as cek:
            assert cek.size == (ukuran, ukuran), f"{nama} ukuran {cek.size}, bukan {ukuran}"

    print("icon siap:", ", ".join(sorted(p.name for p in ASET.iterdir())))


if __name__ == "__main__":
    utama()
