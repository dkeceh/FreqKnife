#!/usr/bin/env bash
# Build FreqKnife.app untuk macOS. Jalankan: bash build/build_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install --quiet -r requirements.txt

python build/make_icons.py

# ffmpeg statis: binary Homebrew bergantung dylib di /opt/homebrew yang tidak
# ikut terbundel — hasilnya app hanya jalan di mesin build.
# (bukan mapfile: macOS masih membawa bash 3.2)
PATHS=$(python build/get_ffmpeg.py)
FF=$(printf '%s\n' "$PATHS" | sed -n 1p)
FP=$(printf '%s\n' "$PATHS" | sed -n 2p)

pyinstaller --noconfirm --clean --onefile --windowed \
  --name FreqKnife \
  --icon assets/icon.icns \
  --add-data "assets/icon.icns:assets" \
  --add-binary "$FF:." \
  --add-binary "$FP:." \
  main.py

echo "Build selesai: dist/FreqKnife.app"

# Biner ffmpeg yang dibundel berlisensi GPLv3; distribusi wajib menyertakan
# teks lisensinya. Ditaruh di lokasi stabil yang bisa ditemukan user, bukan di
# direktori ekstraksi onefile yang hilang saat app ditutup.
cp build/LICENSE.GPLv3 dist/FreqKnife.app/Contents/Resources/

echo "Selftest:"
./dist/FreqKnife.app/Contents/MacOS/FreqKnife --selftest
