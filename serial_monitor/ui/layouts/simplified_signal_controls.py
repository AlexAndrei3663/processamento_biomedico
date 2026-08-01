from __future__ import annotations

from contextlib import suppress
from typing import Iterable

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


COMPACT_SIGNAL_CONTROLS_QSS = """
QFrame#filterEditorPanel {
    border: 1px solid palette(mid);
    border-radius: 2px;
}
QFrame#filterEditorPanel QGroupBox {
    margin-top: 8px;
}
QPushButton#filterToggleButton,
QPushButton#domainToggleButton,
QPushButton#timeScaleButton,
QPushButton#spectrumScaleButton {
    min-height: 34px;
    max-height: 40px;
    padding: 3px 8px;
}
QPushButton#filterApplyButton {
    min-height: 38px;
    font-weight: 700;
}
"""


def normalize_filter_ids(filter_ids: Iterable[str]) -> set[str]:
    """Converte o passa-faixa virtual em passa-altas + passa-baixas."""
    normalized = {str(filter_id) for filter_id in filter_ids}
    if "bandpass" in normalized:
        normalized.discard("bandpass")
        normalized.update(("highpass", "lowpass"))
    return normalized


def _find_group(tab: QWidget, *titles: str) -> QGroupBox | None:
    expected = {title.casefold() for title in titles}
    for group in tab.findChildren(QGroupBox):
        if group.title().strip().casefold() in expected:
            return group
    return None


def _disconnect_signal(signal) -> None:
    with suppress(TypeError, RuntimeError):
        signal.disconnect()


class SimplifiedSignalControls(QObject):
    """Transforma os controles da aba em uma interface transacional.

    Os filtros e seus parâmetros ficam em estado pendente enquanto o painel
    está aberto. Somente ``Aplicar`` emite alterações ao controlador.
    """

    def __init__(self, tab: QWidget) -> None:
        super().__init__(tab)
        self.tab = tab
        self._filter_panel_visible = False
        self._active_filter_ids: set[str] = set()
        self._active_filter_parameters = self._read_parameter_controls()
        self._build_top_controls()
        self._build_filter_editor()
        self._disconnect_immediate_filter_application()
        self._hide_redundant_side_controls()
        self._wrap_snapshot_update()
        self._sync_editor_from_active()
        self._sync_display_mode()
        self._refresh_top_controls()
        tab.setStyleSheet(tab.styleSheet() + COMPACT_SIGNAL_CONTROLS_QSS)

    def _toolbar_layout(self) -> QHBoxLayout:
        layout = self.tab.toolbar_widget.layout()
        if not isinstance(layout, QHBoxLayout):
            raise RuntimeError("A barra da aba de sinal deve usar QHBoxLayout.")
        return layout

    def _build_top_controls(self) -> None:
        toolbar = self._toolbar_layout()

        self.filters_button = QPushButton("Filtros")
        self.filters_button.setObjectName("filterToggleButton")
        self.filters_button.setCheckable(True)
        self.filters_button.setMaximumWidth(120)
        self.filters_button.setToolTip(
            "Selecionar filtros. As mudanças só entram em vigor ao aplicar."
        )

        # O botão já existe no painel lateral e já está ligado ao método
        # _toggle_spectrum. Apenas o promovemos para a barra superior.
        self.domain_button = self.tab.toggle_spectrum_button
        parent_layout = self.domain_button.parentWidget().layout()
        if parent_layout is not None:
            parent_layout.removeWidget(self.domain_button)
        self.domain_button.setParent(self.tab.toolbar_widget)
        self.domain_button.setObjectName("domainToggleButton")
        self.domain_button.setMaximumWidth(110)

        self.time_scale_button = QPushButton()
        self.time_scale_button.setObjectName("timeScaleButton")
        self.time_scale_button.setMaximumWidth(110)
        self.time_scale_button.setToolTip(
            "Alternar entre escala automática e faixa completa do ADC."
        )

        self.spectrum_scale_button = QPushButton()
        self.spectrum_scale_button.setObjectName("spectrumScaleButton")
        self.spectrum_scale_button.setMaximumWidth(120)
        self.spectrum_scale_button.setToolTip(
            "Alternar o espectro entre magnitude linear e dBFS."
        )

        # Antes do espaçador: os controles do gráfico permanecem agrupados.
        insert_index = 1
        for button in (
            self.filters_button,
            self.domain_button,
            self.time_scale_button,
            self.spectrum_scale_button,
        ):
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            toolbar.insertWidget(insert_index, button)
            insert_index += 1

        self.filters_button.toggled.connect(self.set_filter_panel_visible)
        self.time_scale_button.clicked.connect(self._toggle_time_scale)
        self.spectrum_scale_button.clicked.connect(
            self._toggle_spectrum_scale
        )
        self.tab.plot_domain_changed.connect(
            lambda _channel, _domain: self._refresh_top_controls()
        )
        self.tab.vertical_auto_radio.toggled.connect(
            self._refresh_top_controls
        )
        self.tab.vertical_full_scale_radio.toggled.connect(
            self._refresh_top_controls
        )
        self.tab.spectrum_linear_radio.toggled.connect(
            self._refresh_top_controls
        )
        self.tab.spectrum_dbfs_radio.toggled.connect(
            self._refresh_top_controls
        )

    def _build_filter_editor(self) -> None:
        filter_group = _find_group(
            self.tab,
            "Filtros",
            "Filtros pré-definidos",
        )
        if filter_group is None:
            raise RuntimeError("O grupo de filtros da aba não foi encontrado.")

        self.filter_group = filter_group
        self.filter_group.setTitle("Selecionar filtros")

        previous_parent = filter_group.parentWidget()
        previous_layout = (
            previous_parent.layout() if previous_parent is not None else None
        )
        if previous_layout is not None:
            previous_layout.removeWidget(filter_group)

        self.filter_panel = QFrame(self.tab)
        self.filter_panel.setObjectName("filterEditorPanel")
        self.filter_panel.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        panel_layout = QVBoxLayout(self.filter_panel)
        panel_layout.setContentsMargins(5, 3, 5, 5)
        panel_layout.setSpacing(4)
        filter_group.setParent(self.filter_panel)
        panel_layout.addWidget(filter_group)

        self.apply_filters_button = QPushButton("Aplicar filtros")
        self.apply_filters_button.setObjectName("filterApplyButton")
        self.apply_filters_button.setToolTip(
            "Aplicar filtros e frequências de corte selecionados."
        )
        panel_layout.addWidget(self.apply_filters_button)

        root = self.tab.layout()
        if not isinstance(root, QVBoxLayout):
            raise RuntimeError("A aba de sinal deve usar QVBoxLayout.")
        root.insertWidget(1, self.filter_panel)
        self.filter_panel.setVisible(False)

        self.apply_filters_button.clicked.connect(self.apply_filters)

    def _disconnect_immediate_filter_application(self) -> None:
        for filter_id, checkbox in self.tab.filter_checkboxes.items():
            _disconnect_signal(checkbox.toggled)
            checkbox.toggled.connect(
                lambda checked, fid=filter_id: (
                    self._on_pending_filter_toggled(fid, checked)
                )
            )

        parameter_controls = getattr(
            self.tab,
            "filter_parameter_controls",
            {},
        )
        for parameter_id, control in parameter_controls.items():
            _disconnect_signal(control.valueChanged)
            control.valueChanged.connect(
                lambda value, pid=parameter_id: (
                    self._on_pending_parameter_changed(pid, float(value))
                )
            )

    def _hide_redundant_side_controls(self) -> None:
        # A escolha base/processado passa a ser automática.
        view_group = _find_group(self.tab, "Sinal exibido")
        if view_group is not None:
            view_group.hide()

        # Domínio e escalas foram promovidos para a barra superior.
        domain_group = _find_group(self.tab, "Domínio")
        if domain_group is not None:
            domain_group.hide()
        self.tab.vertical_scale_group.hide()
        self.tab.spectrum_scale_group.hide()

    def _wrap_snapshot_update(self) -> None:
        original = self.tab.update_from_snapshot

        def update_with_pending_state(snapshot) -> None:
            pending_ids = None
            pending_parameters = None
            if self._filter_panel_visible:
                pending_ids = self._editor_filter_ids()
                pending_parameters = self._read_parameter_controls()

            original(snapshot)
            self._active_filter_ids = normalize_filter_ids(
                snapshot.active_filters
            )

            if pending_ids is not None:
                self._set_editor_filter_ids(pending_ids)
                self._write_parameter_controls(pending_parameters or {})
            else:
                self._sync_editor_from_active()
                self._sync_display_mode()

            self._refresh_filter_button()
            self._refresh_top_controls()

        self.tab.update_from_snapshot = update_with_pending_state

    def _editor_filter_ids(self) -> set[str]:
        selected = {
            filter_id
            for filter_id, checkbox in self.tab.filter_checkboxes.items()
            if checkbox.isChecked()
        }
        return normalize_filter_ids(selected)

    def _set_editor_filter_ids(self, filter_ids: Iterable[str]) -> None:
        selected = normalize_filter_ids(filter_ids)
        for filter_id, checkbox in self.tab.filter_checkboxes.items():
            checked = (
                {"highpass", "lowpass"}.issubset(selected)
                if filter_id == "bandpass"
                else filter_id in selected
            )
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)

    def _read_parameter_controls(self) -> dict[str, float]:
        controls = getattr(self.tab, "filter_parameter_controls", {})
        return {
            parameter_id: float(control.value())
            for parameter_id, control in controls.items()
        }

    def _write_parameter_controls(
        self,
        parameters: dict[str, float],
    ) -> None:
        controls = getattr(self.tab, "filter_parameter_controls", {})
        for parameter_id, value in parameters.items():
            control = controls.get(parameter_id)
            if control is None:
                continue
            control.blockSignals(True)
            control.setValue(float(value))
            control.blockSignals(False)

    def _sync_editor_from_active(self) -> None:
        self._set_editor_filter_ids(self._active_filter_ids)
        self._write_parameter_controls(self._active_filter_parameters)

    def _on_pending_filter_toggled(
        self,
        filter_id: str,
        checked: bool,
    ) -> None:
        checkboxes = self.tab.filter_checkboxes

        if filter_id == "bandpass":
            for component in ("highpass", "lowpass"):
                checkbox = checkboxes.get(component)
                if checkbox is not None:
                    checkbox.blockSignals(True)
                    checkbox.setChecked(bool(checked))
                    checkbox.blockSignals(False)
            return

        if filter_id in {"highpass", "lowpass"}:
            bandpass = checkboxes.get("bandpass")
            highpass = checkboxes.get("highpass")
            lowpass = checkboxes.get("lowpass")
            if (
                bandpass is not None
                and highpass is not None
                and lowpass is not None
            ):
                bandpass.blockSignals(True)
                bandpass.setChecked(
                    highpass.isChecked() and lowpass.isChecked()
                )
                bandpass.blockSignals(False)

    def _on_pending_parameter_changed(
        self,
        parameter_id: str,
        _value: float,
    ) -> None:
        controls = getattr(self.tab, "filter_parameter_controls", {})
        highpass = controls.get("highpass_cutoff_hz")
        lowpass = controls.get("lowpass_cutoff_hz")
        if highpass is None or lowpass is None:
            return

        hp = float(highpass.value())
        lp = float(lowpass.value())
        step = 0.01

        if parameter_id == "highpass_cutoff_hz" and hp >= lp:
            adjusted = min(float(lowpass.maximum()), hp + step)
            if adjusted > hp:
                lowpass.blockSignals(True)
                lowpass.setValue(adjusted)
                lowpass.blockSignals(False)
            else:
                highpass.blockSignals(True)
                highpass.setValue(max(float(highpass.minimum()), lp - step))
                highpass.blockSignals(False)

        elif parameter_id == "lowpass_cutoff_hz" and lp <= hp:
            adjusted = max(float(highpass.minimum()), lp - step)
            highpass.blockSignals(True)
            highpass.setValue(adjusted)
            highpass.blockSignals(False)

    def set_filter_panel_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible:
            self._sync_editor_from_active()
        else:
            # Fechar sem aplicar descarta apenas o rascunho da interface.
            self._sync_editor_from_active()

        self._filter_panel_visible = visible
        self.filter_panel.setVisible(visible)

        if self.filters_button.isChecked() != visible:
            self.filters_button.blockSignals(True)
            self.filters_button.setChecked(visible)
            self.filters_button.blockSignals(False)

    def apply_filters(self) -> None:
        selected = self._editor_filter_ids()
        pending_parameters = self._read_parameter_controls()

        for filter_id in sorted(self._active_filter_ids | selected):
            was_active = filter_id in self._active_filter_ids
            should_be_active = filter_id in selected
            if was_active != should_be_active:
                self.tab.filter_toggled.emit(
                    self.tab.channel.index,
                    filter_id,
                    should_be_active,
                )

        parameter_signal = getattr(
            self.tab,
            "filter_parameter_changed",
            None,
        )
        if parameter_signal is not None:
            for parameter_id, value in pending_parameters.items():
                previous = self._active_filter_parameters.get(parameter_id)
                if previous is None or abs(previous - value) > 1e-12:
                    parameter_signal.emit(
                        self.tab.channel.index,
                        parameter_id,
                        value,
                    )

        self._active_filter_ids = selected
        self._active_filter_parameters = pending_parameters
        self._sync_display_mode()
        self._refresh_filter_button()
        self.set_filter_panel_visible(False)

    def _sync_display_mode(self) -> None:
        # Sem filtros, o gráfico base já é o resultado correto. Com qualquer
        # filtro ativo, o gráfico processado passa a ser selecionado.
        if self._active_filter_ids:
            if not self.tab.processed_radio.isChecked():
                self.tab.processed_radio.setChecked(True)
        elif not self.tab.base_radio.isChecked():
            self.tab.base_radio.setChecked(True)

    def _toggle_time_scale(self) -> None:
        if self.tab.vertical_auto_radio.isChecked():
            self.tab.vertical_full_scale_radio.setChecked(True)
        else:
            self.tab.vertical_auto_radio.setChecked(True)

    def _toggle_spectrum_scale(self) -> None:
        if self.tab.spectrum_linear_radio.isChecked():
            self.tab.spectrum_dbfs_radio.setChecked(True)
        else:
            self.tab.spectrum_linear_radio.setChecked(True)

    def _refresh_filter_button(self) -> None:
        count = len(self._active_filter_ids)
        self.filters_button.setText(
            "Filtros" if count == 0 else f"Filtros [{count}]"
        )

    def _refresh_top_controls(self, *_args) -> None:
        is_time = self.tab.plot_domain == self.tab.TIME_DOMAIN
        self.domain_button.setText("Espectro" if is_time else "Tempo")
        self.time_scale_button.setVisible(is_time)
        self.spectrum_scale_button.setVisible(not is_time)

        self.time_scale_button.setText(
            "Y: Auto"
            if self.tab.vertical_auto_radio.isChecked()
            else "Y: ADC"
        )
        self.spectrum_scale_button.setText(
            "FFT: Linear"
            if self.tab.spectrum_linear_radio.isChecked()
            else "FFT: dBFS"
        )
        self._refresh_filter_button()


def apply_simplified_signal_controls(
    tab: QWidget,
) -> SimplifiedSignalControls:
    """Aplica os controles uma vez e preserva a API pública de SignalTab."""
    current = getattr(tab, "_simplified_signal_controls", None)
    if isinstance(current, SimplifiedSignalControls):
        return current
    return SimplifiedSignalControls(tab)
