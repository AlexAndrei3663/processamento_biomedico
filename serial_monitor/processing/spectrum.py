from __future__ import annotations

import numpy as np

from serial_monitor.domain.models import SpectrumSnapshot


def _empty_spectrum() -> SpectrumSnapshot:
    empty = np.array([], dtype=float)
    return SpectrumSnapshot(
        frequencies_hz=empty,
        magnitudes=empty,
        peak_frequency_hz=None,
        peak_magnitude=None,
        resolution_hz=None,
    )


def calculate_single_sided_spectrum(
    values: np.ndarray,
    sample_rate_hz: float,
    *,
    remove_mean: bool = True,
    apply_window: bool = True,
) -> SpectrumSnapshot:
    """Calcula o espectro unilateral de magnitude de uma janela temporal.

    A função é deliberadamente independente da GUI. Ela recebe uma janela de
    amostras e retorna os vetores frequência x magnitude prontos para plotagem.
    Para janelas muito curtas ou taxa inválida, retorna um espectro vazio.
    """
    data = np.asarray(values, dtype=float)
    if data.size < 2 or sample_rate_hz <= 0:
        return _empty_spectrum()

    # Evita que NaN/inf contaminem todo o gráfico de espectro.
    data = data[np.isfinite(data)]
    if data.size < 2:
        return _empty_spectrum()

    if remove_mean:
        data = data - float(np.mean(data))

    n = data.size
    if apply_window and n > 2:
        window = np.hanning(n)
        coherent_gain = float(np.sum(window) / n)
        if coherent_gain <= 0:
            coherent_gain = 1.0
        data_for_fft = data * window
    else:
        coherent_gain = 1.0
        data_for_fft = data

    spectrum = np.fft.rfft(data_for_fft)
    frequencies = np.fft.rfftfreq(n, d=1.0 / sample_rate_hz)

    magnitudes = np.abs(spectrum) / (n * coherent_gain)
    if magnitudes.size > 2:
        magnitudes[1:-1] *= 2.0

    resolution_hz = float(sample_rate_hz / n)

    peak_frequency_hz: float | None = None
    peak_magnitude: float | None = None
    if magnitudes.size:
        search_start = 1 if magnitudes.size > 1 else 0
        peak_index_relative = int(np.argmax(magnitudes[search_start:]))
        peak_index = peak_index_relative + search_start
        peak_frequency_hz = float(frequencies[peak_index])
        peak_magnitude = float(magnitudes[peak_index])

    return SpectrumSnapshot(
        frequencies_hz=frequencies,
        magnitudes=magnitudes,
        peak_frequency_hz=peak_frequency_hz,
        peak_magnitude=peak_magnitude,
        resolution_hz=resolution_hz,
    )
