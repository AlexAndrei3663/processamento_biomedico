from __future__ import annotations

from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class StoredPage(QWidget):
    """Página reservada para sessões armazenadas.

    A persistência real entra em etapa posterior. Esta página já fixa a navegação
    e os pontos de extensão para listar, abrir e exportar aquisições salvas.
    """

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
        self.sessions_list.addItem("Nenhuma sessão armazenada nesta etapa.")
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
        self.details.setPlainText(
            "A tela de sinais armazenados já faz parte da navegação final.\n\n"
            "A gravação, indexação, abertura e visualização de sessões salvas serão "
            "implementadas na etapa de armazenamento."
        )
        details_layout.addWidget(self.details)

        content.addWidget(list_group, stretch=1)
        content.addWidget(details_group, stretch=2)
        root.addLayout(content, stretch=1)
