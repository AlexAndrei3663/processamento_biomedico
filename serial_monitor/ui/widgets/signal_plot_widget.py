from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from serial_monitor.domain.models import SignalChannelConfig, SpectrumSnapshot


class SignalPlotWidget(QWidget):
    """Gráfico leve com pan e zoom somente no eixo horizontal."""

    follow_mode_changed = pyqtSignal(bool)

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
        self._current_domain: str | None = None
        self._current_y_unit: str | None = None
        self._last_title: str | None = None
        self._follow_latest = True
        self._programmatic_range_change = False
        self._range_initialized = False
        self._last_x: np.ndarray = np.array([], dtype=float)
        self._last_y: np.ndarray = np.array([], dtype=float)

        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setMinimumSize(0, 0)
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(auto=True, mode="peak")
        self.curve = self.plot_widget.plot([], [])
        layout.addWidget(self.plot_widget)

        view_box = self.plot_widget.getViewBox()
        view_box.setMouseEnabled(x=True, y=False)
        view_box.setMouseMode(pg.ViewBox.PanMode)
        view_box.disableAutoRange()
        manual_signal = getattr(view_box, "sigRangeChangedManually", None)
        if manual_signal is not None:
            manual_signal.connect(self._on_manual_range_change)

        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()
        self.set_time_axes()

    @property
    def follow_latest(self) -> bool:
        return self._follow_latest

    def set_follow_latest(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._follow_latest:
            if enabled:
                self._apply_navigation_limits(self._last_x, self._last_y)
            return
        self._follow_latest = enabled
        self.follow_mode_changed.emit(enabled)
        if enabled:
            self._apply_navigation_limits(self._last_x, self._last_y)

    def zoom_horizontal(self, factor: float) -> None:
        """Aplica zoom horizontal sem recalcular filtros, FFT ou dados."""

        if factor <= 0 or self._last_x.size < 2:
            return
        finite_x = self._last_x[np.isfinite(self._last_x)]
        if finite_x.size < 2:
            return
        data_min = max(0.0, float(np.min(finite_x))) if self._current_domain == "time" else float(np.min(finite_x))
        data_max = float(np.max(finite_x))
        data_span = max(data_max - data_min, np.finfo(float).eps)

        current = self.plot_widget.getViewBox().viewRange()[0]
        current_span = max(float(current[1] - current[0]), np.finfo(float).eps)
        minimum_span = max(data_span / max(100.0, float(self.max_plot_points)), np.finfo(float).eps)
        new_span = min(data_span, max(minimum_span, current_span * float(factor)))
        center = (float(current[0]) + float(current[1])) / 2.0
        left = max(data_min, min(center - new_span / 2.0, data_max - new_span))
        right = left + new_span

        self.set_follow_latest(False)
        self._set_x_range(left, right)

    def set_max_plot_points(self, max_plot_points: int) -> None:
        self.max_plot_points = max(100, int(max_plot_points))

    def set_fixed_x_window(self, fixed_x_window: float | None) -> None:
        self.fixed_x_window = fixed_x_window
        self._range_initialized = False

    def set_time_axes(self, unit: str | None = None) -> None:
        unit = unit or self.channel.unit
        if self._current_domain == "time" and self._current_y_unit == unit:
            return
        self._current_domain = "time"
        self._current_y_unit = unit
        self._range_initialized = False
        self._follow_latest = True
        self.plot_widget.setLabel("bottom", "Tempo", units="s")
        self.plot_widget.setLabel("left", self.channel.display_name, units=unit)

    def set_spectrum_axes(self, unit: str | None = None) -> None:
        unit = unit or self.channel.unit
        if self._current_domain == "spectrum" and self._current_y_unit == unit:
            return
        self._current_domain = "spectrum"
        self._current_y_unit = unit
        self._range_initialized = False
        self._follow_latest = True
        self.plot_widget.setLabel("bottom", "Frequência", units="Hz")
        self.plot_widget.setLabel("left", "Magnitude", units=unit)

    def set_time_series(
        self,
        x_seconds: np.ndarray,
        values: np.ndarray,
        title_suffix: str = "tempo",
        unit: str | None = None,
    ) -> None:
        self.set_time_axes(unit)
        self._set_title(f"{self.channel.display_name} - {title_suffix}")
        self._set_data(x_seconds, values)

    def set_spectrum(
        self,
        spectrum: SpectrumSnapshot,
        title_suffix: str = "espectro",
        unit: str | None = None,
    ) -> None:
        self.set_spectrum_axes(unit)
        self._set_title(f"{self.channel.display_name} - {title_suffix}")
        self._set_data(spectrum.frequencies_hz, spectrum.magnitudes)

    def set_series(
        self,
        x_seconds: np.ndarray,
        values: np.ndarray,
        title_suffix: str = "tempo",
        unit: str | None = None,
    ) -> None:
        self.set_time_series(x_seconds, values, title_suffix, unit=unit)

    def clear(self) -> None:
        self._last_x = np.array([], dtype=float)
        self._last_y = np.array([], dtype=float)
        self._range_initialized = False
        self.curve.setData(self._last_x, self._last_y)

    def _set_data(self, x_values: np.ndarray, y_values: np.ndarray) -> None:
        x = np.asarray(x_values, dtype=float)
        y = np.asarray(y_values, dtype=float)
        if x.size == 0 or y.size == 0 or x.size != y.size:
            self.clear()
            return
        x_plot, y_plot = self._decimate(x, y)
        self._last_x = x_plot
        self._last_y = y_plot
        self.curve.setData(x_plot, y_plot)
        self._apply_navigation_limits(x_plot, y_plot)

    def _set_title(self, title: str) -> None:
        if title == self._last_title:
            return
        self._last_title = title
        self.plot_widget.setTitle(title)

    def _decimate(
        self, x_values: np.ndarray, y_values: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        if y_values.size <= self.max_plot_points:
            return x_values, y_values
        step = int(np.ceil(y_values.size / self.max_plot_points))
        return x_values[::step], y_values[::step]

    def _on_manual_range_change(self, *_args) -> None:
        if self._programmatic_range_change:
            return
        if self._follow_latest:
            self._follow_latest = False
            self.follow_mode_changed.emit(False)

    def _set_x_range(self, left: float, right: float) -> None:
        self._programmatic_range_change = True
        try:
            self.plot_widget.getViewBox().setXRange(left, right, padding=0)
        finally:
            self._programmatic_range_change = False

    def _apply_navigation_limits(
        self, x_values: np.ndarray, y_values: np.ndarray
    ) -> None:
        finite_x = x_values[np.isfinite(x_values)]
        finite_y = y_values[np.isfinite(y_values)]
        if finite_x.size == 0 or finite_y.size == 0:
            return

        data_x_min = float(np.min(finite_x))
        data_x_max = float(np.max(finite_x))
        x_min = max(0.0, data_x_min) if self._current_domain == "time" else data_x_min
        x_max = max(x_min, data_x_max)
        if x_max <= x_min:
            x_max = x_min + (1.0 if self._current_domain == "time" else 0.5)

        data_y_min = float(np.min(finite_y))
        data_y_max = float(np.max(finite_y))
        y_min = min(0.0, data_y_min)
        y_max = max(0.0, data_y_max)
        if y_max <= y_min:
            y_max = y_min + 1.0
        y_span = y_max - y_min
        x_span = x_max - x_min
        minimum_x_span = max(x_span / max(100.0, float(self.max_plot_points)), np.finfo(float).eps)

        view_box = self.plot_widget.getViewBox()
        view_box.setLimits(
            xMin=x_min,
            xMax=x_max,
            minXRange=minimum_x_span,
            maxXRange=x_span,
            yMin=y_min,
            yMax=y_max,
            minYRange=y_span,
            maxYRange=y_span,
        )

        self._programmatic_range_change = True
        try:
            view_box.setYRange(y_min, y_max, padding=0)
        finally:
            self._programmatic_range_change = False

        if not self._range_initialized:
            window = x_span
            if self.fixed_x_window is not None:
                window = min(x_span, max(float(self.fixed_x_window), minimum_x_span))
            self._set_x_range(x_max - window, x_max)
            self._range_initialized = True
            return

        if self._follow_latest:
            current = view_box.viewRange()[0]
            window = max(minimum_x_span, min(x_span, float(current[1] - current[0])))
            self._set_x_range(max(x_min, x_max - window), x_max)
