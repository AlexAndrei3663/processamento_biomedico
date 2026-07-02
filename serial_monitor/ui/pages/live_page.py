from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
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
    """Página de visualização ao vivo para telas de 1024 x 600 pixels.

    A página usa três faixas compactas acima do gráfico:

    1. navegação;
    2. aquisição e gravação;
    3. estado resumido da gravação.

    Os controles de gravação permanecem visíveis também em tela cheia. A área
    do gráfico recebe todo o espaço restante e não usa rolagem global, evitando
    que a página ultrapasse as dimensões físicas da tela.
    """

    filter_toggled = pyqtSignal(int, str, bool)
    display_mode_changed = pyqtSignal(int, str)
    fullscreen_requested = pyqtSignal()

    def __init__(
        self,
        update_interval_ms: int = 100,
        max_plot_points: int = 5000,
    ) -> None:
        super().__init__()
        self.setObjectName("livePage")

        self.signal_tabs: Dict[int, SignalTab] = {}
        self.max_plot_points = max_plot_points
        self._latest_snapshot: ProcessedAcquisitionSnapshot | None = None
        self._fullscreen_layout = False

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(5, 5, 5, 5)
        self.root.setSpacing(4)

        self._build_header(self.root)
        self._build_controls(self.root)
        self._build_recording_status(self.root)
        self._build_signal_tabs(self.root)

        # Mantido no construtor por compatibilidade com MainWindow. O intervalo
        # é configurado na página de configuração.
        _ = update_interval_ms

        self.fullscreen_button.clicked.connect(self.fullscreen_requested.emit)

    def _build_header(self, root: QVBoxLayout) -> None:
        self.header_widget = QWidget()
        self.header_widget.setObjectName("liveHeader")
        self.header_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self.title_label = QLabel("Visualização ao vivo")
        self.title_label.setStyleSheet("font-size: 17px; font-weight: 700;")
        header_layout.addWidget(self.title_label)

        self.navigation_widget = QWidget()
        navigation = QHBoxLayout(self.navigation_widget)
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(4)

        self.open_config_button = QPushButton("Config.")
        self.open_config_button.setToolTip("Abrir a configuração da sessão.")
        self.open_stored_button = QPushButton("Sessões")
        self.open_stored_button.setToolTip("Abrir os sinais armazenados.")
        self.fullscreen_button = QPushButton("Tela cheia")
        self.back_menu_button = QPushButton("Menu")

        navigation.addWidget(self.open_config_button)
        navigation.addWidget(self.open_stored_button)
        navigation.addWidget(self.fullscreen_button)
        navigation.addWidget(self.back_menu_button)

        header_layout.addStretch(1)
        header_layout.addWidget(self.navigation_widget)
        root.addWidget(self.header_widget)

    def _build_controls(self, root: QVBoxLayout) -> None:
        self.controls_group = QFrame()
        self.controls_group.setObjectName("liveControlsPanel")
        self.controls_group.setFrameShape(QFrame.StyledPanel)
        self.controls_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        controls = QGridLayout(self.controls_group)
        controls.setContentsMargins(5, 4, 5, 4)
        controls.setHorizontalSpacing(4)
        controls.setVerticalSpacing(0)

        self.connect_button = QPushButton("Conectar")
        self.disconnect_button = QPushButton("Desconectar")
        self.clear_buffers_button = QPushButton("Limpar")
        self.start_recording_button = QPushButton("Gravar")
        self.finalize_recording_button = QPushButton("Finalizar")
        self.cancel_recording_button = QPushButton("Cancelar")

        self.clear_buffers_button.setToolTip(
            "Limpa somente a janela de visualização, sem apagar a sessão gravada."
        )
        self.start_recording_button.setToolTip("Iniciar a gravação da sessão.")
        self.finalize_recording_button.setToolTip(
            "Finalizar e salvar a sessão gravada."
        )
        self.cancel_recording_button.setToolTip("Cancelar a gravação atual.")

        self.disconnect_button.setEnabled(False)
        self.finalize_recording_button.setEnabled(False)
        self.cancel_recording_button.setEnabled(False)

        buttons = (
            self.connect_button,
            self.disconnect_button,
            self.clear_buffers_button,
            self.start_recording_button,
            self.finalize_recording_button,
            self.cancel_recording_button,
        )
        for column, button in enumerate(buttons):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            controls.addWidget(button, 0, column)
            controls.setColumnStretch(column, 1)

        root.addWidget(self.controls_group)

    def _build_recording_status(self, root: QVBoxLayout) -> None:
        self.recording_group = QFrame()
        self.recording_group.setObjectName("recordingStatusPanel")
        self.recording_group.setFrameShape(QFrame.StyledPanel)
        self.recording_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        recording_layout = QGridLayout(self.recording_group)
        recording_layout.setContentsMargins(6, 4, 6, 4)
        recording_layout.setHorizontalSpacing(8)
        recording_layout.setVerticalSpacing(0)

        self.recording_state_label = QLabel("Estado: inativa")
        self.recording_duration_label = QLabel("Duração: 00:00:00")
        self.recording_frames_label = QLabel("Frames: 0/0")
        self.recording_queue_label = QLabel("Fila: 0/0")
        self.recording_size_label = QLabel("Arquivo: 0 B")
        self.recording_path_label = QLabel("Destino: --")
        self.recording_path_label.setMinimumWidth(0)
        self.recording_path_label.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        self.recording_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        labels = (
            self.recording_state_label,
            self.recording_duration_label,
            self.recording_frames_label,
            self.recording_queue_label,
            self.recording_size_label,
            self.recording_path_label,
        )
        for column, label in enumerate(labels):
            label.setMinimumWidth(0)
            recording_layout.addWidget(label, 0, column)
            recording_layout.setColumnStretch(column, 2 if column == 5 else 1)

        root.addWidget(self.recording_group)

    def _build_signal_tabs(self, root: QVBoxLayout) -> None:
        self.live_group = QFrame()
        self.live_group.setObjectName("liveSignalPanel")
        self.live_group.setMinimumSize(0, 0)
        self.live_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        live_layout = QVBoxLayout(self.live_group)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_layout.setSpacing(0)

        self.live_tabs = QTabWidget()
        self.live_tabs.setDocumentMode(True)
        self.live_tabs.setMinimumSize(0, 0)
        self.live_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        placeholder = QLabel(
            "Configure e valide a sessão para criar as abas dos sinais."
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        self.live_tabs.addTab(placeholder, "Sem sessão")
        self.live_tabs.currentChanged.connect(self._refresh_current_tab)

        live_layout.addWidget(self.live_tabs, stretch=1)
        root.addWidget(self.live_group, stretch=1)

    def set_fullscreen_mode(self, enabled: bool) -> None:
        """Ajusta o layout sem ocultar aquisição ou gravação.

        Em tela cheia, somente o título e os atalhos de navegação secundários
        são ocultados. Os botões de conexão, gravação, finalização e cancelamento
        e o estado da sessão permanecem visíveis.
        """

        enabled = bool(enabled)
        if enabled == self._fullscreen_layout:
            return

        self._fullscreen_layout = enabled
        self.title_label.setVisible(not enabled)
        self.open_config_button.setVisible(not enabled)
        self.open_stored_button.setVisible(not enabled)
        self.back_menu_button.setVisible(not enabled)

        # A gravação deve continuar controlável na tela cheia.
        self.controls_group.setVisible(True)
        self.recording_group.setVisible(True)

        self.fullscreen_button.setText(
            "Sair da tela cheia" if enabled else "Tela cheia"
        )
        self.root.setContentsMargins(*(2, 2, 2, 2) if enabled else (5, 5, 5, 5))
        self.root.setSpacing(2 if enabled else 4)

        for tab in self.signal_tabs.values():
            tab.set_fullscreen_mode(enabled)

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
            tab.set_fullscreen_mode(self._fullscreen_layout)
            self.signal_tabs[channel.index] = tab
            self.live_tabs.addTab(
                tab,
                f"ch{channel.index} - {channel.display_name}",
            )

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

        channel_snapshot = self._latest_snapshot.channels.get(
            current_tab.channel.index
        )
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
                "font-weight: 700; color: #b00020; font-size: 14px;"
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
        full_path = str(path) if path is not None else "--"
        display_name = getattr(path, "name", None) or full_path
        self.recording_path_label.setText(f"Destino: {display_name}")

        tooltip = full_path
        if status.error_message:
            tooltip = f"{tooltip}\nErro: {status.error_message}"
        self.recording_path_label.setToolTip(tooltip)

        active = status.state in {
            RecordingState.RECORDING,
            RecordingState.FINALIZING,
        }
        self.start_recording_button.setEnabled(not active)
        self.finalize_recording_button.setEnabled(
            status.state == RecordingState.RECORDING
        )
        self.cancel_recording_button.setEnabled(
            status.state == RecordingState.RECORDING
        )

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(max(0, value))
        for unit in ("B", "KiB", "MiB", "GiB"):
            if size < 1024.0 or unit == "GiB":
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GiB"
