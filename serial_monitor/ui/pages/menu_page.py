from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class MenuPage(QWidget):
    """Tela inicial do projeto."""

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.setSpacing(16)

        title = QLabel("Monitor de Sinais Biomédicos V1.0")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 700;")

        subtitle = QLabel("Sistema de aquisição, visualização e análise de sinais via microcontrolador")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px;")

        self.start_button = QPushButton("Iniciar monitoramento")
        self.config_button = QPushButton("Configurar sessão")
        self.stored_button = QPushButton("Sinais armazenados")
        self.exit_button = QPushButton("Sair")

        for button in (
            self.start_button,
            self.config_button,
            self.stored_button,
            self.exit_button,
        ):
            button.setMinimumWidth(260)
            button.setMinimumHeight(38)

        root.addStretch(1)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(16)
        root.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.config_button, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.stored_button, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.exit_button, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addStretch(2)
