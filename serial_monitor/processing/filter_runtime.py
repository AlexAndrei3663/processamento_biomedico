from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import numpy as np
from scipy import signal

from serial_monitor.processing.filter_config import FilterParameters

REAL_FILTER_IDS = frozenset(
    {
        "baseline",
        "dc_remove",
        "highpass",
        "notch_60hz",
        "lowpass",
        "moving_average",
        "envelope",
    }
)
VIRTUAL_FILTER_IDS = frozenset({"bandpass"})
FILTER_ORDER = (
    "baseline",
    "dc_remove",
    "highpass",
    "notch_60hz",
    "lowpass",
    "moving_average",
    "envelope",
)
DISPLAY_FILTER_ORDER = (
    "baseline",
    "dc_remove",
    "highpass",
    "bandpass",
    "notch_60hz",
    "lowpass",
    "moving_average",
    "envelope",
)


def expand_filter_ids(filter_ids: Iterable[str]) -> set[str]:
    """Converte filtros virtuais em filtros reais executáveis."""
    expanded: set[str] = set()
    for filter_id in filter_ids:
        if filter_id == "bandpass":
            expanded.update(("highpass", "lowpass"))
        elif filter_id in REAL_FILTER_IDS:
            expanded.add(filter_id)
    return expanded


def _as_float_array(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=float)


def _safe_sos_filter(values: np.ndarray, sos: np.ndarray) -> np.ndarray:
    if values.size < 12:
        return values.copy()
    try:
        return signal.sosfiltfilt(sos, values)
    except ValueError:
        return values.copy()


def _key(value: float) -> float:
    return round(float(value), 9)


@lru_cache(maxsize=256)
def _cached_butter_sos(
    btype: str,
    order: int,
    sample_rate_hz: float,
    cutoff_hz: float,
) -> np.ndarray:
    sos = np.asarray(
        signal.butter(
            int(order),
            float(cutoff_hz),
            btype=btype,
            fs=float(sample_rate_hz),
            output="sos",
        ),
        dtype=float,
    )
    return sos


@lru_cache(maxsize=64)
def _cached_notch_ba(
    sample_rate_hz: float,
    frequency_hz: float,
    q: float,
) -> tuple[np.ndarray, np.ndarray]:
    b, a = signal.iirnotch(
        w0=float(frequency_hz),
        Q=float(q),
        fs=float(sample_rate_hz),
    )
    b = np.asarray(b, dtype=float)
    a = np.asarray(a, dtype=float)
    return b, a


def coefficient_cache_info() -> dict[str, object]:
    return {
        "butter": _cached_butter_sos.cache_info(),
        "notch": _cached_notch_ba.cache_info(),
    }


def clear_coefficient_cache() -> None:
    _cached_butter_sos.cache_clear()
    _cached_notch_ba.cache_clear()


def apply_filter(
    filter_id: str,
    values: np.ndarray,
    sample_rate_hz: float,
    parameters: FilterParameters,
) -> np.ndarray:
    values = _as_float_array(values)
    parameters = parameters.validated(sample_rate_hz)

    if filter_id == "dc_remove":
        if values.size == 0:
            return values.copy()
        return values - float(np.mean(values))

    if filter_id == "baseline":
        cutoff = min(0.5, parameters.lowpass_cutoff_hz * 0.5)
        if not 0 < cutoff < sample_rate_hz / 2.0:
            return values.copy()
        sos = _cached_butter_sos(
            "highpass", 2, _key(sample_rate_hz), _key(cutoff)
        )
        return _safe_sos_filter(values, sos)

    if filter_id == "highpass":
        sos = _cached_butter_sos(
            "highpass",
            parameters.butterworth_order,
            _key(sample_rate_hz),
            _key(parameters.highpass_cutoff_hz),
        )
        return _safe_sos_filter(values, sos)

    if filter_id == "lowpass":
        sos = _cached_butter_sos(
            "lowpass",
            parameters.butterworth_order,
            _key(sample_rate_hz),
            _key(parameters.lowpass_cutoff_hz),
        )
        return _safe_sos_filter(values, sos)

    if filter_id == "notch_60hz":
        frequency = parameters.notch_frequency_hz
        if values.size < 24 or frequency >= sample_rate_hz / 2.0:
            return values.copy()
        b, a = _cached_notch_ba(
            _key(sample_rate_hz),
            _key(frequency),
            _key(parameters.notch_q),
        )
        try:
            return signal.filtfilt(b, a, values)
        except ValueError:
            return values.copy()

    if filter_id == "moving_average":
        if values.size < 3:
            return values.copy()
        window = int(
            max(
                3,
                min(
                    values.size,
                    round(sample_rate_hz * parameters.moving_average_ms / 1000.0),
                ),
            )
        )
        if window % 2 == 0:
            window += 1
        if window > values.size:
            window = values.size if values.size % 2 == 1 else values.size - 1
        if window < 3:
            return values.copy()
        kernel = np.ones(window, dtype=float) / window
        return np.convolve(values, kernel, mode="same")

    if filter_id == "envelope":
        rectified = np.abs(values)
        return apply_filter(
            "moving_average", rectified, sample_rate_hz, parameters
        )

    raise ValueError(f"Filtro executável desconhecido: {filter_id}")
