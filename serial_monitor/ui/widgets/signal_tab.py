from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from serial_monitor.domain.models import ChannelBufferSnapshot, SignalChannelConfig
from serial_monitor.ui.widgets.signal_plot_widget import SignalPlotWidget


class SignalTab(QWidget):
    """Aba de visualização de um canal.

    Nesta etapa a aba contém o gráfico temporal bruto e um painel lateral com
    metadados mínimos. Filtros, espectro e métricas biomédicas entram nas etapas
    seguintes usando este mesmo ponto de extensão.
    """

    def __init__(self, channel: SignalChannelConfig) -> None:
        super().__init__()
        self.channel = channel
        self.plot = SignalPlotWidget(channel)

        root = QHBoxLayout(self)
        root.addWidget(self.plot, stretch=4)

        side_panel = QFrame()
        side_panel.setFrameShape(QFrame.StyledPanel)
        side_panel.setMinimumWidth(230)
        side_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        side_layout = QVBoxLayout(side_panel)

        self.title_label = QLabel(f"<b>{channel.display_name}</b>")
        self.type_label = QLabel(f"Tipo: {channel.signal_type.value}")
        self.index_label = QLabel(f"Canal: ch{channel.index}")
        self.unit_label = QLabel(f"Unidade: {channel.unit}")
        self.sample_rate_label = QLabel(f"Taxa: {channel.sample_rate_hz:g} Hz")
        self.sample_count_label = QLabel("Amostras: 0")
        self.last_value_label = QLabel("Último valor: --")
        self.last_time_label = QLabel("Último timestamp: --")
        self.filters_label = QLabel("Filtros padrão: " + (", ".join(channel.default_filters) or "nenhum"))
        self.filters_label.setWordWrap(True)

        for widget in (
            self.title_label,
            self.type_label,
            self.index_label,
            self.unit_label,
            self.sample_rate_label,
            self.sample_count_label,
            self.last_value_label,
            self.last_time_label,
            self.filters_label,
        ):
            side_layout.addWidget(widget)

        side_layout.addStretch(1)
        root.addWidget(side_panel, stretch=1)

    def update_from_snapshot(self, snapshot: ChannelBufferSnapshot) -> None:
        self.plot.update_from_snapshot(snapshot)
        self.sample_count_label.setText(f"Amostras: {snapshot.sample_count}")

        if snapshot.last_value is None:
            self.last_value_label.setText("Último valor: --")
            self.last_time_label.setText("Último timestamp: --")
            return

        self.last_value_label.setText(f"Último valor: {snapshot.last_value:g} {self.channel.unit}")
        self.last_time_label.setText(f"Último timestamp: {snapshot.last_timestamp_ms} ms")

    def clear(self) -> None:
        self.plot.clear()
        self.sample_count_label.setText("Amostras: 0")
        self.last_value_label.setText("Último valor: --")
        self.last_time_label.setText("Último timestamp: --")
