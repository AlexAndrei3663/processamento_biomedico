import pytest

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser


def build_session():
    return SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=3,
        signal_order_text="ecg,ppg",
    )


def test_live_acquisition_distributes_frames_to_channel_buffers():
    session = build_session()
    parser = FrameCsvParser()
    service = LiveAcquisitionService()
    service.configure(session)

    service.ingest_frame(parser.parse_line("FRAME,1,1000,0.1,0.2", session).frame)
    service.ingest_frame(parser.parse_line("FRAME,2,1001,0.3,0.4", session).frame)

    snapshot = service.snapshot()

    assert snapshot.frames_received == 2
    assert snapshot.sequence_gaps == 0
    assert snapshot.channels[0].values.tolist() == [pytest.approx(0.1), pytest.approx(0.3)]
    assert snapshot.channels[1].values.tolist() == [pytest.approx(0.2), pytest.approx(0.4)]
    assert snapshot.channels[0].last_value == pytest.approx(0.3)
    assert snapshot.channels[1].last_value == pytest.approx(0.4)


def test_live_acquisition_detects_sequence_gap():
    session = build_session()
    parser = FrameCsvParser()
    service = LiveAcquisitionService()
    service.configure(session)

    service.ingest_frame(parser.parse_line("FRAME,1,1000,0.1,0.2", session).frame)
    service.ingest_frame(parser.parse_line("FRAME,3,1002,0.3,0.4", session).frame)

    snapshot = service.snapshot()

    assert snapshot.frames_received == 2
    assert snapshot.sequence_gaps == 1
    assert snapshot.last_sequence_id == 3
