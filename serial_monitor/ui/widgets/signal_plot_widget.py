from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from serial_monitor.domain.models import SignalChannelConfig, SpectrumSnapshot


class SignalPlotWidget(QWidget):
    """Gráfico de um canal no domínio do tempo ou da frequência.

    A classe recebe vetores prontos para renderização. Ela não conhece serial,
    parser, buffers, filtros ou FFT.

    Para reduzir a carga de renderização na Raspberry Pi, o widget:

    - limita a quantidade máxima de pontos enviados ao PyQtGraph;
    - reconfigura os rótulos dos eixos somente ao trocar de domínio;
    - altera o título somente quando o texto muda;
    - reaplica limites e faixas apenas quando os dados relevantes mudam.

    Essas otimizações afetam somente a visualização. Os dados mantidos nos
    buffers e utilizados no armazenamento não são reduzidos.
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

        initial_title = f"{channel.display_name} - tempo"

        # Estados utilizados para evitar reconfigurações repetidas do gráfico.
        self._last_range_signature: tuple[object, ...] | None = None
        self._current_domain: str | None = None
        self._last_title: str | None = initial_title

        layout = QVBoxLayout(self)

        self.plot_widget = pg.PlotWidget(title=initial_title)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(auto=True, mode="peak")

        self.curve = self.plot_widget.plot([], [])
        layout.addWidget(self.plot_widget)

        self._configure_horizontal_pan_only()
        self.set_time_axes()

    def set_max_plot_points(self, max_plot_points: int) -> None:
        """Define o máximo de pontos enviados ao PyQtGraph por atualização."""

        new_limit = max(100, int(max_plot_points))
        if new_limit == self.max_plot_points:
            return

        self.max_plot_points = new_limit
        self._last_range_signature = None

    def set_fixed_x_window(self, fixed_x_window: float | None) -> None:
        """Define uma largura fixa para a janela horizontal, em segundos/Hz."""

        if fixed_x_window == self.fixed_x_window:
            return

        self.fixed_x_window = fixed_x_window
        self._last_range_signature = None

    def set_time_axes(self) -> None:
        """Configura os eixos para apresentação no domínio do tempo."""

        if self._current_domain == "time":
            return

        self._current_domain = "time"
        self._last_range_signature = None

        self.plot_widget.setLabel("bottom", "Tempo", units="s")
        self.plot_widget.setLabel(
            "left",
            self.channel.display_name,
            units=self.channel.unit,
        )

    def set_spectrum_axes(self) -> None:
        """Configura os eixos para apresentação no domínio da frequência."""

        if self._current_domain == "spectrum":
            return

        self._current_domain = "spectrum"
        self._last_range_signature = None

        self.plot_widget.setLabel("bottom", "Frequência", units="Hz")
        self.plot_widget.setLabel(
            "left",
            "Magnitude",
            units=self.channel.unit,
        )

    def set_time_series(
        self,
        x_seconds: np.ndarray,
        values: np.ndarray,
        title_suffix: str = "tempo",
    ) -> None:
        """Exibe uma série no domínio do tempo."""

        self.set_time_axes()
        self._set_title(f"{self.channel.display_name} - {title_suffix}")

        if values.size == 0 or x_seconds.size == 0:
            self.clear()
            return

        if len(x_seconds) != len(values):
            return

        x_plot, y_plot = self._decimate(x_seconds, values)
        self.curve.setData(x_plot, y_plot)

        # Os limites são calculados sobre os dados efetivamente renderizados.
        self._apply_horizontal_pan_only_limits(x_plot, y_plot)

    def set_spectrum(
        self,
        spectrum: SpectrumSnapshot,
        title_suffix: str = "espectro",
    ) -> None:
        """Exibe o espectro unilateral de magnitude do canal."""

        self.set_spectrum_axes()
        self._set_title(f"{self.channel.display_name} - {title_suffix}")

        if spectrum.frequencies_hz.size == 0 or spectrum.magnitudes.size == 0:
            self.clear()
            return

        if len(spectrum.frequencies_hz) != len(spectrum.magnitudes):
            return

        x_plot, y_plot = self._decimate(
            spectrum.frequencies_hz,
            spectrum.magnitudes,
        )
        self.curve.setData(x_plot, y_plot)

        self._apply_horizontal_pan_only_limits(x_plot, y_plot)

    def set_series(
        self,
        x_seconds: np.ndarray,
        values: np.ndarray,
        title_suffix: str = "tempo",
    ) -> None:
        """Compatibilidade interna com chamadas existentes."""

        self.set_time_series(x_seconds, values, title_suffix)

    def clear(self) -> None:
        """Limpa somente a curva exibida."""

        self._last_range_signature = None
        self.curve.setData(
            np.array([], dtype=float),
            np.array([], dtype=float),
        )

    def _set_title(self, title: str) -> None:
        """Atualiza o título somente quando seu conteúdo muda."""

        if title == self._last_title:
            return

        self._last_title = title
        self.plot_widget.setTitle(title)

    def _decimate(
        self,
        x_values: np.ndarray,
        y_values: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Reduz somente a quantidade de pontos enviados ao gráfico."""

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

    def _apply_horizontal_pan_only_limits(
        self,
        x_values: np.ndarray,
        y_values: np.ndarray,
    ) -> None:
        """Trava zoom e escala vertical, permitindo apenas pan horizontal.

        Os limites não são reaplicados quando o domínio, o número de pontos e
        os extremos dos dados permanecem iguais à atualização anterior.
        """

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
            x_window = max(
                float(self.fixed_x_window),
                np.finfo(float).eps,
            )
            x_window = min(x_window, x_span)

        range_signature = (
            self._current_domain,
            len(x_values),
            round(x_min, 9),
            round(x_max, 9),
            round(y_min, 9),
            round(y_max, 9),
            round(x_window, 9),
            self.fixed_x_window,
        )

        if range_signature == self._last_range_signature:
            return

        self._last_range_signature = range_signature

        view_box = self.plot_widget.getViewBox()

        current_x_range = view_box.viewRange()[0]
        current_x_min = float(current_x_range[0])
        current_x_max = float(current_x_range[1])
        current_x_span = current_x_max - current_x_min

        should_keep_current_position = (
            current_x_span > 0
            and abs(current_x_span - x_window)
            <= max(x_window * 0.001, 1e-9)
        )

        if should_keep_current_position:
            view_x_min = current_x_min
        else:
            view_x_min = x_max - x_window

        view_x_min = max(
            x_min,
            min(view_x_min, x_max - x_window),
        )
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
