# FreqKnife

Split a single audio file into separate frequency-band files — like an
equalizer, except each band becomes its own file.

**Built to make DaVinci Resolve sound visualizers easier** — see
[Background](#background).

`ffmpeg`/`ffprobe` ship as bundled static builds, so **you do not need to
install ffmpeg**. On Linux you still need the system Qt libraries — see
[Linux](#linux).

## Background

Resolve's audio-driven effects react to the overall amplitude of a clip. That
gives you one signal for the whole track, not one signal per frequency band —
so building a multi-bar spectrum visualizer means cutting the audio apart by
frequency first.

FreqKnife does that cut for you.

Want a sound visualizer with **10 bars**, each reacting to a different
frequency range? Split the track into **10 files**, one per band:

1. Put each band file on its own timeline track.
2. Drive one bar per track — each track now carries exactly one frequency
   range, so its bar responds only to that range.

5 bars → 5 files. 10 bars → 10 files. No manual cutting, no plugins.

## Download

Grab an artifact from
[Actions](https://github.com/dkeceh/FreqKnife/actions) — every push to `main`
builds all three:

| Platform | Artifact | Notes |
|---|---|---|
| macOS | `FreqKnife-mac` | `FreqKnife.app`, auto ad-hoc signed by PyInstaller (required on Apple Silicon) |
| Windows | `FreqKnife-win` | `FreqKnife.exe` |
| Linux | `FreqKnife-linux` | needs system Qt libraries, see [Linux](#linux) |

## How to use

1. Open the app, then pick a file or **drag one onto the window**.
2. Set the **number of output files** (slider 3–10, or type 2–30).
3. Pick a **preset** for how the cut points are spread.
4. Destination folder defaults to the source folder. Change it if you want.
5. Click **Process**. The progress bar shows the percentage; **Cancel** can be
   pressed at any time and partial results are cleaned up.

5 output files means **4** cut points. With `lagu.mp3` as the source:

```
lagu_band01.mp3  lagu_band02.mp3  lagu_band03.mp3  lagu_band04.mp3  lagu_band05.mp3
```

Names already in use get a `_2`, `_3`, … suffix automatically — existing files
are never overwritten.

### Presets

Cut points are always spread logarithmically from 20 Hz up to
`min(20 kHz, 0.98 × Nyquist)`, then shifted by a single skew factor:

| Preset | Spreading |
|---|---|
| Flat (log) | even on a log scale |
| Bass-heavy | lower bands narrower — bass resolves into finer bars |
| Mid/High-heavy | upper bands narrower — mid/high resolves into finer bars |

Measured at 44.1 kHz with 5 bands, the lowest band is 60 Hz wide for *Flat (log)*,
14 Hz for *Bass-heavy*, and 235 Hz for *Mid/High-heavy*.

For a visualizer, that is the knob that matters: *Bass-heavy* gives you
several low bars if the bass is what should move, and *Mid/High-heavy* does
the same for the top end.

### Formats

Selectable input is limited to this list (the dialog filter and the drag & drop
check both enforce it):

`WAV, MP3, FLAC, M4A/AAC, OGG/Opus, AIFF, WMA, MP4, WebM`

Output format **follows the input** for WAV, MP3, FLAC, M4A/AAC and OGG/Opus.
The rest — AIFF, WMA, MP4, WebM — have no codec mapping here and fall back to
WAV. Channel count is always preserved: stereo in → stereo out per band.

## Linux

`ffmpeg` is bundled in full, but PySide6 still links against the system's Qt
libraries. Install these first (the same list CI uses):

```bash
sudo apt-get install -y --no-install-recommends \
  libegl1 libgl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 \
  libfontconfig1 libx11-xcb1 libxcb-cursor0 libxcb-icccm4 \
  libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
  libxcb-shape0 libxcb-xinerama0 libxcb-xkb1
```

Without them the app stops at import with `ImportError: libEGL.so.1`. This is a
Qt limitation on Linux, not a bundling gap — macOS and Windows are unaffected.

## Build from source

Needs Python 3.11+. On macOS:

```bash
bash build/build_mac.sh
```

The script creates a venv, installs dependencies, generates the icons, downloads
static `ffmpeg`/`ffprobe` into `vendor/`, then builds `dist/FreqKnife.app` and
selftests it immediately. Windows and Linux are built through
[GitHub Actions](.github/workflows/build.yml); the commands live there.

Without PyInstaller, run straight from Python:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Development

```bash
.venv/bin/pytest        # 64 tests
python main.py --selftest
```

CI runs the full suite on all three platforms before building, so a green
artifact also means the tests passed on that OS.

`--selftest` verifies the bundled binary **without a GUI**: it checks DSP
reconstruction error, then performs a real decode + encode with the bundled
ffmpeg. This is what stops a broken artifact from being uploaded — a Linux build
that cannot run stops here.

Layout:

```
main.py          main window, selftest
dsp.py           frequency cutting — pure numpy, no Qt
audio_io.py      decode/encode via ffmpeg subprocess
worker.py        QThread + process_file
build/           make_icons.py, get_ffmpeg.py, build_mac.sh
tests/           64 tests
docs/            design spec and implementation plan
```

## License

FreqKnife's own source is [MIT](LICENSE).

**Attention — the bundled binaries are differently licensed.** The
`ffmpeg`/`ffprobe` builds shipped inside the app are **GPLv3** static builds
(their configuration includes `--enable-gpl --enable-version3 --enable-libx264
--enable-libx265`). These are separate works: the app invokes them through a
subprocess, so the MIT license applies to FreqKnife's source and does not carry
over to it.

But **distributing FreqKnife artifacts means also distributing GPLv3 software**,
so its conditions apply to that distribution. The license text ships inside every
artifact — `FreqKnife.app/Contents/Resources/LICENSE.GPLv3` on macOS, and
`LICENSE.GPLv3` next to the executable on Windows and Linux. Corresponding
source:

- https://www.martin-riedl.de/ffmpeg/ (macOS)
- https://github.com/BtbN/FFmpeg-Builds (Linux, Windows)
