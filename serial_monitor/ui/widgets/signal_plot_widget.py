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

    def __init__(
        self,
        channel: SignalChannelConfig,
        max_plot_points: int = 5000,
        fixed_x_window: float | None = None,
    ) -> None:
        super().__init__()
        self.channel = channel
        self.max_plot_points = max(100, int(max_plot_points))
        self.fixed_x_window = fixed_x_window

        layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget(title=f"{channel.display_name} - tempo")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(auto=True, mode="peak")

        self.curve = self.plot_widget.plot([], [])
        layout.addWidget(self.plot_widget)

        self._configure_horizontal_pan_only()
        self.set_time_axes()

    def set_max_plot_points(self, max_plot_points: int) -> None:
        self.max_plot_points = max(100, int(max_plot_points))

    def set_fixed_x_window(self, fixed_x_window: float | None) -> None:
        self.fixed_x_window = fixed_x_window

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

        self._apply_horizontal_pan_only_limits(x_seconds, values)

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

        self._apply_horizontal_pan_only_limits(spectrum.frequencies_hz, spectrum.magnitudes)

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

    def _configure_horizontal_pan_only(self) -> None:
        """Configura o gráfico para permitir somente pan horizontal."""
        view_box = self.plot_widget.getViewBox()
        view_box.setMouseEnabled(x=True, y=False)
        view_box.setMouseMode(pg.ViewBox.PanMode)
        view_box.disableAutoRange()
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()

    def _apply_horizontal_pan_only_limits(self, x_values: np.ndarray, y_values: np.ndarray) -> None:
        """Trava zoom e escala vertical, permitindo apenas pan horizontal."""
        finite_x = x_values[np.isfinite(x_values)]
        finite_y = y_values[np.isfinite(y_values)]

        if finite_x.size == 0 or finite_y.size == 0:
            return

        x_min = float(np.min(finite_x))
        x_max = float(np.max(finite_x))
        y_min = float(np.min(finite_y))
        y_max = float(np.max(finite_y))

        x_span = x_max - x_min
        y_span = y_max - y_min

        if x_span <= 0:
            x_min -= 0.5
            x_max += 0.5
            x_span = x_max - x_min

        if y_span <= 0:
            padding = max(abs(y_min) * 0.05, 1.0)
            y_min -= padding
            y_max += padding
            y_span = y_max - y_min

        if self.fixed_x_window is None:
            x_window = x_span
        else:
            x_window = max(float(self.fixed_x_window), np.finfo(float).eps)
            x_window = min(x_window, x_span)

        view_box = self.plot_widget.getViewBox()

        current_x_range = view_box.viewRange()[0]
        current_x_min = float(current_x_range[0])
        current_x_max = float(current_x_range[1])
        current_x_span = current_x_max - current_x_min

        should_keep_current_position = (
            current_x_span > 0
            and abs(current_x_span - x_window) <= max(x_window * 0.001, 1e-9)
        )

        if should_keep_current_position:
            view_x_min = current_x_min
        else:
            view_x_min = x_max - x_window

        view_x_min = max(x_min, min(view_x_min, x_max - x_window))
        view_x_max = view_x_min + x_window

        view_box.setLimits(
            # Limites de navegação horizontal.
            xMin=x_min,
            xMax=x_max,

            # Trava o zoom horizontal.
            minXRange=x_window,
            maxXRange=x_window,

            # Trava completamente o eixo Y.
            yMin=y_min,
            yMax=y_max,
            minYRange=y_span,
            maxYRange=y_span,
        )

        view_box.setRange(
            xRange=(view_x_min, view_x_max),
            yRange=(y_min, y_max),
            padding=0,
        )

        view_box.disableAutoRange()