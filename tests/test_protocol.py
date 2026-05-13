import pytest

from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import SignalType
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser, FrameProtocolError


session = SessionService().build_session(
    port="COM3",
    baudrate=115200,
    base_sample_rate_hz=1000,
    window_size=1000,
    signal_order_text="ecg,ppg,oximetria",
)


def test_parse_valid_frame() -> None:
    parser = FrameCsvParser()
    parsed = parser.parse_line("FRAME,10,123456,1.5,2.5,97", session)

    assert parsed.frame.sequence_id == 10
    assert parsed.frame.timestamp_ms == 123456
    assert parsed.frame.values_in_order == [pytest.approx(1.5), pytest.approx(2.5), pytest.approx(97.0)]
    assert parsed.frame.values_by_signal[SignalType.ECG] == pytest.approx(1.5)
    assert parsed.frame.values_by_signal[SignalType.PPG] == pytest.approx(2.5)
    assert parsed.frame.values_by_signal[SignalType.OXIMETRIA] == pytest.approx(97.0)


def test_reject_frame_with_wrong_field_count() -> None:
    parser = FrameCsvParser()

    with pytest.raises(FrameProtocolError):
        parser.parse_line("FRAME,10,123456,1.5,2.5", session)
