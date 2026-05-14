from __future__ import annotations

from typing import Iterable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial_monitor.infrastructure.storage.session_repository import StoredSessionSummary


class StoredPage(QWidget):
    """Página de listagem e abertura de sessões armazenadas."""

    SESSION_ID_ROLE = Qt.UserRole + 1

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
        self.open_selected_button = QPushButton("Abrir sessão")
        self.open_selected_button.setEnabled(False)
        list_layout.addWidget(self.sessions_list)
        list_layout.addWidget(self.refresh_button)
        list_layout.addWidget(self.open_selected_button)

        details_group = QGroupBox("Detalhes")
        details_layout = QVBoxLayout(details_group)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        details_layout.addWidget(self.details)

        content.addWidget(list_group, stretch=1)
        content.addWidget(details_group, stretch=2)
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

    def set_sessions(self, summaries: Iterable[StoredSessionSummary]) -> None:
        self.sessions_list.clear()
        summaries = list(summaries)
        if not summaries:
            self.sessions_list.addItem("Nenhuma sessão armazenada encontrada.")
            self.open_selected_button.setEnabled(False)
            self.details.setPlainText(
                "Ainda não há sessões salvas em data/sessions.\n\n"
                "Para criar uma sessão armazenada, faça uma aquisição ou insira frames de teste "
                "e clique em 'Salvar sessão' na tela de visualização ao vivo."
            )
            return

        for summary in summaries:
            label = (
                f"{summary.created_at} | {summary.frames_received} frames | "
                f"{summary.channel_count} canais"
            )
            item = QListWidgetItem(label)
            item.setData(self.SESSION_ID_ROLE, summary.session_id)
            item.setToolTip(summary.session_id)
            self.sessions_list.addItem(item)

        self.sessions_list.setCurrentRow(0)

    def set_details(self, text: str) -> None:
        self.details.setPlainText(text)

    def _on_selection_changed(self) -> None:
        self.open_selected_button.setEnabled(self.selected_session_id is not None)
