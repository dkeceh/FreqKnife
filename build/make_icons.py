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

    for n in ukuran_png:
        gambar(n).save(ASET / f"icon_{n}.png")

    gambar(256).save(ASET / "icon.png")
    gambar(512).save(ASET / "icon_512.png")
    gambar(256).save(ASET / "icon.ico",
                     sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    iconset = ASET / "icon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()

    # slot @2x HARUS 2× piksel aslinya. Menyimpan gambar beresolusi dasar ke
    # nama @2x membuat iconutil menerima file, tapi macOS menskalakannya dan
    # ikon jadi buram di layar Retina.
    for dasar in (16, 32, 128, 256, 512):
        gambar(dasar).save(iconset / f"icon_{dasar}x{dasar}.png")
        gambar(2 * dasar).save(iconset / f"icon_{dasar}x{dasar}@2x.png")

    # verifikasi sendiri: nama file = piksel di dalamnya
    for p in iconset.glob("icon_*.png"):  # glob "icon_" agar file AppleDouble ._ ikut terlewat
        dasar = int(p.stem.replace("icon_", "").split("x")[0])
        faktor = 2 if p.stem.endswith("@2x") else 1
        with Image.open(p) as cek:
            assert cek.size == (dasar * faktor,) * 2, \
                f"{p.name} berisi {cek.size}, seharusnya {(dasar * faktor,) * 2}"

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
