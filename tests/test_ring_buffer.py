import pytest

from serial_monitor.application.session_service import SessionService
from serial_monitor.processing.ring_buffer import RingBuffer


def test_ring_buffer_snapshot_is_chronological_after_wrap():
    session = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=3,
        signal_order_text="ecg",
    )
    buffer = RingBuffer(session.channels[0], capacity=3)

    buffer.append(1.0, timestamp_ms=1000, sequence_id=1)
    buffer.append(2.0, timestamp_ms=1001, sequence_id=2)
    buffer.append(3.0, timestamp_ms=1002, sequence_id=3)
    buffer.append(4.0, timestamp_ms=1003, sequence_id=4)

    snapshot = buffer.snapshot()

    assert snapshot.sample_count == 3
    assert snapshot.values.tolist() == [pytest.approx(2.0), pytest.approx(3.0), pytest.approx(4.0)]
    assert snapshot.timestamps_ms.tolist() == [1001, 1002, 1003]
    assert snapshot.sequence_ids.tolist() == [2, 3, 4]
    assert snapshot.x_seconds.tolist() == [pytest.approx(0.0), pytest.approx(0.001), pytest.approx(0.002)]
    assert snapshot.last_value == pytest.approx(4.0)
