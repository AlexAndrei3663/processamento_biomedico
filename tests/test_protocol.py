import pytest

from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser, FrameProtocolError


def build_session(order="ecg,ppg,oximetria"):
    return SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=100,
        signal_order_text=order,
    )


def test_parse_valid_frame_assigns_values_by_channel_index():
    session = build_session()
    parsed = FrameCsvParser().parse_line("FRAME,1,1000,0.52,0.81,97", session)

    assert parsed.frame.sequence_id == 1
    assert parsed.frame.timestamp_ms == 1000
    assert parsed.frame.values_in_order == [pytest.approx(0.52), pytest.approx(0.81), pytest.approx(97.0)]
    assert parsed.frame.value_for_channel(0) == pytest.approx(0.52)
    assert parsed.frame.value_for_channel(1) == pytest.approx(0.81)
    assert parsed.frame.value_for_channel(2) == pytest.approx(97.0)


def test_parser_rejects_wrong_channel_count():
    session = build_session()

    try:
        FrameCsvParser().parse_line("FRAME,1,1000,0.52,0.81", session)
    except FrameProtocolError as exc:
        assert "Quantidade de campos inválida" in str(exc)
    else:
        raise AssertionError("Parser deveria rejeitar frame com quantidade incorreta de campos.")


def test_parser_supports_repeated_signal_types_by_channel_index():
    session = build_session("ecg,ecg,outro")
    parsed = FrameCsvParser().parse_line("FRAME,3,2000,1.0,2.0,3.0", session)

    assert parsed.frame.value_for_channel(0) == pytest.approx(1.0)
    assert parsed.frame.value_for_channel(1) == pytest.approx(2.0)
    assert parsed.frame.value_for_channel(2) == pytest.approx(3.0)
