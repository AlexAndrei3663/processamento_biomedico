from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.domain.models import ProcessedChannelSnapshot, SignalChannelConfig
from serial_monitor.processing.filter_pipeline import FILTER_DEFINITIONS
from serial_monitor.ui.widgets.signal_plot_widget import SignalPlotWidget


class SignalTab(QWidget):
    """Aba de visualização e processamento de um canal."""

    filter_toggled = pyqtSignal(int, str, bool)
    display_mode_changed = pyqtSignal(int, str)

    RAW_MODE = "raw"
    PROCESSED_MODE = "processed"

    def __init__(self, channel: SignalChannelConfig) -> None:
        super().__init__()
        self.channel = channel
        self.display_mode = self.RAW_MODE
        self.filter_checkboxes: Dict[str, QCheckBox] = {}
        self.plot = SignalPlotWidget(channel)

        root = QHBoxLayout(self)
        root.addWidget(self.plot, stretch=4)

        side_panel = QFrame()
        side_panel.setFrameShape(QFrame.StyledPanel)
        side_panel.setMinimumWidth(285)
        side_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        side_layout = QVBoxLayout(side_panel)

        self.title_label = QLabel(f"<b>{channel.display_name}</b>")
        self.type_label = QLabel(f"Tipo: {channel.signal_type.value}")
        self.index_label = QLabel(f"Canal: ch{channel.index}")
        self.unit_label = QLabel(f"Unidade: {channel.unit}")
        self.sample_rate_label = QLabel(f"Taxa: {channel.sample_rate_hz:g} Hz")
        self.sample_count_label = QLabel("Amostras: 0")
        self.last_raw_value_label = QLabel("Último bruto: --")
        self.last_processed_value_label = QLabel("Último processado: --")
        self.last_time_label = QLabel("Último timestamp: --")

        for widget in (
            self.title_label,
            self.type_label,
            self.index_label,
            self.unit_label,
            self.sample_rate_label,
            self.sample_count_label,
            self.last_raw_value_label,
            self.last_processed_value_label,
            self.last_time_label,
        ):
            side_layout.addWidget(widget)

        view_group = QGroupBox("Visualização")
        view_layout = QVBoxLayout(view_group)
        self.raw_radio = QRadioButton("Sinal bruto")
        self.processed_radio = QRadioButton("Sinal processado")
        self.raw_radio.setChecked(True)
        self.view_button_group = QButtonGroup(self)
        self.view_button_group.addButton(self.raw_radio)
        self.view_button_group.addButton(self.processed_radio)
        view_layout.addWidget(self.raw_radio)
        view_layout.addWidget(self.processed_radio)
        side_layout.addWidget(view_group)

        filter_group = QGroupBox("Filtros pré-definidos")
        filter_layout = QVBoxLayout(filter_group)
        if channel.default_filters:
            for filter_id in channel.default_filters:
                definition = FILTER_DEFINITIONS.get(filter_id)
                label = definition.display_name if definition else filter_id
                checkbox = QCheckBox(label)
                checkbox.setToolTip(definition.description if definition else filter_id)
                checkbox.toggled.connect(
                    lambda checked, fid=filter_id: self.filter_toggled.emit(
                        self.channel.index,
                        fid,
                        checked,
                    )
                )
                self.filter_checkboxes[filter_id] = checkbox
                filter_layout.addWidget(checkbox)
        else:
            filter_layout.addWidget(QLabel("Nenhum filtro pré-definido para este sinal."))
        side_layout.addWidget(filter_group)

        metrics_group = QGroupBox("Métricas da janela processada")
        metrics_layout = QVBoxLayout(metrics_group)
        self.mean_label = QLabel("Média: --")
        self.rms_label = QLabel("RMS: --")
        self.min_label = QLabel("Mínimo: --")
        self.max_label = QLabel("Máximo: --")
        for widget in (self.mean_label, self.rms_label, self.min_label, self.max_label):
            metrics_layout.addWidget(widget)
        side_layout.addWidget(metrics_group)

        self.active_filters_label = QLabel("Filtros ativos: nenhum")
        self.active_filters_label.setWordWrap(True)
        self.filter_status_label = QLabel("Status: --")
        self.filter_status_label.setWordWrap(True)
        side_layout.addWidget(self.active_filters_label)
        side_layout.addWidget(self.filter_status_label)

        side_layout.addStretch(1)
        root.addWidget(side_panel, stretch=1)

        self.raw_radio.toggled.connect(self._on_display_mode_toggled)
        self.processed_radio.toggled.connect(self._on_display_mode_toggled)

    def _on_display_mode_toggled(self) -> None:
        mode = self.PROCESSED_MODE if self.processed_radio.isChecked() else self.RAW_MODE
        if mode == self.display_mode:
            return
        self.display_mode = mode
        self.display_mode_changed.emit(self.channel.index, mode)

    def update_from_snapshot(self, snapshot: ProcessedChannelSnapshot) -> None:
        self.sample_count_label.setText(f"Amostras: {snapshot.sample_count}")

        if snapshot.last_raw_value is None:
            self.last_raw_value_label.setText("Último bruto: --")
            self.last_processed_value_label.setText("Último processado: --")
            self.last_time_label.setText("Último timestamp: --")
            self._update_metrics(snapshot)
            self.plot.clear()
            return

        self.last_raw_value_label.setText(f"Último bruto: {snapshot.last_raw_value:g} {self.channel.unit}")
        if snapshot.last_processed_value is None:
            self.last_processed_value_label.setText("Último processado: --")
        else:
            self.last_processed_value_label.setText(
                f"Último processado: {snapshot.last_processed_value:g} {self.channel.unit}"
            )
        self.last_time_label.setText(f"Último timestamp: {snapshot.last_timestamp_ms} ms")

        if snapshot.active_filters:
            names = []
            for filter_id in snapshot.active_filters:
                definition = FILTER_DEFINITIONS.get(filter_id)
                names.append(definition.display_name if definition else filter_id)
            self.active_filters_label.setText("Filtros ativos: " + ", ".join(names))
        else:
            self.active_filters_label.setText("Filtros ativos: nenhum")

        self.filter_status_label.setText("Status: " + " | ".join(snapshot.filter_status))
        self._update_metrics(snapshot)

        if self.display_mode == self.PROCESSED_MODE:
            self.plot.set_series(snapshot.x_seconds, snapshot.processed_values, "processado")
        else:
            self.plot.set_series(snapshot.x_seconds, snapshot.raw_values, "bruto")

    def _update_metrics(self, snapshot: ProcessedChannelSnapshot) -> None:
        metrics = snapshot.metrics
        unit = self.channel.unit
        self.mean_label.setText("Média: --" if metrics.mean is None else f"Média: {metrics.mean:g} {unit}")
        self.rms_label.setText("RMS: --" if metrics.rms is None else f"RMS: {metrics.rms:g} {unit}")
        self.min_label.setText("Mínimo: --" if metrics.minimum is None else f"Mínimo: {metrics.minimum:g} {unit}")
        self.max_label.setText("Máximo: --" if metrics.maximum is None else f"Máximo: {metrics.maximum:g} {unit}")

    def clear(self) -> None:
        self.plot.clear()
        self.sample_count_label.setText("Amostras: 0")
        self.last_raw_value_label.setText("Último bruto: --")
        self.last_processed_value_label.setText("Último processado: --")
        self.last_time_label.setText("Último timestamp: --")
        self.active_filters_label.setText("Filtros ativos: nenhum")
        self.filter_status_label.setText("Status: --")
        self.mean_label.setText("Média: --")
        self.rms_label.setText("RMS: --")
        self.min_label.setText("Mínimo: --")
        self.max_label.setText("Máximo: --")
