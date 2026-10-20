import subprocess
from pathlib import Path

import pytest

import audio_io
import worker

pytestmark = pytest.mark.skipif(
    audio_io.ffmpeg_missing(), reason="ffmpeg tidak tersedia")


def _buat_sumber(tmp_path, nama="lagu.wav", sr=44100, detik=2.0):
    path = tmp_path / nama
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:sample_rate={sr}:duration={detik}", path],
        check=True)
    return path


def test_menghasilkan_n_file_dengan_nama_benar(tmp_path):
    src = _buat_sumber(tmp_path)
    hasil = worker.process_file(src, tmp_path, 5, "Rata (log)")
    assert len(hasil) == 5
    assert [p.name for p in hasil] == [
        f"lagu_band0{i}.wav" for i in range(1, 6)]
    for p in hasil:
        assert p.exists() and p.stat().st_size > 0
        assert audio_io.probe(p)["sample_rate"] == 44100


def test_progress_monoton_naik_sampai_100(tmp_path):
    src = _buat_sumber(tmp_path, nama="lagu.mp3", detik=1.0)
    nilai = []
    worker.process_file(src, tmp_path, 4, "Rata (log)",
                        on_progress=nilai.append)
    assert nilai == sorted(nilai)
    assert nilai[-1] == 100
    assert all(0 <= v <= 100 for v in nilai)


def test_format_output_mengikuti_input_mp3(tmp_path):
    src = _buat_sumber(tmp_path, nama="lagu.wav")
    mp3 = tmp_path / "lagu.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), str(mp3)], check=True)
    hasil = worker.process_file(mp3, tmp_path / "keluar", 3, "Rata (log)")
    assert all(p.suffix == ".mp3" for p in hasil)
    assert audio_io.probe(hasil[0])["channels"] == 1


def test_folder_tujuan_dibuat_bila_belum_ada(tmp_path):
    src = _buat_sumber(tmp_path, detik=0.5)
    tujuan = tmp_path / "belum" / "ada"
    hasil = worker.process_file(src, tujuan, 2, "Rata (log)")
    assert all(p.exists() for p in hasil)


def test_file_band_yang_sudah_ada_tidak_pernah_ditimpa(tmp_path):
    """Jaminan \"file user tidak pernah hilang\" ada di pemanggil, bukan di ffmpeg."""
    src = _buat_sumber(tmp_path, detik=1.0)
    lama = tmp_path / "lagu_band01.wav"
    lama.write_bytes(b"PUNYA USER JANGAN DITIMPA")

    hasil = worker.process_file(src, tmp_path, 3, "Rata (log)")

    assert lama.read_bytes() == b"PUNYA USER JANGAN DITIMPA"
    assert [p.name for p in hasil] == [
        "lagu_band01_2.wav", "lagu_band02.wav", "lagu_band03.wav"]


def test_cancel_menghentikan_dan_melempar_jobcancelled(tmp_path):
    src = _buat_sumber(tmp_path, detik=3.0)
    dipanggil = []

    def batal():
        return len(dipanggil) > 0

    with pytest.raises(worker.JobCancelled):
        worker.process_file(src, tmp_path, 5, "Rata (log)",
                            on_progress=lambda p: dipanggil.append(p),
                            is_cancelled=batal)


def test_file_terlanjur_tulis_tercatat_untuk_dihapus(tmp_path):
    src = _buat_sumber(tmp_path, detik=3.0)
    ditulis = []
    panggilan = []

    def batal():
        return len(panggilan) > 3

    with pytest.raises(worker.JobCancelled):
        worker.process_file(src, tmp_path, 5, "Rata (log)",
                            on_progress=lambda p: panggilan.append(p),
                            is_cancelled=batal, written=ditulis)
    # sebelum encode tidak ada file keluaran, jadi daftar kosong
    assert ditulis == []


def test_folder_temp_dibersihkan(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    src = _buat_sumber(tmp_path, detik=0.5)
    worker.process_file(src, tmp_path, 2, "Rata (log)")
    assert list((tmp_path / "tmp").iterdir()) == []


def test_batal_tidak_meninggalkan_folder_tujuan(tmp_path):
    src = _buat_sumber(tmp_path, detik=3.0)
    tujuan = tmp_path / "belum-pernah-ada"
    panggilan = []

    with pytest.raises(worker.JobCancelled):
        worker.process_file(src, tujuan, 5, "Rata (log)",
                            on_progress=lambda p: panggilan.append(p),
                            is_cancelled=lambda: len(panggilan) > 3)

    assert not tujuan.exists()


def test_encode_gagal_dicatat_untuk_dibersihkan(tmp_path, monkeypatch):
    """Encode yang gagal di tengah meninggalkan file parsial — harus tercatat."""
    src = _buat_sumber(tmp_path, detik=0.5)
    ditulis = []

    def setengah_jalan(raw_path, out_path, *args, **kwargs):
        # simulasi ffmpeg meninggalkan file parsial lalu mati
        Path(out_path).write_bytes(b"RIFFparsial")
        raise RuntimeError("ffmpeg gagal encode (simulasi)")

    monkeypatch.setattr(audio_io, "encode_raw", setengah_jalan)

    with pytest.raises(RuntimeError):
        worker.process_file(src, tmp_path, 3, "Rata (log)", written=ditulis)

    # band pertama gagal → targetnya harus sudah tercatat, siap dihapus pemanggil
    assert len(ditulis) == 1
    assert ditulis[0].name == "lagu_band01.wav"
    assert ditulis[0].exists()


def test_split_worker_punya_sinyal_yang_dibutuhkan_ui():
    for nama in ("progress", "status", "finished_ok", "failed", "cancelled"):
        assert hasattr(worker.SplitWorker, nama), nama
    assert hasattr(worker.SplitWorker, "cancel")


def test_split_worker_bisa_dibuat_tanpa_qapp():
    w = worker.SplitWorker("a.wav", "/tmp", 5, "Rata (log)")
    assert w.n_bands == 5
    assert not w._cancel
    w.cancel()
    assert w._cancel
