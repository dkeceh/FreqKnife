# FreqKnife — Design Spec

**Tanggal:** 2026-10-20
**Status:** Disetujui user
**Target rilis pertama:** macOS

## 1. Ringkasan

FreqKnife adalah aplikasi desktop yang memisahkan satu file suara menjadi beberapa file
berdasarkan frekuensi, seperti mengiris lagu menjadi pita low / mid / high pada equalizer.
Jumlah file ditentukan user lewat slider, posisi pemotongan dihitung otomatis secara
logaritmik dengan pilihan preset sebaran.

Target akhir: macOS, Windows, Linux dari satu codebase. Rilis pertama macOS.

## 2. Keputusan yang sudah dikunci

| Topik | Keputusan |
|---|---|
| Arti angka slider | **Jumlah file output.** 5 → 5 file, 4 titik cut |
| Rentang | Slider 3–10; field angka bisa diisi 2–30, di-clamp |
| Posisi cut | Otomatis logaritmik 20 Hz – min(20 kHz, sr/2) |
| Preset | Mengubah kurva sebaran cut (satu parameter `p`) |
| Channel | **Dipertahankan.** Stereo masuk → stereo di tiap pita. Tidak memecah channel |
| Format output | **Mengikuti format input.** MP3 in → MP3 out, dst. |
| Nama output | `<namaasli>_band01.<ext>` … `<namaasli>_bandNN.<ext>` |
| File bentrok | Auto-rename: `lagu_band01_2.mp3` |
| Cancel | Berhenti + hapus folder temp + hapus hasil parsial sesi ini |
| Masukan file | Picker **dan drag & drop** ke jendela |
| Stack | Python 3.11+ / PySide6 / numpy / scipy / ffmpeg |
| Distribusi | PyInstaller `--onefile --windowed`, icon sendiri |

## 3. Arsitektur

```
freqknife/
├── main.py          # entry point + MainWindow (PySide6)
├── dsp.py           # pemotongan frekuensi — numpy murni, tanpa Qt
├── audio_io.py      # decode/encode lewat subprocess ffmpeg
├── worker.py        # QThread: decode → split → encode, memancarkan progress
├── assets/          # icon: .icns / .ico / .png + sumber SVG
├── tests/
│   └── test_dsp.py  # pytest, numpy saja, tanpa Qt
├── build/           # skrip build per OS
└── .github/workflows/build.yml
```

Batas modul:

- `dsp.py` bergantung hanya pada numpy. Tidak menyentuh Qt, tidak menyentuh filesystem.
  Menerima `np.ndarray`, mengembalikan generator `np.ndarray`.
- `audio_io.py` bergantung pada `ffmpeg`/`ffprobe` di PATH (atau binary yang dibundel).
  Satu-satunya tempat yang menjalankan subprocess media.
- `worker.py` menjahit keduanya dan memancarkan sinyal Qt. Tidak menghitung DSP.
- `main.py` murni UI dan binding. Tidak ada perhitungan.

## 4. DSP — inti aplikasi

Pemotongan memakai **STFT overlap-add**.

Parameter:

- Ukuran frame: 4096 sampel
- Hop: frame / 2 = 2048
- Jendela: Hann periodik
- Domain: `rfft` per frame, per channel (channel diproses sepanjang sumbu terakhir)

Titik cut:

```
f(k) = 20 * (fmax / 20) ** (t ** p),   t = k / N,   k = 1 … N-1
fmax = min(20000, sr * 0.5 * 0.98)
```

`p` berasal dari preset:

| Preset | p | Efek |
|---|---|---|
| Rata (log) | 1.0 | Sebaran seragam secara logaritmik |
| Bass dominan | 1.6 | Cut menumpuk di bawah ±300 Hz |
| Mid-High dominan | 0.62 | Cut menumpuk di 300 Hz ke atas |

Titik cut dipetakan ke indeks bin FFT lalu dibulatkan ke bawah, dan hasilnya
di-deduplicate agar tidak ada dua pita dengan batas identik (akan membuat satu pita
kosong). Jika setelah dedup jumlah pita berkurang, jumlah file ikut berkurang dan ini
dilaporkan ke UI sebelum memulai.

Partisi bin bersifat **bertetangga, saling melengkapi, tanpa celah dan tanpa tumpang
tindih**. Konsekuensinya: menjumlahkan seluruh file output menghasilkan sinyal asli
persis (sampai presisi float). Ini sifat yang membedakan pendekatan ini dari filter
`highpass`/`lowpass` berurutan, yang hasil jumlahnya tidak rata.

### Streaming

Proses berjalan per blok frame, bukan seluruh file sekaligus.

Tiap pita memegang accumulator sepanjang satu frame (4096 × channels × 4 byte ≈ 32 KB
untuk stereo). Per blok frame:

1. `acc[:, :frame] += hasil_ifft_pita`
2. Lepas sampel pertama sepanjang `hop`, kirim ke penulis file pita
3. Geser `acc` ke kiri sepanjang `hop`

Memori total tidak bertambah walau file berdurasi berjam-jam.

### Rekonstruksi

Karena bin dipartisi bertetangga dan jendela diterapkan sekali saja (analysis-only),
OLA dari seluruh pita = OLA terwindow dari sinyal asli. Dengan Hann 50% overlap,
jumlah jendela konstan (properti COLA), sehingga tidak perlu normalisasi tambahan.
Pengujian rekonstruksi di `tests/test_dsp.py` memastikan ini tetap terjaga.

## 5. Alur data

1. **Decode** — `ffmpeg -i sumber -vn -f f32le -acodec pcm_f32le -` → stdout dibaca
   → `np.frombuffer(dtype=np.float32)` → reshape `(frames, channels)`.
   Sample rate dan jumlah channel dari `ffprobe -v error -show_streams -of json`.
   Semua format yang didukung ffmpeg bisa dibuka: WAV, MP3, FLAC, M4A/AAC, OGG, AIFF.
2. **Split** — streaming OLA. Tiap pita menulis bertahap ke file mentah `.f32le`
   di dalam `tempfile.mkdtemp()`.
3. **Encode** — per pita:
   `ffmpeg -f f32le -ar SR -ac CH -i temp.raw -c:a <codec> keluaran.<ext>`
   | Format input | Codec output |
   |---|---|
   | mp3 | `libmp3lame` |
   | flac | `flac` |
   | m4a / aac | `aac` |
   | wav | `pcm_s24le` |
   | ogg | `libvorbis` |
   | aiff | `pcm_s24le` di kontainer aiff |
   | format tak dikenal (wma, dsf, …) | fallback `pcm_s16le` di kontainer wav, diberi tahu di UI |
4. **Auto-rename** — jika nama sudah dipakai, tambah suffix `_2`, `_3`, …
5. **Cleanup** — folder temp dihapus di blok `finally` pada semua jalur: selesai,
   batal, maupun exception.

Folder tujuan default mengikuti folder file sumber, dan ikut berubah saat user memilih
sumber baru — kecuali user sudah mengubah tujuan secara manual, yang lalu dikunci.

## 6. UI — satu jendela, bahasa Indonesia

```
┌─ Frequency Knife ───────────────────────────┐
│ Sumber    [ /Users/…/lagu.mp3      ] [Pilih…]│
│ Tujuan    [ /Users/…/              ] [Pilih…]│
│                                              │
│ Jumlah file output                           │
│   ────●───────────  [ 5 ]                    │
│   (akan menghasilkan 5 file)                 │
│                                              │
│ Preset sebaran  [ Rata (log)         ▾ ]     │
│                                              │
│ ▓▓▓▓▓▓▓▓▓░░░░░░░░░  62%                     │
│ Proses 3/5 — encoding band03.mp3             │
│                                              │
│              [ Batalkan ]  [ Proses ]        │
└──────────────────────────────────────────────┘
```

- Slider dan field angka saling ter-sync dua arah. Nilai di luar 2–30 di-clamp.
- Label "akan menghasilkan N file" ikut berubah saat slider bergerak.
- Tombol **Batalkan** hanya aktif saat proses berjalan; **Proses** dinonaktifkan saat
  berjalan.
- Tombol **Proses** juga dinonaktifkan bila sumber belum dipilih atau belum valid.
- Selesai → dialog sukses berisi daftar file + tombol **Buka Folder Tujuan**
  (macOS: `open <path>`).
- Error → dialog berisi pesan, tanpa stack trace mentah.

### Drag & drop

`MainWindow` memakai `setAcceptDrops(True)`.

- `dragEnterEvent` menerima hanya `QMimeData` berisi `urls` dengan ekstensi audio
  (daftar di §5). Tanpa ekstensi valid, `event.ignoreProposedAction()`.
- `dropEvent` mengambil file pertama, memasangnya sebagai sumber, dan menyetel ulang
  folder tujuan (kecuali sudah dikunci manual).
- Drop diterima di area mana pun dalam jendela, tidak hanya di field Sumber.
- Bila user men-drop lebih dari satu file, hanya yang pertama dipakai dan muncul
  catatan singkat di status bar.

## 7. Threading, progress, cancel

Worker berjalan di `QThread`. Sinyal yang dipancarkan:

| Sinyal | Kapan |
|---|---|
| `progress(int)` | 0–100, bobot: decode 10%, split 20%, encode 70% dibagi rata per pita |
| `status(str)` | "Membuka lagu.mp3…", "Memotong pita 3/5…", "Encoding band03.mp3…" |
| `finished(list)` | Daftar path hasil, dijalankan di thread UI |
| `error(str)` | Pesan ramah, dijalankan di thread UI |

Cancel diperiksa di:

- setiap akhir blok frame (dalam split)
- sebelum memulai encode tiap pita

Saat cancel: worker berhenti, memancarkan `cancelled`, `finally` menghapus folder temp,
dan `main.py` menghapus daftar file keluaran yang tercatat sebagai milik sesi ini.

## 8. Error handling

| Kondisi | Penanganan |
|---|---|
| Decode gagal / file rusak | Dialog berisi 5 baris terakhir stderr ffmpeg |
| Folder tujuan tidak bisa ditulis | Dicek dengan `os.access` sebelum mulai, ditolak lebih awal |
| Disk penuh / gagal tulis | `finally` bersihkan temp + hasil parsial, dialog error |
| ffmpeg tidak ditemukan | Dialog: "ffmpeg tidak ditemukan. Aplikasi memerlukan ffmpeg." |
| File sumber lebih dari 2 GB | Tetap jalan (streaming), tanpa batasan khusus |
| Ekstensi tidak dikenal saat drop | `ignore` di `dragEnterEvent`, field tidak berubah |

## 9. Testing

`tests/test_dsp.py` — pytest, numpy saja, tanpa Qt, jalan di CI headless:

1. **Rekonstruksi** — jumlah seluruh pita ≈ sinyal asli, galat maks < 1e-3, untuk
   sinyal acak dan untuk beberapa sinus campuran, pada mono dan stereo.
2. **Pemisahan benar** — sinus 100 Hz hanya mampu di pita yang memuat 100 Hz;
   pita lain di bawah ambang energi.
3. **Jumlah pita** — `N` pita menghasilkan `N` keluaran dengan `N-1` titik cut.
4. **Channel** — stereo masuk → stereo keluar per pita, dan kanal kiri/kanal kanan
   tidak tercampur.
5. **Preset** — cut selalu monotone naik; `p > 1` menumpukkan cut di bawah, `p < 1` di atas.
6. **Edge** — N=2 (minimum), N=30 (maksimum), sumber mono, sample rate 8 kHz
   (fmax di bawah 20 kHz, pastikan tidak ada titik cut ≥ Nyquist).

Uji end-to-end (decode ffmpeg → encode ffmpeg) dijalankan lokal saat build, tidak
wajib di CI karena butuh ffmpeg.

## 10. Packaging & build lintas OS

- **PyInstaller**: `--onefile --windowed --icon=freqknife.icns`, bundle id
  `com.freqknife.app`, `ffmpeg` dan `ffprobe` ikut dibundel sebagai **build statis** yang diunduh
  `build/get_ffmpeg.py` (macOS: ffmpeg.martin-riedl.de; Windows dan Linux: BtbN/FFmpeg-Builds).
  Binary dari brew/apt/choco TIDAK bisa dipakai: mereka bergantung puluhan
  library dinamis yang hanya ada di mesin build, sehingga aplikasi gagal di
  mesin lain sementara CI tetap hijau karena selftest berjalan di mesin yang sama.
- **Ketergantungan Linux**: `ffmpeg`/`ffprobe` memang dibundel penuh, tapi PySide6
  masih menautkan pustaka Qt milik sistem (`libEGL.so.1`, `libGL`, `libxkbcommon0`,
  `libdbus-1-3`, `libfontconfig1`, `libxcb-*`). Jadi artefak Linux hanya berjalan
  di mesin yang sudah memasangnya —
  `sudo apt-get install libegl1 libgl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 libfontconfig1 libxcb-cursor0`.
  Ini batasan Qt di Linux, bukan kekurangan bundling; macOS dan Windows tidak terpengaruh.
- **Icon** dibuat sendiri: SVG → PNG (16/32/128/256/512) → `.icns` via `iconutil`
  untuk macOS, `.ico` untuk Windows, `.png` 512 untuk Linux. Bukan icon bawaan Python.
- **GitHub Actions** matrix `macos-latest` / `windows-latest` / `ubuntu-latest`
  menghasilkan `FreqKnife.app` (macOS), `FreqKnife.exe` (Windows), dan executable
  tunggal (Linux). AppImage ditunda — butuh `appimagetool` tambahan.
- **Signing**: ad-hoc (`codesign --force --deep -s -`) untuk rilis internal.
  Notarisasi Apple butuh akun Apple Developer — di luar cakupan rilis pertama.
- Catatan kompatibilitas: untuk distribusi luas, build macOS di runner macOS 13/14
  (bukan mesin dev yang macOS 27 + Python 3.13) agar binary jalan di mesin lama.
  `MACOSX_DEPLOYMENT_TARGET=11.0`.

## 11. Di luar cakupan (YAGNI)

Sengaja tidak dibuat, dan arsitektur di atas memungkinkannya ditambah nanti tanpa
merombak:

- Batch beberapa file sumber sekaligus
- Preview pemutaran hasil
- Edit titik cut manual
- Ekspor ke format selain mengikuti format input
- Memecah channel L/R menjadi file terpisah
- Simpan / muat profil preset buatan user
