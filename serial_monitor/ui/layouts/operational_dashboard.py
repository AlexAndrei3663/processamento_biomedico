from __future__ import annotations

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


DASHBOARD_QSS = """
QFrame#operationalCommandBar {
    border: 1px solid palette(mid);
    border-radius: 2px;
}
QFrame#operationalCommandBar QPushButton {
    min-height: 34px;
    max-height: 38px;
    padding: 3px 7px;
}
QFrame#operationalStatusStrip {
    border: 1px solid palette(mid);
    border-radius: 2px;
}
QFrame#operationalStatusStrip QLabel {
    min-width: 0;
    padding: 1px 4px;
    font-weight: 600;
}
QFrame#operationalNavigationPanel,
QFrame#operationalDiagnosticsWrapper {
    border: 0;
}
QFrame#operationalDiagnosticsPanel {
    border: 1px solid palette(mid);
    border-radius: 2px;
}
QPushButton#navigationToggleButton,
QPushButton#diagnosticsToggleButton {
    min-width: 72px;
}
"""


def _clear_layout(layout) -> None:
    """Remove itens do layout sem destruir os widgets reutilizados."""
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        if child_layout is not None:
            _clear_layout(child_layout)


def _configure_button(button: QPushButton, *, minimum_width: int = 0) -> None:
    button.setMinimumWidth(minimum_width)
    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class OperationalDashboardController(QObject):
    """Reorganiza a LivePage sem alterar seus sinais ou regras de negócio."""

    def __init__(self, page: QWidget) -> None:
        super().__init__(page)
        self.page = page
        self._navigation_visible = False
        self._diagnostics_visible = False
        self._build()

    def _build(self) -> None:
        page = self.page
        required = (
            "root",
            "header_widget",
            "navigation_widget",
            "controls_group",
            "recording_group",
            "live_group",
            "title_label",
            "connect_button",
            "disconnect_button",
            "clear_buffers_button",
            "start_recording_button",
            "finalize_recording_button",
            "cancel_recording_button",
            "open_config_button",
            "open_stored_button",
            "fullscreen_button",
            "back_menu_button",
        )
        missing = [name for name in required if not hasattr(page, name)]
        if missing:
            raise RuntimeError(
                "LivePage incompatível com o painel operacional: "
                + ", ".join(missing)
            )

        page.setStyleSheet(page.styleSheet() + DASHBOARD_QSS)
        page.root.setContentsMargins(4, 4, 4, 4)
        page.root.setSpacing(3)

        self._build_command_bar()
        self._build_navigation_panel()
        self._build_status_strip()
        self._build_diagnostics_panel()
        self._rebuild_root_layout()

        page.command_bar = page.header_widget
        page.navigation_panel = self.navigation_wrapper
        page.status_strip = page.controls_group
        page.diagnostics_panel = self.diagnostics_wrapper
        page.navigation_toggle_button = self.navigation_toggle_button
        page.diagnostics_toggle_button = self.diagnostics_toggle_button

    def _build_command_bar(self) -> None:
        page = self.page
        page.header_widget.setObjectName("operationalCommandBar")
        page.header_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = page.header_widget.layout()
        _clear_layout(layout)
        if not isinstance(layout, QHBoxLayout):
            raise RuntimeError("O cabeçalho da LivePage deve usar QHBoxLayout.")
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(4)

        page.title_label.setText("BIOMED // AQUISIÇÃO")
        page.title_label.setMinimumWidth(150)
        page.title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(page.title_label)

        for button in (
            page.connect_button,
            page.disconnect_button,
            page.clear_buffers_button,
            page.start_recording_button,
            page.finalize_recording_button,
            page.cancel_recording_button,
        ):
            _configure_button(button)
            layout.addWidget(button)

        self.diagnostics_toggle_button = QPushButton("DIAG")
        self.diagnostics_toggle_button.setObjectName("diagnosticsToggleButton")
        self.diagnostics_toggle_button.setCheckable(True)
        self.diagnostics_toggle_button.setToolTip(
            "Mostrar ou ocultar diagnóstico detalhado da aquisição."
        )
        self.diagnostics_toggle_button.toggled.connect(
            self.set_diagnostics_visible
        )

        self.navigation_toggle_button = QPushButton("NAV")
        self.navigation_toggle_button.setObjectName("navigationToggleButton")
        self.navigation_toggle_button.setCheckable(True)
        self.navigation_toggle_button.setToolTip(
            "Mostrar ou ocultar atalhos de navegação."
        )
        self.navigation_toggle_button.toggled.connect(
            self.set_navigation_visible
        )

        _configure_button(self.diagnostics_toggle_button, minimum_width=70)
        _configure_button(self.navigation_toggle_button, minimum_width=70)
        _configure_button(page.fullscreen_button, minimum_width=92)

        layout.addWidget(self.diagnostics_toggle_button)
        layout.addWidget(self.navigation_toggle_button)
        layout.addWidget(page.fullscreen_button)

    def _build_navigation_panel(self) -> None:
        page = self.page
        self.navigation_wrapper = QFrame(page)
        self.navigation_wrapper.setObjectName("operationalNavigationPanel")
        self.navigation_wrapper.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        wrapper_layout = QHBoxLayout(self.navigation_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        navigation_layout = page.navigation_widget.layout()
        if not isinstance(navigation_layout, QHBoxLayout):
            raise RuntimeError("A navegação da LivePage deve usar QHBoxLayout.")
        navigation_layout.setContentsMargins(4, 2, 4, 2)
        navigation_layout.setSpacing(4)

        # O fullscreen foi promovido à barra de comando. Os demais atalhos
        # continuam usando os mesmos objetos e conexões do controlador.
        for button in (
            page.open_config_button,
            page.open_stored_button,
            page.back_menu_button,
        ):
            _configure_button(button)
        wrapper_layout.addWidget(page.navigation_widget)
        self.navigation_wrapper.setVisible(False)

    def _build_status_strip(self) -> None:
        page = self.page
        page.controls_group.setObjectName("operationalStatusStrip")
        page.controls_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = page.controls_group.layout()
        _clear_layout(layout)
        if not isinstance(layout, QGridLayout):
            raise RuntimeError("O painel de controles deve usar QGridLayout.")
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(0)

        summary_labels = (
            page.recording_state_label,
            page.recording_duration_label,
            page.recording_frames_label,
            page.missing_frames_label,
            page.cpu_label,
            page.disk_free_label,
        )
        for column, label in enumerate(summary_labels):
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            layout.addWidget(label, 0, column)
            layout.setColumnStretch(column, 1)

    def _build_diagnostics_panel(self) -> None:
        page = self.page
        page.recording_group.setObjectName("operationalDiagnosticsPanel")
        page.recording_group.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        layout = page.recording_group.layout()
        _clear_layout(layout)
        if not isinstance(layout, QGridLayout):
            raise RuntimeError("O diagnóstico deve usar QGridLayout.")
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(2)

        detail_labels = (
            page.recording_queue_label,
            page.recording_size_label,
            page.invalid_frames_label,
            page.crc_errors_label,
            page.memory_label,
            page.temperature_label,
        )
        for column, label in enumerate(detail_labels):
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            layout.addWidget(label, 0, column)
            layout.setColumnStretch(column, 1)
        layout.addWidget(page.recording_path_label, 1, 0, 1, 6)

        self.diagnostics_wrapper = QFrame(page)
        self.diagnostics_wrapper.setObjectName(
            "operationalDiagnosticsWrapper"
        )
        self.diagnostics_wrapper.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        wrapper_layout = QVBoxLayout(self.diagnostics_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addWidget(page.recording_group)
        self.diagnostics_wrapper.setVisible(False)

    def _rebuild_root_layout(self) -> None:
        page = self.page
        for widget in (
            page.controls_group,
            page.recording_group,
            page.live_group,
        ):
            page.root.removeWidget(widget)

        page.root.addWidget(self.navigation_wrapper)
        page.root.addWidget(page.controls_group)
        page.root.addWidget(self.diagnostics_wrapper)
        page.root.addWidget(page.live_group, stretch=1)

    def set_navigation_visible(self, visible: bool) -> None:
        visible = bool(visible)
        self._navigation_visible = visible
        self.navigation_wrapper.setVisible(visible)
        if self.navigation_toggle_button.isChecked() != visible:
            self.navigation_toggle_button.blockSignals(True)
            self.navigation_toggle_button.setChecked(visible)
            self.navigation_toggle_button.blockSignals(False)
        if visible and self._diagnostics_visible:
            self.set_diagnostics_visible(False)

    def set_diagnostics_visible(self, visible: bool) -> None:
        visible = bool(visible)
        self._diagnostics_visible = visible
        self.diagnostics_wrapper.setVisible(visible)
        if self.diagnostics_toggle_button.isChecked() != visible:
            self.diagnostics_toggle_button.blockSignals(True)
            self.diagnostics_toggle_button.setChecked(visible)
            self.diagnostics_toggle_button.blockSignals(False)
        if visible and self._navigation_visible:
            self.set_navigation_visible(False)


def apply_operational_dashboard(page: QWidget) -> OperationalDashboardController:
    """Aplica o painel uma única vez e preserva a API pública da LivePage."""
    current = getattr(page, "_operational_dashboard", None)
    if isinstance(current, OperationalDashboardController):
        return current
    return OperationalDashboardController(page)
