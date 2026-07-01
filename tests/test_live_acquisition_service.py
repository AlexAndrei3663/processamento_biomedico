import pytest

from serial_monitor.application.communication_monitor import UINT32_MAX
from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser


def build_session(window_size=20):
    return SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=window_size,
        signal_order_text="ecg,ppg",
    )


def frame(parser, session, sequence, timestamp_us, value0=0.1, value1=0.2):
    return parser.parse_line(
        f"FRAME,{sequence},{timestamp_us},{value0},{value1}",
        session,
    ).frame


def test_live_acquisition_distributes_accepted_frames_to_channel_buffers():
    session = build_session()
    parser = FrameCsvParser()
    service = LiveAcquisitionService()
    service.configure(session)

    assert service.ingest_frame(frame(parser, session, 1, 1_000_000, 0.1, 0.2))
    assert service.ingest_frame(frame(parser, session, 2, 1_001_000, 0.3, 0.4))

    snapshot = service.snapshot()

    assert snapshot.frames_received == 2
    assert snapshot.communication.gap_events == 0
    assert snapshot.channels[0].values.tolist() == [pytest.approx(0.1), pytest.approx(0.3)]
    assert snapshot.channels[1].values.tolist() == [pytest.approx(0.2), pytest.approx(0.4)]
    assert snapshot.channels[0].sequence_ids.tolist() == [1, 2]
    assert snapshot.last_sequence_id == 2
    assert snapshot.last_timestamp_us == 1_001_000


def test_sequence_diagnostics_distinguish_gap_missing_duplicate_and_out_of_order():
    session = build_session()
    parser = FrameCsvParser()
    service = LiveAcquisitionService()
    service.configure(session)

    sequence = [1, 2, 10, 10, 9, 11]
    accepted = []
    for index, value in enumerate(sequence):
        accepted.append(
            service.ingest_frame(
                frame(parser, session, value, 1_000_000 + index * 1_000)
            )
        )

    assert accepted == [True, True, True, False, False, True]
    stats = service.snapshot().communication
    assert stats.valid_frames == 4
    assert stats.sequence.gap_events == 1
    assert stats.sequence.missing_items == 7
    assert stats.sequence.duplicate_items == 1
    assert stats.sequence.out_of_order_items == 1


def test_timestamp_must_be_strictly_increasing_and_rejected_frame_does_not_advance_sequence():
    session = build_session()
    parser = FrameCsvParser()
    service = LiveAcquisitionService()
    service.configure(session)

    assert service.ingest_frame(frame(parser, session, 1, 1_000_000))
    assert not service.ingest_frame(frame(parser, session, 2, 999_999))
    assert service.ingest_frame(frame(parser, session, 2, 1_001_000))

    snapshot = service.snapshot()
    assert snapshot.communication.timestamp_regressions == 1
    assert snapshot.frames_received == 2
    assert snapshot.last_sequence_id == 2
    assert snapshot.channels[0].sample_count == 2


def test_uint32_sequence_wrap_is_in_order():
    session = build_session()
    parser = FrameCsvParser()
    service = LiveAcquisitionService()
    service.configure(session)

    for index, value in enumerate((UINT32_MAX - 1, UINT32_MAX, 0, 1)):
        assert service.ingest_frame(
            frame(parser, session, value, 1_000_000 + index * 1_000)
        )

    stats = service.snapshot().communication
    assert stats.valid_frames == 4
    assert stats.sequence.gap_events == 0
    assert stats.sequence.out_of_order_items == 0


def test_invalid_and_checksum_errors_are_counted_separately():
    service = LiveAcquisitionService()
    service.configure(build_session())

    service.record_invalid_frame()
    service.record_checksum_error()

    stats = service.snapshot().communication
    assert stats.invalid_frames == 2
    assert stats.checksum_errors == 1
