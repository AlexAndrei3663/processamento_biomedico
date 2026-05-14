from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from serial_monitor.domain.models import SignalChannelConfig, SpectrumSnapshot


class SignalPlotWidget(QWidget):
    """Gráfico de um canal no domínio do tempo ou da frequência.

    A classe recebe vetores prontos para renderização. Ela não conhece serial,
    parser, buffers, filtros ou FFT. Para uso em Raspberry Pi, limita a
    quantidade máxima de pontos enviados ao PyQtGraph sem alterar os buffers.
    """

    def __init__(self, channel: SignalChannelConfig, max_plot_points: int = 5000) -> None:
        super().__init__()
        self.channel = channel
        self.max_plot_points = max(100, int(max_plot_points))

        layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget(title=f"{channel.display_name} - tempo")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(auto=True, mode="peak")

        self.curve = self.plot_widget.plot([], [])
        layout.addWidget(self.plot_widget)
        self.set_time_axes()

    def set_max_plot_points(self, max_plot_points: int) -> None:
        self.max_plot_points = max(100, int(max_plot_points))

    def set_time_axes(self) -> None:
        self.plot_widget.setLabel("bottom", "Tempo", units="s")
        self.plot_widget.setLabel("left", self.channel.display_name, units=self.channel.unit)

    def set_spectrum_axes(self) -> None:
        self.plot_widget.setLabel("bottom", "Frequência", units="Hz")
        self.plot_widget.setLabel("left", "Magnitude", units=self.channel.unit)

    def set_time_series(self, x_seconds: np.ndarray, values: np.ndarray, title_suffix: str = "tempo") -> None:
        if values.size == 0 or x_seconds.size == 0:
            self.clear()
            return
        if len(x_seconds) != len(values):
            return

        x_plot, y_plot = self._decimate(x_seconds, values)
        self.set_time_axes()
        self.plot_widget.setTitle(f"{self.channel.display_name} - {title_suffix}")
        self.curve.setData(x_plot, y_plot)

    def set_spectrum(self, spectrum: SpectrumSnapshot, title_suffix: str = "espectro") -> None:
        if spectrum.frequencies_hz.size == 0 or spectrum.magnitudes.size == 0:
            self.clear()
            return
        if len(spectrum.frequencies_hz) != len(spectrum.magnitudes):
            return

        x_plot, y_plot = self._decimate(spectrum.frequencies_hz, spectrum.magnitudes)
        self.set_spectrum_axes()
        self.plot_widget.setTitle(f"{self.channel.display_name} - {title_suffix}")
        self.curve.setData(x_plot, y_plot)

    def set_series(self, x_seconds: np.ndarray, values: np.ndarray, title_suffix: str = "tempo") -> None:
        """Compatibilidade interna com chamadas existentes."""
        self.set_time_series(x_seconds, values, title_suffix)

    def clear(self) -> None:
        self.curve.setData(np.array([], dtype=float), np.array([], dtype=float))

    def _decimate(self, x_values: np.ndarray, y_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if len(y_values) <= self.max_plot_points:
            return x_values, y_values
        step = int(np.ceil(len(y_values) / self.max_plot_points))
        return x_values[::step], y_values[::step]
