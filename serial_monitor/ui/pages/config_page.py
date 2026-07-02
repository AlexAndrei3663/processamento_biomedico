from __future__ import annotations

import serial.tools.list_ports
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.infrastructure.storage.config_repository import SessionPreset


class ConfigPage(QWidget):
    """Página de configuração da sessão, presets e validação manual do protocolo."""

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        title = QLabel("Configuração da sessão")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(title)

        session_group = QGroupBox("Parâmetros da aquisição")
        session_layout = QVBoxLayout(session_group)

        form = QFormLayout()
        port_line = QHBoxLayout()
        self.port_selector = QComboBox()
        self.port_selector.setPlaceholderText("Selecione a porta")
        self.refresh_ports_button = QPushButton("Atualizar portas")
        port_line.addWidget(self.port_selector, stretch=3)
        port_line.addWidget(self.refresh_ports_button, stretch=1)

        self.baudrate_input = QLineEdit("115200")
        self.sample_rate_input = QLineEdit("1000")
        self.window_size_input = QLineEdit("1000")
        self.signal_order_input = QLineEdit("ecg,ppg,oximetria")

        self.baudrate_input.setValidator(QIntValidator(1, 10_000_000))
        self.sample_rate_input.setValidator(QIntValidator(1, 1_000_000))
        self.window_size_input.setValidator(QIntValidator(10, 1_000_000))

        form.addRow("Porta serial", port_line)
        form.addRow("Baudrate", self.baudrate_input)
        form.addRow("Taxa base (Hz)", self.sample_rate_input)
        form.addRow("Janela de amostras", self.window_size_input)
        form.addRow("Sinais em ordem", self.signal_order_input)
        session_layout.addLayout(form)

        session_buttons = QHBoxLayout()
        self.validate_button = QPushButton("Validar sessão")
        self.go_live_button = QPushButton("Ir para visualização")
        self.back_menu_button = QPushButton("Voltar ao menu")
        session_buttons.addWidget(self.validate_button)
        session_buttons.addWidget(self.go_live_button)
        session_buttons.addWidget(self.back_menu_button)
        session_layout.addLayout(session_buttons)

        root.addWidget(session_group)

        presets_group = QGroupBox("Presets de configuração")
        presets_layout = QVBoxLayout(presets_group)
        presets_form = QFormLayout()
        self.preset_name_input = QLineEdit("Projeto padrão")
        self.preset_selector = QComboBox()
        self.preset_selector.setPlaceholderText("Selecione um preset")
        presets_form.addRow("Nome do preset", self.preset_name_input)
        presets_form.addRow("Presets salvos", self.preset_selector)
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

        protocol_group = QGroupBox("Validação manual do protocolo")
        protocol_layout = QVBoxLayout(protocol_group)
        protocol_form = QFormLayout()
        self.sample_frame_input = QLineEdit("FRAME,1,1000000,0.52,0.81,97")
        protocol_form.addRow("Frame de teste", self.sample_frame_input)
        protocol_layout.addLayout(protocol_form)

        protocol_buttons = QHBoxLayout()
        self.validate_frame_button = QPushButton("Testar parser")
        self.ingest_frame_button = QPushButton("Inserir frame no buffer")
        self.clear_buffers_button = QPushButton("Limpar buffers")
        protocol_buttons.addWidget(self.validate_frame_button)
        protocol_buttons.addWidget(self.ingest_frame_button)
        protocol_buttons.addWidget(self.clear_buffers_button)
        protocol_layout.addLayout(protocol_buttons)

        root.addWidget(protocol_group)

        log_group = QGroupBox("Log de configuração")
        log_layout = QVBoxLayout(log_group)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.clear_log_button = QPushButton("Limpar log")
        log_layout.addWidget(self.log)
        log_layout.addWidget(self.clear_log_button)

        root.addWidget(log_group, stretch=1)

        self.refresh_ports_button.clicked.connect(self.refresh_ports)
        self.refresh_ports()

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

    def set_presets(self, presets: list[SessionPreset]) -> None:
        current = self.selected_preset_name
        self.preset_selector.clear()
        for preset in presets:
            self.preset_selector.addItem(preset.name, preset.name)
        if current:
            index = self.preset_selector.findData(current)
            if index >= 0:
                self.preset_selector.setCurrentIndex(index)

    def apply_preset(self, preset: SessionPreset) -> None:
        self.preset_name_input.setText(preset.name)
        self.port_selector.setCurrentText(preset.port)
        self.baudrate_input.setText(str(preset.baudrate))
        self.sample_rate_input.setText(str(preset.base_sample_rate_hz))
        self.window_size_input.setText(str(preset.window_size))
        self.signal_order_input.setText(preset.signal_order_text)

    def refresh_ports(self) -> None:
        ports = serial.tools.list_ports.comports()
        current = self.port_selector.currentText()

        self.port_selector.clear()
        for port in ports:
            self.port_selector.addItem(port.device, port.device)
        
        if current:
            index = self.port_selector.findData(current)
            if index >= 0:
                self.port_selector.setCurrentIndex(index)
        else:
            self.port_selector.setCurrentIndex(0 if ports else -1)


    def append_log(self, level: str, message: str) -> None:
        line = f"[{level}] {message}"
        self.log.append(line)
        print(line, flush=True)