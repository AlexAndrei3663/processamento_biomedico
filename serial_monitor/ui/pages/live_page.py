from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
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
    """Página de visualização ao vivo otimizada para telas pequenas."""

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
        outer_layout.addWidget(scroll_area)

        content_widget = QWidget()
        root = QVBoxLayout(content_widget)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        scroll_area.setWidget(content_widget)

        self._build_header(root)
        self._build_controls(root)
        self._build_recording_status(root)
        self._build_performance_controls(root, update_interval_ms, max_plot_points)
        self._build_signal_tabs(root)

        self.apply_update_interval_button.clicked.connect(
            lambda: self.update_interval_changed.emit(self.update_interval_spinbox.value())
        )
        self.fullscreen_button.clicked.connect(self.fullscreen_requested.emit)

    def _build_header(self, root: QVBoxLayout) -> None:
        title_line = QHBoxLayout()
        self.title_label = QLabel("Visualização ao vivo")
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        title_line.addWidget(self.title_label)
        title_line.addStretch(1)
        root.addLayout(title_line)

        navigation = QHBoxLayout()
        self.open_config_button = QPushButton("Configurações")
        self.open_stored_button = QPushButton("Sinais armazenados")
        self.fullscreen_button = QPushButton("Tela cheia / janela")
        self.back_menu_button = QPushButton("Menu")
        navigation.addWidget(self.open_config_button)
        navigation.addWidget(self.open_stored_button)
        navigation.addWidget(self.fullscreen_button)
        navigation.addWidget(self.back_menu_button)
        root.addLayout(navigation)

    def _build_controls(self, root: QVBoxLayout) -> None:
        controls_group = QGroupBox("Aquisição e gravação")
        controls = QGridLayout(controls_group)

        self.connect_button = QPushButton("Conectar")
        self.disconnect_button = QPushButton("Desconectar")
        self.clear_buffers_button = QPushButton("Limpar visualização")
        self.start_recording_button = QPushButton("Iniciar gravação")
        self.finalize_recording_button = QPushButton("Finalizar gravação")
        self.cancel_recording_button = QPushButton("Cancelar gravação")

        self.disconnect_button.setEnabled(False)
        self.finalize_recording_button.setEnabled(False)
        self.cancel_recording_button.setEnabled(False)

        controls.addWidget(self.connect_button, 0, 0)
        controls.addWidget(self.disconnect_button, 0, 1)
        controls.addWidget(self.clear_buffers_button, 0, 2)
        controls.addWidget(self.start_recording_button, 1, 0)
        controls.addWidget(self.finalize_recording_button, 1, 1)
        controls.addWidget(self.cancel_recording_button, 1, 2)
        root.addWidget(controls_group)

    def _build_recording_status(self, root: QVBoxLayout) -> None:
        recording_group = QGroupBox("Estado da sessão")
        recording_layout = QGridLayout(recording_group)
        self.recording_state_label = QLabel("Estado: inativa")
        self.recording_duration_label = QLabel("Duração: 00:00:00")
        self.recording_frames_label = QLabel("Frames: 0/0")
        self.recording_queue_label = QLabel("Fila: 0/0")
        self.recording_size_label = QLabel("Arquivo: 0 B")
        self.recording_path_label = QLabel("Caminho: --")
        self.recording_path_label.setWordWrap(True)
        self.recording_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        recording_layout.addWidget(self.recording_state_label, 0, 0)
        recording_layout.addWidget(self.recording_duration_label, 0, 1)
        recording_layout.addWidget(self.recording_frames_label, 0, 2)
        recording_layout.addWidget(self.recording_queue_label, 1, 0)
        recording_layout.addWidget(self.recording_size_label, 1, 1)
        recording_layout.addWidget(self.recording_path_label, 2, 0, 1, 3)
        root.addWidget(recording_group)

    def _build_performance_controls(
        self,
        root: QVBoxLayout,
        update_interval_ms: int,
        max_plot_points: int,
    ) -> None:
        performance_group = QGroupBox("Atualização da tela")
        performance = QHBoxLayout(performance_group)
        self.update_interval_label = QLabel("Intervalo (ms)")
        self.update_interval_spinbox = QSpinBox()
        self.update_interval_spinbox.setRange(50, 2000)
        self.update_interval_spinbox.setSingleStep(25)
        self.update_interval_spinbox.setValue(update_interval_ms)
        self.update_interval_spinbox.setAccelerated(True)
        self.apply_update_interval_button = QPushButton("Aplicar")
        self.performance_hint_label = QLabel(
            f"Máximo de {max_plot_points} pontos por curva."
        )
        self.performance_hint_label.setWordWrap(True)
        performance.addWidget(self.update_interval_label)
        performance.addWidget(self.update_interval_spinbox)
        performance.addWidget(self.apply_update_interval_button)
        performance.addStretch(1)
        performance.addWidget(self.performance_hint_label)
        root.addWidget(performance_group)

    def _build_signal_tabs(self, root: QVBoxLayout) -> None:
        live_group = QGroupBox("Sinais")
        live_layout = QVBoxLayout(live_group)
        self.live_tabs = QTabWidget()
        self.live_tabs.setDocumentMode(True)
        placeholder = QLabel("Configure e valide a sessão para criar as abas dos sinais.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        self.live_tabs.addTab(placeholder, "Sem sessão")
        self.live_tabs.currentChanged.connect(self._refresh_current_tab)
        live_layout.addWidget(self.live_tabs)
        root.addWidget(live_group, stretch=1)

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
        if status.state in {RecordingState.RECORDING, RecordingState.FAILED}:
            self.recording_state_label.setStyleSheet(
                "font-weight: 700; color: #b00020; font-size: 16px;"
            )
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
