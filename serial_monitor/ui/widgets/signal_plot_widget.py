from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

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
        self._current_y_unit: str | None = None

        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.plot_widget = pg.PlotWidget(title=initial_title)
        self.plot_widget.setMinimumSize(0, 0)
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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

    def set_time_axes(self, unit: str | None = None) -> None:
        """Configura os eixos para apresentação no domínio do tempo."""

        unit = unit or self.channel.unit
        if self._current_domain == "time" and self._current_y_unit == unit:
            return

        self._current_domain = "time"
        self._current_y_unit = unit
        self._last_range_signature = None

        self.plot_widget.setLabel("bottom", "Tempo", units="s")
        self.plot_widget.setLabel(
            "left",
            self.channel.display_name,
            units=unit,
        )

    def set_spectrum_axes(self, unit: str | None = None) -> None:
        """Configura os eixos para apresentação no domínio da frequência."""

        unit = unit or self.channel.unit
        if self._current_domain == "spectrum" and self._current_y_unit == unit:
            return

        self._current_domain = "spectrum"
        self._current_y_unit = unit
        self._last_range_signature = None

        self.plot_widget.setLabel("bottom", "Frequência", units="Hz")
        self.plot_widget.setLabel(
            "left",
            "Magnitude",
            units=unit,
        )

    def set_time_series(
        self,
        x_seconds: np.ndarray,
        values: np.ndarray,
        title_suffix: str = "tempo",
        unit: str | None = None,
    ) -> None:
        """Exibe uma série no domínio do tempo."""

        self.set_time_axes(unit)
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
        unit: str | None = None,
    ) -> None:
        """Exibe o espectro unilateral de magnitude do canal."""

        self.set_spectrum_axes(unit)
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
        unit: str | None = None,
    ) -> None:
        """Compatibilidade interna com chamadas existentes."""

        self.set_time_series(x_seconds, values, title_suffix, unit=unit)

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

        data_x_min = float(np.min(finite_x))
        data_x_max = float(np.max(finite_x))
        data_y_min = float(np.min(finite_y))
        data_y_max = float(np.max(finite_y))

        # No domínio do tempo, a navegação nunca avança para valores negativos.
        # O RingBuffer fornece tempo decorrido desde o primeiro timestamp válido
        # do fluxo, portanto zero é a origem natural do eixo X.
        x_min = max(0.0, data_x_min) if self._current_domain == "time" else data_x_min
        x_max = max(x_min, data_x_max)

        # Mantém uma referência visual em zero. Para sinais estritamente
        # positivos o limite inferior é zero; para sinais que assumem valores
        # negativos, o menor valor observado passa a ser o limite inferior.
        y_min = min(0.0, data_y_min)
        y_max = max(0.0, data_y_max)

        x_span = x_max - x_min
        y_span = y_max - y_min

        if x_span <= 0:
            if self._current_domain == "time":
                x_min = 0.0
                x_max = max(data_x_max, 1.0)
            else:
                x_min -= 0.5
                x_max += 0.5
            x_span = x_max - x_min

        if y_span <= 0:
            # Uma série constante em zero ainda precisa de uma faixa visível.
            # O limite inferior continua travado em zero.
            y_min = min(0.0, data_y_min)
            y_max = max(1.0, data_y_max)
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

        # A janela acompanha sempre o timestamp mais recente. Quando o buffer
        # circular começa a sobrescrever amostras antigas, o eixo X continua
        # avançando em vez de retornar a zero ou permanecer em uma faixa antiga.
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
