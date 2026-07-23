from __future__ import annotations

import threading
import time

from serial_monitor.application.async_processing import LatestProcessingWorker


class _FakeProcessingService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.kwargs: list[dict] = []
        self.first_started = threading.Event()
        self.release_first = threading.Event()

    def process(self, snapshot: str, **kwargs):
        self.calls.append(snapshot)
        self.kwargs.append(kwargs)
        if snapshot == "first":
            self.first_started.set()
            assert self.release_first.wait(2.0)
        return f"processed:{snapshot}"


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def test_latest_request_wins() -> None:
    service = _FakeProcessingService()
    worker = LatestProcessingWorker(service)
    worker.start()
    try:
        worker.submit("first", channel_indexes={0})
        assert service.first_started.wait(1.0)

        worker.submit("second", channel_indexes={0})
        worker.submit("third", channel_indexes={1}, display_modes={1: "base"})
        service.release_first.set()

        assert _wait_until(lambda: len(service.calls) >= 2)
        assert service.calls == ["first", "third"]
        assert service.kwargs[-1]["channel_indexes"] == {1}
        assert service.kwargs[-1]["display_modes"] == {1: "base"}
        assert worker.statistics()["replaced"] >= 1
    finally:
        service.release_first.set()
        worker.stop()
        assert worker.wait(3000)


def test_invalidate_removes_pending_request() -> None:
    service = _FakeProcessingService()
    worker = LatestProcessingWorker(service)
    worker.start()
    try:
        worker.submit("first")
        assert service.first_started.wait(1.0)
        worker.submit("obsolete")
        worker.invalidate()
        service.release_first.set()

        assert _wait_until(lambda: service.calls == ["first"])
        time.sleep(0.05)
        assert service.calls == ["first"]
    finally:
        service.release_first.set()
        worker.stop()
        assert worker.wait(3000)
