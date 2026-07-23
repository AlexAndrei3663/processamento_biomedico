import pytest

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.processing.ring_buffer import RingBuffer


def build_session(window_size: int = 20):
    return SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=window_size,
        signal_order_text="ecg,ppg",
    )


def build_frame(parser, session, sequence, timestamp_us, value0=0.1, value1=0.2):
    return parser.parse_line(
        f"FRAME,{sequence},{timestamp_us},{value0},{value1}",
        session,
    ).frame


def test_append_batch_preserves_order_across_wrap():
    channel = build_session(window_size=3).channels[0]
    buffer = RingBuffer(channel, capacity=3)
    buffer.append_batch([1.0, 2.0], [1_000_000, 1_001_000], [1, 2])
    buffer.append_batch([3.0, 4.0], [1_002_000, 1_003_000], [3, 4])

    snapshot = buffer.snapshot()
    assert snapshot.values.tolist() == [2.0, 3.0, 4.0]
    assert snapshot.sequence_ids.tolist() == [2, 3, 4]
    assert snapshot.x_seconds.tolist() == pytest.approx([0.001, 0.002, 0.003])


def test_append_batch_larger_than_capacity_keeps_latest_samples():
    channel = build_session(window_size=3).channels[0]
    buffer = RingBuffer(channel, capacity=3)
    buffer.append_batch(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [10_000, 20_000, 30_000, 40_000, 50_000],
        [1, 2, 3, 4, 5],
    )

    snapshot = buffer.snapshot()
    assert snapshot.values.tolist() == [3.0, 4.0, 5.0]
    assert snapshot.timestamps_us.tolist() == [30_000, 40_000, 50_000]
    assert snapshot.sequence_ids.tolist() == [3, 4, 5]
    assert snapshot.x_seconds.tolist() == pytest.approx([0.02, 0.03, 0.04])


def test_ingest_frames_returns_only_accepted_frames():
    session = build_session(window_size=10)
    parser = FrameCsvParser()
    service = LiveAcquisitionService()
    service.configure(session)

    frames = (
        build_frame(parser, session, 1, 1_000_000, 0.1, 0.2),
        build_frame(parser, session, 2, 1_001_000, 0.3, 0.4),
        build_frame(parser, session, 2, 1_002_000, 9.0, 9.0),
        build_frame(parser, session, 3, 1_003_000, 0.5, 0.6),
    )

    accepted = service.ingest_frames(frames)
    snapshot = service.snapshot()

    assert [item.sequence_id for item in accepted] == [1, 2, 3]
    assert snapshot.channels[0].values.tolist() == pytest.approx([0.1, 0.3, 0.5])
    assert snapshot.channels[1].values.tolist() == pytest.approx([0.2, 0.4, 0.6])
    assert snapshot.communication.valid_frames == 3
    assert snapshot.communication.duplicate_frames == 1
