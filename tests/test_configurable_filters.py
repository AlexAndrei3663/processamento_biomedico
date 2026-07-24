from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from serial_monitor.processing.filter_config import FilterParameters
from serial_monitor.processing.filter_pipeline import ProcessingService
from serial_monitor.processing.filter_runtime import (
    apply_filter,
    clear_coefficient_cache,
    coefficient_cache_info,
    expand_filter_ids,
)


def test_bandpass_is_highpass_plus_lowpass() -> None:
    assert expand_filter_ids(["bandpass"]) == {"highpass", "lowpass"}


def test_processing_service_expands_bandpass() -> None:
    channel = SimpleNamespace(index=0, sample_rate_hz=1000.0)
    session = SimpleNamespace(channels=[channel])
    service = ProcessingService()
    service.configure(session)
    service.set_filter_enabled(0, "bandpass", True)
    assert service.active_filters_for(0) == ["highpass", "lowpass"]
    service.set_filter_enabled(0, "bandpass", False)
    assert service.active_filters_for(0) == []


def test_cutoff_validation() -> None:
    parameters = FilterParameters.defaults_for_sample_rate(1000.0)
    updated = parameters.with_value("lowpass_cutoff_hz", 80.0, 1000.0)
    assert updated.lowpass_cutoff_hz == 80.0
    try:
        updated.with_value("highpass_cutoff_hz", 100.0, 1000.0)
    except ValueError:
        pass
    else:
        raise AssertionError("Frequências invertidas deveriam ser rejeitadas.")


def test_lowpass_cutoff_changes_output() -> None:
    fs = 1000.0
    time = np.arange(0.0, 2.0, 1.0 / fs)
    values = np.sin(2.0 * np.pi * 5.0 * time) + np.sin(2.0 * np.pi * 120.0 * time)
    low = FilterParameters(highpass_cutoff_hz=0.5, lowpass_cutoff_hz=20.0)
    high = FilterParameters(highpass_cutoff_hz=0.5, lowpass_cutoff_hz=200.0)
    low_output = apply_filter("lowpass", values, fs, low)
    high_output = apply_filter("lowpass", values, fs, high)
    assert np.std(high_output - low_output) > 0.20


def test_butterworth_coefficients_are_cached() -> None:
    clear_coefficient_cache()
    fs = 1000.0
    values = np.linspace(-1.0, 1.0, 500)
    parameters = FilterParameters.defaults_for_sample_rate(fs)
    apply_filter("lowpass", values, fs, parameters)
    first = coefficient_cache_info()["butter"]
    apply_filter("lowpass", values, fs, parameters)
    second = coefficient_cache_info()["butter"]
    assert second.hits == first.hits + 1
