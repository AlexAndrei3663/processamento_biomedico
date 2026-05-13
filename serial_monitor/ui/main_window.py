from __future__ import annotations

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

    Nesta etapa a interface não executa o monitoramento completo; ela apenas
    expõe os campos necessários para montar uma SessionConfig e registrar os
    frames recebidos futuramente.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Serial Monitor - Etapa 1")
        self.resize(900, 500)

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

        form.addRow("Porta", self.port_input)
        form.addRow("Baudrate", self.baudrate_input)
        form.addRow("Taxa base (Hz)", self.sample_rate_input)
        form.addRow("Janela", self.window_size_input)
        form.addRow("Sinais em ordem", self.signal_order_input)
        root.addLayout(form)

        buttons = QHBoxLayout()
        self.validate_button = QPushButton("Validar sessão")
        self.connect_button = QPushButton("Conectar")
        self.disconnect_button = QPushButton("Desconectar")
        self.disconnect_button.setEnabled(False)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.connect_button)
        buttons.addWidget(self.disconnect_button)
        root.addLayout(buttons)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log)
