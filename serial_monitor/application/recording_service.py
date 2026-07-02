from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from serial_monitor.domain.enums import RecordingState
from serial_monitor.domain.models import (
    CommunicationStats,
    RecordingStatus,
    SampleFrame,
    SessionConfig,
)
from serial_monitor.infrastructure.storage.hdf5_session_writer import Hdf5SessionWriter


class RecordingQueueFullError(RuntimeError):
    """A fila de gravação atingiu o limite e a sessão foi marcada como falha."""


class RecordingService:
    """Grava continuamente todos os frames aceitos em uma thread dedicada.

    O serviço não lê buffers circulares. Cada frame aceito pela aquisição é enviado
    diretamente para uma fila limitada e persistido em HDF5 em pequenos lotes.
    """

    def __init__(
        self,
        base_dir: str | Path,
        *,
        queue_capacity: int = 8192,
        batch_size: int = 256,
        flush_interval_s: float = 1.0,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.queue_capacity = max(1, int(queue_capacity))
        self.batch_size = max(1, int(batch_size))
        self.flush_interval_s = max(0.05, float(flush_interval_s))

        self._lock = threading.RLock()
        self._queue: queue.Queue[SampleFrame] = queue.Queue(maxsize=self.queue_capacity)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._cancel_requested = False
        self._failed_reason: str | None = None
        self._final_communication = CommunicationStats()
        self._communication_baseline = CommunicationStats()
        self._end_reason = "user"

        self._state = RecordingState.IDLE
        self._session_id: str | None = None
        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None
        self._frames_enqueued = 0
        self._frames_written = 0
        self._output_path: Path | None = None
        self._partial_path: Path | None = None
        self._error_message: str | None = None
        self._writer: Hdf5SessionWriter | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._state == RecordingState.RECORDING

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._state in {RecordingState.RECORDING, RecordingState.FINALIZING}

    def start(
        self,
        session: SessionConfig,
        active_filters: Dict[int, List[str]] | None = None,
        communication_baseline: CommunicationStats | None = None,
    ) -> RecordingStatus:
        with self._lock:
            if self._state in {RecordingState.RECORDING, RecordingState.FINALIZING}:
                raise RuntimeError("Já existe uma gravação ativa.")

            self._queue = queue.Queue(maxsize=self.queue_capacity)
            self._stop_event = threading.Event()
            self._cancel_requested = False
            self._failed_reason = None
            self._final_communication = CommunicationStats()
            self._communication_baseline = communication_baseline or CommunicationStats()
            self._end_reason = "user"
            self._started_at = datetime.now()
            self._ended_at = None
            self._frames_enqueued = 0
            self._frames_written = 0
            self._output_path = None
            self._error_message = None

            session_id = self._started_at.strftime("session_%Y%m%d_%H%M%S_%f")[:-3]
            self._session_id = session_id
            writer = Hdf5SessionWriter(
                base_dir=self.base_dir,
                session_id=session_id,
                session=session,
                active_filters=active_filters,
                chunk_size=self.batch_size,
            )
            self._writer = writer
            self._partial_path = writer.partial_path
            self._state = RecordingState.RECORDING

            self._thread = threading.Thread(
                target=self._worker_loop,
                name=f"SessionWriter-{session_id}",
                daemon=True,
            )
            self._thread.start()
            return self.status()

    def enqueue_frame(self, frame: SampleFrame) -> None:
        with self._lock:
            if self._state != RecordingState.RECORDING:
                return

        try:
            self._queue.put_nowait(frame)
        except queue.Full as exc:
            message = (
                "Fila de gravação saturada. A sessão foi interrompida para evitar "
                "perda silenciosa de dados."
            )
            self.fail(message)
            raise RecordingQueueFullError(message) from exc

        with self._lock:
            self._frames_enqueued += 1

    def finalize(
        self,
        communication: CommunicationStats,
        *,
        reason: str = "user",
        timeout_s: float = 15.0,
    ) -> RecordingStatus:
        with self._lock:
            if self._state == RecordingState.IDLE:
                return self.status()
            if self._state in {RecordingState.COMPLETED, RecordingState.CANCELLED}:
                return self.status()
            if self._state == RecordingState.FAILED:
                thread = self._thread
            else:
                self._state = RecordingState.FINALIZING
                self._final_communication = self._communication_delta(communication)
                self._end_reason = reason
                self._stop_event.set()
                thread = self._thread

        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.1, timeout_s))
            if thread.is_alive():
                self.fail("Tempo excedido ao finalizar a gravação HDF5.")

        return self.status()

    def cancel(self, *, timeout_s: float = 10.0) -> RecordingStatus:
        with self._lock:
            if self._state == RecordingState.IDLE:
                return self.status()
            self._cancel_requested = True
            self._end_reason = "cancelled_by_user"
            self._state = RecordingState.FINALIZING
            self._stop_event.set()
            thread = self._thread

        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.1, timeout_s))
            if thread.is_alive():
                self.fail("Tempo excedido ao cancelar a gravação HDF5.")
        return self.status()

    def fail(
        self,
        message: str,
        communication: CommunicationStats | None = None,
    ) -> None:
        with self._lock:
            if self._state in {RecordingState.COMPLETED, RecordingState.CANCELLED}:
                return
            self._failed_reason = message
            self._error_message = message
            if communication is not None:
                self._final_communication = self._communication_delta(communication)
            self._state = RecordingState.FAILED
            self._end_reason = "recording_error"
            self._stop_event.set()

    def status(self) -> RecordingStatus:
        with self._lock:
            now = self._ended_at or datetime.now()
            duration = (
                max(0.0, (now - self._started_at).total_seconds())
                if self._started_at is not None
                else 0.0
            )
            output_path = self._output_path
            partial_path = self._partial_path
            state = self._state
            session_id = self._session_id
            started_at = (
                self._started_at.isoformat(timespec="milliseconds")
                if self._started_at is not None
                else None
            )
            ended_at = (
                self._ended_at.isoformat(timespec="milliseconds")
                if self._ended_at is not None
                else None
            )
            frames_enqueued = self._frames_enqueued
            frames_written = self._frames_written
            error_message = self._error_message
            end_reason = self._end_reason if self._started_at is not None else None

        path_for_size = output_path or partial_path
        try:
            file_size = int(path_for_size.stat().st_size) if path_for_size else 0
        except OSError:
            file_size = 0

        return RecordingStatus(
            state=state,
            session_id=session_id,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            frames_enqueued=frames_enqueued,
            frames_written=frames_written,
            queue_size=self._queue.qsize(),
            queue_capacity=self.queue_capacity,
            file_size_bytes=file_size,
            output_path=output_path,
            partial_path=partial_path,
            end_reason=end_reason,
            error_message=error_message,
        )

    def _communication_delta(self, current: CommunicationStats) -> CommunicationStats:
        baseline = self._communication_baseline
        return CommunicationStats(
            valid_frames=max(0, current.valid_frames - baseline.valid_frames),
            invalid_frames=max(0, current.invalid_frames - baseline.invalid_frames),
            checksum_errors=max(0, current.checksum_errors - baseline.checksum_errors),
            timestamp_regressions=max(
                0,
                current.timestamp_regressions - baseline.timestamp_regressions,
            ),
            sequence=type(current.sequence)(
                gap_events=max(
                    0, current.sequence.gap_events - baseline.sequence.gap_events
                ),
                missing_items=max(
                    0, current.sequence.missing_items - baseline.sequence.missing_items
                ),
                duplicate_items=max(
                    0, current.sequence.duplicate_items - baseline.sequence.duplicate_items
                ),
                out_of_order_items=max(
                    0,
                    current.sequence.out_of_order_items
                    - baseline.sequence.out_of_order_items,
                ),
            ),
        )

    def _worker_loop(self) -> None:
        writer = self._writer
        if writer is None:
            self.fail("Escritor HDF5 não foi configurado.")
            return

        batch: list[SampleFrame] = []
        last_flush = time.monotonic()

        try:
            writer.open()

            while True:
                if self._stop_event.is_set() and self._queue.empty():
                    break

                timeout = max(0.05, self.flush_interval_s - (time.monotonic() - last_flush))
                try:
                    frame = self._queue.get(timeout=timeout)
                except queue.Empty:
                    frame = None

                if frame is not None:
                    batch.append(frame)
                    self._queue.task_done()

                should_flush = (
                    len(batch) >= self.batch_size
                    or (batch and time.monotonic() - last_flush >= self.flush_interval_s)
                    or (batch and self._stop_event.is_set() and self._queue.empty())
                )
                if should_flush:
                    written = writer.append_batch(batch)
                    writer.flush()
                    batch.clear()
                    last_flush = time.monotonic()
                    with self._lock:
                        self._frames_written += written

            if batch:
                written = writer.append_batch(batch)
                writer.flush()
                with self._lock:
                    self._frames_written += written

            with self._lock:
                cancel_requested = self._cancel_requested
                failed_reason = self._failed_reason
                communication = self._final_communication
                end_reason = self._end_reason

            if cancel_requested:
                writer.cancel()
                with self._lock:
                    self._state = RecordingState.CANCELLED
                    self._ended_at = datetime.now()
                    self._partial_path = None
                    self._output_path = None
                return

            if failed_reason is not None:
                partial = writer.close_failed(
                    error_message=failed_reason,
                    communication=communication,
                )
                with self._lock:
                    self._state = RecordingState.FAILED
                    self._ended_at = datetime.now()
                    self._partial_path = partial
                return

            output = writer.finalize(
                communication=communication,
                end_reason=end_reason,
            )
            with self._lock:
                self._state = RecordingState.COMPLETED
                self._ended_at = datetime.now()
                self._output_path = output
                self._partial_path = None

        except Exception as exc:
            message = f"Falha na gravação HDF5: {exc}"
            try:
                partial = writer.close_failed(
                    error_message=message,
                    communication=self._final_communication,
                )
            except Exception:
                partial = writer.partial_path
            with self._lock:
                self._state = RecordingState.FAILED
                self._error_message = message
                self._failed_reason = message
                self._ended_at = datetime.now()
                self._partial_path = partial
