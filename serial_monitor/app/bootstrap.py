from __future__ import annotations

import sys
import time
from typing import Any

from PyQt5.QtCore import QObject, QTimer, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMessageBox

from serial_monitor.app.runtime_settings import RuntimeSettings, parse_runtime_settings
from serial_monitor.app.system_report import collect_system_report
from serial_monitor.application.async_processing import (
    LatestProcessingWorker,
    ensure_thread_safe_processing_service,
)
from serial_monitor.application.conversion_service import ConversionService
from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.operational_monitor import OperationalMonitor
from serial_monitor.application.recording_service import RecordingQueueFullError, RecordingService
from serial_monitor.application.session_service import SessionService
from serial_monitor.application.storage_workers import CsvExportWorker, IntegrityCheckWorker
from serial_monitor.domain.models import AcquisitionSnapshot, SampleFrame, StoredSessionSummary
from serial_monitor.infrastructure.serial.serial_reader import SerialReader
from serial_monitor.infrastructure.storage.config_repository import ConfigRepository
from serial_monitor.infrastructure.storage.session_repository import SessionRepository
from serial_monitor.processing.filter_pipeline import ProcessingService
from serial_monitor.ui.main_window import MainWindow


class MainController(QObject):
    """Controlador da aquisição, navegação e interface touch para Raspberry Pi."""

    def __init__(
        self,
        window: MainWindow,
        session_service: SessionService,
        serial_reader: SerialReader,
        acquisition_service: LiveAcquisitionService,
        processing_service: ProcessingService,
        session_repository: SessionRepository,
        config_repository: ConfigRepository,
        recording_service: RecordingService,
        operational_monitor: OperationalMonitor,
        settings: RuntimeSettings,
    ) -> None:
        super().__init__()
        self.window = window
        self.session_service = session_service
        self.serial_reader = serial_reader
        self.acquisition_service = acquisition_service
        self.processing_service = ensure_thread_safe_processing_service(
            processing_service
        )
        self.session_repository = session_repository
        self.config_repository = config_repository
        self.recording_service = recording_service
        self.operational_monitor = operational_monitor
        self.settings = settings
        self._session = None
        self._stored_raw_snapshot: AcquisitionSnapshot | None = None
        self._last_summary_frame_count = -1
        self._last_rendered_sequence_id: int | None = None
        self._export_worker: CsvExportWorker | None = None
        self._integrity_worker: IntegrityCheckWorker | None = None
        self._last_frame_log_monotonic = 0.0
        self._pending_session_validation = False
        self._serial_connected = False
        self._latest_processing_request_id = 0
        self._last_requested_sequence_id: int | None = None
        self.processing_worker = LatestProcessingWorker(
            self.processing_service, parent=self
        )
        self.processing_worker.result_ready.connect(self._on_processing_ready)
        self.processing_worker.failed.connect(self._on_processing_failed)
        self.processing_worker.start()

        self.view_timer = QTimer(self)
        self.view_timer.setInterval(self.settings.update_interval_ms)
        self.view_timer.timeout.connect(self.refresh_live_view)
        self.view_timer.start()

        self.operational_timer = QTimer(self)
        self.operational_timer.setInterval(
            self.settings.operational_update_interval_ms
        )
        self.operational_timer.timeout.connect(self.refresh_operational_status)
        self.operational_timer.start()

        self._connect_signals()
        self.window.update_recording_status(self.recording_service.status())
        self.refresh_operational_status()
        self._finalize_interrupted_sessions()
        self._refresh_presets(auto_load_first=True)
        self.refresh_stored_sessions()
        self.log("INFO", "Controlador inicializado.")
        self._log_startup_report()

    def _connect_signals(self) -> None:
        menu = self.window.menu_page
        config = self.window.config_page
        live = self.window.live_page
        stored = self.window.stored_page

        menu.start_button.clicked.connect(self.start_monitoring_from_menu)
        menu.config_button.clicked.connect(self.window.show_config)
        menu.stored_button.clicked.connect(self.open_stored_page)
        menu.exit_button.clicked.connect(self.close_application)

        config.validate_button.clicked.connect(self.request_session_validation)
        config.go_live_button.clicked.connect(self.go_live_from_config)
        config.back_menu_button.clicked.connect(self.window.show_menu)
        config.save_preset_button.clicked.connect(self.save_config_preset)
        config.load_preset_button.clicked.connect(self.load_config_preset)
        config.delete_preset_button.clicked.connect(self.delete_config_preset)
        config.refresh_presets_button.clicked.connect(self.refresh_presets)
        config.clear_log_button.clicked.connect(self.window.clear_logs)
        config.update_interval_changed.connect(self.update_view_interval)

        live.open_config_button.clicked.connect(self.window.show_config)
        live.open_stored_button.clicked.connect(self.open_stored_page)
        live.fullscreen_requested.connect(self.window.toggle_fullscreen)
        live.back_menu_button.clicked.connect(self.window.show_menu)
        live.connect_button.clicked.connect(self.connect_serial)
        live.disconnect_button.clicked.connect(self.disconnect_serial)
        live.clear_buffers_button.clicked.connect(self.clear_buffers)
        live.start_recording_button.clicked.connect(self.start_recording)
        live.finalize_recording_button.clicked.connect(self.finalize_recording)
        live.cancel_recording_button.clicked.connect(self.cancel_recording)
        live.filter_toggled.connect(self.on_filter_toggled)
        live.display_mode_changed.connect(self.on_display_mode_changed)
        live.plot_domain_changed.connect(self.on_plot_domain_changed)
        live.active_channel_changed.connect(self.on_active_channel_changed)

        stored.open_config_button.clicked.connect(self.window.show_config)
        stored.open_live_button.clicked.connect(self.go_live_from_config)
        stored.back_menu_button.clicked.connect(self.window.show_menu)
        stored.sessions_list.currentItemChanged.connect(lambda *_: self.update_selected_stored_details())
        stored.refresh_button.clicked.connect(self.refresh_stored_sessions)
        stored.open_selected_button.clicked.connect(self.open_selected_stored_session)
        stored.export_csv_button.clicked.connect(self.export_selected_session_csv)
        stored.cancel_export_button.clicked.connect(self.cancel_session_export)
        stored.verify_integrity_button.clicked.connect(self.verify_selected_session_integrity)
        stored.delete_selected_button.clicked.connect(self.delete_selected_stored_session)

        self.serial_reader.frames_received.connect(self.on_frames_received)
        self.serial_reader.error_occurred.connect(self.on_error)
        self.serial_reader.protocol_error.connect(self.on_protocol_error)
        self.serial_reader.connection_changed.connect(self.on_connection_changed)

    def log(self, level: str, message: str) -> None:
        self.window.append_log(level, message)
        print(f"[{level}] {message}", flush=True)

    def _parse_positive_int(self, value: str, field_name: str) -> int:
        text = value.strip()
        if not text:
            raise ValueError(f"O campo '{field_name}' não pode ficar vazio.")
        try:
            parsed = int(text)
        except ValueError as exc:
            raise ValueError(f"O campo '{field_name}' deve ser um número inteiro.") from exc
        if parsed <= 0:
            raise ValueError(f"O campo '{field_name}' deve ser maior que zero.")
        return parsed

    def _log_startup_report(self) -> None:
        report = collect_system_report()
        self.log(
            "SISTEMA",
            (
                f"{report.platform} | Python {report.python} | CPUs={report.cpu_count} | "
                f"update={self.settings.update_interval_ms} ms | max_plot_points={self.settings.max_plot_points} | "
                f"data_dir={self.settings.data_dir} | "
                f"operational_update={self.settings.operational_update_interval_ms} ms | "
                f"minimum_free_disk={self.settings.minimum_free_disk_mb} MiB"
            ),
        )

    def _confirm_action(self, title: str, message: str) -> bool:
        response = QMessageBox.question(
            self.window,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return response == QMessageBox.Yes

    def shutdown(self) -> None:
        self.view_timer.stop()
        self.operational_timer.stop()
        self.processing_worker.stop()
        self.processing_worker.wait()
        if self._export_worker is not None and self._export_worker.isRunning():
            self._export_worker.request_cancel()
            self._export_worker.wait(3000)
        if self._integrity_worker is not None and self._integrity_worker.isRunning():
            self._integrity_worker.wait(3000)
        if self.serial_reader.isRunning():
            self.serial_reader.stop()
        if self.recording_service.is_active:
            communication = self.acquisition_service.snapshot().communication
            self.recording_service.finalize(
                communication,
                reason="application_shutdown",
            )
        self.acquisition_service.stop()
        self.window.update_recording_status(self.recording_service.status())

    @pyqtSlot()
    def start_monitoring_from_menu(self) -> None:
        if self._session is None:
            self.window.show_config()
            self.log("INFO", "Configure e valide a sessão antes de iniciar o monitoramento.")
            return
        self._stored_raw_snapshot = None
        self.window.show_live()
        self.refresh_live_view(force=True)

    @pyqtSlot()
    def go_live_from_config(self) -> None:
        if self._session is None and not self.validate_session():
            return
        self._stored_raw_snapshot = None
        self.window.show_live()
        self.refresh_live_view(force=True)

    @pyqtSlot()
    def close_application(self) -> None:
        self.shutdown()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    @pyqtSlot(int)
    def update_view_interval(self, interval_ms: int) -> None:
        interval_ms = max(50, min(2000, int(interval_ms)))
        self.view_timer.setInterval(interval_ms)
        self.log("PERFORMANCE", f"Intervalo de atualização da GUI ajustado para {interval_ms} ms.")

    @pyqtSlot()
    def refresh_presets(self) -> None:
        self._refresh_presets(auto_load_first=False)

    def _refresh_presets(self, *, auto_load_first: bool) -> None:
        presets = self.config_repository.list_presets()
        self.window.update_presets(presets)
        if auto_load_first and presets:
            self.window.apply_preset(presets[0])
            self.log("CONFIG", f"Primeiro preset carregado automaticamente: {presets[0].name}.")
        self.log("CONFIG", f"Presets de configuração encontrados: {len(presets)}.")

    def _finalize_interrupted_sessions(self) -> None:
        try:
            results = self.session_repository.finalize_incomplete_sessions()
        except Exception as exc:
            self.log("ERRO", f"Não foi possível finalizar sessões interrompidas: {exc}")
            return
        for result in results:
            self.log(
                "STORAGE",
                (
                    f"Sessão interrompida marcada como finalizada: {result.session_id}; "
                    f"frames={result.frames_recovered}; descartados={result.frames_discarded}."
                ),
            )

    @pyqtSlot()
    def save_config_preset(self) -> None:
        try:
            preset = self.config_repository.save_preset(
                name=self.window.preset_name_text,
                port=self.window.selected_port,
                baudrate=self._parse_positive_int(self.window.baudrate_text, "Baudrate"),
                base_sample_rate_hz=self._parse_positive_int(self.window.sample_rate_text, "Taxa base"),
                window_size=self._parse_positive_int(self.window.window_size_text, "Janela"),
                signal_order_text=self.window.signal_order_text,
                channel_conversions=self.window.channel_conversion_configs,
                adc_reference_voltage_v=self.window.adc_reference_voltage_v,
                adc_gain=self.window.adc_gain,
            )
        except Exception as exc:
            self.log("ERRO", f"Não foi possível salvar preset: {exc}")
            return
        self.refresh_presets()
        self.log("CONFIG", f"Preset salvo: {preset.name}.")

    @pyqtSlot()
    def load_config_preset(self) -> None:
        name = self.window.selected_preset_name
        if not name:
            self.log("INFO", "Selecione um preset para carregar.")
            return
        try:
            preset = self.config_repository.load_preset(name)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível carregar preset: {exc}")
            return
        self.window.apply_preset(preset)
        self.log("CONFIG", f"Preset carregado: {preset.name}.")

    @pyqtSlot()
    def delete_config_preset(self) -> None:
        name = self.window.selected_preset_name
        if not name:
            self.log("INFO", "Selecione um preset para excluir.")
            return
        if not self._confirm_action(
            "Excluir preset",
            f"Deseja excluir definitivamente o preset '{name}'?",
        ):
            self.log("CONFIG", "Exclusão de preset cancelada pelo usuário.")
            return
        try:
            self.config_repository.delete_preset(name)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível excluir preset: {exc}")
            return
        self.refresh_presets()
        self.log("CONFIG", f"Preset excluído: {name}.")

    @pyqtSlot()
    def open_stored_page(self) -> None:
        self.refresh_stored_sessions()
        self.window.show_stored()

    @pyqtSlot()
    def refresh_stored_sessions(self) -> None:
        summaries = self.session_repository.list_sessions(include_partial=False)
        active_status = self.recording_service.status()
        if active_status.is_active and active_status.session_id is not None:
            summaries = [
                item for item in summaries if item.session_id != active_status.session_id
            ]
        self.window.update_stored_sessions(summaries)
        if summaries:
            self.window.update_stored_details(self._format_summary_details(summaries[0]))
        self.log("STORAGE", f"Sessões armazenadas encontradas: {len(summaries)}.")

    @pyqtSlot()
    def update_selected_stored_details(self) -> None:
        selected_id = self.window.selected_stored_session_id
        if selected_id is None:
            return
        for summary in self.session_repository.list_sessions(include_partial=False):
            if summary.session_id == selected_id:
                self.window.update_stored_details(self._format_summary_details(summary))
                return

    @pyqtSlot()
    def request_session_validation(self) -> None:
        """Desconecta a serial antes de aplicar uma nova configuração."""

        if self.serial_reader.isRunning() or self._serial_connected:
            self._pending_session_validation = True
            if self.recording_service.is_active:
                self.finalize_recording(reason="configuration_changed")
            self.log(
                "CONFIG",
                "Nova validação solicitada; desconectando a porta serial atual.",
            )
            self.disconnect_serial()
            return
        self.validate_session()

    @pyqtSlot(result=bool)
    def validate_session(self) -> bool:
        try:
            self._session = self.session_service.build_session(
                port=self.window.selected_port,
                baudrate=self._parse_positive_int(self.window.baudrate_text, "Baudrate"),
                base_sample_rate_hz=self._parse_positive_int(self.window.sample_rate_text, "Taxa base"),
                window_size=self._parse_positive_int(self.window.window_size_text, "Janela"),
                signal_order_text=self.window.signal_order_text,
                channel_conversions=self.window.channel_conversion_configs,
                adc_reference_voltage_v=self.window.adc_reference_voltage_v,
                adc_gain=self.window.adc_gain,
            )
            self._stored_raw_snapshot = None
            self.acquisition_service.configure(self._session)
            self.processing_service.configure(self._session)
            self.window.build_signal_tabs(self._session)
            self._last_summary_frame_count = -1
            self._last_rendered_sequence_id = None
        except ValueError as exc:
            self._session = None
            self._stored_raw_snapshot = None
            self.log("ERRO", str(exc))
            self.refresh_live_view(force=True)
            return False
        except Exception as exc:
            self._session = None
            self._stored_raw_snapshot = None
            self.log("ERRO", f"Falha inesperada ao validar sessão: {exc}")
            self.refresh_live_view(force=True)
            return False

        ordered_signals = ", ".join(
            (
                f"{channel.index}:{channel.signal_type.value}"
                + (
                    f"[{channel.conversion.profile_id}]"
                    if channel.conversion.enabled
                    else "[bruto]"
                )
            )
            for channel in self._session.channels
        )
        self.log(
            "OK",
            (
                f"Sessão válida: porta={self._session.port}, baudrate={self._session.baudrate}, "
                f"fs={self._session.base_sample_rate_hz} Hz, janela={self._session.window_size}, "
                f"canais=[{ordered_signals}], ADC=ADS1256 diferencial, "
                f"VREF={self._session.adc.reference_voltage_v:g} V, "
                f"PGA={self._session.adc.gain}"
            ),
        )
        self.refresh_live_view(force=True)
        return True


    @pyqtSlot()
    def connect_serial(self) -> None:
        if self.serial_reader.isRunning() or self._serial_connected:
            self.log("INFO", "A serial já está conectada ou tentando conectar.")
            return
        if self._session is None and not self.validate_session():
            return
        assert self._session is not None
        self._stored_raw_snapshot = None
        self._last_rendered_sequence_id = None
        self._last_frame_log_monotonic = 0.0
        self.acquisition_service.start()
        self.window.clear_signal_tabs()
        self.refresh_live_view(force=True)
        self.window.update_connection_state(False, connecting=True)
        self.log(
            "INFO",
            f"Tentando abrir porta serial {self._session.port} "
            f"a {self._session.baudrate} baud...",
        )
        try:
            self.serial_reader.configure(self._session)
            self.serial_reader.start()
        except Exception as exc:
            self.window.update_connection_state(False)
            self.acquisition_service.stop()
            self.log("ERRO", f"Não foi possível iniciar a leitura serial: {exc}")

    @pyqtSlot()
    def disconnect_serial(self) -> None:
        if not self.serial_reader.isRunning() and not self._serial_connected:
            self.window.update_connection_state(False)
            self.acquisition_service.stop()
            self.log("INFO", "A serial já está desconectada.")
            return
        self.window.update_connection_state(
            self._serial_connected, disconnecting=True
        )
        self.log("INFO", "Encerrando leitura serial...")
        self.serial_reader.stop()

    @pyqtSlot()
    def clear_buffers(self) -> None:
        self._stored_raw_snapshot = None
        self._last_rendered_sequence_id = None
        self.acquisition_service.clear_buffers(reset_stream_baseline=True)
        self.window.clear_signal_tabs()
        self.refresh_live_view(force=True)
        self.log(
            "BUFFER",
            (
                "Buffers de visualização e referências de sequência/timestamp "
                "reiniciados. A gravação contínua, quando ativa, não é apagada."
            ),
        )

    @pyqtSlot()
    def start_recording(self) -> None:
        if self._session is None and not self.validate_session():
            return
        if self._stored_raw_snapshot is not None:
            self.log("ERRO", "Não é possível gravar enquanto uma sessão armazenada está aberta.")
            return
        assert self._session is not None

        try:
            status = self.recording_service.start(
                self._session,
                active_filters=self.processing_service.enabled_filters_snapshot(),
                communication_baseline=self.acquisition_service.snapshot().communication,
            )
        except Exception as exc:
            self.log("ERRO", f"Não foi possível iniciar a gravação: {exc}")
            return

        self.window.update_recording_status(status)
        self.log(
            "GRAVAÇÃO",
            f"Gravação contínua iniciada: {status.session_id}. Os dados serão persistidos em HDF5.",
        )

    @pyqtSlot()
    def finalize_recording(self, reason: str = "user") -> None:
        if not self.recording_service.is_active:
            self.window.update_recording_status(self.recording_service.status())
            return

        communication = self.acquisition_service.snapshot().communication
        status = self.recording_service.finalize(communication, reason=reason)
        self.window.update_recording_status(status)

        if status.state.value == "completed":
            self.refresh_stored_sessions()
            self.log(
                "GRAVAÇÃO",
                f"Sessão finalizada: {status.session_id} ({status.frames_written} frames).",
            )
        elif status.state.value == "failed":
            self.log(
                "ERRO",
                f"Falha ao finalizar sessão: {status.error_message or 'erro desconhecido'}",
            )

    @pyqtSlot()
    def cancel_recording(self) -> None:
        if not self.recording_service.is_active:
            return
        if not self._confirm_action(
            "Cancelar gravação",
            "Deseja cancelar a gravação atual e excluir o arquivo parcial?",
        ):
            return

        status = self.recording_service.cancel()
        self.window.update_recording_status(status)
        self.log("GRAVAÇÃO", "Gravação cancelada e arquivo parcial removido.")

    @pyqtSlot()
    def open_selected_stored_session(self) -> None:
        session_id = self.window.selected_stored_session_id
        summary = self.window.selected_stored_summary
        if session_id is None or summary is None:
            self.log("INFO", "Selecione uma sessão armazenada para abrir.")
            return

        first_timestamp = summary.first_timestamp_us or 0
        start_us = first_timestamp + int(round(self.window.selected_stored_start_seconds * 1_000_000))
        end_us = start_us + int(round(self.window.selected_stored_duration_seconds * 1_000_000))

        try:
            stored = self.session_repository.load_window(
                session_id,
                start_us=start_us,
                end_us=end_us,
                max_points=self.window.selected_stored_max_points,
            )
        except Exception as exc:
            self.log("ERRO", f"Não foi possível abrir o intervalo da sessão: {exc}")
            return

        if self.serial_reader.isRunning():
            self.serial_reader.stop()

        self._session = stored.session
        self._stored_raw_snapshot = stored.snapshot
        self._last_rendered_sequence_id = None
        self.acquisition_service.configure(stored.session)
        self.processing_service.configure(stored.session)
        self.processing_service.set_enabled_filters(stored.active_filters)
        self.window.build_signal_tabs(stored.session)
        self.window.show_live()
        self.refresh_live_view(force=True)
        decimation_note = " com redução visual" if stored.decimated_for_display else ""
        self.log(
            "STORAGE",
            (
                f"Sessão aberta: {stored.summary.session_id}; "
                f"{stored.loaded_frames}/{stored.total_frames} frames carregados{decimation_note}."
            ),
        )

    @pyqtSlot()
    def export_selected_session_csv(self) -> None:
        session_id = self.window.selected_stored_session_id
        if session_id is None:
            self.log("INFO", "Selecione uma sessão armazenada para exportar.")
            return
        if self._export_worker is not None and self._export_worker.isRunning():
            self.log("INFO", "Já existe uma exportação CSV em andamento.")
            return

        worker = CsvExportWorker(self.session_repository, session_id)
        worker.progress_changed.connect(self._on_export_progress)
        worker.completed.connect(self._on_export_completed)
        worker.cancelled.connect(self._on_export_cancelled)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(self._clear_export_worker)
        self._export_worker = worker
        self.window.set_stored_export_running(True)
        self.window.update_stored_export_progress(0, 0, 0)
        self.log("STORAGE", f"Exportação CSV iniciada: {session_id}.")
        worker.start()

    @pyqtSlot()
    def cancel_session_export(self) -> None:
        if self._export_worker is None or not self._export_worker.isRunning():
            return
        self._export_worker.request_cancel()
        self.log("STORAGE", "Cancelamento da exportação solicitado.")

    @pyqtSlot(int, int, int)
    def _on_export_progress(self, percent: int, completed: int, total: int) -> None:
        self.window.update_stored_export_progress(percent, completed, total)

    @pyqtSlot(str)
    def _on_export_completed(self, path: str) -> None:
        self.window.finish_stored_export(f"Exportação concluída: {path}", success=True)
        self.update_selected_stored_details()
        self.log("STORAGE", f"CSV exportado: {path}.")

    @pyqtSlot()
    def _on_export_cancelled(self) -> None:
        self.window.finish_stored_export("Exportação cancelada; arquivo temporário removido.", success=False)
        self.log("STORAGE", "Exportação CSV cancelada.")

    @pyqtSlot(str)
    def _on_export_failed(self, message: str) -> None:
        self.window.finish_stored_export(f"Falha na exportação: {message}", success=False)
        self.log("ERRO", f"Não foi possível exportar CSV: {message}")

    @pyqtSlot()
    def _clear_export_worker(self) -> None:
        self._export_worker = None

    @pyqtSlot()
    def verify_selected_session_integrity(self) -> None:
        session_id = self.window.selected_stored_session_id
        if session_id is None:
            self.log("INFO", "Selecione uma sessão para verificar.")
            return
        if self._integrity_worker is not None and self._integrity_worker.isRunning():
            self.log("INFO", "Já existe uma verificação de integridade em andamento.")
            return
        worker = IntegrityCheckWorker(self.session_repository, session_id)
        worker.completed.connect(self._on_integrity_completed)
        worker.failed.connect(self._on_integrity_failed)
        worker.finished.connect(self._clear_integrity_worker)
        self._integrity_worker = worker
        self.window.stored_page.verify_integrity_button.setEnabled(False)
        self.log("STORAGE", f"Verificação de integridade iniciada: {session_id}.")
        worker.start()

    @pyqtSlot(str)
    def _on_integrity_completed(self, status: str) -> None:
        self.refresh_stored_sessions()
        self.log("STORAGE", f"Verificação de integridade concluída: {status}.")

    @pyqtSlot(str)
    def _on_integrity_failed(self, message: str) -> None:
        self.window.stored_page.verify_integrity_button.setEnabled(True)
        self.log("ERRO", f"Falha na verificação de integridade: {message}")

    @pyqtSlot()
    def _clear_integrity_worker(self) -> None:
        self._integrity_worker = None
        self.window.stored_page.verify_integrity_button.setEnabled(
            self.window.selected_stored_session_id is not None
        )

    @pyqtSlot()
    def delete_selected_stored_session(self) -> None:
        session_id = self.window.selected_stored_session_id
        if session_id is None:
            self.log("INFO", "Selecione uma sessão armazenada para excluir.")
            return
        if not self._confirm_action(
            "Excluir sessão armazenada",
            (
                "Deseja excluir definitivamente a sessão selecionada?\n\n"
                f"ID: {session_id}\n\n"
                "Essa ação remove os arquivos HDF5 e CSV associados."
            ),
        ):
            self.log("STORAGE", "Exclusão de sessão cancelada pelo usuário.")
            return
        try:
            self.session_repository.delete(session_id)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível excluir sessão: {exc}")
            return
        self.refresh_stored_sessions()
        self.log("STORAGE", f"Sessão excluída: {session_id}.")

    @pyqtSlot(int, str, bool)
    def on_filter_toggled(self, channel_index: int, filter_id: str, enabled: bool) -> None:
        try:
            self.processing_service.set_filter_enabled(channel_index, filter_id, enabled)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível alterar filtro: {exc}")
            return

        state = "ativado" if enabled else "desativado"
        self.log("FILTRO", f"Canal ch{channel_index}: filtro '{filter_id}' {state}.")
        self.refresh_live_view(force=True)

    @pyqtSlot(int, str)
    def on_display_mode_changed(self, channel_index: int, mode: str) -> None:
        labels = {
            "base": "base",
            "processed": "processado",
        }
        label = labels.get(mode, mode)
        self.log("VIEW", f"Canal ch{channel_index}: visualização alterada para sinal {label}.")
        self.refresh_live_view(force=True)

    @pyqtSlot(int, str)
    def on_plot_domain_changed(self, channel_index: int, domain: str) -> None:
        self.log("VIEW", f"Canal ch{channel_index}: domínio alterado para {domain}.")
        self.refresh_live_view(force=True)

    @pyqtSlot(int)
    def on_active_channel_changed(self, _channel_index: int) -> None:
        self._last_rendered_sequence_id = None
        self.refresh_live_view(force=True)

    @pyqtSlot()
    def refresh_operational_status(self) -> None:
        # O painel operacional só é redesenhado quando a tela ao vivo está visível.
        if self.window.stack.currentWidget() is not self.window.live_page:
            return
        status = self.recording_service.status()
        communication = self.acquisition_service.snapshot().communication
        resources = self.operational_monitor.sample()
        self.window.update_recording_status(status)
        self.window.update_operational_status(
            communication,
            resources,
            crc_available=False,
            minimum_free_disk_bytes=self.settings.minimum_free_disk_mb * 1024 * 1024,
        )

    @pyqtSlot()
    def refresh_live_view(self, force: bool = False) -> None:
        current_widget = self.window.stack.currentWidget()
        live_visible = current_widget is self.window.live_page
        config_visible = current_widget is self.window.config_page
        if not force and not live_visible and not config_visible:
            return

        raw_snapshot = self._stored_raw_snapshot or self.acquisition_service.snapshot()

        # Na configuração, o resumo continua usando diretamente o dado bruto.
        if config_visible:
            if force or raw_snapshot.frames_received != self._last_summary_frame_count:
                self.window.update_buffer_summary(raw_snapshot)
                self._last_summary_frame_count = raw_snapshot.frames_received
            if not live_visible:
                self._last_rendered_sequence_id = raw_snapshot.last_sequence_id
                return

        if not live_visible:
            return

        if (
            not force
            and raw_snapshot.last_sequence_id == self._last_requested_sequence_id
        ):
            return

        channel_index = self.window.live_page.current_channel_index
        selected = {channel_index} if channel_index is not None else set()
        display_modes: dict[int, str] = {}
        spectrum_modes: dict[int, str] = {}

        if channel_index is not None:
            display_mode = self.window.live_page.current_display_mode
            display_modes[channel_index] = display_mode
            if self.window.live_page.current_plot_domain == "spectrum":
                spectrum_modes[channel_index] = (
                    "processed" if display_mode == "processed" else "base"
                )

        try:
            request_id = self.processing_worker.submit(
                raw_snapshot,
                channel_indexes=selected,
                spectrum_modes=spectrum_modes,
                display_modes=display_modes,
            )
        except RuntimeError:
            return

        self._latest_processing_request_id = request_id
        self._last_requested_sequence_id = raw_snapshot.last_sequence_id

    @pyqtSlot(int, object)
    def _on_processing_ready(self, request_id: int, snapshot: object) -> None:
        if request_id != self._latest_processing_request_id:
            return
        if self.window.stack.currentWidget() is not self.window.live_page:
            return
        self.window.update_live_view(snapshot)
        self._last_rendered_sequence_id = getattr(snapshot, "last_sequence_id", None)

    @pyqtSlot(int, str)
    def _on_processing_failed(self, request_id: int, message: str) -> None:
        if request_id != self._latest_processing_request_id:
            return
        self._last_requested_sequence_id = None
        self.log("ERRO", f"Falha no processamento da visualização: {message}")

    @pyqtSlot(object)
    def on_frames_received(self, frames: tuple[SampleFrame, ...]) -> None:
        """Aplica aquisição e gravação uma única vez por lote Qt."""
        if not frames:
            return

        self._stored_raw_snapshot = None
        try:
            accepted_frames = self.acquisition_service.ingest_frames(frames)
        except Exception as exc:
            self.log("ERRO", f"Lote recebido, mas não inserido nos buffers: {exc}")
            return

        rejected_count = len(frames) - len(accepted_frames)
        if rejected_count:
            stats = self.acquisition_service.snapshot().communication
            self.log(
                "AVISO",
                (
                    f"Lote com {len(frames)} frames: {len(accepted_frames)} aceitos, "
                    f"{rejected_count} rejeitados; "
                    f"duplicados={stats.duplicate_frames}, "
                    f"fora_ordem={stats.out_of_order_frames}, "
                    f"timestamp_regressivo={stats.timestamp_regressions}"
                ),
            )

        if accepted_frames:
            try:
                self._enqueue_recording_frames(accepted_frames)
            except RecordingQueueFullError:
                return

        now = time.monotonic()
        first_log = self._last_frame_log_monotonic <= 0.0
        log_interval_elapsed = now - self._last_frame_log_monotonic >= 5.0
        if not first_log and not log_interval_elapsed:
            return

        self._last_frame_log_monotonic = now
        snapshot = self.acquisition_service.snapshot()
        stats = snapshot.communication
        self.log(
            "FRAME",
            (
                f"frames={snapshot.frames_received}, "
                f"seq={snapshot.last_sequence_id}, "
                f"gaps={stats.gap_events}, "
                f"ausentes={stats.missing_frames}, "
                f"inválidos={stats.invalid_frames}"
            ),
        )

    @pyqtSlot(object)
    def on_frame_received(self, frame: SampleFrame) -> None:
        """Entrada unitária mantida para integrações e testes legados."""
        self.on_frames_received((frame,))

    def _enqueue_recording_frame(self, frame: SampleFrame) -> None:
        self._enqueue_recording_frames((frame,))

    def _enqueue_recording_frames(self, frames: tuple[SampleFrame, ...]) -> None:
        if not self.recording_service.is_recording:
            return
        try:
            self.recording_service.enqueue_frames(frames)
        except RecordingQueueFullError as exc:
            self.recording_service.fail(
                str(exc),
                self.acquisition_service.snapshot().communication,
            )
            self.window.update_recording_status(self.recording_service.status())
            self.log("ERRO", str(exc))
            if self.serial_reader.isRunning():
                self.serial_reader.stop()
            raise

    @pyqtSlot(int, str)
    def on_protocol_error(self, count: int, message: str) -> None:
        self.acquisition_service.record_invalid_frame(count)
        self.log(
            "PROTOCOLO",
            f"{count} frame(s) serial(is) inválido(s) no último intervalo. "
            f"Exemplo: {message}",
        )

    @pyqtSlot(str)
    def on_error(self, message: str) -> None:
        self.log("ERRO", message)

    @pyqtSlot(bool)
    def on_connection_changed(self, connected: bool) -> None:
        self._serial_connected = connected
        self.window.update_connection_state(connected)
        if connected:
            # O primeiro sequence_id e timestamp após cada conexão formam uma
            # nova referência válida sem apagar os diagnósticos acumulados.
            self.acquisition_service.begin_stream()
        else:
            self.acquisition_service.stop()
            if self.recording_service.is_active:
                self.finalize_recording(reason="serial_disconnected")
        state = "conectado" if connected else "desconectado"
        self.refresh_live_view(force=True)
        self.log("STATUS", f"Serial {state}.")

        if not connected and self._pending_session_validation:
            self._pending_session_validation = False
            QTimer.singleShot(0, self.validate_session)

    def _format_summary_details(self, summary: StoredSessionSummary) -> str:
        csv_path = summary.metadata_path.parent / f"{summary.session_id}.csv"
        first_time = (
            f"{summary.first_timestamp_us} µs" if summary.first_timestamp_us is not None else "--"
        )
        last_time = (
            f"{summary.last_timestamp_us} µs" if summary.last_timestamp_us is not None else "--"
        )
        return "\n".join(
            [
                f"ID: {summary.session_id}",
                f"Criada em: {summary.created_at}",
                f"Frames disponíveis: {summary.frames_received}",
                f"Estado: {summary.state}",
                f"Duração registrada: {summary.duration_seconds:.3f} s",
                f"Extensão temporal dos dados: {summary.time_span_seconds:.3f} s",
                f"Primeiro timestamp: {first_time}",
                f"Último timestamp: {last_time}",
                f"Motivo de encerramento: {summary.end_reason or '--'}",
                "",
                f"Versão do formato: {summary.format_version}",
                f"Versão do software: {summary.software_version or '--'}",
                f"Versão do protocolo: {summary.protocol_version or '--'}",
                f"Integridade: {summary.integrity_status}",
                f"SHA-256: {summary.content_sha256 or '--'}",
                f"Tamanho do arquivo: {summary.file_size_bytes / (1024 * 1024):.3f} MiB",
                "",
                f"Eventos de gap: {summary.gap_events}",
                f"Frames ausentes estimados: {summary.missing_frames}",
                f"Frames duplicados: {summary.duplicate_frames}",
                f"Frames fora de ordem: {summary.out_of_order_frames}",
                f"Frames inválidos: {summary.invalid_frames}",
                f"Timestamps não crescentes: {summary.timestamp_regressions}",
                f"Canais: {summary.channel_count}",
                f"Taxa base: {summary.base_sample_rate_hz} Hz",
                "",
                "Ordem dos canais:",
                *(f"  - {label}" for label in summary.channel_labels),
                "",
                f"Arquivo HDF5: {summary.data_path}",
                f"CSV: {csv_path if csv_path.exists() else 'ainda não exportado'}",
            ]
        )



def run() -> int:
    try:
        settings = parse_runtime_settings(sys.argv[1:])
    except ValueError as exc:
        print(f"Erro nos argumentos de execução: {exc}", file=sys.stderr)
        return 2

    app = QApplication([sys.argv[0]])
    window = MainWindow(settings)

    controller = MainController(
        window=window,
        session_service=SessionService(),
        serial_reader=SerialReader(),
        acquisition_service=LiveAcquisitionService(),
        processing_service=ProcessingService(
            conversion_service=ConversionService()
        ),
        session_repository=SessionRepository(settings.sessions_dir),
        config_repository=ConfigRepository(settings.presets_dir),
        recording_service=RecordingService(
            settings.sessions_dir,
            queue_capacity=settings.recording_queue_capacity,
            batch_size=settings.recording_batch_size,
            flush_interval_s=settings.recording_flush_interval_ms / 1000.0,
            minimum_free_disk_bytes=settings.minimum_free_disk_mb * 1024 * 1024,
        ),
        operational_monitor=OperationalMonitor(settings.sessions_dir),
        settings=settings,
    )
    window.controller = controller  # type: ignore[attr-defined]

    if settings.fullscreen:
        window.enter_fullscreen()
    else:
        window.show()
    return app.exec_()
