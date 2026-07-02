from __future__ import annotations

from typing import Iterable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.domain.models import StoredSessionSummary


class StoredPage(QWidget):
    """Página de navegação, exportação e exclusão de sessões finalizadas."""

    SESSION_ID_ROLE = Qt.ItemDataRole.UserRole + 1
    SUMMARY_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Sinais armazenados")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.back_menu_button = QPushButton("Menu")
        self.open_config_button = QPushButton("Configurações")
        self.open_live_button = QPushButton("Visualização ao vivo")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.open_config_button)
        header.addWidget(self.open_live_button)
        header.addWidget(self.back_menu_button)
        root.addLayout(header)

        content = QHBoxLayout()

        list_group = QGroupBox("Sessões disponíveis")
        list_layout = QVBoxLayout(list_group)
        self.sessions_list = QListWidget()
        self.refresh_button = QPushButton("Atualizar lista")
        self.verify_integrity_button = QPushButton("Verificar integridade")
        self.delete_selected_button = QPushButton("Excluir sessão")
        list_layout.addWidget(self.sessions_list)
        list_layout.addWidget(self.refresh_button)
        list_layout.addWidget(self.verify_integrity_button)
        list_layout.addWidget(self.delete_selected_button)

        details_side = QVBoxLayout()

        details_group = QGroupBox("Detalhes")
        details_layout = QVBoxLayout(details_group)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        details_layout.addWidget(self.details)
        details_side.addWidget(details_group, stretch=2)

        range_group = QGroupBox("Intervalo para visualização")
        range_form = QFormLayout(range_group)
        self.start_seconds_input = QDoubleSpinBox()
        self.start_seconds_input.setDecimals(3)
        self.start_seconds_input.setSingleStep(1.0)
        self.start_seconds_input.setSuffix(" s")
        self.duration_seconds_input = QDoubleSpinBox()
        self.duration_seconds_input.setDecimals(3)
        self.duration_seconds_input.setMinimum(0.001)
        self.duration_seconds_input.setSingleStep(1.0)
        self.duration_seconds_input.setSuffix(" s")
        self.max_points_input = QSpinBox()
        self.max_points_input.setRange(10, 100_000)
        self.max_points_input.setValue(3000)
        self.open_selected_button = QPushButton("Abrir intervalo")
        range_form.addRow("Início relativo:", self.start_seconds_input)
        range_form.addRow("Duração:", self.duration_seconds_input)
        range_form.addRow("Máximo de pontos:", self.max_points_input)
        range_form.addRow(self.open_selected_button)
        details_side.addWidget(range_group)

        export_group = QGroupBox("Exportação completa")
        export_layout = QVBoxLayout(export_group)
        self.export_csv_button = QPushButton("Exportar CSV")
        self.cancel_export_button = QPushButton("Cancelar exportação")
        self.cancel_export_button.setEnabled(False)
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_status_label = QLabel("Nenhuma exportação em andamento.")
        export_buttons = QHBoxLayout()
        export_buttons.addWidget(self.export_csv_button)
        export_buttons.addWidget(self.cancel_export_button)
        export_layout.addLayout(export_buttons)
        export_layout.addWidget(self.export_progress)
        export_layout.addWidget(self.export_status_label)
        details_side.addWidget(export_group)

        content.addWidget(list_group, stretch=1)
        content.addLayout(details_side, stretch=2)
        root.addLayout(content, stretch=1)

        self.sessions_list.currentItemChanged.connect(self._on_selection_changed)
        self.set_sessions([])

    @property
    def selected_session_id(self) -> str | None:
        item = self.sessions_list.currentItem()
        if item is None:
            return None
        value = item.data(self.SESSION_ID_ROLE)
        return str(value) if value else None

    @property
    def selected_summary(self) -> StoredSessionSummary | None:
        item = self.sessions_list.currentItem()
        if item is None:
            return None
        value = item.data(self.SUMMARY_ROLE)
        return value if isinstance(value, StoredSessionSummary) else None

    @property
    def selected_start_seconds(self) -> float:
        return float(self.start_seconds_input.value())

    @property
    def selected_duration_seconds(self) -> float:
        return float(self.duration_seconds_input.value())

    @property
    def selected_max_points(self) -> int:
        return int(self.max_points_input.value())

    def set_sessions(self, summaries: Iterable[StoredSessionSummary]) -> None:
        self.sessions_list.clear()
        summaries = list(summaries)
        if not summaries:
            self.sessions_list.addItem("Nenhuma sessão armazenada encontrada.")
            self._set_action_buttons_enabled(False)
            self.details.setPlainText(
                "Ainda não há sessões HDF5 em data/sessions.\n\n"
                "Sessões interrompidas são finalizadas automaticamente na próxima inicialização."
            )
            self._configure_range(None)
            return

        for summary in summaries:
            prefix = ""
            integrity = summary.integrity_status or "unknown"
            label = (
                f"{prefix}{summary.created_at} | {summary.frames_received} frames | "
                f"{summary.state} | integridade={integrity}"
            )
            item = QListWidgetItem(label)
            item.setData(self.SESSION_ID_ROLE, summary.session_id)
            item.setData(self.SUMMARY_ROLE, summary)
            item.setToolTip(str(summary.data_path))
            self.sessions_list.addItem(item)

        self.sessions_list.setCurrentRow(0)

    def set_details(self, text: str) -> None:
        self.details.setPlainText(text)

    def set_export_running(self, running: bool) -> None:
        self.export_csv_button.setEnabled(not running and self.selected_session_id is not None)
        self.cancel_export_button.setEnabled(running)
        self.sessions_list.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.delete_selected_button.setEnabled(not running and self.selected_session_id is not None)
        self.verify_integrity_button.setEnabled(not running and self.selected_session_id is not None)
        self.open_selected_button.setEnabled(not running and self.selected_session_id is not None)

    def update_export_progress(self, percent: int, completed: int, total: int) -> None:
        self.export_progress.setValue(max(0, min(100, int(percent))))
        self.export_status_label.setText(
            f"Exportando: {completed}/{total} frames ({percent}%)."
        )

    def finish_export(self, message: str, *, success: bool) -> None:
        self.set_export_running(False)
        if success:
            self.export_progress.setValue(100)
        self.export_status_label.setText(message)

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        self.open_selected_button.setEnabled(enabled)
        self.export_csv_button.setEnabled(enabled)
        self.delete_selected_button.setEnabled(enabled)
        self.verify_integrity_button.setEnabled(enabled)

    def _on_selection_changed(self, *_args: object) -> None:
        summary = self.selected_summary
        self._set_action_buttons_enabled(summary is not None)
        self._configure_range(summary)

    def _configure_range(self, summary: StoredSessionSummary | None) -> None:
        if summary is None:
            self.start_seconds_input.setRange(0.0, 0.0)
            self.duration_seconds_input.setRange(0.001, 0.001)
            self.duration_seconds_input.setValue(0.001)
            return

        span = max(0.001, summary.time_span_seconds)
        self.start_seconds_input.setRange(0.0, span)
        self.start_seconds_input.setValue(0.0)
        self.duration_seconds_input.setRange(0.001, span)
        self.duration_seconds_input.setValue(min(10.0, span))
