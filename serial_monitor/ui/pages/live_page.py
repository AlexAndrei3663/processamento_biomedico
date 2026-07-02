from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.domain.enums import RecordingState
from serial_monitor.domain.models import (
    ProcessedAcquisitionSnapshot,
    RecordingStatus,
    SessionConfig,
)
from serial_monitor.ui.widgets.signal_tab import SignalTab


class LivePage(QWidget):
    """Página de visualização ao vivo com abas e estado da gravação contínua."""

    filter_toggled = pyqtSignal(int, str, bool)
    display_mode_changed = pyqtSignal(int, str)
    update_interval_changed = pyqtSignal(int)
    fullscreen_requested = pyqtSignal()

    def __init__(self, update_interval_ms: int = 100, max_plot_points: int = 5000) -> None:
        super().__init__()
        self.signal_tabs: Dict[int, SignalTab] = {}
        self.max_plot_points = max_plot_points
        self._latest_snapshot: ProcessedAcquisitionSnapshot | None = None

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
        self.start_recording_button = QPushButton("Iniciar gravação")
        self.finalize_recording_button = QPushButton("Finalizar gravação")
        self.cancel_recording_button = QPushButton("Cancelar gravação")
        self.clear_log_button = QPushButton("Limpar log")
        self.disconnect_button.setEnabled(False)
        self.finalize_recording_button.setEnabled(False)
        self.cancel_recording_button.setEnabled(False)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        controls.addWidget(self.clear_buffers_button)
        controls.addWidget(self.start_recording_button)
        controls.addWidget(self.finalize_recording_button)
        controls.addWidget(self.cancel_recording_button)
        controls.addStretch(1)
        controls.addWidget(self.clear_log_button)
        root.addLayout(controls)

        recording_group = QGroupBox("Gravação contínua da sessão")
        recording_layout = QHBoxLayout(recording_group)
        self.recording_state_label = QLabel("Estado: inativa")
        self.recording_duration_label = QLabel("Duração: 00:00:00")
        self.recording_frames_label = QLabel("Frames: 0/0")
        self.recording_queue_label = QLabel("Fila: 0/0")
        self.recording_size_label = QLabel("Arquivo: 0 B")
        self.recording_path_label = QLabel("Caminho: --")
        self.recording_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        recording_layout.addWidget(self.recording_state_label)
        recording_layout.addWidget(self.recording_duration_label)
        recording_layout.addWidget(self.recording_frames_label)
        recording_layout.addWidget(self.recording_queue_label)
        recording_layout.addWidget(self.recording_size_label)
        recording_layout.addWidget(self.recording_path_label, stretch=1)
        root.addWidget(recording_group)

        performance = QHBoxLayout()
        self.update_interval_label = QLabel("Intervalo da GUI (ms):")
        self.update_interval_spinbox = QSpinBox()
        self.update_interval_spinbox.setRange(50, 2000)
        self.update_interval_spinbox.setSingleStep(25)
        self.update_interval_spinbox.setValue(update_interval_ms)
        self.apply_update_interval_button = QPushButton("Aplicar intervalo")
        self.performance_hint_label = QLabel(
            f"Renderização limitada a {max_plot_points} pontos por curva."
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
        self.live_tabs.addTab(
            QLabel("Configure e valide a sessão para criar as abas dos sinais."),
            "Sem sessão",
        )
        self.live_tabs.currentChanged.connect(self._refresh_current_tab)
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

    def build_signal_tabs(
        self,
        session: SessionConfig,
        max_plot_points: int | None = None,
    ) -> None:
        if max_plot_points is not None:
            self.max_plot_points = max_plot_points
        self._latest_snapshot = None
        self.live_tabs.clear()
        self.signal_tabs.clear()

        for channel in session.channels:
            tab = SignalTab(channel, max_plot_points=self.max_plot_points)
            tab.filter_toggled.connect(self.filter_toggled.emit)
            tab.display_mode_changed.connect(self.display_mode_changed.emit)
            self.signal_tabs[channel.index] = tab
            self.live_tabs.addTab(tab, f"ch{channel.index} - {channel.display_name}")

    def clear_signal_tabs(self) -> None:
        self._latest_snapshot = None
        for tab in self.signal_tabs.values():
            tab.clear()

    def update_live_view(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
        if not snapshot.configured:
            return
        self._latest_snapshot = snapshot
        self._refresh_current_tab()

    def _refresh_current_tab(self, _tab_index: int | None = None) -> None:
        if self._latest_snapshot is None:
            return
        current_tab = self.live_tabs.currentWidget()
        if not isinstance(current_tab, SignalTab):
            return
        channel_snapshot = self._latest_snapshot.channels.get(current_tab.channel.index)
        if channel_snapshot is not None:
            current_tab.update_from_snapshot(channel_snapshot)

    def update_recording_status(self, status: RecordingStatus) -> None:
        labels = {
            RecordingState.IDLE: "inativa",
            RecordingState.RECORDING: "GRAVANDO",
            RecordingState.FINALIZING: "finalizando",
            RecordingState.COMPLETED: "concluída",
            RecordingState.FAILED: "falha",
            RecordingState.CANCELLED: "cancelada",
        }
        self.recording_state_label.setText(f"Estado: {labels[status.state]}")
        if status.state == RecordingState.RECORDING:
            self.recording_state_label.setStyleSheet("font-weight: 700; color: #b00020;")
        elif status.state == RecordingState.FAILED:
            self.recording_state_label.setStyleSheet("font-weight: 700; color: #b00020;")
        else:
            self.recording_state_label.setStyleSheet("font-weight: 600;")

        seconds = max(0, int(status.duration_seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        self.recording_duration_label.setText(
            f"Duração: {hours:02d}:{minutes:02d}:{secs:02d}"
        )
        self.recording_frames_label.setText(
            f"Frames: {status.frames_written}/{status.frames_enqueued}"
        )
        self.recording_queue_label.setText(
            f"Fila: {status.queue_size}/{status.queue_capacity}"
        )
        self.recording_size_label.setText(
            f"Arquivo: {self._format_bytes(status.file_size_bytes)}"
        )
        path = status.output_path or status.partial_path
        path_text = str(path) if path is not None else "--"
        if status.error_message:
            path_text = f"{path_text} | erro: {status.error_message}"
        self.recording_path_label.setText(f"Caminho: {path_text}")

        active = status.state in {RecordingState.RECORDING, RecordingState.FINALIZING}
        self.start_recording_button.setEnabled(not active)
        self.finalize_recording_button.setEnabled(status.state == RecordingState.RECORDING)
        self.cancel_recording_button.setEnabled(status.state == RecordingState.RECORDING)

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(max(0, value))
        for unit in ("B", "KiB", "MiB", "GiB"):
            if size < 1024.0 or unit == "GiB":
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GiB"

    def update_buffer_summary(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
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
                if channel_snapshot.last_processed_value is None
                else f"{channel_snapshot.last_processed_value:g} {channel.unit}"
            )
            lines.append(
                f"  ch{channel.index} | {channel.display_name} ({channel.signal_type.value}) | "
                f"amostras={channel_snapshot.sample_count} | último={last_value}"
            )

        self.buffer_summary.setPlainText("\n".join(lines))
