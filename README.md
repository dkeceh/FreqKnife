# FreqKnife

Pisahkan satu file suara menjadi beberapa file berdasarkan pita frekuensi —
seperti equalizer, tapi hasilnya file terpisah. Berguna untuk mengambil hanya
bass, hanya mid, atau hanya high dari satu rekaman.

Berjalan sebagai aplikasi desktop (PySide6). `ffmpeg`/`ffprobe` sudah dibundel
sebagai build statis, jadi **tidak perlu memasang ffmpeg**. Di Linux masih perlu
pustaka Qt sistem — lihat [Linux](#linux).

## Mengunduh

Ambil artefak dari [Actions](https://github.com/dkeceh/FreqKnife/actions) —
setiap push ke `main` membangun ketiganya:

| Platform | Artefak | Catatan |
|---|---|---|
| macOS | `FreqKnife-mac` | `FreqKnife.app`, otomatis ad-hoc signed oleh PyInstaller (wajib di Apple Silicon) |
| Windows | `FreqKnife-win` | `FreqKnife.exe` |
| Linux | `FreqKnife-linux` | perlu pustaka Qt sistem, lihat [bawah](#linux) |

## Cara pakai

1. Buka aplikasi, lalu **pilih file** atau **tarik file ke jendela**.
2. Atur **jumlah file output** (slider 3–10, atau ketik angka 2–30).
3. Pilih **preset sebaran** titik potong.
4. Folder tujuan default = folder sumber. Ubah jika perlu.
5. Klik **Proses**. Progress bar menampilkan persentase; **Batal** bisa ditekan
   kapan saja dan hasil parsial dibersihkan.

`5` file output berarti `4` titik potong. Contoh dengan sumber `lagu.mp3`:

```
lagu_band01.mp3  lagu_band02.mp3  lagu_band03.mp3  lagu_band04.mp3  lagu_band05.mp3
```

Nama yang sudah terpakai otomatis diberi suffix `_2`, `_3`, … — file lama tidak
pernah ditimpa.

### Preset

Titik potong selalu tersebar logaritmik dari 20 Hz sampai `min(20 kHz, 0.98 × Nyquist)`,
lalu digeser oleh satu faktor skew:

| Preset | Sebaran |
|---|---|
| Rata (log) | seragam pada skala log |
| Bass dominan | pita bawah lebih sempit — bass terurai |
| Mid-High dominan | pita atas lebih sempit — mid/high terurai |

### Format

Yang bisa dipilih dibatasi daftar ini (filter dialog dan pemeriksaan drag & drop):

`WAV, MP3, FLAC, M4A/AAC, OGG/Opus, AIFF, WMA, MP4, WebM`

Format output **mengikuti format input** untuk WAV, MP3, FLAC, M4A/AAC dan
OGG/Opus. Sisanya — AIFF, WMA, MP4, WebM — tidak punya pemetaan codec di sini
dan hasilnya jatuh ke WAV. Jumlah kanal selalu dipertahankan — stereo masuk →
stereo keluar per pita.

## Linux

`ffmpeg` sudah dibundel penuh, tapi PySide6 masih menautkan pustaka Qt milik
sistem. Pasang dulu (daftar yang sama dengan yang dipakai CI):

```bash
sudo apt-get install -y --no-install-recommends \
  libegl1 libgl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 \
  libfontconfig1 libx11-xcb1 libxcb-cursor0 libxcb-icccm4 \
  libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
  libxcb-shape0 libxcb-xinerama0 libxcb-xkb1
```

Tanpa ini aplikasi berhenti di import dengan `ImportError: libEGL.so.1`.
Ini batasan Qt di Linux, bukan kekurangan bundling — macOS dan Windows tidak
terpengaruh.

## Bangun dari sumber

Butuh Python 3.11+. macOS:

```bash
bash build/build_mac.sh
```

Skrip itu membuat venv, memasang dependensi, menghasilkan icon, mengunduh
`ffmpeg`/`ffprobe` statis ke `vendor/`, lalu membangun `dist/FreqKnife.app`
dan langsung menjalankan selftest-nya. Windows dan Linux dibangun lewat
[GitHub Actions](.github/workflows/build.yml); skripnya ada di situ.

Tanpa PyInstaller, jalankan langsung dari Python:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Pengembangan

```bash
.venv/bin/pytest        # 64 test
python main.py --selftest
```

Selftest memakai `--selftest` untuk memverifikasi binary terbungkus **tanpa GUI**:
ia memeriksa galat rekonstruksi DSP, lalu melakukan decode + encode sungguhan
dengan ffmpeg yang dibundel. Inilah yang mencegah artefak rusak terunggah —
build Linux yang tidak bisa dijalankan akan berhenti di sini.

Struktur:

```
main.py          jendela utama, selftest
dsp.py           pemotongan frekuensi — numpy murni, tanpa Qt
audio_io.py      decode/encode lewat subprocess ffmpeg
worker.py        QThread + process_file
build/           make_icons.py, get_ffmpeg.py, build_mac.sh
tests/           64 test
docs/            spesifikasi dan rencana implementasi
```

## Lisensi

Kode sumber FreqKnife memakai [MIT](LICENSE).

**Perhatian — biner yang dibundel berlisensi lain.** `ffmpeg`/`ffprobe` yang
ikut terbungkus adalah build statis GPLv3 (konfigurasinya memuat
`--enable-gpl --enable-version3 --enable-libx264 --enable-libx265`). Ini karya
terpisah: aplikasi memanggilnya lewat subprocess, jadi lisensi MIT tetap berlaku
pada kode sumber FreqKnife dan tidak menular ke sana.

Tapi **mendistribusikan artefak FreqKnife berarti ikut mendistribusikan perangkat
lunak GPLv3**, sehingga wajib memenuhi syaratnya — minimal menyertakan teks
lisensi GPL dan menautkan kode sumber ffmpeg:

- https://www.martin-riedl.de/ffmpeg/ (macOS)
- https://github.com/BtbN/FFmpeg-Builds (Linux, Windows)
