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
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.domain.models import ProcessedChannelSnapshot, SignalChannelConfig, SpectrumSnapshot
from serial_monitor.processing.filter_pipeline import FILTER_DEFINITIONS
from serial_monitor.ui.widgets.signal_plot_widget import SignalPlotWidget


class SignalTab(QWidget):
    """Aba de visualização, processamento e espectro de um canal."""

    filter_toggled = pyqtSignal(int, str, bool)
    display_mode_changed = pyqtSignal(int, str)

    RAW_MODE = "raw"
    PROCESSED_MODE = "processed"
    TIME_DOMAIN = "time"
    SPECTRUM_DOMAIN = "spectrum"

    def __init__(self, channel: SignalChannelConfig) -> None:
        super().__init__()
        self.channel = channel
        self.display_mode = self.RAW_MODE
        self.plot_domain = self.TIME_DOMAIN
        self._last_snapshot: ProcessedChannelSnapshot | None = None
        self.filter_checkboxes: Dict[str, QCheckBox] = {}
        self.plot = SignalPlotWidget(channel)

        root = QHBoxLayout(self)
        root.addWidget(self.plot, stretch=4)

        side_panel = QFrame()
        side_panel.setFrameShape(QFrame.StyledPanel)
        side_panel.setMinimumWidth(305)
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

        view_group = QGroupBox("Sinal exibido")
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

        domain_group = QGroupBox("Domínio")
        domain_layout = QVBoxLayout(domain_group)
        self.time_radio = QRadioButton("Tempo")
        self.spectrum_radio = QRadioButton("Espectro")
        self.time_radio.setChecked(True)
        self.domain_button_group = QButtonGroup(self)
        self.domain_button_group.addButton(self.time_radio)
        self.domain_button_group.addButton(self.spectrum_radio)
        self.toggle_spectrum_button = QPushButton("Mostrar espectro")
        domain_layout.addWidget(self.time_radio)
        domain_layout.addWidget(self.spectrum_radio)
        domain_layout.addWidget(self.toggle_spectrum_button)
        side_layout.addWidget(domain_group)

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

        spectrum_group = QGroupBox("Espectro da janela exibida")
        spectrum_layout = QVBoxLayout(spectrum_group)
        self.peak_frequency_label = QLabel("Pico: --")
        self.peak_magnitude_label = QLabel("Magnitude do pico: --")
        self.resolution_label = QLabel("Resolução: --")
        for widget in (self.peak_frequency_label, self.peak_magnitude_label, self.resolution_label):
            spectrum_layout.addWidget(widget)
        side_layout.addWidget(spectrum_group)

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
        self.time_radio.toggled.connect(self._on_plot_domain_toggled)
        self.spectrum_radio.toggled.connect(self._on_plot_domain_toggled)
        self.toggle_spectrum_button.clicked.connect(self._toggle_spectrum)

    def _on_display_mode_toggled(self) -> None:
        mode = self.PROCESSED_MODE if self.processed_radio.isChecked() else self.RAW_MODE
        if mode == self.display_mode:
            return
        self.display_mode = mode
        self.display_mode_changed.emit(self.channel.index, mode)
        self._redraw_last_snapshot()

    def _on_plot_domain_toggled(self) -> None:
        domain = self.SPECTRUM_DOMAIN if self.spectrum_radio.isChecked() else self.TIME_DOMAIN
        if domain == self.plot_domain:
            return
        self.plot_domain = domain
        self.toggle_spectrum_button.setText("Mostrar tempo" if domain == self.SPECTRUM_DOMAIN else "Mostrar espectro")
        self._redraw_last_snapshot()

    def _toggle_spectrum(self) -> None:
        if self.plot_domain == self.TIME_DOMAIN:
            self.spectrum_radio.setChecked(True)
        else:
            self.time_radio.setChecked(True)

    def update_from_snapshot(self, snapshot: ProcessedChannelSnapshot) -> None:
        self._last_snapshot = snapshot
        self.sample_count_label.setText(f"Amostras: {snapshot.sample_count}")

        if snapshot.last_raw_value is None:
            self.last_raw_value_label.setText("Último bruto: --")
            self.last_processed_value_label.setText("Último processado: --")
            self.last_time_label.setText("Último timestamp: --")
            self._update_metrics(snapshot)
            self._update_spectrum_info(snapshot)
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

        active_filter_set = set(snapshot.active_filters)
        for filter_id, checkbox in self.filter_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(filter_id in active_filter_set)
            checkbox.blockSignals(False)

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
        self._update_spectrum_info(snapshot)
        self._draw_snapshot(snapshot)

    def _redraw_last_snapshot(self) -> None:
        if self._last_snapshot is not None:
            self._update_spectrum_info(self._last_snapshot)
            self._draw_snapshot(self._last_snapshot)

    def _draw_snapshot(self, snapshot: ProcessedChannelSnapshot) -> None:
        if self.plot_domain == self.SPECTRUM_DOMAIN:
            spectrum = self._selected_spectrum(snapshot)
            label = "espectro processado" if self.display_mode == self.PROCESSED_MODE else "espectro bruto"
            self.plot.set_spectrum(spectrum, label)
            return

        if self.display_mode == self.PROCESSED_MODE:
            self.plot.set_time_series(snapshot.x_seconds, snapshot.processed_values, "processado")
        else:
            self.plot.set_time_series(snapshot.x_seconds, snapshot.raw_values, "bruto")

    def _selected_spectrum(self, snapshot: ProcessedChannelSnapshot) -> SpectrumSnapshot:
        if self.display_mode == self.PROCESSED_MODE:
            return snapshot.processed_spectrum
        return snapshot.raw_spectrum

    def _update_metrics(self, snapshot: ProcessedChannelSnapshot) -> None:
        metrics = snapshot.metrics
        unit = self.channel.unit
        self.mean_label.setText("Média: --" if metrics.mean is None else f"Média: {metrics.mean:g} {unit}")
        self.rms_label.setText("RMS: --" if metrics.rms is None else f"RMS: {metrics.rms:g} {unit}")
        self.min_label.setText("Mínimo: --" if metrics.minimum is None else f"Mínimo: {metrics.minimum:g} {unit}")
        self.max_label.setText("Máximo: --" if metrics.maximum is None else f"Máximo: {metrics.maximum:g} {unit}")

    def _update_spectrum_info(self, snapshot: ProcessedChannelSnapshot) -> None:
        spectrum = self._selected_spectrum(snapshot)
        if spectrum.peak_frequency_hz is None:
            self.peak_frequency_label.setText("Pico: --")
            self.peak_magnitude_label.setText("Magnitude do pico: --")
            self.resolution_label.setText("Resolução: --")
            return

        self.peak_frequency_label.setText(f"Pico: {spectrum.peak_frequency_hz:g} Hz")
        self.peak_magnitude_label.setText(
            "Magnitude do pico: --"
            if spectrum.peak_magnitude is None
            else f"Magnitude do pico: {spectrum.peak_magnitude:g} {self.channel.unit}"
        )
        self.resolution_label.setText(
            "Resolução: --"
            if spectrum.resolution_hz is None
            else f"Resolução: {spectrum.resolution_hz:g} Hz/bin"
        )

    def clear(self) -> None:
        self._last_snapshot = None
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
        self.peak_frequency_label.setText("Pico: --")
        self.peak_magnitude_label.setText("Magnitude do pico: --")
        self.resolution_label.setText("Resolução: --")
