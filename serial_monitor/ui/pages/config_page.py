from __future__ import annotations

from typing import Iterable

import serial.tools.list_ports
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QDoubleSpinBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.app.signals_catalog import SIGNAL_PRESETS
from serial_monitor.domain.enums import SignalType
from serial_monitor.domain.models import AcquisitionSnapshot
from serial_monitor.infrastructure.storage.config_repository import SessionPreset


class ConfigPage(QWidget):
    """Página de configuração otimizada para telas pequenas e operação por toque."""

    update_interval_changed = pyqtSignal(int)

    SIGNAL_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1

    BAUDRATE_OPTIONS = (
        9600,
        19200,
        38400,
        57600,
        115200,
        230400,
        460800,
        921600,
    )
    SAMPLE_RATE_OPTIONS = (
        10,
        25,
        50,
        100,
        125,
        200,
        250,
        500,
        1000,
        2000,
        4000,
        8000,
    )
    PRESET_SLOTS = (
        "Projeto padrão",
        "Preset 1",
        "Preset 2",
        "Preset 3",
        "Preset 4",
        "Preset 5",
        "Preset 6",
        "Preset 7",
        "Preset 8",
    )


    def __init__(self) -> None:
        super().__init__()
        self._channel_conversion_configs: list[dict] = []
        self._updating_conversion_editor = False

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer_layout.addWidget(scroll_area)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        scroll_area.setWidget(content)

        title = QLabel("Configuração da sessão")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        root.addWidget(title)

        self._build_acquisition_group(root)
        self._build_display_update_group(root)
        self._build_channels_group(root)
        self._build_conversion_group(root)
        self._build_preset_group(root)
        self._build_buffer_summary_group(root)
        self._build_log_group(root)

        self.refresh_ports_button.clicked.connect(self.refresh_ports)
        self.add_channel_button.clicked.connect(self.add_selected_channel)
        self.remove_channel_button.clicked.connect(self.remove_selected_channel)
        self.move_channel_up_button.clicked.connect(lambda: self._move_selected_channel(-1))
        self.move_channel_down_button.clicked.connect(lambda: self._move_selected_channel(1))
        self.clear_channels_button.clicked.connect(self.clear_channels)
        self.apply_update_interval_button.clicked.connect(
            lambda: self.update_interval_changed.emit(self.update_interval_spinbox.value())
        )
        self.channel_order_list.currentRowChanged.connect(self._sync_conversion_editor)
        self.channel_base_mode_selector.currentIndexChanged.connect(
            self._on_channel_base_mode_changed
        )
        self.adc_reference_voltage_input.valueChanged.connect(
            lambda _value: self._refresh_conversion_details()
        )
        self.adc_gain_selector.currentIndexChanged.connect(
            lambda _index: self._refresh_conversion_details()
        )

        self.refresh_ports()
        self.set_channel_order(
            [SignalType.ECG, SignalType.PPG, SignalType.OXIMETRIA]
        )

    def _build_acquisition_group(self, root: QVBoxLayout) -> None:
        session_group = QGroupBox("Parâmetros da aquisição")
        session_layout = QVBoxLayout(session_group)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        port_line = QHBoxLayout()
        self.port_selector = QComboBox()
        self.port_selector.setPlaceholderText("Nenhuma porta encontrada")
        self.refresh_ports_button = QPushButton("Atualizar portas")
        port_line.addWidget(self.port_selector, stretch=3)
        port_line.addWidget(self.refresh_ports_button, stretch=2)

        self.baudrate_selector = QComboBox()
        for value in self.BAUDRATE_OPTIONS:
            self.baudrate_selector.addItem(str(value), value)
        self._select_combo_data(self.baudrate_selector, 115200)

        self.sample_rate_selector = QComboBox()
        for value in self.SAMPLE_RATE_OPTIONS:
            self.sample_rate_selector.addItem(f"{value} Hz", value)
        self._select_combo_data(self.sample_rate_selector, 1000)

        self.window_size_input = QSpinBox()
        self.window_size_input.setRange(100, 1_000_000)
        self.window_size_input.setSingleStep(100)
        self.window_size_input.setValue(1000)
        self.window_size_input.setAccelerated(True)

        form.addRow("Porta serial", port_line)
        form.addRow("Baudrate", self.baudrate_selector)
        form.addRow("Taxa base", self.sample_rate_selector)
        form.addRow("Janela de amostras", self.window_size_input)
        session_layout.addLayout(form)

        buttons = QHBoxLayout()
        self.validate_button = QPushButton("Validar sessão")
        self.go_live_button = QPushButton("Ir para visualização")
        self.back_menu_button = QPushButton("Voltar ao menu")
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.go_live_button)
        buttons.addWidget(self.back_menu_button)
        session_layout.addLayout(buttons)
        root.addWidget(session_group)

    def _build_display_update_group(self, root: QVBoxLayout) -> None:
        performance_group = QGroupBox("Atualização da tela")
        performance_layout = QFormLayout(performance_group)

        self.update_interval_spinbox = QSpinBox()
        self.update_interval_spinbox.setRange(50, 2000)
        self.update_interval_spinbox.setSingleStep(25)
        self.update_interval_spinbox.setValue(100)
        self.update_interval_spinbox.setSuffix(" ms")
        self.update_interval_spinbox.setAccelerated(True)

        self.apply_update_interval_button = QPushButton(
            "Aplicar intervalo de atualização"
        )
        self.performance_hint_label = QLabel(
            "Intervalos maiores reduzem o uso de CPU. A alteração afeta apenas "
            "a renderização, sem modificar a aquisição nem a gravação."
        )
        self.performance_hint_label.setWordWrap(True)

        performance_layout.addRow(
            "Intervalo entre atualizações",
            self.update_interval_spinbox,
        )
        performance_layout.addRow(self.apply_update_interval_button)
        performance_layout.addRow(self.performance_hint_label)
        root.addWidget(performance_group)

    def set_performance_settings(
        self,
        update_interval_ms: int,
        max_plot_points: int,
    ) -> None:
        self.update_interval_spinbox.setValue(
            max(50, min(2000, int(update_interval_ms)))
        )
        self.performance_hint_label.setText(
            "Intervalos maiores reduzem o uso de CPU. A alteração afeta somente "
            "a renderização, sem modificar aquisição ou gravação. "
            f"Máximo atual: {int(max_plot_points)} pontos por curva."
        )

    def _build_channels_group(self, root: QVBoxLayout) -> None:
        channels_group = QGroupBox("Canais da sessão")
        channels_layout = QVBoxLayout(channels_group)

        add_line = QHBoxLayout()
        self.available_signal_selector = QComboBox()
        for signal_type in SignalType:
            preset = SIGNAL_PRESETS[signal_type]
            self.available_signal_selector.addItem(
                f"{preset.display_name} ({signal_type.value})",
                signal_type.value,
            )
        self.add_channel_button = QPushButton("Adicionar canal")
        add_line.addWidget(self.available_signal_selector, stretch=3)
        add_line.addWidget(self.add_channel_button, stretch=2)
        channels_layout.addLayout(add_line)

        helper = QLabel(
            "A ordem abaixo define a ordem dos valores enviados pelo microcontrolador. "
            "É permitido adicionar mais de um canal do mesmo tipo."
        )
        helper.setWordWrap(True)
        channels_layout.addWidget(helper)

        self.channel_order_list = QListWidget()
        self.channel_order_list.setMinimumHeight(150)
        channels_layout.addWidget(self.channel_order_list)

        channel_buttons = QHBoxLayout()
        self.move_channel_up_button = QPushButton("Subir")
        self.move_channel_down_button = QPushButton("Descer")
        self.remove_channel_button = QPushButton("Remover")
        self.clear_channels_button = QPushButton("Limpar lista")
        channel_buttons.addWidget(self.move_channel_up_button)
        channel_buttons.addWidget(self.move_channel_down_button)
        channel_buttons.addWidget(self.remove_channel_button)
        channel_buttons.addWidget(self.clear_channels_button)
        channels_layout.addLayout(channel_buttons)
        root.addWidget(channels_group)

    def _build_conversion_group(self, root: QVBoxLayout) -> None:
        conversion_group = QGroupBox("Conversão da saída do ADS1256")
        conversion_layout = QVBoxLayout(conversion_group)

        helper = QLabel(
            "O microcontrolador envia a contagem bruta assinada do ADS1256. "
            "O ganho e a referência são únicos para todos os canais. Para cada "
            "canal, escolha se o sinal base será exibido em counts ou como tensão "
            "diferencial AINP-AINN. O arquivo HDF5 preserva sempre os counts brutos."
        )
        helper.setWordWrap(True)
        conversion_layout.addWidget(helper)

        adc_form = QFormLayout()
        self.adc_reference_voltage_input = QDoubleSpinBox()
        self.adc_reference_voltage_input.setRange(0.100, 5.000)
        self.adc_reference_voltage_input.setDecimals(3)
        self.adc_reference_voltage_input.setSingleStep(0.050)
        self.adc_reference_voltage_input.setValue(2.500)
        self.adc_reference_voltage_input.setSuffix(" V")
        self.adc_reference_voltage_input.setAccelerated(True)

        self.adc_gain_selector = QComboBox()
        for gain in (1, 2, 4, 8, 16, 32, 64):
            self.adc_gain_selector.addItem(f"PGA {gain}", gain)

        self.conversion_channel_label = QLabel("Nenhum canal selecionado")
        self.channel_base_mode_selector = QComboBox()
        self.channel_base_mode_selector.addItem("Contagem bruta", "raw")
        self.channel_base_mode_selector.addItem(
            "Tensão diferencial na entrada do ADC", "voltage"
        )
        self.channel_base_mode_selector.setEnabled(False)

        self.conversion_details_label = QLabel("Selecione um canal.")
        self.conversion_details_label.setWordWrap(True)

        adc_form.addRow("ADC", QLabel("ADS1256 — entrada diferencial"))
        adc_form.addRow("Tensão de referência", self.adc_reference_voltage_input)
        adc_form.addRow("Ganho global", self.adc_gain_selector)
        adc_form.addRow("Canal", self.conversion_channel_label)
        adc_form.addRow("Sinal base", self.channel_base_mode_selector)
        adc_form.addRow("Faixa nominal", self.conversion_details_label)
        conversion_layout.addLayout(adc_form)
        root.addWidget(conversion_group)

    @property
    def channel_conversion_configs(self) -> list[dict]:
        return [dict(item) for item in self._channel_conversion_configs]

    @property
    def adc_reference_voltage_v(self) -> float:
        return float(self.adc_reference_voltage_input.value())

    @property
    def adc_gain(self) -> int:
        value = self.adc_gain_selector.currentData()
        return int(value) if value is not None else 1

    def _sync_conversion_editor(self, row: int) -> None:
        self._updating_conversion_editor = True
        try:
            valid = 0 <= row < self.channel_order_list.count()
            self.channel_base_mode_selector.setEnabled(valid)
            if not valid:
                self.conversion_channel_label.setText("Nenhum canal selecionado")
                self.channel_base_mode_selector.setCurrentIndex(0)
                self.conversion_details_label.setText("Selecione um canal.")
                return

            signal_type = self._signal_type_at(row)
            preset = SIGNAL_PRESETS[signal_type]
            config = self._channel_conversion_configs[row]
            self.conversion_channel_label.setText(
                f"ch{row} — {preset.display_name} | entrada: {preset.raw_unit}"
            )
            mode = str(config.get("mode", "raw"))
            index = self.channel_base_mode_selector.findData(mode)
            self.channel_base_mode_selector.setCurrentIndex(max(0, index))
            self._refresh_conversion_details()
        finally:
            self._updating_conversion_editor = False

    def _on_channel_base_mode_changed(self, _index: int) -> None:
        if self._updating_conversion_editor:
            return
        row = self.channel_order_list.currentRow()
        if not 0 <= row < len(self._channel_conversion_configs):
            return
        mode = self.channel_base_mode_selector.currentData()
        self._channel_conversion_configs[row] = {
            "channel_index": row,
            "mode": str(mode or "raw"),
        }
        self._update_channel_item_label(row)
        self._refresh_conversion_details()

    def _refresh_conversion_details(self) -> None:
        full_scale = (
            2.0 * self.adc_reference_voltage_v / max(1, self.adc_gain)
        )
        row = self.channel_order_list.currentRow()
        if not 0 <= row < len(self._channel_conversion_configs):
            self.conversion_details_label.setText(
                f"Faixa diferencial nominal global: ±{full_scale:.6g} V."
            )
            return
        mode = str(self._channel_conversion_configs[row].get("mode", "raw"))
        if mode == "voltage":
            self.conversion_details_label.setText(
                f"Sinal base em volts; faixa nominal: -{full_scale:.6g} V a "
                f"+{full_scale:.6g} V. Conversão aplicada apenas à visualização "
                "e ao processamento."
            )
        else:
            self.conversion_details_label.setText(
                "Sinal base em counts assinados de 24 bits. A conversão para "
                f"tensão permanece disponível com a faixa global ±{full_scale:.6g} V."
            )

    def _signal_type_at(self, row: int) -> SignalType:
        item = self.channel_order_list.item(row)
        if item is None:
            return SignalType.from_text("")
        return SignalType.from_text(str(item.data(self.SIGNAL_TYPE_ROLE)))

    def _build_preset_group(self, root: QVBoxLayout) -> None:
        presets_group = QGroupBox("Presets de configuração")
        presets_layout = QVBoxLayout(presets_group)
        presets_form = QFormLayout()

        self.preset_name_selector = QComboBox()
        for name in self.PRESET_SLOTS:
            self.preset_name_selector.addItem(name, name)

        self.preset_selector = QComboBox()
        self.preset_selector.setPlaceholderText("Nenhum preset salvo")
        presets_form.addRow("Salvar no perfil", self.preset_name_selector)
        presets_form.addRow("Preset salvo", self.preset_selector)
        presets_layout.addLayout(presets_form)

        presets_buttons = QHBoxLayout()
        self.save_preset_button = QPushButton("Salvar preset")
        self.load_preset_button = QPushButton("Carregar preset")
        self.delete_preset_button = QPushButton("Excluir preset")
        self.refresh_presets_button = QPushButton("Atualizar presets")
        presets_buttons.addWidget(self.save_preset_button)
        presets_buttons.addWidget(self.load_preset_button)
        presets_buttons.addWidget(self.delete_preset_button)
        presets_buttons.addWidget(self.refresh_presets_button)
        presets_layout.addLayout(presets_buttons)
        root.addWidget(presets_group)


    def _build_buffer_summary_group(self, root: QVBoxLayout) -> None:
        summary_group = QGroupBox("Resumo dos buffers e da comunicação")
        summary_layout = QVBoxLayout(summary_group)
        self.buffer_summary = QPlainTextEdit()
        self.buffer_summary.setReadOnly(True)
        self.buffer_summary.setMinimumHeight(300)
        self.buffer_summary.setPlainText("Aquisição ainda não configurada.")
        summary_layout.addWidget(self.buffer_summary)
        root.addWidget(summary_group)

    def _build_log_group(self, root: QVBoxLayout) -> None:
        log_group = QGroupBox("Log de configuração e diagnóstico")
        log_layout = QVBoxLayout(log_group)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMinimumHeight(160)
        self.clear_log_button = QPushButton("Limpar log")
        log_layout.addWidget(self.log)
        log_layout.addWidget(self.clear_log_button)
        root.addWidget(log_group)

    @property
    def selected_port(self) -> str | None:
        value = self.port_selector.currentData()
        if value:
            return str(value)
        text = self.port_selector.currentText().strip()
        return text or None

    @property
    def selected_preset_name(self) -> str | None:
        value = self.preset_selector.currentData()
        if value:
            return str(value)
        text = self.preset_selector.currentText().strip()
        return text or None

    @property
    def preset_name(self) -> str:
        value = self.preset_name_selector.currentData()
        return str(value or self.preset_name_selector.currentText()).strip()

    @property
    def baudrate(self) -> int:
        return int(self.baudrate_selector.currentData())

    @property
    def sample_rate_hz(self) -> int:
        return int(self.sample_rate_selector.currentData())

    @property
    def window_size(self) -> int:
        return int(self.window_size_input.value())

    @property
    def signal_order_text(self) -> str:
        values: list[str] = []
        for row in range(self.channel_order_list.count()):
            item = self.channel_order_list.item(row)
            value = item.data(self.SIGNAL_TYPE_ROLE) if item is not None else None
            if value:
                values.append(str(value))
        return ",".join(values)


    def refresh_ports(self) -> None:
        ports = list(serial.tools.list_ports.comports())
        current = self.selected_port
        self.port_selector.clear()
        for port in ports:
            description = port.description or "porta serial"
            self.port_selector.addItem(f"{port.device} — {description}", port.device)

        if current:
            index = self.port_selector.findData(current)
            if index >= 0:
                self.port_selector.setCurrentIndex(index)
                return
        if self.port_selector.count() > 0:
            self.port_selector.setCurrentIndex(0)

    def set_presets(self, presets: list[SessionPreset]) -> None:
        current = self.selected_preset_name
        self.preset_selector.clear()
        for preset in presets:
            self.preset_selector.addItem(preset.name, preset.name)
            if self.preset_name_selector.findData(preset.name) < 0:
                self.preset_name_selector.addItem(preset.name, preset.name)

        if current:
            index = self.preset_selector.findData(current)
            if index >= 0:
                self.preset_selector.setCurrentIndex(index)
                return
        if self.preset_selector.count() > 0:
            self.preset_selector.setCurrentIndex(0)

    def apply_preset(self, preset: SessionPreset) -> None:
        if self.preset_name_selector.findData(preset.name) < 0:
            self.preset_name_selector.addItem(preset.name, preset.name)
        self._select_combo_data(self.preset_name_selector, preset.name)

        port_index = self.port_selector.findData(preset.port)
        if port_index >= 0:
            self.port_selector.setCurrentIndex(port_index)

        self._select_combo_data(self.baudrate_selector, preset.baudrate)
        self._select_combo_data(self.sample_rate_selector, preset.base_sample_rate_hz)
        self.window_size_input.setValue(preset.window_size)
        self.adc_reference_voltage_input.setValue(preset.adc_reference_voltage_v)
        self._select_combo_data(self.adc_gain_selector, preset.adc_gain)

        signal_types = [
            SignalType.from_text(item)
            for item in preset.signal_order_text.split(",")
            if item.strip()
        ]
        self.set_channel_order(signal_types, preset.channel_conversions)

    def add_selected_channel(self) -> None:
        value = self.available_signal_selector.currentData()
        if value is None:
            return
        self.add_channel(SignalType.from_text(str(value)))

    def add_channel(self, signal_type: SignalType) -> None:
        item = QListWidgetItem()
        item.setData(self.SIGNAL_TYPE_ROLE, signal_type.value)
        self.channel_order_list.addItem(item)
        self._channel_conversion_configs.append(
            {
                "channel_index": self.channel_order_list.count() - 1,
                "mode": "raw",
            }
        )
        self._refresh_channel_labels()
        self.channel_order_list.setCurrentRow(self.channel_order_list.count() - 1)

    def set_channel_order(
        self,
        signal_types: Iterable[SignalType],
        conversion_configs: list[dict] | None = None,
    ) -> None:
        self.channel_order_list.clear()
        self._channel_conversion_configs = []
        source_configs = list(conversion_configs or [])
        for index, signal_type in enumerate(signal_types):
            item = QListWidgetItem()
            item.setData(self.SIGNAL_TYPE_ROLE, signal_type.value)
            self.channel_order_list.addItem(item)
            source = source_configs[index] if index < len(source_configs) else {}
            mode = str(source.get("mode", "")).strip().lower()
            if mode not in {"raw", "voltage"}:
                mode = "voltage" if bool(source.get("enabled", False)) else "raw"
            self._channel_conversion_configs.append(
                {
                    "channel_index": index,
                    "mode": mode,
                }
            )
        self._refresh_channel_labels()
        if self.channel_order_list.count() > 0:
            self.channel_order_list.setCurrentRow(0)
        else:
            self._sync_conversion_editor(-1)

    def remove_selected_channel(self) -> None:
        row = self.channel_order_list.currentRow()
        if row < 0:
            return
        self.channel_order_list.takeItem(row)
        if row < len(self._channel_conversion_configs):
            self._channel_conversion_configs.pop(row)
        self._refresh_channel_labels()
        if self.channel_order_list.count() > 0:
            self.channel_order_list.setCurrentRow(min(row, self.channel_order_list.count() - 1))

    def clear_channels(self) -> None:
        self.channel_order_list.clear()
        self._channel_conversion_configs.clear()
        self._refresh_channel_labels()
        self._sync_conversion_editor(-1)

    def _move_selected_channel(self, offset: int) -> None:
        current = self.channel_order_list.currentRow()
        target = current + offset
        if current < 0 or target < 0 or target >= self.channel_order_list.count():
            return
        item = self.channel_order_list.takeItem(current)
        self.channel_order_list.insertItem(target, item)
        conversion = self._channel_conversion_configs.pop(current)
        self._channel_conversion_configs.insert(target, conversion)
        self.channel_order_list.setCurrentRow(target)
        self._refresh_channel_labels()

    def _refresh_channel_labels(self) -> None:
        for row in range(self.channel_order_list.count()):
            conversion = (
                self._channel_conversion_configs[row]
                if row < len(self._channel_conversion_configs)
                else {"mode": "raw"}
            )
            conversion["channel_index"] = row
            self._update_channel_item_label(row)
        self._sync_conversion_editor(self.channel_order_list.currentRow())

    def _update_channel_item_label(self, row: int) -> None:
        if not 0 <= row < self.channel_order_list.count():
            return
        item = self.channel_order_list.item(row)
        if item is None:
            return
        signal_type = SignalType.from_text(str(item.data(self.SIGNAL_TYPE_ROLE)))
        preset = SIGNAL_PRESETS[signal_type]
        conversion = (
            self._channel_conversion_configs[row]
            if row < len(self._channel_conversion_configs)
            else {"mode": "raw"}
        )
        marker = (
            " | base: tensão"
            if conversion.get("mode") == "voltage"
            else " | base: counts"
        )
        item.setText(
            f"ch{row} — {preset.display_name} ({signal_type.value}){marker}"
        )


    def update_buffer_summary(self, snapshot: AcquisitionSnapshot) -> None:
        if not snapshot.configured:
            self.buffer_summary.setPlainText("Aquisição ainda não configurada.")
            return

        stats = snapshot.communication
        lines = [
            f"Estado: {'rodando' if snapshot.running else 'parada'}",
            f"Frames válidos: {stats.valid_frames}",
            f"Frames inválidos: {stats.invalid_frames}",
            f"Erros de checksum: {stats.checksum_errors}",
            f"Timestamps não crescentes: {stats.timestamp_regressions}",
            f"Wraps de timestamp: {stats.timestamp_wraps}",
            f"Reinícios do dispositivo: {stats.device_resets}",
            "",
            "Sequência dos ciclos de aquisição:",
            f"  gaps={stats.sequence.gap_events}",
            f"  ausentes={stats.sequence.missing_items}",
            f"  duplicados={stats.sequence.duplicate_items}",
            f"  fora de ordem={stats.sequence.out_of_order_items}",
            "",
            f"Último seq: {snapshot.last_sequence_id}",
            f"Último timestamp_us: {snapshot.last_timestamp_us}",
            "",
            "Canais:",
        ]
        for index in sorted(snapshot.channels):
            channel_snapshot = snapshot.channels[index]
            channel = channel_snapshot.channel
            last_value = (
                "--"
                if channel_snapshot.last_value is None
                else f"{channel_snapshot.last_value:g} {channel.raw_unit}"
            )
            lines.append(
                f"  ch{channel.index} | {channel.display_name} ({channel.signal_type.value}) | "
                f"amostras={channel_snapshot.sample_count} | último={last_value}"
            )
        self.buffer_summary.setPlainText("\n".join(lines))

    def append_log(self, level: str, message: str) -> None:
        line = f"[{level}] {message}"
        self.log.appendPlainText(line)
        print(line, flush=True)

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
            return
        combo.addItem(str(value), value)
        combo.setCurrentIndex(combo.count() - 1)

    @staticmethod
    def _format_number(value: float) -> str:
        return f"{value:.12g}"
