from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from serial_monitor.domain.models import SignalChannelConfig, SpectrumSnapshot


class SignalPlotWidget(QWidget):
    """Gráfico de um canal no domínio do tempo ou da frequência.

    A classe recebe vetores prontos para renderização. Ela não conhece serial,
    parser, buffers, filtros ou FFT.
    """

    def __init__(self, channel: SignalChannelConfig) -> None:
        super().__init__()
        self.channel = channel

        layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget(title=f"{channel.display_name} - tempo")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(auto=True, mode="peak")

        self.curve = self.plot_widget.plot([], [])
        layout.addWidget(self.plot_widget)
        self.set_time_axes()

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

        self.set_time_axes()
        self.plot_widget.setTitle(f"{self.channel.display_name} - {title_suffix}")
        self.curve.setData(x_seconds, values)

    def set_spectrum(self, spectrum: SpectrumSnapshot, title_suffix: str = "espectro") -> None:
        if spectrum.frequencies_hz.size == 0 or spectrum.magnitudes.size == 0:
            self.clear()
            return
        if len(spectrum.frequencies_hz) != len(spectrum.magnitudes):
            return

        self.set_spectrum_axes()
        self.plot_widget.setTitle(f"{self.channel.display_name} - {title_suffix}")
        self.curve.setData(spectrum.frequencies_hz, spectrum.magnitudes)

    def set_series(self, x_seconds: np.ndarray, values: np.ndarray, title_suffix: str = "tempo") -> None:
        """Compatibilidade interna com chamadas existentes."""
        self.set_time_series(x_seconds, values, title_suffix)

    def clear(self) -> None:
        self.curve.setData(np.array([], dtype=float), np.array([], dtype=float))
