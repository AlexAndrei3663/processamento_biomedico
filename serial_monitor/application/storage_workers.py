from __future__ import annotations

import threading
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from serial_monitor.infrastructure.storage.session_repository import (
    ExportCancelledError,
    SessionRepository,
)


class CsvExportWorker(QThread):
    """Executa a exportação CSV fora da thread da interface."""

    progress_changed = pyqtSignal(int, int, int)  # percentual, concluídos, total
    completed = pyqtSignal(str)
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        repository: SessionRepository,
        session_id: str,
        output_path: Path | None = None,
        *,
        chunk_size: int = 4096,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.session_id = session_id
        self.output_path = output_path
        self.chunk_size = max(1, int(chunk_size))
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            path = self.repository.export_csv(
                self.session_id,
                self.output_path,
                chunk_size=self.chunk_size,
                progress_callback=self._on_progress,
                cancel_check=self._cancel_event.is_set,
            )
        except ExportCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.completed.emit(str(path))

    def _on_progress(self, completed: int, total: int) -> None:
        percent = 0 if total <= 0 else int(round(100 * completed / total))
        self.progress_changed.emit(max(0, min(100, percent)), completed, total)


class IntegrityCheckWorker(QThread):
    """Recalcula a integridade HDF5 sem bloquear a interface."""

    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, repository: SessionRepository, session_id: str) -> None:
        super().__init__()
        self.repository = repository
        self.session_id = session_id

    def run(self) -> None:
        try:
            status = self.repository.verify_integrity(self.session_id)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.completed.emit(status)
