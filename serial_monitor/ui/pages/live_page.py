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
    CommunicationStats,
    ProcessedAcquisitionSnapshot,
    RecordingStatus,
    SessionConfig,
    SystemResourceSnapshot,
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
    plot_domain_changed = pyqtSignal(int, str)
    active_channel_changed = pyqtSignal(int)
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
        recording_layout.setContentsMargins(6, 3, 6, 3)
        recording_layout.setHorizontalSpacing(8)
        recording_layout.setVerticalSpacing(1)

        # Linha 1: estado da persistência.
        self.recording_state_label = QLabel("Estado: inativa")
        self.recording_duration_label = QLabel("Duração: 00:00:00")
        self.recording_frames_label = QLabel("Frames: 0/0")
        self.recording_queue_label = QLabel("Fila: 0/0")
        self.recording_size_label = QLabel("Arquivo: 0 B")
        self.disk_free_label = QLabel("Disco livre: --")

        # Linha 2: integridade da comunicação e recursos da Raspberry Pi.
        self.missing_frames_label = QLabel("Ausentes: 0")
        self.invalid_frames_label = QLabel("Inválidos: 0")
        self.crc_errors_label = QLabel("CRC: n/d")
        self.cpu_label = QLabel("CPU: --")
        self.memory_label = QLabel("RAM: --")
        self.temperature_label = QLabel("Temp.: --")

        first_row = (
            self.recording_state_label,
            self.recording_duration_label,
            self.recording_frames_label,
            self.recording_queue_label,
            self.recording_size_label,
            self.disk_free_label,
        )
        second_row = (
            self.missing_frames_label,
            self.invalid_frames_label,
            self.crc_errors_label,
            self.cpu_label,
            self.memory_label,
            self.temperature_label,
        )
        for row, labels in enumerate((first_row, second_row)):
            for column, label in enumerate(labels):
                label.setMinimumWidth(0)
                label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                recording_layout.addWidget(label, row, column)
                recording_layout.setColumnStretch(column, 1)

        self.recording_path_label = QLabel("Destino: --")
        self.recording_path_label.setMinimumWidth(0)
        self.recording_path_label.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        self.recording_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        recording_layout.addWidget(self.recording_path_label, 2, 0, 1, 6)

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
        self.live_tabs.currentChanged.connect(self._on_current_tab_changed)

        live_layout.addWidget(self.live_tabs, stretch=1)
        root.addWidget(self.live_group, stretch=1)

    def set_fullscreen_mode(self, enabled: bool) -> None:
        """Ajusta apenas margens e espaçamentos para o modo de tela cheia.

        Todos os controles da faixa superior permanecem visíveis, incluindo
        Configuração, Sessões, Tela cheia e Menu. Os controles de conexão,
        gravação e o resumo da sessão também continuam disponíveis.
        """

        enabled = bool(enabled)
        if enabled == self._fullscreen_layout:
            return

        self._fullscreen_layout = enabled

        # Mantém a mesma composição da faixa superior nos dois modos.
        self.header_widget.setVisible(True)
        self.title_label.setVisible(True)
        self.navigation_widget.setVisible(True)
        self.open_config_button.setVisible(True)
        self.open_stored_button.setVisible(True)
        self.fullscreen_button.setVisible(True)
        self.back_menu_button.setVisible(True)

        # Aquisição, gravação e estado permanecem controláveis em tela cheia.
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
            tab.plot_domain_changed.connect(self.plot_domain_changed.emit)
            tab.set_fullscreen_mode(self._fullscreen_layout)
            self.signal_tabs[channel.index] = tab
            self.live_tabs.addTab(
                tab,
                f"ch{channel.index} - {channel.display_name}",
            )

    @property
    def current_channel_index(self) -> int | None:
        current_tab = self.live_tabs.currentWidget()
        return current_tab.channel.index if isinstance(current_tab, SignalTab) else None

    @property
    def current_display_mode(self) -> str:
        current_tab = self.live_tabs.currentWidget()
        return current_tab.display_mode if isinstance(current_tab, SignalTab) else "base"

    @property
    def current_plot_domain(self) -> str:
        current_tab = self.live_tabs.currentWidget()
        return current_tab.plot_domain if isinstance(current_tab, SignalTab) else "time"

    def _on_current_tab_changed(self, _tab_index: int) -> None:
        self._refresh_current_tab()
        channel_index = self.current_channel_index
        if channel_index is not None:
            self.active_channel_changed.emit(channel_index)

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
        if status.state == RecordingState.RECORDING:
            self.recording_state_label.setStyleSheet(
                "font-weight: 800; color: #b00020; font-size: 14px;"
            )
        elif status.state == RecordingState.FAILED:
            self.recording_state_label.setStyleSheet(
                "font-weight: 800; color: #b00020;"
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
            f"Fila: {status.queue_size}/{status.queue_capacity} "
            f"(máx. {status.queue_high_watermark})"
        )
        queue_ratio = (
            status.queue_size / status.queue_capacity
            if status.queue_capacity > 0
            else 0.0
        )
        self._set_warning_style(self.recording_queue_label, queue_ratio >= 0.80)

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

    def update_operational_status(
        self,
        communication: CommunicationStats,
        resources: SystemResourceSnapshot,
        *,
        crc_available: bool,
        minimum_free_disk_bytes: int = 0,
    ) -> None:
        """Atualiza perdas, integridade e recursos sem depender do repaint do gráfico."""

        self.missing_frames_label.setText(
            f"Ausentes: {communication.missing_frames}"
        )
        self.invalid_frames_label.setText(
            f"Inválidos: {communication.invalid_frames}"
        )
        self.crc_errors_label.setText(
            f"CRC: {communication.checksum_errors}" if crc_available else "CRC: n/d"
        )
        if not crc_available:
            self.crc_errors_label.setToolTip(
                "O protocolo FRAME_CSV atual não transporta CRC. O campo será "
                "ativado quando o protocolo com integridade for adotado."
            )

        self.disk_free_label.setText(
            f"Disco livre: {self._format_bytes(resources.disk_free_bytes)}"
        )
        disk_warning = (
            minimum_free_disk_bytes > 0
            and resources.disk_free_bytes < minimum_free_disk_bytes
        )
        self._set_warning_style(self.disk_free_label, disk_warning)

        self.cpu_label.setText(
            "CPU: --"
            if resources.cpu_percent is None
            else f"CPU: {resources.cpu_percent:.0f}%"
        )
        self.memory_label.setText(
            "RAM: --"
            if resources.memory_percent is None
            else f"RAM: {resources.memory_percent:.0f}%"
        )
        self.temperature_label.setText(
            "Temp.: --"
            if resources.temperature_c is None
            else f"Temp.: {resources.temperature_c:.1f} °C"
        )

        self._set_warning_style(
            self.cpu_label,
            resources.cpu_percent is not None and resources.cpu_percent >= 90.0,
        )
        self._set_warning_style(
            self.memory_label,
            resources.memory_percent is not None and resources.memory_percent >= 90.0,
        )
        self._set_warning_style(
            self.temperature_label,
            resources.temperature_c is not None and resources.temperature_c >= 75.0,
        )
        self._set_warning_style(
            self.missing_frames_label, communication.missing_frames > 0
        )
        self._set_warning_style(
            self.invalid_frames_label, communication.invalid_frames > 0
        )
        self._set_warning_style(
            self.crc_errors_label, crc_available and communication.checksum_errors > 0
        )

    @staticmethod
    def _set_warning_style(label: QLabel, warning: bool) -> None:
        label.setStyleSheet(
            "font-weight: 700; color: #b00020;" if warning else ""
        )

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(max(0, value))
        for unit in ("B", "KiB", "MiB", "GiB"):
            if size < 1024.0 or unit == "GiB":
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GiB"
