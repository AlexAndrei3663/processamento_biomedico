from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from serial_monitor.domain.models import ProcessedAcquisitionSnapshot, SessionConfig
from serial_monitor.ui.widgets.signal_tab import SignalTab


class LivePage(QWidget):
    """Página de visualização ao vivo com abas por canal."""

    filter_toggled = pyqtSignal(int, str, bool)
    display_mode_changed = pyqtSignal(int, str)
    update_interval_changed = pyqtSignal(int)
    fullscreen_requested = pyqtSignal()

    def __init__(self, update_interval_ms: int = 100, max_plot_points: int = 5000) -> None:
        super().__init__()
        self.signal_tabs: Dict[int, SignalTab] = {}
        self.max_plot_points = max_plot_points

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content_widget = QWidget()
        root = QVBoxLayout(content_widget)

        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area)

        header = QHBoxLayout()
        self.title_label = QLabel("Visualização ao vivo")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.open_config_button = QPushButton("Configurações")
        self.back_menu_button = QPushButton("Menu")
        self.open_stored_button = QPushButton("Sinais armazenados")
        self.fullscreen_button = QPushButton("Tela cheia / janela")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.open_config_button)
        header.addWidget(self.open_stored_button)
        header.addWidget(self.fullscreen_button)
        header.addWidget(self.back_menu_button)
        root.addLayout(header)

        controls = QHBoxLayout()
        self.connect_button = QPushButton("Conectar")
        self.disconnect_button = QPushButton("Desconectar")
        self.clear_buffers_button = QPushButton("Limpar buffers")
        self.save_session_button = QPushButton("Salvar sessão")
        self.clear_log_button = QPushButton("Limpar log")
        self.disconnect_button.setEnabled(False)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        controls.addWidget(self.clear_buffers_button)
        controls.addWidget(self.save_session_button)
        controls.addStretch(1)
        controls.addWidget(self.clear_log_button)
        root.addLayout(controls)

        performance = QHBoxLayout()
        self.update_interval_label = QLabel("Intervalo da GUI (ms):")
        self.update_interval_spinbox = QSpinBox()
        self.update_interval_spinbox.setRange(50, 2000)
        self.update_interval_spinbox.setSingleStep(25)
        self.update_interval_spinbox.setValue(update_interval_ms)
        self.apply_update_interval_button = QPushButton("Aplicar intervalo")
        self.performance_hint_label = QLabel(
            f"Renderização limitada a {max_plot_points} pontos por curva para reduzir carga gráfica."
        )
        performance.addWidget(self.update_interval_label)
        performance.addWidget(self.update_interval_spinbox)
        performance.addWidget(self.apply_update_interval_button)
        performance.addStretch(1)
        performance.addWidget(self.performance_hint_label)
        root.addLayout(performance)

        splitter = QSplitter(Qt.Orientation.Vertical)

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

        self.apply_update_interval_button.clicked.connect(
            lambda: self.update_interval_changed.emit(self.update_interval_spinbox.value())
        )
        self.fullscreen_button.clicked.connect(self.fullscreen_requested.emit)

    def build_signal_tabs(self, session: SessionConfig, max_plot_points: int | None = None) -> None:
        if max_plot_points is not None:
            self.max_plot_points = max_plot_points
        self.live_tabs.clear()
        self.signal_tabs.clear()

        for channel in session.channels:
            tab = SignalTab(channel, max_plot_points=self.max_plot_points)
            tab.filter_toggled.connect(self.filter_toggled.emit)
            tab.display_mode_changed.connect(self.display_mode_changed.emit)
            self.signal_tabs[channel.index] = tab
            self.live_tabs.addTab(tab, f"ch{channel.index} - {channel.display_name}")

    def clear_signal_tabs(self) -> None:
        for tab in self.signal_tabs.values():
            tab.clear()

    def update_live_view(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
        if not snapshot.configured:
            return

        for index, channel_snapshot in snapshot.channels.items():
            tab = self.signal_tabs.get(index)
            if tab is not None:
                tab.update_from_snapshot(channel_snapshot)

    def update_buffer_summary(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
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
                if channel_snapshot.last_processed_value is None
                else f"{channel_snapshot.last_processed_value:g} {channel.unit}"
            )
            lines.append(
                f"  ch{channel.index} | {channel.display_name} ({channel.signal_type.value}) | "
                f"amostras={channel_snapshot.sample_count} | último={last_value}"
            )

        self.buffer_summary.setPlainText("\n".join(lines))
