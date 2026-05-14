from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.domain.models import AcquisitionSnapshot, SessionConfig
from serial_monitor.ui.widgets.signal_tab import SignalTab


class LivePage(QWidget):
    """Página de visualização ao vivo com abas por canal."""

    def __init__(self) -> None:
        super().__init__()
        self.signal_tabs: Dict[int, SignalTab] = {}

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        self.title_label = QLabel("Visualização ao vivo")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.open_config_button = QPushButton("Configurações")
        self.back_menu_button = QPushButton("Menu")
        self.open_stored_button = QPushButton("Sinais armazenados")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.open_config_button)
        header.addWidget(self.open_stored_button)
        header.addWidget(self.back_menu_button)
        root.addLayout(header)

        controls = QHBoxLayout()
        self.connect_button = QPushButton("Conectar")
        self.disconnect_button = QPushButton("Desconectar")
        self.clear_buffers_button = QPushButton("Limpar buffers")
        self.clear_log_button = QPushButton("Limpar log")
        self.disconnect_button.setEnabled(False)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        controls.addWidget(self.clear_buffers_button)
        controls.addStretch(1)
        controls.addWidget(self.clear_log_button)
        root.addLayout(controls)

        splitter = QSplitter(Qt.Vertical)

        live_group = QGroupBox("Sinais")
        live_layout = QVBoxLayout(live_group)
        self.live_tabs = QTabWidget()
        self.live_tabs.setDocumentMode(True)
        self.live_tabs.addTab(QLabel("Configure e valide a sessão para criar as abas dos sinais."), "Sem sessão")
        live_layout.addWidget(self.live_tabs)
        splitter.addWidget(live_group)

        diagnostics_widget = QWidget()
        diagnostics_layout = QHBoxLayout(diagnostics_widget)

        summary_group = QGroupBox("Resumo dos buffers")
        summary_layout = QVBoxLayout(summary_group)
        self.buffer_summary = QTextEdit()
        self.buffer_summary.setReadOnly(True)
        summary_layout.addWidget(self.buffer_summary)

        log_group = QGroupBox("Log da aquisição")
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
