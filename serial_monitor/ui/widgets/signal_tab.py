from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.domain.models import (
    ProcessedChannelSnapshot,
    SignalChannelConfig,
    SpectrumSnapshot,
)
from serial_monitor.processing.filter_pipeline import FILTER_DEFINITIONS
from serial_monitor.ui.widgets.signal_plot_widget import SignalPlotWidget


class SignalTab(QWidget):
    """Aba de visualização do bruto, convertido, processado e espectro.

    O gráfico e o painel lateral são separados por um ``QSplitter``. O painel
    de controles possui rolagem própria, portanto seu conteúdo nunca força a
    aba a ultrapassar as dimensões da tela. O modo de foco oculta o painel e
    entrega toda a área disponível ao gráfico.
    """

    filter_toggled = pyqtSignal(int, str, bool)
    display_mode_changed = pyqtSignal(int, str)

    RAW_MODE = "raw"
    CONVERTED_MODE = "converted"
    PROCESSED_MODE = "processed"
    TIME_DOMAIN = "time"
    SPECTRUM_DOMAIN = "spectrum"

    def __init__(self, channel: SignalChannelConfig, max_plot_points: int = 5000) -> None:
        super().__init__()
        self.channel = channel
        self.display_mode = self.RAW_MODE
        self.plot_domain = self.TIME_DOMAIN
        self._last_snapshot: ProcessedChannelSnapshot | None = None
        self._plot_focused = False
        self._fullscreen_mode = False
        self._normal_splitter_sizes = [740, 260]
        self.filter_checkboxes: Dict[str, QCheckBox] = {}
        self.plot = SignalPlotWidget(channel, max_plot_points=max_plot_points)

        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.toolbar_widget = QWidget()
        self.toolbar_widget.setObjectName("signalTabToolbar")
        self.toolbar_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar = QHBoxLayout(self.toolbar_widget)
        toolbar.setContentsMargins(2, 0, 2, 0)
        toolbar.setSpacing(4)

        self.compact_channel_label = QLabel(
            f"ch{channel.index} — {channel.display_name}"
        )
        self.compact_channel_label.setStyleSheet("font-weight: 600;")
        self.focus_plot_button = QPushButton("Focar")
        self.focus_plot_button.setCheckable(True)
        self.focus_plot_button.setMaximumWidth(150)
        self.focus_plot_button.setToolTip(
            "Oculta ou restaura o painel lateral para ampliar o gráfico."
        )
        toolbar.addWidget(self.compact_channel_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.focus_plot_button)
        root.addWidget(self.toolbar_widget)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        self.splitter.setMinimumSize(0, 0)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.plot.setMinimumSize(0, 0)
        self.plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.addWidget(self.plot)

        self.side_scroll = QScrollArea()
        self.side_scroll.setWidgetResizable(True)
        self.side_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.side_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.side_scroll.setMinimumWidth(235)
        self.side_scroll.setMaximumWidth(310)
        self.side_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        side_panel = QFrame()
        side_panel.setFrameShape(QFrame.StyledPanel)
        side_panel.setMinimumWidth(0)
        side_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(6, 6, 6, 6)
        side_layout.setSpacing(4)

        self.title_label = QLabel(f"<b>{channel.display_name}</b>")
        self.type_label = QLabel(f"Tipo: {channel.signal_type.value}")
        self.index_label = QLabel(f"Canal: ch{channel.index}")
        self.unit_label = QLabel(
            f"Unidades: bruto={channel.raw_unit} | exibição={channel.unit}"
        )
        self.unit_label.setWordWrap(True)
        self.sample_rate_label = QLabel(f"Taxa: {channel.sample_rate_hz:g} Hz")
        self.sample_count_label = QLabel("Amostras: 0")
        self.last_raw_value_label = QLabel("Último bruto: --")
        self.last_converted_value_label = QLabel("Último convertido: --")
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
            self.last_converted_value_label,
            self.last_processed_value_label,
            self.last_time_label,
        ):
            side_layout.addWidget(widget)

        view_group = QGroupBox("Sinal exibido")
        view_layout = QVBoxLayout(view_group)
        self.raw_radio = QRadioButton("Bruto recebido")
        self.converted_radio = QRadioButton("Convertido")
        self.processed_radio = QRadioButton(
            "Convertido + filtros" if channel.conversion_enabled else "Bruto + filtros"
        )
        self.raw_radio.setChecked(True)
        self.converted_radio.setEnabled(channel.conversion_enabled)
        self.view_button_group = QButtonGroup(self)
        for button in (self.raw_radio, self.converted_radio, self.processed_radio):
            self.view_button_group.addButton(button)
            view_layout.addWidget(button)
        side_layout.addWidget(view_group)

        conversion_group = QGroupBox("Conversão")
        conversion_layout = QVBoxLayout(conversion_group)
        self.conversion_profile_label = QLabel(
            "Perfil: "
            + (
                channel.conversion.profile_id
                if channel.conversion.enabled and channel.conversion.profile_id
                else "desabilitada"
            )
        )
        self.conversion_profile_label.setWordWrap(True)
        self.conversion_status_label = QLabel("Status: --")
        self.conversion_status_label.setWordWrap(True)
        conversion_layout.addWidget(self.conversion_profile_label)
        conversion_layout.addWidget(self.conversion_status_label)
        side_layout.addWidget(conversion_group)

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
            filter_layout.addWidget(QLabel("Nenhum filtro pré-definido."))
        side_layout.addWidget(filter_group)

        metrics_group = QGroupBox("Métricas do processado")
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
        for widget in (
            self.peak_frequency_label,
            self.peak_magnitude_label,
            self.resolution_label,
        ):
            spectrum_layout.addWidget(widget)
        side_layout.addWidget(spectrum_group)

        self.active_filters_label = QLabel("Filtros ativos: nenhum")
        self.active_filters_label.setWordWrap(True)
        self.filter_status_label = QLabel("Status dos filtros: --")
        self.filter_status_label.setWordWrap(True)
        side_layout.addWidget(self.active_filters_label)
        side_layout.addWidget(self.filter_status_label)
        side_layout.addStretch(1)

        self.side_scroll.setWidget(side_panel)
        self.splitter.addWidget(self.side_scroll)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes(self._normal_splitter_sizes)
        root.addWidget(self.splitter, stretch=1)

        self.raw_radio.toggled.connect(self._on_display_mode_toggled)
        self.converted_radio.toggled.connect(self._on_display_mode_toggled)
        self.processed_radio.toggled.connect(self._on_display_mode_toggled)
        self.time_radio.toggled.connect(self._on_plot_domain_toggled)
        self.spectrum_radio.toggled.connect(self._on_plot_domain_toggled)
        self.toggle_spectrum_button.clicked.connect(self._toggle_spectrum)
        self.focus_plot_button.toggled.connect(self.set_plot_focused)

    def set_plot_focused(self, focused: bool) -> None:
        """Expande o gráfico sem permitir que ele ultrapasse a aba disponível."""

        focused = bool(focused)
        if focused == self._plot_focused:
            return

        if focused:
            sizes = self.splitter.sizes()
            if len(sizes) == 2 and sizes[1] > 0:
                self._normal_splitter_sizes = sizes
            self.side_scroll.hide()
            self.splitter.setSizes([max(1, sum(sizes)), 0])
            self.focus_plot_button.setText("Controles")
        else:
            self.side_scroll.show()
            self.splitter.setSizes(self._normal_splitter_sizes)
            self.focus_plot_button.setText("Focar")

        self._plot_focused = focused
        self.focus_plot_button.blockSignals(True)
        self.focus_plot_button.setChecked(focused)
        self.focus_plot_button.blockSignals(False)

    def set_fullscreen_mode(self, enabled: bool) -> None:
        """Ajusta espaçamentos internos sem impor tamanhos maiores que a tela."""

        self._fullscreen_mode = bool(enabled)
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2 if enabled else 4)
        self.compact_channel_label.setVisible(not enabled or not self._plot_focused)

    def _on_display_mode_toggled(self) -> None:
        if self.processed_radio.isChecked():
            mode = self.PROCESSED_MODE
        elif self.converted_radio.isChecked():
            mode = self.CONVERTED_MODE
        else:
            mode = self.RAW_MODE
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
        self.toggle_spectrum_button.setText(
            "Mostrar tempo" if domain == self.SPECTRUM_DOMAIN else "Mostrar espectro"
        )
        self._redraw_last_snapshot()

    def _toggle_spectrum(self) -> None:
        if self.plot_domain == self.TIME_DOMAIN:
            self.spectrum_radio.setChecked(True)
        else:
            self.time_radio.setChecked(True)

    def update_from_snapshot(self, snapshot: ProcessedChannelSnapshot) -> None:
        self._last_snapshot = snapshot
        self.sample_count_label.setText(f"Amostras: {snapshot.sample_count}")
        self.converted_radio.setEnabled(snapshot.conversion_enabled)
        self.conversion_profile_label.setText(
            f"Perfil: {snapshot.conversion_profile_id or 'desabilitada'}"
        )
        self.conversion_status_label.setText(
            "Status: " + " | ".join(snapshot.conversion_status)
        )

        if snapshot.last_raw_value is None:
            self._clear_values_only(snapshot)
            return

        self.last_raw_value_label.setText(
            f"Último bruto: {snapshot.last_raw_value:g} {snapshot.conversion_input_unit}"
        )
        self.last_converted_value_label.setText(
            "Último convertido: --"
            if snapshot.last_converted_value is None
            else (
                f"Último convertido: {snapshot.last_converted_value:g} "
                f"{snapshot.conversion_output_unit}"
            )
        )
        self.last_processed_value_label.setText(
            "Último processado: --"
            if snapshot.last_processed_value is None
            else (
                f"Último processado: {snapshot.last_processed_value:g} "
                f"{snapshot.conversion_output_unit}"
            )
        )
        self.last_time_label.setText(f"Último timestamp: {snapshot.last_timestamp_us} µs")

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

        self.filter_status_label.setText(
            "Status dos filtros: " + " | ".join(snapshot.filter_status)
        )
        self._update_metrics(snapshot)
        self._update_spectrum_info(snapshot)
        self._draw_snapshot(snapshot)

    def _clear_values_only(self, snapshot: ProcessedChannelSnapshot) -> None:
        self.last_raw_value_label.setText("Último bruto: --")
        self.last_converted_value_label.setText("Último convertido: --")
        self.last_processed_value_label.setText("Último processado: --")
        self.last_time_label.setText("Último timestamp: --")
        self._update_metrics(snapshot)
        self._update_spectrum_info(snapshot)
        self.plot.clear()

    def _redraw_last_snapshot(self) -> None:
        if self._last_snapshot is not None:
            self._update_spectrum_info(self._last_snapshot)
            self._draw_snapshot(self._last_snapshot)

    def _selected_values(self, snapshot: ProcessedChannelSnapshot):
        if self.display_mode == self.PROCESSED_MODE:
            return snapshot.processed_values, snapshot.conversion_output_unit, "processado"
        if self.display_mode == self.CONVERTED_MODE:
            return snapshot.converted_values, snapshot.conversion_output_unit, "convertido"
        return snapshot.raw_values, snapshot.conversion_input_unit, "bruto"

    def _draw_snapshot(self, snapshot: ProcessedChannelSnapshot) -> None:
        _, unit, label = self._selected_values(snapshot)
        if self.plot_domain == self.SPECTRUM_DOMAIN:
            self.plot.set_spectrum(self._selected_spectrum(snapshot), f"espectro {label}", unit=unit)
            return
        values, unit, label = self._selected_values(snapshot)
        self.plot.set_time_series(snapshot.x_seconds, values, label, unit=unit)

    def _selected_spectrum(self, snapshot: ProcessedChannelSnapshot) -> SpectrumSnapshot:
        if self.display_mode == self.PROCESSED_MODE:
            return snapshot.processed_spectrum
        if self.display_mode == self.CONVERTED_MODE:
            return snapshot.converted_spectrum
        return snapshot.raw_spectrum

    def _selected_unit(self, snapshot: ProcessedChannelSnapshot) -> str:
        return (
            snapshot.conversion_input_unit
            if self.display_mode == self.RAW_MODE
            else snapshot.conversion_output_unit
        )

    def _update_metrics(self, snapshot: ProcessedChannelSnapshot) -> None:
        metrics = snapshot.metrics
        unit = snapshot.conversion_output_unit
        self.mean_label.setText(
            "Média: --" if metrics.mean is None else f"Média: {metrics.mean:g} {unit}"
        )
        self.rms_label.setText(
            "RMS: --" if metrics.rms is None else f"RMS: {metrics.rms:g} {unit}"
        )
        self.min_label.setText(
            "Mínimo: --" if metrics.minimum is None else f"Mínimo: {metrics.minimum:g} {unit}"
        )
        self.max_label.setText(
            "Máximo: --" if metrics.maximum is None else f"Máximo: {metrics.maximum:g} {unit}"
        )

    def _update_spectrum_info(self, snapshot: ProcessedChannelSnapshot) -> None:
        spectrum = self._selected_spectrum(snapshot)
        if spectrum.peak_frequency_hz is None:
            self.peak_frequency_label.setText("Pico: --")
            self.peak_magnitude_label.setText("Magnitude do pico: --")
            self.resolution_label.setText("Resolução: --")
            return

        unit = self._selected_unit(snapshot)
        self.peak_frequency_label.setText(f"Pico: {spectrum.peak_frequency_hz:g} Hz")
        self.peak_magnitude_label.setText(
            "Magnitude do pico: --"
            if spectrum.peak_magnitude is None
            else f"Magnitude do pico: {spectrum.peak_magnitude:g} {unit}"
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
        self.last_converted_value_label.setText("Último convertido: --")
        self.last_processed_value_label.setText("Último processado: --")
        self.last_time_label.setText("Último timestamp: --")
        self.conversion_status_label.setText("Status: --")
        self.active_filters_label.setText("Filtros ativos: nenhum")
        self.filter_status_label.setText("Status dos filtros: --")
        for label in (
            self.mean_label,
            self.rms_label,
            self.min_label,
            self.max_label,
            self.peak_frequency_label,
            self.peak_magnitude_label,
            self.resolution_label,
        ):
            text = label.text().split(":", 1)[0]
            label.setText(f"{text}: --")
