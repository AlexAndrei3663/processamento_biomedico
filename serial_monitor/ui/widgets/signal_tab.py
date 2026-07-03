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
    AdcConfig,
    ProcessedChannelSnapshot,
    SignalChannelConfig,
    SpectrumSnapshot,
)
from serial_monitor.processing.filter_pipeline import FILTER_DEFINITIONS
from serial_monitor.processing.spectrum import convert_spectrum_to_dbfs
from serial_monitor.ui.widgets.signal_plot_widget import SignalPlotWidget


class SignalTab(QWidget):
    """Aba de um canal com sinal base, processado e navegação horizontal."""

    filter_toggled = pyqtSignal(int, str, bool)
    display_mode_changed = pyqtSignal(int, str)
    plot_domain_changed = pyqtSignal(int, str)

    BASE_MODE = "base"
    PROCESSED_MODE = "processed"
    TIME_DOMAIN = "time"
    SPECTRUM_DOMAIN = "spectrum"
    VERTICAL_AUTO = "auto"
    VERTICAL_FULL_SCALE = "full_scale"
    SPECTRUM_LINEAR = "linear"
    SPECTRUM_DBFS = "dbfs"

    def __init__(
        self,
        channel: SignalChannelConfig,
        max_plot_points: int = 5000,
        adc: AdcConfig | None = None,
    ) -> None:
        super().__init__()
        self.channel = channel
        self.display_mode = self.BASE_MODE
        self.plot_domain = self.TIME_DOMAIN
        self.vertical_scale_mode = self.VERTICAL_AUTO
        self.spectrum_scale = self.SPECTRUM_LINEAR
        self.adc = adc or AdcConfig()
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

        self.compact_channel_label = QLabel(f"ch{channel.index} — {channel.display_name}")
        self.compact_channel_label.setStyleSheet("font-weight: 600;")
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setMinimumSize(58, 40)
        self.zoom_out_button.setMaximumWidth(64)
        self.zoom_out_button.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.zoom_out_button.setToolTip("Reduz o zoom horizontal.")
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setMinimumSize(58, 40)
        self.zoom_in_button.setMaximumWidth(64)
        self.zoom_in_button.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.zoom_in_button.setToolTip("Amplia o zoom horizontal.")
        self.follow_signal_button = QPushButton("Seguir")
        self.follow_signal_button.setCheckable(True)
        self.follow_signal_button.setChecked(True)
        self.follow_signal_button.setMaximumWidth(110)
        self.follow_signal_button.setToolTip(
            "Mantém a janela temporal acompanhando o timestamp mais recente."
        )
        self.focus_plot_button = QPushButton("Focar")
        self.focus_plot_button.setCheckable(True)
        self.focus_plot_button.setMaximumWidth(120)

        toolbar.addWidget(self.compact_channel_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.follow_signal_button)
        toolbar.addWidget(self.focus_plot_button)
        root.addWidget(self.toolbar_widget)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        self.splitter.setMinimumSize(0, 0)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.addWidget(self.plot)

        self.side_scroll = QScrollArea()
        self.side_scroll.setWidgetResizable(True)
        self.side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.side_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.side_scroll.setMinimumWidth(235)
        self.side_scroll.setMaximumWidth(310)
        self.side_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        side_panel = QFrame()
        side_panel.setFrameShape(QFrame.StyledPanel)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(6, 6, 6, 6)
        side_layout.setSpacing(4)

        self.title_label = QLabel(f"<b>{channel.display_name}</b>")
        self.type_label = QLabel(f"Tipo: {channel.signal_type.value}")
        self.index_label = QLabel(f"Canal: ch{channel.index}")
        self.unit_label = QLabel(
            "Sinal base: "
            + (
                "tensão diferencial na entrada do ADC (V)"
                if channel.conversion_enabled
                else f"contagem bruta ({channel.raw_unit})"
            )
        )
        self.unit_label.setWordWrap(True)
        self.sample_rate_label = QLabel(f"Taxa: {channel.sample_rate_hz:g} Hz")
        self.sample_count_label = QLabel("Amostras: 0")
        self.last_base_value_label = QLabel("Último base: --")
        self.last_processed_value_label = QLabel("Último processado: --")
        self.last_time_label = QLabel("Último timestamp: --")
        for widget in (
            self.title_label,
            self.type_label,
            self.index_label,
            self.unit_label,
            self.sample_rate_label,
            self.sample_count_label,
            self.last_base_value_label,
            self.last_processed_value_label,
            self.last_time_label,
        ):
            side_layout.addWidget(widget)

        view_group = QGroupBox("Sinal exibido")
        view_layout = QVBoxLayout(view_group)
        self.base_radio = QRadioButton("Base")
        self.processed_radio = QRadioButton("Processado")
        self.base_radio.setChecked(True)
        self.view_button_group = QButtonGroup(self)
        for button in (self.base_radio, self.processed_radio):
            self.view_button_group.addButton(button)
            view_layout.addWidget(button)
        side_layout.addWidget(view_group)

        conversion_group = QGroupBox("Conversão configurada")
        conversion_layout = QVBoxLayout(conversion_group)
        self.conversion_profile_label = QLabel(
            "Base: " + ("tensão diferencial" if channel.conversion_enabled else "counts")
        )
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

        self.vertical_scale_group = QGroupBox("Escala vertical no tempo")
        vertical_scale_layout = QVBoxLayout(self.vertical_scale_group)
        self.vertical_auto_radio = QRadioButton("Automática")
        self.vertical_full_scale_radio = QRadioButton("Faixa completa do ADC")
        self.vertical_auto_radio.setChecked(True)
        self.vertical_scale_button_group = QButtonGroup(self)
        self.vertical_scale_button_group.addButton(self.vertical_auto_radio)
        self.vertical_scale_button_group.addButton(self.vertical_full_scale_radio)
        self.vertical_full_scale_radio.setToolTip(
            "Fixa o eixo Y entre os limites teóricos do ADS1256 para o ganho global."
        )
        vertical_scale_layout.addWidget(self.vertical_auto_radio)
        vertical_scale_layout.addWidget(self.vertical_full_scale_radio)
        side_layout.addWidget(self.vertical_scale_group)

        self.spectrum_scale_group = QGroupBox("Escala do espectro")
        spectrum_scale_layout = QVBoxLayout(self.spectrum_scale_group)
        self.spectrum_linear_radio = QRadioButton("Magnitude linear")
        self.spectrum_dbfs_radio = QRadioButton("dBFS")
        self.spectrum_linear_radio.setChecked(True)
        self.spectrum_scale_button_group = QButtonGroup(self)
        self.spectrum_scale_button_group.addButton(self.spectrum_linear_radio)
        self.spectrum_scale_button_group.addButton(self.spectrum_dbfs_radio)
        self.spectrum_dbfs_radio.setToolTip(
            "Mostra 20·log10(magnitude/escala completa do ADC), sem recalcular a FFT."
        )
        spectrum_scale_layout.addWidget(self.spectrum_linear_radio)
        spectrum_scale_layout.addWidget(self.spectrum_dbfs_radio)
        self.spectrum_scale_group.setEnabled(False)
        side_layout.addWidget(self.spectrum_scale_group)

        filter_group = QGroupBox("Filtros pré-definidos")
        filter_layout = QVBoxLayout(filter_group)
        if channel.default_filters:
            for filter_id in channel.default_filters:
                definition = FILTER_DEFINITIONS.get(filter_id)
                checkbox = QCheckBox(
                    definition.display_name if definition else filter_id
                )
                checkbox.setToolTip(
                    definition.description if definition else filter_id
                )
                checkbox.toggled.connect(
                    lambda checked, fid=filter_id: self.filter_toggled.emit(
                        self.channel.index, fid, checked
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

        spectrum_group = QGroupBox("Espectro exibido")
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

        self.base_radio.toggled.connect(self._on_display_mode_toggled)
        self.processed_radio.toggled.connect(self._on_display_mode_toggled)
        self.time_radio.toggled.connect(self._on_plot_domain_toggled)
        self.spectrum_radio.toggled.connect(self._on_plot_domain_toggled)
        self.vertical_auto_radio.toggled.connect(self._on_vertical_scale_toggled)
        self.vertical_full_scale_radio.toggled.connect(self._on_vertical_scale_toggled)
        self.spectrum_linear_radio.toggled.connect(self._on_spectrum_scale_toggled)
        self.spectrum_dbfs_radio.toggled.connect(self._on_spectrum_scale_toggled)
        self.toggle_spectrum_button.clicked.connect(self._toggle_spectrum)
        self.focus_plot_button.toggled.connect(self.set_plot_focused)
        self.zoom_in_button.clicked.connect(lambda: self.plot.zoom_horizontal(0.70))
        self.zoom_out_button.clicked.connect(lambda: self.plot.zoom_horizontal(1.40))
        self.follow_signal_button.toggled.connect(self.plot.set_follow_latest)
        self.plot.follow_mode_changed.connect(self._set_follow_button_state)

    @property
    def requires_spectrum(self) -> bool:
        return self.plot_domain == self.SPECTRUM_DOMAIN

    @property
    def spectrum_source(self) -> str:
        return "processed" if self.display_mode == self.PROCESSED_MODE else "base"

    def _set_follow_button_state(self, enabled: bool) -> None:
        self.follow_signal_button.blockSignals(True)
        self.follow_signal_button.setChecked(enabled)
        self.follow_signal_button.blockSignals(False)

    def _time_full_scale_range(self) -> tuple[float, float]:
        if self.channel.conversion_enabled:
            full_scale = float(self.adc.full_scale_voltage_v)
            return (-full_scale, full_scale)
        return (-8388608.0, 8388607.0)

    def _spectrum_reference_amplitude(self) -> float:
        if self.channel.conversion_enabled:
            return float(self.adc.full_scale_voltage_v)
        return 8388607.0

    def _on_vertical_scale_toggled(self) -> None:
        mode = (
            self.VERTICAL_FULL_SCALE
            if self.vertical_full_scale_radio.isChecked()
            else self.VERTICAL_AUTO
        )
        if mode == self.vertical_scale_mode:
            return
        self.vertical_scale_mode = mode
        self.plot.set_vertical_scale_mode(mode, self._time_full_scale_range())
        self._redraw_last_snapshot()

    def _on_spectrum_scale_toggled(self) -> None:
        scale = (
            self.SPECTRUM_DBFS
            if self.spectrum_dbfs_radio.isChecked()
            else self.SPECTRUM_LINEAR
        )
        if scale == self.spectrum_scale:
            return
        self.spectrum_scale = scale
        self._redraw_last_snapshot()

    def set_plot_focused(self, focused: bool) -> None:
        focused = bool(focused)
        if focused == self._plot_focused:
            return
        sizes = self.splitter.sizes()
        if focused:
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

    def set_fullscreen_mode(self, enabled: bool) -> None:
        self._fullscreen_mode = bool(enabled)
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2 if enabled else 4)

    def _on_display_mode_toggled(self) -> None:
        mode = self.PROCESSED_MODE if self.processed_radio.isChecked() else self.BASE_MODE
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
        is_time = domain == self.TIME_DOMAIN
        self.follow_signal_button.setVisible(is_time)
        self.vertical_scale_group.setEnabled(is_time)
        self.spectrum_scale_group.setEnabled(not is_time)
        self.toggle_spectrum_button.setText(
            "Mostrar tempo" if domain == self.SPECTRUM_DOMAIN else "Mostrar espectro"
        )
        self.plot_domain_changed.emit(self.channel.index, domain)
        self._redraw_last_snapshot()

    def _toggle_spectrum(self) -> None:
        if self.plot_domain == self.TIME_DOMAIN:
            self.spectrum_radio.setChecked(True)
        else:
            self.time_radio.setChecked(True)

    def update_from_snapshot(self, snapshot: ProcessedChannelSnapshot) -> None:
        self._last_snapshot = snapshot
        self.sample_count_label.setText(f"Amostras: {snapshot.sample_count}")
        self.conversion_profile_label.setText(f"Base: {snapshot.base_label}")
        self.conversion_status_label.setText(
            "Status: " + " | ".join(snapshot.conversion_status)
        )

        self.last_base_value_label.setText(
            "Último base: --"
            if snapshot.last_base_value is None
            else f"Último base: {snapshot.last_base_value:g} {snapshot.base_unit}"
        )
        self.last_processed_value_label.setText(
            "Último processado: --"
            if snapshot.last_processed_value is None
            else f"Último processado: {snapshot.last_processed_value:g} {snapshot.base_unit}"
        )
        self.last_time_label.setText(
            "Último timestamp: --"
            if snapshot.last_timestamp_us is None
            else f"Último timestamp: {snapshot.last_timestamp_us} µs"
        )

        active = set(snapshot.active_filters)
        for filter_id, checkbox in self.filter_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(filter_id in active)
            checkbox.blockSignals(False)
        if snapshot.active_filters:
            names = [
                FILTER_DEFINITIONS[fid].display_name
                if fid in FILTER_DEFINITIONS
                else fid
                for fid in snapshot.active_filters
            ]
            self.active_filters_label.setText("Filtros ativos: " + ", ".join(names))
        else:
            self.active_filters_label.setText("Filtros ativos: nenhum")
        self.filter_status_label.setText(
            "Status dos filtros: " + " | ".join(snapshot.filter_status)
        )
        self._update_metrics(snapshot)
        self._update_spectrum_info(snapshot)
        self._draw_snapshot(snapshot)

    def _redraw_last_snapshot(self) -> None:
        if self._last_snapshot is not None:
            self._update_spectrum_info(self._last_snapshot)
            self._draw_snapshot(self._last_snapshot)

    def _selected_values(self, snapshot: ProcessedChannelSnapshot):
        if self.display_mode == self.PROCESSED_MODE:
            return snapshot.processed_values, snapshot.base_unit, "processado"
        return snapshot.base_values, snapshot.base_unit, "base"

    def _selected_spectrum(self, snapshot: ProcessedChannelSnapshot) -> SpectrumSnapshot:
        return (
            snapshot.processed_spectrum
            if self.display_mode == self.PROCESSED_MODE
            else snapshot.base_spectrum
        )

    def _display_spectrum(self, snapshot: ProcessedChannelSnapshot) -> SpectrumSnapshot:
        spectrum = self._selected_spectrum(snapshot)
        if self.spectrum_scale == self.SPECTRUM_DBFS:
            return convert_spectrum_to_dbfs(
                spectrum,
                self._spectrum_reference_amplitude(),
            )
        return spectrum

    def _draw_snapshot(self, snapshot: ProcessedChannelSnapshot) -> None:
        values, unit, label = self._selected_values(snapshot)
        if self.plot_domain == self.SPECTRUM_DOMAIN:
            spectrum_unit = "dBFS" if self.spectrum_scale == self.SPECTRUM_DBFS else unit
            scale_label = "dBFS" if self.spectrum_scale == self.SPECTRUM_DBFS else "linear"
            self.plot.set_spectrum(
                self._display_spectrum(snapshot),
                f"espectro {label} — {scale_label}",
                unit=spectrum_unit,
            )
        else:
            self.plot.set_vertical_scale_mode(
                self.vertical_scale_mode,
                self._time_full_scale_range(),
            )
            self.plot.set_time_series(snapshot.x_seconds, values, label, unit=unit)

    def _update_metrics(self, snapshot: ProcessedChannelSnapshot) -> None:
        metrics = snapshot.metrics
        unit = snapshot.base_unit
        self.mean_label.setText("Média: --" if metrics.mean is None else f"Média: {metrics.mean:g} {unit}")
        self.rms_label.setText("RMS: --" if metrics.rms is None else f"RMS: {metrics.rms:g} {unit}")
        self.min_label.setText("Mínimo: --" if metrics.minimum is None else f"Mínimo: {metrics.minimum:g} {unit}")
        self.max_label.setText("Máximo: --" if metrics.maximum is None else f"Máximo: {metrics.maximum:g} {unit}")

    def _update_spectrum_info(self, snapshot: ProcessedChannelSnapshot) -> None:
        spectrum = self._display_spectrum(snapshot)
        if spectrum.peak_frequency_hz is None:
            self.peak_frequency_label.setText("Pico: --")
            self.peak_magnitude_label.setText("Magnitude do pico: --")
            self.resolution_label.setText("Resolução: --")
            return
        self.peak_frequency_label.setText(f"Pico: {spectrum.peak_frequency_hz:g} Hz")
        magnitude_unit = (
            "dBFS"
            if self.spectrum_scale == self.SPECTRUM_DBFS
            else snapshot.base_unit
        )
        self.peak_magnitude_label.setText(
            "Magnitude do pico: --"
            if spectrum.peak_magnitude is None
            else f"Magnitude do pico: {spectrum.peak_magnitude:g} {magnitude_unit}"
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
        self.last_base_value_label.setText("Último base: --")
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
            label.setText(f"{label.text().split(':', 1)[0]}: --")
