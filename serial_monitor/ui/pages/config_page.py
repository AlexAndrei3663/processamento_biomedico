from __future__ import annotations

from PyQt5.QtWidgets import (
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


class ConfigPage(QWidget):
    """Página de configuração da sessão e validação manual do protocolo."""

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Configuração da sessão"))

        session_group = QGroupBox("Parâmetros da aquisição")
        session_layout = QVBoxLayout(session_group)

        form = QFormLayout()
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("/dev/ttyUSB0 ou COM3")
        self.baudrate_input = QLineEdit("115200")
        self.sample_rate_input = QLineEdit("1000")
        self.window_size_input = QLineEdit("1000")
        self.signal_order_input = QLineEdit("ecg,ppg,oximetria")

        form.addRow("Porta serial", self.port_input)
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

        protocol_group = QGroupBox("Validação manual do protocolo")
        protocol_layout = QVBoxLayout(protocol_group)
        protocol_form = QFormLayout()
        self.sample_frame_input = QLineEdit("FRAME,1,1000,0.52,0.81,97")
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
