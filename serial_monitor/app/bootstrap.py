from __future__ import annotations

import sys
from typing import Any

from PyQt5.QtCore import QObject, QTimer, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMessageBox

from serial_monitor.app.runtime_settings import RuntimeSettings, parse_runtime_settings
from serial_monitor.app.system_report import collect_system_report
from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.models import AcquisitionSnapshot
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.infrastructure.serial.serial_reader import SerialReader
from serial_monitor.infrastructure.storage.config_repository import ConfigRepository
from serial_monitor.infrastructure.storage.session_repository import SessionRepository, StoredSessionSummary
from serial_monitor.processing.filter_pipeline import ProcessingService
from serial_monitor.ui.main_window import MainWindow

from serial_monitor.domain.models import SampleFrame

class MainController(QObject):
    """Controlador da navegação, aquisição, processamento, armazenamento, presets e execução em Raspberry Pi."""

    def __init__(
        self,
        window: MainWindow,
        session_service: SessionService,
        serial_reader: SerialReader,
        acquisition_service: LiveAcquisitionService,
        processing_service: ProcessingService,
        session_repository: SessionRepository,
        config_repository: ConfigRepository,
        settings: RuntimeSettings,
    ) -> None:
        super().__init__()
        self.window = window
        self.session_service = session_service
        self.serial_reader = serial_reader
        self.acquisition_service = acquisition_service
        self.processing_service = processing_service
        self.session_repository = session_repository
        self.config_repository = config_repository
        self.settings = settings
        self.parser = FrameCsvParser()
        self._session = None
        self._stored_raw_snapshot: AcquisitionSnapshot | None = None
        self._last_summary_frame_count = -1

        self.view_timer = QTimer(self)
        self.view_timer.setInterval(self.settings.update_interval_ms)
        self.view_timer.timeout.connect(self.refresh_live_view)
        self.view_timer.start()

        self._connect_signals()
        self.refresh_presets()
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

        config.validate_button.clicked.connect(self.validate_session)
        config.go_live_button.clicked.connect(self.go_live_from_config)
        config.back_menu_button.clicked.connect(self.window.show_menu)
        config.save_preset_button.clicked.connect(self.save_config_preset)
        config.load_preset_button.clicked.connect(self.load_config_preset)
        config.delete_preset_button.clicked.connect(self.delete_config_preset)
        config.refresh_presets_button.clicked.connect(self.refresh_presets)
        config.validate_frame_button.clicked.connect(self.validate_sample_frame)
        config.ingest_frame_button.clicked.connect(self.ingest_sample_frame)
        config.clear_buffers_button.clicked.connect(self.clear_buffers)
        config.clear_log_button.clicked.connect(self.window.clear_logs)

        live.open_config_button.clicked.connect(self.window.show_config)
        live.open_stored_button.clicked.connect(self.open_stored_page)
        live.fullscreen_requested.connect(self.window.toggle_fullscreen)
        live.back_menu_button.clicked.connect(self.window.show_menu)
        live.connect_button.clicked.connect(self.connect_serial)
        live.disconnect_button.clicked.connect(self.disconnect_serial)
        live.clear_buffers_button.clicked.connect(self.clear_buffers)
        live.save_session_button.clicked.connect(self.save_current_session)
        live.clear_log_button.clicked.connect(self.window.clear_logs)
        live.update_interval_changed.connect(self.update_view_interval)
        live.filter_toggled.connect(self.on_filter_toggled)
        live.display_mode_changed.connect(self.on_display_mode_changed)

        stored.open_config_button.clicked.connect(self.window.show_config)
        stored.open_live_button.clicked.connect(self.go_live_from_config)
        stored.back_menu_button.clicked.connect(self.window.show_menu)
        stored.sessions_list.currentItemChanged.connect(lambda *_: self.update_selected_stored_details())
        stored.refresh_button.clicked.connect(self.refresh_stored_sessions)
        stored.open_selected_button.clicked.connect(self.open_selected_stored_session)
        stored.export_csv_button.clicked.connect(self.export_selected_session_csv)
        stored.delete_selected_button.clicked.connect(self.delete_selected_stored_session)

        self.serial_reader.frame_received.connect(self.on_frame_received)
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
                f"data_dir={self.settings.data_dir}"
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
        if self.serial_reader.isRunning():
            self.serial_reader.stop()
        self.acquisition_service.stop()

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
        if self._session is None and not self._validate_session():
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
        presets = self.config_repository.list_presets()
        self.window.update_presets(presets)
        self.log("CONFIG", f"Presets de configuração encontrados: {len(presets)}.")

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
        summaries = self.session_repository.list_sessions()
        self.window.update_stored_sessions(summaries)
        if summaries:
            self.window.update_stored_details(self._format_summary_details(summaries[0]))
        self.log("STORAGE", f"Sessões armazenadas encontradas: {len(summaries)}.")

    @pyqtSlot()
    def update_selected_stored_details(self) -> None:
        selected_id = self.window.selected_stored_session_id
        if selected_id is None:
            return
        for summary in self.session_repository.list_sessions():
            if summary.session_id == selected_id:
                self.window.update_stored_details(self._format_summary_details(summary))
                return

    @pyqtSlot()
    def validate_session(self) -> None:
        self._validate_session()

    def _validate_session(self) -> bool:
        try:
            self._session = self.session_service.build_session(
                port=self.window.selected_port,
                baudrate=self._parse_positive_int(self.window.baudrate_text, "Baudrate"),
                base_sample_rate_hz=self._parse_positive_int(self.window.sample_rate_text, "Taxa base"),
                window_size=self._parse_positive_int(self.window.window_size_text, "Janela"),
                signal_order_text=self.window.signal_order_text,
            )
            self._stored_raw_snapshot = None
            self.acquisition_service.configure(self._session)
            self.processing_service.configure(self._session)
            self.window.build_signal_tabs(self._session)
            self._last_summary_frame_count = -1
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
            f"{channel.index}:{channel.signal_type.value}" for channel in self._session.channels
        )
        self.log(
            "OK",
            (
                f"Sessão válida: porta={self._session.port}, baudrate={self._session.baudrate}, "
                f"fs={self._session.base_sample_rate_hz} Hz, janela={self._session.window_size}, "
                f"canais=[{ordered_signals}]"
            ),
        )
        self.refresh_live_view(force=True)
        return True

    @pyqtSlot()
    def validate_sample_frame(self) -> None:
        if self._session is None and not self._validate_session():
            return
        assert self._session is not None

        line = self.window.sample_frame_text
        try:
            parsed = self.parser.parse_line(line, self._session)
        except Exception as exc:
            self.log("ERRO", f"Frame de teste inválido: {exc}")
            return

        frame = parsed.frame
        pairs = []
        for channel, value in zip(self._session.channels, frame.values_in_order, strict=True):
            pairs.append(f"ch{channel.index}:{channel.signal_type.value}={value:g} {channel.unit}")
        self.log(
            "OK",
            (
                f"Frame aceito: packet_seq={frame.packet_sequence}, scan_seq={frame.scan_sequence}, "
                f"timestamp_us={frame.timestamp_us}, " + ", ".join(pairs)
            ),
        )

    @pyqtSlot()
    def ingest_sample_frame(self) -> None:
        if self._session is None and not self._validate_session():
            return
        assert self._session is not None

        self._stored_raw_snapshot = None
        line = self.window.sample_frame_text
        try:
            frame = self.parser.parse_line(line, self._session).frame
            accepted = self.acquisition_service.ingest_frame(frame)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível inserir frame no buffer: {exc}")
            return

        self.refresh_live_view(force=True)
        if accepted:
            self.log(
                "BUFFER",
                f"Frame packet_seq={frame.packet_sequence}, scan_seq={frame.scan_sequence} inserido nos buffers.",
            )
        else:
            self.log(
                "AVISO",
                f"Frame packet_seq={frame.packet_sequence}, scan_seq={frame.scan_sequence} rejeitado pelo diagnóstico.",
            )

    @pyqtSlot()
    def connect_serial(self) -> None:
        if self.serial_reader.isRunning():
            self.log("INFO", "A serial já está conectada ou tentando conectar.")
            return
        if self._session is None and not self._validate_session():
            return
        assert self._session is not None
        self._stored_raw_snapshot = None
        self.acquisition_service.start()
        self.refresh_live_view(force=True)
        self.log("INFO", f"Tentando abrir porta serial {self._session.port} a {self._session.baudrate} baud...")
        self.serial_reader.configure(self._session)
        self.serial_reader.start()

    @pyqtSlot()
    def disconnect_serial(self) -> None:
        if not self.serial_reader.isRunning():
            self.log("INFO", "A serial já está desconectada.")
            self.acquisition_service.stop()
            self.refresh_live_view(force=True)
            return
        self.log("INFO", "Encerrando leitura serial...")
        self.serial_reader.stop()

    @pyqtSlot()
    def clear_buffers(self) -> None:
        self._stored_raw_snapshot = None
        self.acquisition_service.reset()
        self.window.clear_signal_tabs()
        self.refresh_live_view(force=True)
        self.log("BUFFER", "Buffers multicanais limpos.")

    @pyqtSlot()
    def save_current_session(self) -> None:
        if self._session is None:
            self.log("ERRO", "Não há sessão validada para salvar.")
            return

        snapshot = self.acquisition_service.snapshot()
        try:
            summary = self.session_repository.save(
                session=self._session,
                snapshot=snapshot,
                active_filters=self.processing_service.enabled_filters_snapshot(),
            )
        except Exception as exc:
            self.log("ERRO", f"Não foi possível salvar a sessão: {exc}")
            return

        self.refresh_stored_sessions()
        self.log(
            "STORAGE",
            f"Sessão salva: {summary.session_id} ({summary.frames_received} frames, {summary.channel_count} canais).",
        )

    @pyqtSlot()
    def open_selected_stored_session(self) -> None:
        session_id = self.window.selected_stored_session_id
        if session_id is None:
            self.log("INFO", "Selecione uma sessão armazenada para abrir.")
            return

        try:
            stored = self.session_repository.load(session_id)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível abrir a sessão armazenada: {exc}")
            return

        if self.serial_reader.isRunning():
            self.serial_reader.stop()

        self._session = stored.session
        self._stored_raw_snapshot = stored.snapshot
        self.acquisition_service.configure(stored.session)
        self.processing_service.configure(stored.session)
        self.processing_service.set_enabled_filters(stored.active_filters)
        self.window.build_signal_tabs(stored.session)
        self.window.show_live()
        self.refresh_live_view(force=True)
        self.log(
            "STORAGE",
            f"Sessão armazenada aberta: {stored.summary.session_id} ({stored.summary.frames_received} frames).",
        )

    @pyqtSlot()
    def export_selected_session_csv(self) -> None:
        session_id = self.window.selected_stored_session_id
        if session_id is None:
            self.log("INFO", "Selecione uma sessão armazenada para exportar.")
            return
        try:
            csv_path = self.session_repository.export_csv(session_id)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível exportar CSV: {exc}")
            return
        self.update_selected_stored_details()
        self.log("STORAGE", f"CSV exportado: {csv_path}.")

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
                "Essa ação remove os arquivos JSON, NPZ e CSV associados."
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
        label = "processado" if mode == "processed" else "bruto"
        self.log("VIEW", f"Canal ch{channel_index}: visualização alterada para sinal {label}.")
        self.refresh_live_view(force=True)

    @pyqtSlot()
    def refresh_live_view(self, force: bool = False) -> None:
        raw_snapshot = self._stored_raw_snapshot or self.acquisition_service.snapshot()
        processed_snapshot = self.processing_service.process(raw_snapshot)
        self.window.update_live_view(processed_snapshot)

        if force or processed_snapshot.frames_received != self._last_summary_frame_count:
            self.window.update_buffer_summary(processed_snapshot)
            self._last_summary_frame_count = processed_snapshot.frames_received

    @pyqtSlot(object)
    def on_frame_received(self, frame: SampleFrame) -> None:
        self._stored_raw_snapshot = None
        try:
            accepted = self.acquisition_service.ingest_frame(frame)
        except Exception as exc:
            self.log("ERRO", f"Frame recebido, mas não inserido nos buffers: {exc}")
            return

        snapshot = self.acquisition_service.snapshot()
        if not accepted:
            stats = snapshot.communication
            self.log(
                "AVISO",
                (
                    f"Frame rejeitado: packet_seq={frame.packet_sequence}, scan_seq={frame.scan_sequence}, "
                    f"duplicados={stats.duplicate_frames}, fora_ordem={stats.out_of_order_frames}, "
                    f"timestamp_regressivo={stats.timestamp_regressions}"
                ),
            )
            return

        if snapshot.frames_received == 1 or snapshot.frames_received % 50 == 0:
            stats = snapshot.communication
            self.log(
                "FRAME",
                (
                    f"frames={snapshot.frames_received}, packet_seq={snapshot.last_packet_sequence}, "
                    f"scan_seq={snapshot.last_scan_sequence}, gaps={stats.gap_events}, "
                    f"ausentes={stats.missing_frames}"
                ),
            )

    @pyqtSlot(str)
    def on_protocol_error(self, message: str) -> None:
        self.acquisition_service.record_invalid_frame()
        self.refresh_live_view(force=True)
        self.log("PROTOCOLO", f"Frame serial inválido: {message}")

    @pyqtSlot(str)
    def on_error(self, message: str) -> None:
        self.log("ERRO", message)

    @pyqtSlot(bool)
    def on_connection_changed(self, connected: bool) -> None:
        self.window.update_connection_state(connected)
        if not connected:
            self.acquisition_service.stop()
        state = "conectado" if connected else "desconectado"
        self.refresh_live_view(force=True)
        self.log("STATUS", f"Serial {state}.")

    def _format_summary_details(self, summary: StoredSessionSummary) -> str:
        csv_path = summary.metadata_path.parent / f"{summary.session_id}.csv"
        return "\n".join(
            [
                f"ID: {summary.session_id}",
                f"Criada em: {summary.created_at}",
                f"Frames: {summary.frames_received}",
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
                f"Metadados: {summary.metadata_path}",
                f"Dados: {summary.data_path}",
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
        processing_service=ProcessingService(),
        session_repository=SessionRepository(settings.sessions_dir),
        config_repository=ConfigRepository(settings.presets_dir),
        settings=settings,
    )
    window.controller = controller  # type: ignore[attr-defined]

    if settings.fullscreen:
        window.showFullScreen()
    else:
        window.show()
    return app.exec_()
