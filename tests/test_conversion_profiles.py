from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from serial_monitor.application.conversion_service import ConversionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import ConversionModel, SignalType
from serial_monitor.domain.models import (
    ConversionConfig,
    ConversionProfile,
    SignalChannelConfig,
)
from serial_monitor.infrastructure.storage.conversion_profile_repository import (
    ConversionProfileRepository,
)


def write_profiles(path: Path) -> None:
    payload = {
        "version": 1,
        "profiles": {
            "ecg_linear": {
                "version": 1,
                "signal_type": "ecg",
                "model": "linear",
                "input_unit": "count",
                "output_unit": "mV",
                "parameters": {"scale": 0.001, "offset": -1.0},
                "valid_input_range": [0, 4095],
            },
            "generic_identity": {
                "version": 1,
                "signal_type": "*",
                "model": "identity",
                "input_unit": "count",
                "output_unit": "count",
                "parameters": {},
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_repository_loads_and_filters_compatible_profiles(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    write_profiles(path)
    repository = ConversionProfileRepository(path)

    assert [item.profile_id for item in repository.compatible_profiles(SignalType.ECG)] == [
        "ecg_linear",
        "generic_identity",
    ]
    assert [item.profile_id for item in repository.compatible_profiles(SignalType.PPG)] == [
        "generic_identity"
    ]


def test_conversion_is_disabled_by_default() -> None:
    channel = SignalChannelConfig(
        index=0,
        signal_type=SignalType.ECG,
        display_name="ECG",
        unit="count",
        raw_unit="count",
        sample_rate_hz=1000,
    )
    source = np.asarray([1.0, 2.0, 3.0])

    result = ConversionService().convert(source, channel)

    assert result.enabled is False
    np.testing.assert_array_equal(result.values, source)
    assert result.output_unit == "count"


def test_linear_conversion_and_input_range_diagnostic() -> None:
    profile = ConversionProfile(
        profile_id="ecg_linear",
        version=1,
        signal_type=SignalType.ECG,
        model=ConversionModel.LINEAR,
        input_unit="count",
        output_unit="mV",
        parameters={"scale": 0.001, "offset": -1.0},
        valid_input_range=(0.0, 4095.0),
    )
    channel = SignalChannelConfig(
        index=0,
        signal_type=SignalType.ECG,
        display_name="ECG",
        unit="mV",
        raw_unit="count",
        sample_rate_hz=1000,
        conversion=ConversionConfig(enabled=True, profile_id=profile.profile_id),
        conversion_profile=profile,
    )

    result = ConversionService().convert(np.asarray([0.0, 2000.0, 5000.0]), channel)

    np.testing.assert_allclose(result.values, [-1.0, 1.0, 4.0])
    assert result.out_of_input_range == 1
    assert result.profile_id == "ecg_linear"


def test_polynomial_and_lookup_table_models() -> None:
    service = ConversionService()
    polynomial = ConversionProfile(
        profile_id="poly",
        version=1,
        signal_type=None,
        model=ConversionModel.POLYNOMIAL,
        input_unit="count",
        output_unit="u",
        parameters={"coefficients": [1.0, 2.0, 3.0]},
    )
    lookup = ConversionProfile(
        profile_id="table",
        version=1,
        signal_type=None,
        model=ConversionModel.LOOKUP_TABLE,
        input_unit="count",
        output_unit="u",
        parameters={"input": [0.0, 10.0], "output": [0.0, 100.0]},
    )

    def channel(profile: ConversionProfile) -> SignalChannelConfig:
        return SignalChannelConfig(
            index=0,
            signal_type=SignalType.OUTRO,
            display_name="Outro",
            unit="u",
            raw_unit="count",
            sample_rate_hz=100,
            conversion=ConversionConfig(True, profile.profile_id),
            conversion_profile=profile,
        )

    np.testing.assert_allclose(
        service.convert(np.asarray([0.0, 2.0]), channel(polynomial)).values,
        [1.0, 17.0],
    )
    np.testing.assert_allclose(
        service.convert(np.asarray([2.5, 5.0]), channel(lookup)).values,
        [25.0, 50.0],
    )


def test_session_service_builds_ads1256_voltage_snapshot() -> None:
    service = SessionService()

    session = service.build_session(
        port="/dev/ttyUSB0",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=1000,
        signal_order_text="ecg,ppg",
        channel_conversions=[
            {"channel_index": 0, "mode": "voltage"},
            {"channel_index": 1, "mode": "raw"},
        ],
        adc_reference_voltage_v=2.5,
        adc_gain=2,
    )

    assert session.adc.reference_voltage_v == pytest.approx(2.5)
    assert session.adc.gain == 2
    assert session.channels[0].conversion.enabled is True
    assert session.channels[0].unit == "V"
    assert session.channels[0].conversion_profile is not None
    assert session.channels[0].conversion_profile.model is ConversionModel.ADS1256_DIFFERENTIAL
    assert session.channels[1].conversion.enabled is False
    assert session.channels[1].unit == "count"


def test_ads1256_differential_conversion_uses_signed_24_bit_limits() -> None:
    service = SessionService()
    session = service.build_session(
        port="/dev/ttyUSB0",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=1000,
        signal_order_text="ecg",
        channel_conversions=[{"channel_index": 0, "mode": "voltage"}],
        adc_reference_voltage_v=2.5,
        adc_gain=1,
    )

    result = ConversionService().convert(
        np.asarray([-8_388_608.0, 0.0, 8_388_607.0]),
        session.channels[0],
    )

    np.testing.assert_allclose(result.values, [-5.0, 0.0, 5.0])


def test_invalid_global_adc_gain_is_rejected() -> None:
    service = SessionService()
    with pytest.raises(ValueError, match="ganho"):
        service.build_session(
            port="/dev/ttyUSB0",
            baudrate=115200,
            base_sample_rate_hz=1000,
            window_size=1000,
            signal_order_text="ppg",
            channel_conversions=[{"channel_index": 0, "mode": "voltage"}],
            adc_gain=3,
        )


def test_preset_persists_adc_and_channel_base_mode(tmp_path: Path) -> None:
    from serial_monitor.infrastructure.storage.config_repository import ConfigRepository

    repository = ConfigRepository(tmp_path)
    repository.save_preset(
        name="Projeto padrão",
        port="/dev/ttyUSB0",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=1000,
        signal_order_text="ecg,ppg",
        channel_conversions=[
            {"channel_index": 0, "mode": "voltage"},
            {"channel_index": 1, "mode": "raw"},
        ],
        adc_reference_voltage_v=2.5,
        adc_gain=8,
    )

    loaded = repository.load_preset("Projeto padrão")

    assert loaded.channel_conversions[0] == {
        "channel_index": 0,
        "mode": "voltage",
    }
    assert loaded.channel_conversions[1]["mode"] == "raw"
    assert loaded.adc_reference_voltage_v == pytest.approx(2.5)
    assert loaded.adc_gain == 8

