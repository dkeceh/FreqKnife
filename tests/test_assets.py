"""Aset ikut di-commit; kalau hilang/rusak, build terbungkus gagal diam-diam."""

from pathlib import Path

from PIL import Image

import main

AKAR = Path(main.__file__).resolve().parent


def test_aset_ikon_ada_dan_valid():
    aset = AKAR / "assets"
    for nama, ukuran in [("icon.icns", None), ("icon.ico", None),
                         ("icon.png", 256), ("icon_512.png", 512)]:
        p = aset / nama
        assert p.exists(), f"{nama} belum dibuat — jalankan build/make_icons.py"
        assert p.stat().st_size > 0, f"{nama} kosong"
        if ukuran:
            with Image.open(p) as img:
                assert img.size == (ukuran, ukuran), f"{nama} = {img.size}"


def test_jendela_memuat_ikon_bila_ada():
    # main.py harus menahan diri saat assets/ belum ada, bukan crash
    assert main.ICON.name in ("icon.icns", "icon.png")
