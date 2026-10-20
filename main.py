"""Jendela utama Frequency Knife."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

import audio_io
import dsp
from worker import SplitWorker

AKAR = Path(__file__).resolve().parent
ICON = AKAR / "assets" / "icon.icns" if sys.platform == "darwin" else AKAR / "assets" / "icon.png"
# daftar ekstensi satu sumber: drag & drop dan dialog pilih memakai filter yang sama
FILTER = "Audio (" + " ".join(sorted(audio_io.AUDIO_EXTENSIONS)) + ")"


def selftest():
    """Verifikasi binary terbungkus tanpa GUI. Dipakai build dan CI."""
    import numpy as np
    rng = np.random.default_rng(0)
    x = (rng.standard_normal((8192, 2)) * 0.1).astype(np.float32)
    bands = dsp.split_bands(x, 44100, 5)
    galat = float(np.abs(np.sum(bands, axis=0) - x).max())
    print(f"selftest: {len(bands)} pita, galat rekonstruksi {galat:.2e}")
    return 0 if galat < 1e-3 else 1


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Frequency Knife")
        if ICON.exists():
            self.setWindowIcon(QIcon(str(ICON)))
        self.setMinimumWidth(470)
        self.dest_manual = False
        self.worker = None

        self.sumber = QLineEdit()
        self.sumber.setReadOnly(True)
        self.sumber.setPlaceholderText("Pilih file… atau tarik ke sini")
        self.tujuan = QLineEdit()
        self.tujuan.setPlaceholderText("Folder tujuan — default sama dengan folder sumber")

        btn_sumber = QPushButton("Pilih…")
        btn_sumber.clicked.connect(self.pilih_sumber)
        btn_tujuan = QPushButton("Pilih…")
        btn_tujuan.clicked.connect(self.pilih_tujuan)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(dsp.BANDS_SLIDER_MIN, dsp.BANDS_SLIDER_MAX)
        self.slider.setValue(dsp.BANDS_DEFAULT)
        self.spin = QSpinBox()
        self.spin.setRange(dsp.BANDS_MIN, dsp.BANDS_MAX)
        self.spin.setValue(dsp.BANDS_DEFAULT)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self._spin_berubah)
        self.hint = QLabel()

        self.preset = QComboBox()
        self.preset.addItems(dsp.PRESET_NAMES)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.status = QLabel("Pilih file suara — atau tarik file ke jendela ini.")

        self.btn_batal = QPushButton("Batalkan")
        self.btn_batal.setEnabled(False)
        self.btn_batal.clicked.connect(self.batalkan)
        self.btn_proses = QPushButton("Proses")
        self.btn_proses.setDefault(True)
        self.btn_proses.clicked.connect(self.proses)

        isi = QWidget()
        grid = QGridLayout()
        grid.addWidget(QLabel("Sumber"), 0, 0)
        grid.addWidget(self.sumber, 0, 1)
        grid.addWidget(btn_sumber, 0, 2)
        grid.addWidget(QLabel("Tujuan"), 1, 0)
        grid.addWidget(self.tujuan, 1, 1)
        grid.addWidget(btn_tujuan, 1, 2)

        jumlah = QHBoxLayout()
        jumlah.addWidget(self.slider)
        jumlah.addWidget(self.spin)
        jumlah.addWidget(QLabel("file"))

        tombol = QHBoxLayout()
        tombol.addStretch(1)
        tombol.addWidget(self.btn_batal)
        tombol.addWidget(self.btn_proses)

        utama = QVBoxLayout(isi)
        utama.addLayout(grid)
        utama.addWidget(QLabel("Jumlah file output"))
        utama.addLayout(jumlah)
        utama.addWidget(self.hint)
        utama.addWidget(QLabel("Preset sebaran"))
        utama.addWidget(self.preset)
        utama.addWidget(self.bar)
        utama.addWidget(self.status)
        utama.addLayout(tombol)
        self.setCentralWidget(isi)

        self.setAcceptDrops(True)
        self._sinkron_hint()

    # --- drag & drop -------------------------------------------------
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in audio_io.AUDIO_EXTENSIONS:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        self.set_sumber(urls[0].toLocalFile())
        if len(urls) > 1:
            self.status.setText("Hanya file pertama yang dipakai.")
        event.acceptProposedAction()

    # --- pemilihan file ----------------------------------------------
    def pilih_sumber(self):
        jalur, _ = QFileDialog.getOpenFileName(self, "Pilih file suara", "", FILTER)
        if jalur:
            self.set_sumber(jalur)

    def set_sumber(self, jalur):
        self.sumber.setText(jalur)
        if not self.dest_manual:
            self.tujuan.setText(str(Path(jalur).parent))
        self._sinkron_hint()

    def pilih_tujuan(self):
        jalur = QFileDialog.getExistingDirectory(self, "Pilih folder tujuan", self.tujuan.text())
        if jalur:
            self.tujuan.setText(jalur)
            self.dest_manual = True

    # --- jumlah file --------------------------------------------------
    def _spin_berubah(self, nilai):
        # slider dibatasi 3–10; nilai di luar itu hanya bisa lewat spin
        if self.slider.minimum() <= nilai <= self.slider.maximum():
            self.slider.blockSignals(True)
            self.slider.setValue(nilai)
            self.slider.blockSignals(False)
        self._sinkron_hint()

    def _sinkron_hint(self):
        n = dsp.clamp_bands(self.spin.value())
        self.hint.setText(f"Akan menghasilkan {n} file")

    # --- proses --------------------------------------------------------
    def proses(self):
        sumber = self.sumber.text().strip()
        tujuan = self.tujuan.text().strip() or str(Path(sumber).parent)

        if not sumber or not Path(sumber).exists():
            QMessageBox.warning(self, "FreqKnife", "File sumber belum dipilih atau tidak ada.")
            return
        if not Path(sumber).is_file():
            QMessageBox.warning(self, "FreqKnife", "Sumber harus berupa file, bukan folder.")
            return
        if audio_io.ffmpeg_missing():
            QMessageBox.critical(self, "FreqKnife",
                                 "ffmpeg tidak ditemukan. Aplikasi memerlukan ffmpeg.")
            return

        # folder tujuan tidak dibuat di sini: worker membuatnya tepat saat
        # akan dipakai, supaya batal/gagal tidak meninggalkan folder kosong

        self.btn_proses.setEnabled(False)
        self.btn_batal.setEnabled(True)
        self.bar.setValue(0)
        self.status.setText("Menyiapkan…")

        self.worker = SplitWorker(sumber, tujuan, dsp.clamp_bands(self.spin.value()),
                                  self.preset.currentText(), self)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.status.connect(self.status.setText)
        self.worker.finished_ok.connect(self._selesai)
        self.worker.cancelled.connect(self._dibatalkan)
        self.worker.failed.connect(self._gagal)
        self.worker.start()

    def batalkan(self):
        if self.worker is not None:
            self.btn_batal.setEnabled(False)
            self.status.setText("Membatalkan…")
            self.worker.cancel()

    def _kembalikan_tombol(self):
        self.btn_proses.setEnabled(True)
        self.btn_batal.setEnabled(False)

    def _selesai(self, hasil):
        self._kembalikan_tombol()
        self.status.setText(f"Selesai — {len(hasil)} file dibuat.")
        daftar = "\n".join(p.name for p in hasil)
        box = QMessageBox(self)
        box.setWindowTitle("FreqKnife")
        box.setText(f"{len(hasil)} file berhasil dibuat.")
        box.setInformativeText(daftar)
        buka = box.addButton("Buka Folder Tujuan", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is buka and hasil:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(hasil[0].parent)))

    def _bersihkan(self, ditulis):
        # ditulis bisa berisi file lengkap, file parsial, atau path yang
        # belum pernah dibuat (append-before-encode) — semua diabaikan bila hilang
        for p in ditulis or []:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass

    def _dibatalkan(self, ditulis):
        self._bersihkan(ditulis)
        self._kembalikan_tombol()
        self.bar.setValue(0)
        self.status.setText("Dibatalkan. Hasil parsial dihapus.")

    def _gagal(self, pesan):
        # encode yang gagal di tengah juga meninggalkan file parsial
        self._bersihkan(self.worker.written)
        self._kembalikan_tombol()
        self.bar.setValue(0)
        self.status.setText("Gagal.")
        QMessageBox.critical(self, "FreqKnife", pesan)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            # menunggu selesai: QThread yang masih jalan saat dihancurkan = crash
            if not self.worker.wait(8000):
                QMessageBox.warning(
                    self, "FreqKnife",
                    "Masih memproses file. Tutup aplikasi lagi setelah selesai.")
                event.ignore()
                return
        event.accept()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if "--selftest" in argv:
        return selftest()
    app = QApplication(argv)
    app.setApplicationName("FreqKnife")
    app.setApplicationDisplayName("Frequency Knife")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
