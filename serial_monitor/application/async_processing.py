from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, RLock
from typing import Any, Dict, Mapping

from PyQt5.QtCore import QThread, pyqtSignal


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    """Snapshot imutável de uma solicitação de renderização.

    O ``request_id`` é monotônico. O controlador usa esse identificador para
    ignorar resultados produzidos depois que canal, domínio ou modo mudou.
    """

    request_id: int
    snapshot: Any
    channel_indexes: frozenset[int] | None
    spectrum_modes: Mapping[int, str] | None
    display_modes: Mapping[int, str] | None


class SynchronizedProcessingService:
    """Fachada que serializa acesso ao ProcessingService existente.

    A etapa mantém o serviço original e sua API. O bloqueio apenas impede que
    uma alteração de filtro/configuração concorra com ``process()`` na thread
    de trabalho.
    """

    def __init__(self, service: Any) -> None:
        self._service = service
        self._lock = RLock()

    @property
    def wrapped_service(self) -> Any:
        return self._service

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._service, name)
        if not callable(attribute):
            return attribute

        def synchronized_call(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return attribute(*args, **kwargs)

        return synchronized_call


def ensure_thread_safe_processing_service(service: Any) -> SynchronizedProcessingService:
    if isinstance(service, SynchronizedProcessingService):
        return service
    return SynchronizedProcessingService(service)


class LatestProcessingWorker(QThread):
    """Executa somente a solicitação pendente mais recente.

    Não há fila crescente. Se a GUI solicitar novas renderizações enquanto um
    cálculo está em andamento, apenas a solicitação mais recente permanece na
    caixa postal. O cálculo em andamento termina normalmente e seu resultado
    pode ser descartado pelo controlador quando estiver obsoleto.
    """

    result_ready = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, processing_service: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.processing_service = ensure_thread_safe_processing_service(
            processing_service
        )
        self._condition = Condition()
        self._pending: ProcessingRequest | None = None
        self._stopping = False
        self._next_request_id = 0
        self._submitted = 0
        self._replaced = 0
        self._completed = 0
        self._failed = 0

    def submit(
        self,
        snapshot: Any,
        *,
        channel_indexes: set[int] | frozenset[int] | None = None,
        spectrum_modes: Dict[int, str] | None = None,
        display_modes: Dict[int, str] | None = None,
    ) -> int:
        """Substitui a solicitação pendente e devolve seu identificador."""
        with self._condition:
            if self._stopping:
                raise RuntimeError("O trabalhador de processamento está encerrando.")
            self._next_request_id += 1
            request_id = self._next_request_id
            if self._pending is not None:
                self._replaced += 1
            self._pending = ProcessingRequest(
                request_id=request_id,
                snapshot=snapshot,
                channel_indexes=(
                    None if channel_indexes is None else frozenset(channel_indexes)
                ),
                spectrum_modes=(
                    None if spectrum_modes is None else dict(spectrum_modes)
                ),
                display_modes=(
                    None if display_modes is None else dict(display_modes)
                ),
            )
            self._submitted += 1
            self._condition.notify()
            return request_id

    def invalidate(self) -> int:
        """Descarta a solicitação pendente e cria uma barreira de obsolescência."""
        with self._condition:
            self._next_request_id += 1
            request_id = self._next_request_id
            if self._pending is not None:
                self._replaced += 1
            self._pending = None
            return request_id

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._pending = None
            self._condition.notify_all()

    def statistics(self) -> dict[str, int]:
        with self._condition:
            return {
                "submitted": self._submitted,
                "replaced": self._replaced,
                "completed": self._completed,
                "failed": self._failed,
                "pending": int(self._pending is not None),
            }

    def run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                request = self._pending
                self._pending = None

            assert request is not None
            try:
                result = self.processing_service.process(
                    request.snapshot,
                    channel_indexes=(
                        None
                        if request.channel_indexes is None
                        else set(request.channel_indexes)
                    ),
                    spectrum_modes=(
                        None
                        if request.spectrum_modes is None
                        else dict(request.spectrum_modes)
                    ),
                    display_modes=(
                        None
                        if request.display_modes is None
                        else dict(request.display_modes)
                    ),
                )
            except Exception as exc:  # a GUI recebe mensagem, não a exceção bruta
                with self._condition:
                    self._failed += 1
                self.failed.emit(request.request_id, str(exc))
                continue

            with self._condition:
                self._completed += 1
            self.result_ready.emit(request.request_id, result)
