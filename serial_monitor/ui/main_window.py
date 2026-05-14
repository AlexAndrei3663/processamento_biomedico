from __future__ import annotations

from datetime import datetime
from typing import Dict

from PyQt5.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt

from serial_monitor.domain.models import AcquisitionSnapshot, SessionConfig
from serial_monitor.ui.widgets.signal_tab import SignalTab


class MainWindow(QMainWindow):
    """Janela de validação da Etapa 3.

    A interface ainda é propositalmente simples, mas já possui abas de
    visualização ao vivo por canal. O objetivo desta etapa é validar o modelo de
    aquisição e a atualização dos gráficos antes da navegação final por páginas.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Serial Monitor - Etapa 3")
        self.resize(1220, 780)
        self.signal_tabs: Dict[int, SignalTab] = {}

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(QLabel("Etapa 3: visualização ao vivo com abas por sinal."))

        config_group = QGroupBox("Configuração da sessão")
        config_layout = QVBoxLayout(config_group)

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
        config_layout.addLayout(form)

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
        config_layout.addLayout(buttons)

        root.addWidget(config_group)

        splitter = QSplitter(Qt.Vertical)

        live_group = QGroupBox("Visualização ao vivo")
        live_layout = QVBoxLayout(live_group)
        self.live_tabs = QTabWidget()
        self.live_tabs.setDocumentMode(True)
        self.live_tabs.addTab(QLabel("Valide a sessão para criar as abas dos sinais."), "Sem sessão")
        live_layout.addWidget(self.live_tabs)
        splitter.addWidget(live_group)

        diagnostics_widget = QWidget()
        diagnostics_layout = QHBoxLayout(diagnostics_widget)

        summary_group = QGroupBox("Resumo dos buffers")
        summary_layout = QVBoxLayout(summary_group)
        self.buffer_summary = QTextEdit()
        self.buffer_summary.setReadOnly(True)
        summary_layout.addWidget(self.buffer_summary)

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        log_layout.addWidget(self.log)

        diagnostics_layout.addWidget(summary_group, stretch=1)
        diagnostics_layout.addWidget(log_group, stretch=2)
        splitter.addWidget(diagnostics_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, stretch=1)

    def append_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log.append(f"[{timestamp}] [{level}] {message}")

    def build_signal_tabs(self, session: SessionConfig) -> None:
        self.live_tabs.clear()
        self.signal_tabs.clear()

        for channel in session.channels:
            tab = SignalTab(channel)
            self.signal_tabs[channel.index] = tab
            self.live_tabs.addTab(tab, f"ch{channel.index} - {channel.display_name}")

    def clear_signal_tabs(self) -> None:
        for tab in self.signal_tabs.values():
            tab.clear()

    def update_live_view(self, snapshot: AcquisitionSnapshot) -> None:
        if not snapshot.configured:
            return

        for index, channel_snapshot in snapshot.channels.items():
            tab = self.signal_tabs.get(index)
            if tab is not None:
                tab.update_from_snapshot(channel_snapshot)

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
