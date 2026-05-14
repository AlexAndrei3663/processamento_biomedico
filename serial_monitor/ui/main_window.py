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

from serial_monitor.domain.models import AcquisitionSnapshot


class MainWindow(QMainWindow):
    """Janela mínima para validar sessão, protocolo e buffers multicanais."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Serial Monitor - Etapa 2")
        self.resize(1050, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(QLabel("Etapa 2: sessão, protocolo serial e buffers multicanais."))

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
        self.ingest_frame_button = QPushButton("Inserir frame no buffer")
        self.connect_button = QPushButton("Conectar")
        self.disconnect_button = QPushButton("Desconectar")
        self.clear_buffers_button = QPushButton("Limpar buffers")
        self.clear_log_button = QPushButton("Limpar log")
        self.disconnect_button.setEnabled(False)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.validate_frame_button)
        buttons.addWidget(self.ingest_frame_button)
        buttons.addWidget(self.connect_button)
        buttons.addWidget(self.disconnect_button)
        buttons.addWidget(self.clear_buffers_button)
        buttons.addWidget(self.clear_log_button)
        root.addLayout(buttons)

        root.addWidget(QLabel("Resumo dos buffers"))
        self.buffer_summary = QTextEdit()
        self.buffer_summary.setReadOnly(True)
        self.buffer_summary.setMaximumHeight(190)
        root.addWidget(self.buffer_summary)

        root.addWidget(QLabel("Log"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log)

    def append_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log.append(f"[{timestamp}] [{level}] {message}")

    def update_buffer_summary(self, snapshot: AcquisitionSnapshot) -> None:
        if not snapshot.configured:
            self.buffer_summary.setPlainText("Aquisição ainda não configurada.")
            return

        lines = [
            f"Estado: {'rodando' if snapshot.running else 'parada'}",
            f"Frames recebidos: {snapshot.frames_received}",
            f"Gaps de sequência detectados: {snapshot.sequence_gaps}",
            f"Último seq: {snapshot.last_sequence_id}",
            f"Último timestamp_ms: {snapshot.last_timestamp_ms}",
            "",
            "Canais:",
        ]
        for index in sorted(snapshot.channels):
            channel_snapshot = snapshot.channels[index]
            channel = channel_snapshot.channel
            last_value = (
                "--"
                if channel_snapshot.last_value is None
                else f"{channel_snapshot.last_value:g} {channel.unit}"
            )
            lines.append(
                f"  ch{channel.index} | {channel.display_name} ({channel.signal_type.value}) | "
                f"amostras={channel_snapshot.sample_count} | último={last_value}"
            )

        self.buffer_summary.setPlainText("\n".join(lines))
