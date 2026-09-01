from __future__ import annotations

import csv
from typing import cast

import h5py
import pytest

from serial_monitor.application.recording_service import RecordingService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.models import CommunicationStats
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.infrastructure.storage.hdf5_session_writer import Hdf5SessionWriter
from serial_monitor.infrastructure.storage.session_repository import (
    ExportCancelledError,
    SessionRepository,
)


def _session(window_size: int = 100):
    return SessionService().build_session(
        port="TEST",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=window_size,
        signal_order_text="ecg,ppg,oximetria",
    )


def _frame(parser: FrameCsvParser, session, sequence: int):
    return parser.parse_line(
        f"FRAME,{sequence},{1_000_000 + sequence * 1_000},"
        f"{sequence},{sequence + 0.5},{97 + sequence % 2}",
        session,
    ).frame


def _record_complete(tmp_path, *, frame_count: int = 1000):
    session = _session(window_size=100)
    parser = FrameCsvParser()
    recorder = RecordingService(
        tmp_path,
        queue_capacity=max(2048, frame_count + 10),
        batch_size=64,
        flush_interval_s=0.01,
    )
    recorder.start(session)
    for sequence in range(1, frame_count + 1):
        recorder.enqueue_frame(_frame(parser, session, sequence))
    status = recorder.finalize(CommunicationStats(valid_frames=frame_count), reason="test")
    assert status.output_path is not None
    return session, status


def test_load_window_reads_only_requested_interval_and_decimates(tmp_path):
    _, status = _record_complete(tmp_path, frame_count=1000)
    repository = SessionRepository(tmp_path)
    summary = repository.list_sessions()[0]

    assert summary.format_version == Hdf5SessionWriter.FORMAT_VERSION
    assert summary.integrity_status == "verified"
    assert summary.content_sha256
    assert summary.first_timestamp_us == 1_001_000
    assert summary.last_timestamp_us == 2_000_000

    loaded = repository.load_window(
        summary.session_id,
        start_us=1_200_000,
        end_us=1_400_000,
        max_points=50,
    )

    assert loaded.total_frames == 1000
    assert loaded.loaded_frames == 50
    assert loaded.decimated_for_display is True
    assert loaded.loaded_start_us is not None and loaded.loaded_start_us >= 1_200_000
    assert loaded.loaded_end_us is not None and loaded.loaded_end_us <= 1_400_000
    assert loaded.snapshot.channels[0].sample_count == 50
    assert status.output_path is not None and status.output_path.exists()


def test_incomplete_session_is_finalized_automatically(tmp_path):
    session = _session(window_size=10)
    parser = FrameCsvParser()
    writer = Hdf5SessionWriter(
        base_dir=tmp_path,
        session_id="session_interrupted",
        session=session,
        chunk_size=8,
    )
    writer.open()
    writer.append_batch([_frame(parser, session, seq) for seq in range(1, 21)])
    writer.flush()
    partial_path = writer.close_failed(error_message="simulated power loss")

    repository = SessionRepository(tmp_path)
    assert repository.list_sessions() == []

    results = repository.finalize_incomplete_sessions()
    assert len(results) == 1
    assert results[0].frames_recovered == 20
    assert results[0].frames_discarded == 0
    assert results[0].output_path.exists()
    assert not partial_path.exists()

    finalized = repository.list_sessions()[0]
    assert finalized.is_partial is False
    assert finalized.state == "completed"
    assert finalized.end_reason == "unexpected_shutdown"
    assert finalized.integrity_status == "verified"
    assert repository.verify_integrity(finalized.session_id) == "verified"

def test_csv_export_reports_progress_and_removes_temporary_file_when_cancelled(tmp_path):
    _, _ = _record_complete(tmp_path, frame_count=120)
    repository = SessionRepository(tmp_path)
    session_id = repository.list_sessions()[0].session_id

    progress: list[tuple[int, int]] = []
    output = repository.export_csv(
        session_id,
        output_path=tmp_path / "complete.csv",
        chunk_size=17,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )
    assert progress[0] == (0, 120)
    assert progress[-1] == (120, 120)
    with output.open(newline="", encoding="utf-8") as fp:
        assert len(list(csv.reader(fp))) == 121

    cancel_state = {"cancel": False}

    def on_progress(completed: int, total: int) -> None:
        if completed >= 20:
            cancel_state["cancel"] = True

    cancelled_output = tmp_path / "cancelled.csv"
    with pytest.raises(ExportCancelledError):
        repository.export_csv(
            session_id,
            output_path=cancelled_output,
            chunk_size=20,
            progress_callback=on_progress,
            cancel_check=lambda: cancel_state["cancel"],
        )
    assert not cancelled_output.exists()
    assert not (tmp_path / "cancelled.csv.partial").exists()


def test_integrity_verification_detects_modified_dataset(tmp_path):
    _, status = _record_complete(tmp_path, frame_count=30)
    repository = SessionRepository(tmp_path)
    session_id = repository.list_sessions()[0].session_id
    assert repository.verify_integrity(session_id) == "verified"

    assert status.output_path is not None
    with h5py.File(status.output_path, "r+") as h5:
        dataset = cast(h5py.Dataset, h5["frames/raw_values"])
        dataset[0, 0] = 999999.0
        h5.flush()

    assert repository.verify_integrity(session_id) == "failed"
    assert repository.get_summary(session_id).integrity_status == "failed"


def test_effective_sample_rate_is_persisted_and_restored(tmp_path):
    session = _session(window_size=10)
    parser = FrameCsvParser()
    recorder = RecordingService(
        tmp_path,
        queue_capacity=32,
        batch_size=8,
        flush_interval_s=0.01,
    )
    recorder.start(session)
    recorder.enqueue_frame(_frame(parser, session, 1))
    status = recorder.finalize(
        CommunicationStats(
            valid_frames=1,
            estimated_sample_rate_hz=1093.5,
            sample_rate_locked=True,
            sample_rate_windows=2,
            sample_rate_deviation_percent=9.35,
        ),
        reason="test",
    )

    assert status.output_path is not None
    with h5py.File(status.output_path, "r") as h5:
        assert float(h5.attrs["effective_sample_rate_hz"]) == pytest.approx(1093.5)
        assert bool(h5.attrs["sample_rate_locked"])

    stored = SessionRepository(tmp_path).load(status.session_id)
    assert stored.summary.effective_sample_rate_hz == pytest.approx(1093.5)
    assert stored.snapshot.communication.estimated_sample_rate_hz == pytest.approx(1093.5)
    assert stored.session.channels[0].sample_rate_hz == pytest.approx(1093.5)
