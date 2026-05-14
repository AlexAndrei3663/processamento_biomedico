from __future__ import annotations

from datetime import datetime

from PyQt5.QtWidgets import QMainWindow, QStackedWidget

from serial_monitor.domain.models import ProcessedAcquisitionSnapshot, SessionConfig
from serial_monitor.ui.pages.config_page import ConfigPage
from serial_monitor.ui.pages.live_page import LivePage
from serial_monitor.ui.pages.menu_page import MenuPage
from serial_monitor.ui.pages.stored_page import StoredPage


class MainWindow(QMainWindow):
    """Janela principal da Etapa 4.

    A janela passa a ser composta por páginas navegáveis. A lógica de aquisição,
    parser e buffers permanece fora da UI; esta classe apenas coordena a troca de
    páginas e expõe métodos de atualização usados pelo controlador.
    """

    MENU_PAGE = 0
    CONFIG_PAGE = 1
    LIVE_PAGE = 2
    STORED_PAGE = 3

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Serial Monitor - Etapa 5")
        self.resize(1260, 820)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.menu_page = MenuPage()
        self.config_page = ConfigPage()
        self.live_page = LivePage()
        self.stored_page = StoredPage()

        self.stack.addWidget(self.menu_page)
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.live_page)
        self.stack.addWidget(self.stored_page)

        self.show_menu()
        self.statusBar().showMessage("Pronto")

    def show_menu(self) -> None:
        self.stack.setCurrentIndex(self.MENU_PAGE)
        self.statusBar().showMessage("Menu inicial")

    def show_config(self) -> None:
        self.stack.setCurrentIndex(self.CONFIG_PAGE)
        self.statusBar().showMessage("Configuração da sessão")

    def show_live(self) -> None:
        self.stack.setCurrentIndex(self.LIVE_PAGE)
        self.statusBar().showMessage("Visualização ao vivo")

    def show_stored(self) -> None:
        self.stack.setCurrentIndex(self.STORED_PAGE)
        self.statusBar().showMessage("Sinais armazenados")

    def append_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level}] {message}"
        self.config_page.log.append(line)
        self.live_page.log.append(line)
        self.statusBar().showMessage(f"[{level}] {message}", 5000)

    def clear_logs(self) -> None:
        self.config_page.log.clear()
        self.live_page.log.clear()

    def build_signal_tabs(self, session: SessionConfig) -> None:
        self.live_page.build_signal_tabs(session)

    def clear_signal_tabs(self) -> None:
        self.live_page.clear_signal_tabs()

    def update_live_view(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
        self.live_page.update_live_view(snapshot)

    def update_buffer_summary(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
        self.live_page.update_buffer_summary(snapshot)

    def update_connection_state(self, connected: bool) -> None:
        self.live_page.connect_button.setEnabled(not connected)
        self.live_page.disconnect_button.setEnabled(connected)

    # Atalhos usados pelo controlador para manter a leitura do código simples.
    @property
    def port_text(self) -> str:
        return self.config_page.port_input.text().strip()

    @property
    def baudrate_text(self) -> str:
        return self.config_page.baudrate_input.text().strip()

    @property
    def sample_rate_text(self) -> str:
        return self.config_page.sample_rate_input.text().strip()

    @property
    def window_size_text(self) -> str:
        return self.config_page.window_size_input.text().strip()

    @property
    def signal_order_text(self) -> str:
        return self.config_page.signal_order_input.text()

    @property
    def sample_frame_text(self) -> str:
        return self.config_page.sample_frame_input.text()
