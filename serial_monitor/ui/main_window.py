from __future__ import annotations

from datetime import datetime

from PyQt5.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Janela mínima para validar a fundação do projeto.

    Nesta etapa a interface permite validar a SessionConfig, testar o parser
    de protocolo com um frame de exemplo e abrir a porta serial para inspecionar
    frames reais recebidos do microcontrolador.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Serial Monitor - Etapa 1")
        self.resize(950, 560)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(QLabel("Base limpa do projeto: sessão e protocolo serial."))

        form = QFormLayout()
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("/dev/ttyUSB0 ou COM3")
        self.baudrate_input = QLineEdit("115200")
        self.sample_rate_input = QLineEdit("1000")
        self.window_size_input = QLineEdit("1000")
        self.signal_order_input = QLineEdit("ecg,ppg,oximetria")
        self.sample_frame_input = QLineEdit("FRAME,1,1000,0.52,0.81,97")

        form.addRow("Porta", self.port_input)
        form.addRow("Baudrate", self.baudrate_input)
        form.addRow("Taxa base (Hz)", self.sample_rate_input)
        form.addRow("Janela", self.window_size_input)
        form.addRow("Sinais em ordem", self.signal_order_input)
        form.addRow("Frame de teste", self.sample_frame_input)
        root.addLayout(form)

        buttons = QHBoxLayout()
        self.validate_button = QPushButton("Validar sessão")
        self.validate_frame_button = QPushButton("Testar parser")
        self.connect_button = QPushButton("Conectar")
        self.disconnect_button = QPushButton("Desconectar")
        self.clear_log_button = QPushButton("Limpar log")
        self.disconnect_button.setEnabled(False)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.validate_frame_button)
        buttons.addWidget(self.connect_button)
        buttons.addWidget(self.disconnect_button)
        buttons.addWidget(self.clear_log_button)
        root.addLayout(buttons)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log)

    def append_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log.append(f"[{timestamp}] [{level}] {message}")
