import os

import pytest

import main


def test_selftest_lulus():
    assert main.selftest() == 0


def test_ekstensi_audio_dikenali():
    import audio_io
    assert ".mp3" in audio_io.AUDIO_EXTENSIONS
    assert ".wav" in audio_io.AUDIO_EXTENSIONS
    assert ".txt" not in audio_io.AUDIO_EXTENSIONS


def test_filter_dialog_pakai_wildcard():
    """Qt butuh "*.wav"; tanpa bintang semua file nonaktif di dialog Pilih."""
    from PySide6.QtCore import QDir
    import audio_io
    for e in audio_io.AUDIO_EXTENSIONS:
        assert "*" + e in main.FILTER, e
    assert QDir.match("*.wav", "lagu.wav")
    assert not QDir.match(".wav", "lagu.wav")  # jebakan yang menghasilkan bug ini


@pytest.fixture(scope="module")
def app():
    # tanpa display: semua test jendela pakai platform offscreen
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def jendela(app):
    return main.MainWindow()


def test_tujuan_otomatis_dari_sumber_lalu_terkunci(jendela):
    jendela.set_sumber("/tmp/lagu.mp3")
    assert jendela.tujuan.text() == "/tmp"

    # user mengunci tujuan secara manual (tanpa membuka dialog)
    jendela.dest_manual = True
    jendela.tujuan.setText("/tmp/lain")
    jendela.set_sumber("/tmp/lagu2.mp3")
    assert jendela.tujuan.text() == "/tmp/lain", "tujuan manual harus bertahan"
    assert jendela.sumber.text() == "/tmp/lagu2.mp3"


def test_slider_dan_spin_sinkron(jendela):
    # slider dibatasi 3–10, spin 2–30
    jendela.spin.setValue(7)
    assert jendela.slider.value() == 7
    assert jendela.hint.text() == "Akan menghasilkan 7 file"

    # nilai di luar jangkauan slider: hint mengikuti spin, slider tidak dipaksa
    jendela.spin.setValue(30)
    assert jendela.slider.value() == 7, "slider tidak boleh dipaksa ke luar jangkauan"
    assert jendela.hint.text() == "Akan menghasilkan 30 file"


def test_proses_menolak_tanpa_sumber(jendela, monkeypatch):
    peringatan = []
    monkeypatch.setattr(main.QMessageBox, "warning",
                        lambda *a, **k: peringatan.append(a))
    jendela.proses()
    assert len(peringatan) == 1
    # tombol tidak boleh terkunci: tidak ada job yang berjalan
    assert jendela.btn_proses.isEnabled()
    assert not jendela.btn_batal.isEnabled()


def test_batal_awal_kembalikan_keadaan_normal(app, jendela, tmp_path, monkeypatch):
    """Sinyal cancelled → _dibatalkan: tombol pulih, tidak ada file tersisa.

    Pembatalan di sini ditekan saat status pertama, jadi belum ada pita yang
    di-encode — pembersihan file parsial sendiri sudah diuji di tingkat
    process_file (test_file_terlanjur_tulis_tercatat_untuk_dihapus).
    Yang diuji di sini adalah jalur sinyal Qt-nya, yang tidak bisa dicapai
    dari test worker.py.
    """
    import subprocess
    import time

    src = tmp_path / "lagu.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:sample_rate=44100:duration=4", str(src)],
        check=True)

    jendela.set_sumber(str(src))
    jendela.spin.setValue(5)

    # tanpa dialog modal yang menggantung test
    monkeypatch.setattr(main.QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *a, **k: None)

    jendela.proses()
    assert not jendela.btn_proses.isEnabled()
    assert jendela.btn_batal.isEnabled()

    # tekan Batalkan begitu ada kemajuan; sinyal status masuk lewat event
    # loop GUI, jadi event loop harus dipompa, bukan worker.wait() yang memblokir
    jendela.worker.status.connect(jendela.batalkan)
    batas = time.time() + 60
    while jendela.worker.isRunning() and time.time() < batas:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    assert not jendela.worker.isRunning(), "job harus berhenti"
    assert jendela.btn_proses.isEnabled(), "tombol Proses harus pulih"
    assert not jendela.btn_batal.isEnabled()
    assert list(tmp_path.glob("*_band*")) == [], "tidak boleh ada file parsial"
    assert "Dibatalkan" in jendela.status.text()
