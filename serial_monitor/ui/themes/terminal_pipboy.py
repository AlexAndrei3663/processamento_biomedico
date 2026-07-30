from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt5.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt5.QtWidgets import QWidget


DEFAULT_THEME_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "ui_theme.json"
)


@dataclass(frozen=True, slots=True)
class ThemeConfig:
    name: str
    font_size_pt: int
    plot_line_width: float
    plot_grid_alpha: float
    colors: dict[str, str]

    def color(self, name: str) -> str:
        try:
            return self.colors[name]
        except KeyError as exc:
            raise ValueError(f"Cor obrigatória ausente no tema: {name}") from exc


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Arquivo de tema não encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido no tema {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("A configuração do tema deve ser um objeto JSON.")
    return payload


def load_theme_config(path: str | Path | None = None) -> ThemeConfig:
    selected_path = Path(
        path
        or os.environ.get("BIOMED_UI_THEME_PATH", "")
        or DEFAULT_THEME_PATH
    )
    payload = _load_payload(selected_path)
    colors = payload.get("colors", {})
    if not isinstance(colors, dict):
        raise ValueError("A seção 'colors' deve ser um objeto.")

    config = ThemeConfig(
        name=str(payload.get("theme", "pipboy")).strip().lower(),
        font_size_pt=int(payload.get("font_size_pt", 10)),
        plot_line_width=float(payload.get("plot_line_width", 1.5)),
        plot_grid_alpha=float(payload.get("plot_grid_alpha", 0.22)),
        colors={str(key): str(value) for key, value in colors.items()},
    )
    validate_theme_config(config)
    return config


def validate_theme_config(config: ThemeConfig) -> None:
    if config.name not in {"pipboy", "terminal", "classic"}:
        raise ValueError(f"Tema desconhecido: {config.name}")
    if not 7 <= config.font_size_pt <= 18:
        raise ValueError("font_size_pt deve estar entre 7 e 18.")
    if not 0.5 <= config.plot_line_width <= 5.0:
        raise ValueError("plot_line_width deve estar entre 0,5 e 5.")
    if not 0.0 <= config.plot_grid_alpha <= 1.0:
        raise ValueError("plot_grid_alpha deve estar entre 0 e 1.")

    required = {
        "background",
        "panel",
        "panel_alt",
        "foreground",
        "foreground_dim",
        "accent",
        "border",
        "selection",
        "warning",
        "critical",
        "disabled",
        "plot_secondary",
        "plot_tertiary",
    }
    missing = sorted(required.difference(config.colors))
    if missing:
        raise ValueError("Cores obrigatórias ausentes: " + ", ".join(missing))
    for name, value in config.colors.items():
        if not QColor(value).isValid():
            raise ValueError(f"Cor inválida em {name}: {value}")


def active_theme_name(config: ThemeConfig | None = None) -> str:
    override = os.environ.get("BIOMED_UI_THEME", "").strip().lower()
    if override in {"classic", "terminal", "pipboy"}:
        return override
    return (config or load_theme_config()).name


def _fixed_font(size_pt: int) -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    if not font.family():
        font = QFont("DejaVu Sans Mono")
    font.setPointSize(size_pt)
    font.setStyleHint(QFont.Monospace)
    return font


def _base_touch_qss() -> str:
    return """
QPushButton {
    min-height: 46px;
    padding: 7px 12px;
    font-size: 15px;
    font-weight: 600;
}
QComboBox, QSpinBox, QDoubleSpinBox {
    min-height: 42px;
    padding: 4px 8px;
    font-size: 14px;
}
QListWidget {
    font-size: 15px;
}
QListWidget::item {
    min-height: 38px;
    padding: 5px;
}
QTabBar::tab {
    min-height: 40px;
    min-width: 105px;
    padding: 6px 10px;
    font-size: 14px;
}
QCheckBox, QRadioButton {
    min-height: 36px;
    spacing: 10px;
    font-size: 14px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 24px;
    height: 24px;
}
QGroupBox {
    font-size: 14px;
    font-weight: 600;
    margin-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QWidget#livePage QPushButton {
    min-height: 36px;
    max-height: 40px;
    padding: 3px 7px;
    font-size: 13px;
}
QWidget#livePage QTabBar::tab {
    min-height: 32px;
    min-width: 90px;
    padding: 4px 8px;
    font-size: 13px;
}
QWidget#livePage QCheckBox,
QWidget#livePage QRadioButton {
    min-height: 32px;
    spacing: 8px;
    font-size: 13px;
}
QWidget#livePage QCheckBox::indicator,
QWidget#livePage QRadioButton::indicator {
    width: 22px;
    height: 22px;
}
QWidget#livePage QLabel {
    font-size: 12px;
}
"""


def build_terminal_qss(config: ThemeConfig) -> str:
    c = config.colors
    return _base_touch_qss() + f"""
QMainWindow, QDialog, QMessageBox, QWidget {{
    background-color: {c["background"]};
    color: {c["foreground"]};
}}

QWidget#livePage,
QWidget#menuPage,
QWidget#configPage,
QWidget#storedPage {{
    background-color: {c["background"]};
}}

QFrame,
QGroupBox,
QTabWidget::pane {{
    background-color: {c["panel"]};
    border: 1px solid {c["border"]};
    border-radius: 2px;
}}

QFrame#liveControlsPanel,
QFrame#recordingStatusPanel,
QFrame#liveSignalPanel {{
    background-color: {c["panel"]};
    border: 1px solid {c["border"]};
}}

QLabel {{
    background: transparent;
    color: {c["foreground"]};
}}

QLabel[warning="true"] {{
    color: {c["warning"]};
    font-weight: 700;
}}

QLabel[critical="true"] {{
    color: {c["critical"]};
    font-weight: 800;
}}

QPushButton {{
    background-color: {c["panel_alt"]};
    color: {c["accent"]};
    border: 1px solid {c["border"]};
    border-radius: 2px;
}}

QPushButton:hover {{
    background-color: {c["selection"]};
    border-color: {c["accent"]};
}}

QPushButton:pressed,
QPushButton:checked {{
    background-color: {c["accent"]};
    color: {c["background"]};
}}

QPushButton:disabled {{
    background-color: {c["panel"]};
    color: {c["disabled"]};
    border-color: {c["disabled"]};
}}

QLineEdit,
QPlainTextEdit,
QTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QListWidget,
QTableView,
QTreeView {{
    background-color: {c["panel_alt"]};
    color: {c["foreground"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["selection"]};
    selection-color: {c["accent"]};
}}

QPlainTextEdit,
QTextEdit {{
    font-family: monospace;
}}

QComboBox::drop-down {{
    border-left: 1px solid {c["border"]};
    width: 28px;
}}

QComboBox QAbstractItemView {{
    background-color: {c["panel_alt"]};
    color: {c["foreground"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["selection"]};
}}

QTabBar::tab {{
    background-color: {c["panel"]};
    color: {c["foreground_dim"]};
    border: 1px solid {c["border"]};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background-color: {c["selection"]};
    color: {c["accent"]};
    border-color: {c["accent"]};
}}

QTabBar::tab:hover:!selected {{
    color: {c["foreground"]};
    background-color: {c["panel_alt"]};
}}

QCheckBox::indicator,
QRadioButton::indicator {{
    background-color: {c["background"]};
    border: 1px solid {c["border"]};
}}

QCheckBox::indicator:checked,
QRadioButton::indicator:checked {{
    background-color: {c["accent"]};
    border-color: {c["accent"]};
}}

QHeaderView::section {{
    background-color: {c["panel_alt"]};
    color: {c["accent"]};
    border: 1px solid {c["border"]};
    padding: 5px;
}}

QProgressBar {{
    background-color: {c["background"]};
    color: {c["accent"]};
    border: 1px solid {c["border"]};
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {c["accent"]};
}}

QScrollBar:vertical,
QScrollBar:horizontal {{
    background-color: {c["background"]};
    border: 1px solid {c["border"]};
}}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {{
    background-color: {c["border"]};
    min-height: 24px;
    min-width: 24px;
}}

QStatusBar {{
    background-color: {c["panel_alt"]};
    color: {c["foreground_dim"]};
    border-top: 1px solid {c["border"]};
}}

QToolTip {{
    background-color: {c["panel_alt"]};
    color: {c["accent"]};
    border: 1px solid {c["border"]};
}}

QMenu {{
    background-color: {c["panel_alt"]};
    color: {c["foreground"]};
    border: 1px solid {c["border"]};
}}

QMenu::item:selected {{
    background-color: {c["selection"]};
    color: {c["accent"]};
}}
"""


def _apply_palette(widget: QWidget, config: ThemeConfig) -> None:
    c = config.colors
    palette = widget.palette()
    palette.setColor(QPalette.Window, QColor(c["background"]))
    palette.setColor(QPalette.WindowText, QColor(c["foreground"]))
    palette.setColor(QPalette.Base, QColor(c["panel_alt"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["panel"]))
    palette.setColor(QPalette.Text, QColor(c["foreground"]))
    palette.setColor(QPalette.Button, QColor(c["panel_alt"]))
    palette.setColor(QPalette.ButtonText, QColor(c["foreground"]))
    palette.setColor(QPalette.Highlight, QColor(c["selection"]))
    palette.setColor(QPalette.HighlightedText, QColor(c["accent"]))
    widget.setPalette(palette)


def apply_application_theme(widget: QWidget) -> ThemeConfig:
    config = load_theme_config()
    selected = active_theme_name(config)
    widget.setFont(_fixed_font(config.font_size_pt))
    _apply_palette(widget, config)

    if selected == "classic":
        widget.setStyleSheet(_base_touch_qss())
    else:
        widget.setStyleSheet(build_terminal_qss(config))
        widget.setProperty("biomedTheme", selected)
    return config


def style_plot_widgets(root: QWidget) -> int:
    config = load_theme_config()
    if active_theme_name(config) == "classic":
        return 0

    try:
        import pyqtgraph as pg
    except ImportError:
        return 0

    c = config.colors
    curve_colors = (
        c["accent"],
        c["plot_secondary"],
        c["plot_tertiary"],
    )
    styled = 0

    for widget in root.findChildren(QWidget):
        get_plot_item = getattr(widget, "getPlotItem", None)
        if not callable(get_plot_item):
            continue
        try:
            plot_item = get_plot_item()
            widget.setBackground(c["background"])
            plot_item.setBackground(c["background"])
            plot_item.showGrid(
                x=True,
                y=True,
                alpha=config.plot_grid_alpha,
            )
            for axis_name in ("left", "bottom", "right", "top"):
                axis = plot_item.getAxis(axis_name)
                axis.setPen(pg.mkPen(c["border"], width=1))
                axis.setTextPen(pg.mkPen(c["foreground_dim"]))
            for index, curve in enumerate(plot_item.listDataItems()):
                curve.setPen(
                    pg.mkPen(
                        curve_colors[index % len(curve_colors)],
                        width=config.plot_line_width,
                    )
                )
            widget.setProperty("biomedPlotTheme", config.name)
            styled += 1
        except (AttributeError, RuntimeError, TypeError):
            continue
    return styled
