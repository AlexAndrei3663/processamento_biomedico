from __future__ import annotations

from serial_monitor.infrastructure.storage.config_repository import ConfigRepository


def test_config_repository_saves_loads_lists_and_deletes(tmp_path):
    repository = ConfigRepository(tmp_path)

    saved = repository.save_preset(
        name="Teste ECG",
        port="/dev/ttyUSB0",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=500,
        signal_order_text="ecg,ppg",
    )

    assert saved.path.exists()
    assert saved.name == "Teste ECG"

    listed = repository.list_presets()
    assert [preset.name for preset in listed] == ["Teste ECG"]

    loaded = repository.load_preset("Teste ECG")
    assert loaded.port == "/dev/ttyUSB0"
    assert loaded.signal_order_text == "ecg,ppg"

    repository.delete_preset("Teste ECG")
    assert repository.list_presets() == []
