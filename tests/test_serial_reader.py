from serial_monitor.infrastructure.serial.protocol import FrameProtocolError
from serial_monitor.infrastructure.serial.serial_reader import SerialReader


class BufferConfigurablePort:
    def __init__(self) -> None:
        self.rx_size = None

    def set_buffer_size(self, *, rx_size: int) -> None:
        self.rx_size = rx_size


def test_decode_line_accepts_firmware_ascii_frame():
    assert SerialReader._decode_line(b"FRAME,1,1000,1,2,3,4\r\n") == (
        "FRAME,1,1000,1,2,3,4\r\n"
    )


def test_decode_line_rejects_invalid_utf8():
    try:
        SerialReader._decode_line(b"FRAME,1,1000,1,2,3,\xff\n")
    except FrameProtocolError as exc:
        assert exc.category == "encoding"
    else:
        raise AssertionError("Linha inválida deveria ser rejeitada.")


def test_decode_line_rejects_unterminated_oversized_payload():
    try:
        SerialReader._decode_line(b"X" * SerialReader.MAX_LINE_BYTES)
    except FrameProtocolError as exc:
        assert exc.category == "line_length"
    else:
        raise AssertionError("Linha longa deveria ser rejeitada.")


def test_input_buffer_is_expanded_when_supported():
    port = BufferConfigurablePort()

    assert SerialReader._configure_input_buffer(port)
    assert port.rx_size == SerialReader.INPUT_BUFFER_BYTES


def test_protocol_summary_groups_categories():
    summary = SerialReader._format_protocol_summary(
        {"encoding": 2, "field_count": 3},
        "falha final",
    )

    assert summary == "encoding=2, field_count=3. Último erro: falha final"
