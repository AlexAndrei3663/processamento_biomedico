import pytest

from serial_monitor.application.session_service import SessionService
from serial_monitor.processing.ring_buffer import RingBuffer


def build_channel():
    session = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=3,
        signal_order_text="ecg",
    )
    return session.channels[0]


def test_ring_buffer_keeps_latest_samples_in_chronological_order():
    buffer = RingBuffer(build_channel(), capacity=3)
    buffer.append(1.0, timestamp_us=1_000_000, sequence_id=11)
    buffer.append(2.0, timestamp_us=1_001_000, sequence_id=12)
    buffer.append(3.0, timestamp_us=1_002_000, sequence_id=13)
    buffer.append(4.0, timestamp_us=1_003_000, sequence_id=14)

    snapshot = buffer.snapshot()

    assert snapshot.sample_count == 3
    assert snapshot.values.tolist() == [2.0, 3.0, 4.0]
    assert snapshot.timestamps_us.tolist() == [1_001_000, 1_002_000, 1_003_000]
    assert snapshot.sequence_ids.tolist() == [12, 13, 14]
    assert snapshot.x_seconds.tolist() == pytest.approx([0.0, 0.001, 0.002])
