from __future__ import annotations

import json

import pytest

from serial_monitor.app.tcc_profile import TCC_PROFILE, load_tcc_profile
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import SignalType


def test_tcc_profile_has_fixed_four_channel_contract():
    assert TCC_PROFILE.base_sample_rate_hz == 1000
    assert TCC_PROFILE.baudrate == 115200
    assert TCC_PROFILE.window_size == 10_000
    assert [channel.index for channel in TCC_PROFILE.channels] == [0, 1, 2, 3]
    assert [channel.signal_type for channel in TCC_PROFILE.channels] == [
        SignalType.ECG,
        SignalType.ECG,
        SignalType.PPG,
        SignalType.OUTRO,
    ]
    assert [channel.display_name for channel in TCC_PROFILE.channels] == [
        "ECG 1",
        "ECG 2",
        "PPG",
        "Reserva",
    ]


def test_tcc_profile_builds_session_with_unique_display_names():
    session = TCC_PROFILE.build_session(SessionService(), port="TEST")
    assert session.port == "TEST"
    assert session.channel_count == 4
    assert session.base_sample_rate_hz == 1000
    assert session.window_size == 10_000
    assert [channel.display_name for channel in session.channels] == [
        "ECG 1",
        "ECG 2",
        "PPG",
        "Reserva",
    ]
    assert [channel.conversion_enabled for channel in session.channels] == [
        True,
        True,
        True,
        False,
    ]


def test_profile_metadata_is_json_serializable_and_firmware_ready():
    metadata = TCC_PROFILE.source_metadata()
    serialized = json.dumps(metadata, sort_keys=True)
    assert "blackpill_ads1256-display" in serialized
    assert metadata["expected_channel_count"] == 4
    assert metadata["protocol"]["supports_future_binary_transport"] is True
    assert metadata["channel_map"][3]["physical_input"] == "AIN6-AIN7"


def test_profile_preserves_runtime_selected_port_in_preset():
    preset = TCC_PROFILE.to_preset(port="/dev/ttyACM0")
    assert preset.port == "/dev/ttyACM0"
    assert preset.signal_order_text == "ecg,ecg,ppg,outro"
    assert preset.window_size == 10_000


def test_profile_rejects_empty_port():
    with pytest.raises(ValueError, match="porta serial"):
        TCC_PROFILE.build_session(SessionService(), port="")


def test_loader_rejects_protocol_channel_mismatch(tmp_path):
    payload = {
        "profile_version": 1,
        "name": "inválido",
        "baudrate": 115200,
        "base_sample_rate_hz": 1000,
        "window_seconds": 10,
        "adc": {"reference_voltage_v": 2.5, "gain": 1},
        "protocol": {"expected_channel_count": 3},
        "firmware": {},
        "channels": [
            {
                "index": index,
                "signal_type": signal,
                "display_name": name,
                "physical_input": "",
                "base_mode": "raw",
            }
            for index, signal, name in (
                (0, "ecg", "ECG 1"),
                (1, "ecg", "ECG 2"),
                (2, "ppg", "PPG"),
                (3, "outro", "Reserva"),
            )
        ],
    }
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="quantidade de canais"):
        load_tcc_profile(path)
