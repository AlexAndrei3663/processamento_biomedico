from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from serial_monitor.domain.models import SignalChannelConfig


class SignalPlotWidget(QWidget):
    """Gráfico temporal de um canal.

    A classe recebe vetores prontos para renderização. Ela não conhece serial,
    parser, buffers ou filtros.
    """

    def __init__(self, channel: SignalChannelConfig) -> None:
        super().__init__()
        self.channel = channel

        layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget(title=f"{channel.display_name} - tempo")
        self.plot_widget.setLabel("bottom", "Tempo", units="s")
        self.plot_widget.setLabel("left", channel.display_name, units=channel.unit)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(auto=True, mode="peak")

        self.curve = self.plot_widget.plot([], [])
        layout.addWidget(self.plot_widget)

    def set_series(self, x_seconds: np.ndarray, values: np.ndarray, title_suffix: str = "tempo") -> None:
        if values.size == 0 or x_seconds.size == 0:
            self.clear()
            return
        if len(x_seconds) != len(values):
            return

        self.plot_widget.setTitle(f"{self.channel.display_name} - {title_suffix}")
        self.curve.setData(x_seconds, values)

    def clear(self) -> None:
        self.curve.setData(np.array([], dtype=float), np.array([], dtype=float))
