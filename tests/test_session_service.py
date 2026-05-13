from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import ProtocolMode, SignalType


def test_build_session_from_signal_order() -> None:
    service = SessionService()
    session = service.build_session(
        port="/dev/ttyUSB0",
        baudrate=230400,
        base_sample_rate_hz=500,
        window_size=2048,
        signal_order_text="ecg, emg, outro",
    )

    assert session.protocol_mode == ProtocolMode.FRAME_CSV
    assert session.channel_count == 3
    assert session.signal_order == [SignalType.ECG, SignalType.EMG, SignalType.OUTRO]
    assert session.channels[1].display_name == "EMG"
    assert session.channels[1].default_filters == ["highpass", "notch_60hz", "envelope"]
