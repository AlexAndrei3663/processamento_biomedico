import pytest

from serial_monitor.application.communication_monitor import (
    UINT32_MAX,
    UINT64_MAX,
    estimate_timestamp_us,
)
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import (
    FrameCsvParser,
    FrameProtocolError,
    format_frame_csv,
)


def build_session(order="ecg,ppg,oximetria"):
    return SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=100,
        signal_order_text=order,
    )


def test_parse_valid_frame_assigns_temporal_fields_and_channels():
    session = build_session()
    parsed = FrameCsvParser().parse_line(
        "FRAME,20,1000000,0.52,0.81,97",
        session,
    )

    assert parsed.frame.sequence_id == 20
    assert parsed.frame.timestamp_us == 1_000_000
    assert parsed.frame.values_in_order == [
        pytest.approx(0.52),
        pytest.approx(0.81),
        pytest.approx(97.0),
    ]
    assert parsed.frame.value_for_channel(0) == pytest.approx(0.52)
    assert parsed.frame.value_for_channel(1) == pytest.approx(0.81)
    assert parsed.frame.value_for_channel(2) == pytest.approx(97.0)


def test_parser_rejects_wrong_channel_count():
    session = build_session()

    with pytest.raises(FrameProtocolError, match="Quantidade de campos inválida"):
        FrameCsvParser().parse_line("FRAME,1,1000000,0.52,0.81", session)


def test_parser_supports_repeated_signal_types_by_channel_index():
    session = build_session("ecg,ecg,outro")
    parsed = FrameCsvParser().parse_line(
        "FRAME,7,2000000,1.0,2.0,3.0",
        session,
    )

    assert parsed.frame.value_for_channel(0) == pytest.approx(1.0)
    assert parsed.frame.value_for_channel(1) == pytest.approx(2.0)
    assert parsed.frame.value_for_channel(2) == pytest.approx(3.0)


@pytest.mark.parametrize(
    "line,expected_message",
    [
        ("FRAME,-1,0,1,2,3", "sequence_id fora da faixa"),
        (f"FRAME,{UINT32_MAX + 1},0,1,2,3", "sequence_id fora da faixa"),
        (f"FRAME,0,{UINT64_MAX + 1},1,2,3", "timestamp_us fora da faixa"),
        ("FRAME,0,0,nan,2,3", "NaN ou infinitos"),
        ("FRAME,0,0,inf,2,3", "NaN ou infinitos"),
    ],
)
def test_parser_rejects_values_outside_contract(line, expected_message):
    with pytest.raises(FrameProtocolError, match=expected_message):
        FrameCsvParser().parse_line(line, build_session())


def test_format_frame_csv_uses_single_sequence_contract():
    line = format_frame_csv(5, 1_234_567, [1.0, 2.5])
    assert line == "FRAME,5,1234567,1.0,2.5"


def test_timestamp_can_be_estimated_from_sequence_on_ideal_grid():
    assert estimate_timestamp_us(
        sequence_id=15,
        origin_sequence_id=10,
        origin_timestamp_us=1_000_000,
        sample_rate_hz=1000,
    ) == 1_005_000


def test_timestamp_estimation_handles_uint32_wrap():
    assert estimate_timestamp_us(
        sequence_id=1,
        origin_sequence_id=UINT32_MAX - 1,
        origin_timestamp_us=1_000_000,
        sample_rate_hz=1000,
    ) == 1_003_000
