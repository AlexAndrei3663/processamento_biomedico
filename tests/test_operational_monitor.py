from __future__ import annotations

from collections import namedtuple

from serial_monitor.application.operational_monitor import OperationalMonitor


DiskUsage = namedtuple("DiskUsage", "total used free")


def test_operational_monitor_reads_linux_resources(tmp_path) -> None:
    proc = tmp_path / "proc"
    thermal = tmp_path / "sys" / "class" / "thermal" / "thermal_zone0"
    proc.mkdir()
    thermal.mkdir(parents=True)
    (proc / "stat").write_text("cpu  100 0 100 800 0 0 0 0 0 0\n", encoding="utf-8")
    (proc / "meminfo").write_text(
        "MemTotal: 1000 kB\nMemAvailable: 600 kB\n", encoding="utf-8"
    )
    (thermal / "temp").write_text("52500\n", encoding="utf-8")

    monitor = OperationalMonitor(
        tmp_path,
        proc_root=proc,
        sys_root=tmp_path / "sys",
        disk_usage=lambda _: DiskUsage(1000, 400, 600),
    )
    first = monitor.sample()
    assert first.cpu_percent is None
    assert first.memory_percent == 40.0
    assert first.temperature_c == 52.5
    assert first.disk_free_bytes == 600

    (proc / "stat").write_text("cpu  150 0 150 900 0 0 0 0 0 0\n", encoding="utf-8")
    second = monitor.sample()
    assert second.cpu_percent == 50.0


def test_operational_monitor_tolerates_unavailable_platform_files(tmp_path) -> None:
    monitor = OperationalMonitor(
        tmp_path,
        proc_root=tmp_path / "missing_proc",
        sys_root=tmp_path / "missing_sys",
        disk_usage=lambda _: DiskUsage(1000, 100, 900),
    )
    snapshot = monitor.sample()
    assert snapshot.cpu_percent is None
    assert snapshot.memory_percent is None
    assert snapshot.temperature_c is None
    assert snapshot.disk_free_bytes == 900
