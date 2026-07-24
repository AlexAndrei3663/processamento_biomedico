from __future__ import annotations

import csv

import h5py
from typing import cast
import pytest

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.recording_service import RecordingService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import RecordingState
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.infrastructure.storage.session_repository import SessionRepository


def test_continuous_recording_preserves_complete_session_beyond_ring_buffer(tmp_path):
    session = SessionService().build_session(
        port="TEST",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=5,
        signal_order_text="ecg,ppg,oximetria",
    )
    parser = FrameCsvParser()
    acquisition = LiveAcquisitionService()
    acquisition.configure(session)

    recorder = RecordingService(
        tmp_path,
        queue_capacity=128,
        batch_size=16,
        flush_interval_s=0.05,
    )
    recorder.start(session, active_filters={0: ["baseline"], 1: ["lowpass"]})

    for sequence in range(1, 101):
        frame = parser.parse_line(
            f"FRAME,{sequence},{1_000_000 + sequence * 1_000},"
            f"{sequence},{sequence + 0.5},{97 + sequence % 2}",
            session,
        ).frame
        assert acquisition.ingest_frame(frame)
        recorder.enqueue_frame(frame)
        if sequence == 50:
            acquisition.clear_buffers()
            assert acquisition.snapshot().frames_received == 50
            assert acquisition.snapshot().channels[0].sample_count == 0

    acquisition.record_invalid_frame()
    status = recorder.finalize(
        acquisition.snapshot().communication,
        reason="test_completed",
    )

    assert status.state is RecordingState.COMPLETED
    assert status.frames_enqueued == 100
    assert status.frames_written == 100
    assert status.output_path is not None
    assert status.output_path.exists()

    # O buffer visual preserva somente as cinco amostras mais recentes.
    live_snapshot = acquisition.snapshot()
    assert live_snapshot.channels[0].sample_count == 5
    assert live_snapshot.channels[0].values[0] == pytest.approx(96.0)
    assert live_snapshot.channels[0].values[-1] == pytest.approx(100.0)

    # O HDF5 preserva todos os cem frames, independentemente da janela visual.
    with h5py.File(status.output_path, "r") as h5:
        sequence_ids = cast(h5py.Dataset, h5["frames/sequence_id"])
        timestamp_us = cast(h5py.Dataset, h5["frames/timestamp_us"])
        raw_values = cast(h5py.Dataset, h5["frames/raw_values"])

        assert sequence_ids.shape == (100,)
        assert timestamp_us.shape == (100,)
        assert raw_values.shape == (100, 3)
        assert int(sequence_ids[0]) == 1
        assert int(sequence_ids[-1]) == 100
        assert float(raw_values[0, 0]) == pytest.approx(1.0)
        assert float(raw_values[-1, 0]) == pytest.approx(100.0)

    repository = SessionRepository(tmp_path)
    listed = repository.list_sessions()
    assert len(listed) == 1
    assert listed[0].frames_received == 100
    assert listed[0].invalid_frames == 1
    assert listed[0].end_reason == "test_completed"

    # A abertura para visualização carrega somente a última janela, mas mantém
    # nos metadados a contagem integral da sessão.
    loaded = repository.load(listed[0].session_id)
    assert loaded.summary.frames_received == 100
    assert loaded.snapshot.frames_received == 100
    assert loaded.snapshot.channels[0].sample_count == 5
    assert loaded.snapshot.channels[0].values[-1] == pytest.approx(100.0)
    assert loaded.active_filters == {}

    csv_path = repository.export_csv(listed[0].session_id, chunk_size=13)
    with csv_path.open(newline="", encoding="utf-8") as fp:
        rows = list(csv.reader(fp))
    assert len(rows) == 101
    assert rows[0][:3] == ["sample_index", "sequence_id", "timestamp_us"]
    assert rows[1][1] == "1"
    assert rows[-1][1] == "100"

    repository.delete(listed[0].session_id)
    assert repository.list_sessions() == []
    assert not status.output_path.exists()


def test_cancel_recording_removes_partial_file(tmp_path):
    session = SessionService().build_session(
        port="TEST",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=10,
        signal_order_text="ecg",
    )
    parser = FrameCsvParser()
    recorder = RecordingService(
        tmp_path,
        queue_capacity=32,
        batch_size=4,
        flush_interval_s=0.05,
    )
    started = recorder.start(session)
    assert started.partial_path is not None

    frame = parser.parse_line("FRAME,1,1000000,10", session).frame
    recorder.enqueue_frame(frame)
    status = recorder.cancel()

    assert status.state is RecordingState.CANCELLED
    assert list(tmp_path.glob("*.partial.h5")) == []
    assert list(tmp_path.glob("*.h5")) == []
