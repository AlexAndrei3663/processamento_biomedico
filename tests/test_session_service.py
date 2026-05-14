from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import SignalType


def test_build_session_from_signal_order():
    session = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=500,
        signal_order_text="ecg, ppg, oximetria",
    )

    assert session.channel_count == 3
    assert session.signal_order == [SignalType.ECG, SignalType.PPG, SignalType.OXIMETRIA]
    assert session.channels[0].index == 0
    assert session.channels[1].index == 1
    assert session.channels[2].index == 2
    assert session.channels[0].channel_id == "ch0_ecg"
