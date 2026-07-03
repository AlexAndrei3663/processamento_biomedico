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


def convert_spectrum_to_dbfs(
    spectrum: SpectrumSnapshot,
    reference_amplitude: float,
    *,
    floor_db: float = -160.0,
) -> SpectrumSnapshot:
    """Converte somente a escala de exibição de magnitude para dBFS.

    A FFT não é recalculada. ``reference_amplitude`` representa a amplitude
    de escala completa positiva do ADC na unidade base exibida (counts ou V).
    Valores nulos são limitados por ``floor_db`` para evitar ``-inf``.
    """

    if reference_amplitude <= 0:
        raise ValueError("A referência de dBFS deve ser maior que zero.")

    magnitudes = np.asarray(spectrum.magnitudes, dtype=float)
    if magnitudes.size == 0:
        return _empty_spectrum()

    safe_ratio = np.maximum(
        np.abs(magnitudes) / float(reference_amplitude),
        np.finfo(float).tiny,
    )
    dbfs = 20.0 * np.log10(safe_ratio)
    dbfs = np.maximum(dbfs, float(floor_db))

    peak_magnitude: float | None = None
    if spectrum.peak_magnitude is not None:
        peak_ratio = max(
            abs(float(spectrum.peak_magnitude)) / float(reference_amplitude),
            np.finfo(float).tiny,
        )
        peak_magnitude = max(20.0 * float(np.log10(peak_ratio)), float(floor_db))

    return SpectrumSnapshot(
        frequencies_hz=np.asarray(spectrum.frequencies_hz, dtype=float),
        magnitudes=dbfs,
        peak_frequency_hz=spectrum.peak_frequency_hz,
        peak_magnitude=peak_magnitude,
        resolution_hz=spectrum.resolution_hz,
    )
