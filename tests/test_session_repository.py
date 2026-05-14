from __future__ import annotations

import pytest

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.infrastructure.storage.session_repository import SessionRepository


def test_session_repository_saves_lists_and_loads(tmp_path):
    session = SessionService().build_session(
        port="TEST",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=100,
        signal_order_text="ecg,ppg,oximetria",
    )
    parser = FrameCsvParser()
    acquisition = LiveAcquisitionService()
    acquisition.configure(session)

    for line in (
        "FRAME,1,1000,0.52,0.81,97",
        "FRAME,2,1001,0.55,0.83,98",
        "FRAME,3,1002,0.58,0.84,98",
    ):
        acquisition.ingest_frame(parser.parse_line(line, session).frame)

    repository = SessionRepository(tmp_path)
    saved = repository.save(
        session=session,
        snapshot=acquisition.snapshot(),
        active_filters={0: ["baseline"], 1: ["lowpass"]},
    )

    assert saved.frames_received == 3
    assert saved.channel_count == 3
    assert saved.metadata_path.exists()
    assert saved.data_path.exists()

    listed = repository.list_sessions()
    assert len(listed) == 1
    assert listed[0].session_id == saved.session_id

    loaded = repository.load(saved.session_id)
    assert loaded.session.channel_count == 3
    assert loaded.snapshot.frames_received == 3
    assert loaded.snapshot.channels[0].values[-1] == pytest.approx(0.58)
    assert loaded.snapshot.channels[2].values[-1] == 98
    assert loaded.active_filters[0] == ["baseline"]
    assert loaded.active_filters[1] == ["lowpass"]
