"""Orkestrasi pemisahan: `process_file` murni Python, `SplitWorker` pembungkus QThread tipis."""

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

import audio_io
import dsp

FRAME = dsp.FRAME_DEFAULT


class JobCancelled(Exception):
    pass


def process_file(source, dest_dir, n_bands, preset,
                 on_progress=None, on_status=None, is_cancelled=None, written=None):
    """Pisahkan satu file. Kembalikan daftar Path hasil.

    `written` diisi bertahap supaya pemanggil bisa menghapus hasil parsial saat batal.
    """
    source = Path(source)
    dest_dir = Path(dest_dir)
    written = [] if written is None else written
    on_progress = on_progress or (lambda p: None)
    on_status = on_status or (lambda s: None)
    is_cancelled = is_cancelled or (lambda: False)

    def cek():
        if is_cancelled():
            raise JobCancelled()

    on_status(f"Opening {source.name}…")
    on_progress(2)
    tmp = Path(tempfile.mkdtemp(prefix="freqknife-"))
    samples = None
    try:
        raw_in = tmp / "source.f32le"
        sr, channels, n_frames = audio_io.decode_to_raw(source, raw_in)
        samples = audio_io.open_raw(raw_in, n_frames, channels)
        cek()

        on_status("Cutting bands…")
        masks = dsp.band_masks(FRAME, sr, n_bands, preset)
        n_out = len(masks)
        if n_out != n_bands:
            on_status(f"Sebaran menyesuaikan: {n_out} file")

        ext, codec = audio_io.output_plan(source.suffix)
        raw_out = [tmp / f"band{i:02d}.f32le" for i in range(n_out)]
        handles = [open(p, "wb") for p in raw_out]
        ditulis_per_pita = [0] * n_out

        lapor = -1
        try:
            for i, chunk in dsp.iter_split(samples, sr, n_bands, preset, FRAME):
                handles[i].write(chunk.tobytes())
                ditulis_per_pita[i] += len(chunk)
                if i == n_out - 1:
                    maju = min(ditulis_per_pita[i], n_frames)
                    persen = 10 + int(20 * maju / max(n_frames, 1))
                    if persen != lapor:
                        lapor = persen
                        on_progress(persen)
                        cek()
        finally:
            for fh in handles:
                fh.close()
        cek()

        dest_dir.mkdir(parents=True, exist_ok=True)
        hasil = []
        for i in range(n_out):
            cek()
            on_status(f"Encoding band{i + 1:02d}{ext}")
            target = audio_io.available_path(audio_io.band_path(dest_dir, source.stem, i + 1, ext))
            # dicatat SEBELUM encode: encode gagal di tengah meninggalkan file
            # parsial, dan file itu harus ikut terhapus saat batal/gagal
            written.append(target)
            audio_io.encode_raw(raw_out[i], target, sr, channels, codec)
            hasil.append(target)
            on_progress(30 + int(70 * (i + 1) / n_out))

        on_progress(100)
        on_status("Done")
        return hasil
    finally:
        del samples
        shutil.rmtree(tmp, ignore_errors=True)


def friendly_error(exc):
    """Pesan yang aman ditampilkan ke user."""
    return str(exc).strip() or exc.__class__.__name__


class SplitWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished_ok = Signal(list)
    failed = Signal(str)
    cancelled = Signal(list)

    def __init__(self, source, dest_dir, n_bands, preset, parent=None):
        super().__init__(parent)
        self.source, self.dest_dir = source, dest_dir
        self.n_bands, self.preset = n_bands, preset
        self._cancel = False
        self.written = []

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            hasil = process_file(
                self.source, self.dest_dir, self.n_bands, self.preset,
                on_progress=self.progress.emit,
                on_status=self.status.emit,
                is_cancelled=lambda: self._cancel,
                written=self.written,
            )
        except JobCancelled:
            self.cancelled.emit(self.written)
        except Exception as exc:
            self.failed.emit(friendly_error(exc))
        else:
            self.finished_ok.emit(hasil)
