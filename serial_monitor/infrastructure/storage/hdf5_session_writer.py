from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import h5py
import numpy as np

from serial_monitor.domain.models import CommunicationStats, SampleFrame, SessionConfig


class Hdf5SessionWriter:
    """Escritor incremental de uma sessão sincronizada multicanal.

    Somente a thread de gravação deve acessar esta instância. Os datasets são
    extensíveis e recebem lotes de frames sem reescrever o arquivo inteiro.
    """

    FORMAT_VERSION = 4

    def __init__(
        self,
        *,
        base_dir: str | Path,
        session_id: str,
        session: SessionConfig,
        active_filters: Mapping[int, Sequence[str]] | None = None,
        chunk_size: int = 256,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.session_id = session_id
        self.session = session
        self.active_filters = {
            int(index): list(filters)
            for index, filters in (active_filters or {}).items()
        }
        self.chunk_size = max(1, int(chunk_size))

        self.partial_path = self.base_dir / f"{session_id}.partial.h5"
        self.final_path = self.base_dir / f"{session_id}.h5"

        self._file: h5py.File | None = None
        self._sequence_dataset: h5py.Dataset | None = None
        self._timestamp_dataset: h5py.Dataset | None = None
        self._values_dataset: h5py.Dataset | None = None
        self._frames_written = 0
        self._started_at = datetime.now()

    @property
    def frames_written(self) -> int:
        return self._frames_written

    @property
    def file_size_bytes(self) -> int:
        path = self.partial_path if self.partial_path.exists() else self.final_path
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0

    def open(self) -> None:
        if self._file is not None:
            raise RuntimeError("O escritor HDF5 já está aberto.")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        if self.partial_path.exists() or self.final_path.exists():
            raise FileExistsError(f"Já existe arquivo para a sessão {self.session_id}.")

        h5 = h5py.File(self.partial_path, "w")
        self._file = h5

        h5.attrs["format_version"] = self.FORMAT_VERSION
        h5.attrs["session_id"] = self.session_id
        h5.attrs["state"] = "recording"
        h5.attrs["created_at"] = self._started_at.isoformat(timespec="milliseconds")
        h5.attrs["started_at"] = self._started_at.isoformat(timespec="milliseconds")
        h5.attrs["ended_at"] = ""
        h5.attrs["end_reason"] = ""
        h5.attrs["frames_written"] = 0
        h5.attrs["channel_count"] = self.session.channel_count
        h5.attrs["base_sample_rate_hz"] = self.session.base_sample_rate_hz
        h5.attrs["window_size"] = self.session.window_size
        h5.attrs["port"] = self.session.port
        h5.attrs["baudrate"] = self.session.baudrate
        h5.attrs["protocol_mode"] = self.session.protocol_mode.value
        h5.attrs["protocol_contract"] = json.dumps(
            {
                "frame": "FRAME,<sequence_id>,<timestamp_us>,<v0>,...,<vN>",
                "sequence_id": "uint32; um incremento por ciclo multicanal; wrap em 2^32",
                "timestamp_us": "uint64; microssegundos desde o boot; primeira conversão do ciclo",
            },
            ensure_ascii=False,
        )
        h5.attrs["channels_json"] = json.dumps(
            [
                {
                    "index": channel.index,
                    "signal_type": channel.signal_type.value,
                    "display_name": channel.display_name,
                    "unit": channel.unit,
                    "sample_rate_hz": channel.sample_rate_hz,
                    "scale": channel.scale,
                    "offset": channel.offset,
                    "default_filters": list(channel.default_filters),
                }
                for channel in self.session.channels
            ],
            ensure_ascii=False,
        )
        h5.attrs["active_filters_json"] = json.dumps(
            {str(index): list(filters) for index, filters in self.active_filters.items()},
            ensure_ascii=False,
        )
        h5.attrs["communication_json"] = json.dumps({}, ensure_ascii=False)

        frames_group = h5.create_group("frames")
        self._sequence_dataset = frames_group.create_dataset(
            "sequence_id",
            shape=(0,),
            maxshape=(None,),
            dtype=np.uint32,
            chunks=(self.chunk_size,),
            compression="gzip",
            compression_opts=1,
            shuffle=True,
        )
        self._timestamp_dataset = frames_group.create_dataset(
            "timestamp_us",
            shape=(0,),
            maxshape=(None,),
            dtype=np.uint64,
            chunks=(self.chunk_size,),
            compression="gzip",
            compression_opts=1,
            shuffle=True,
        )
        self._values_dataset = frames_group.create_dataset(
            "raw_values",
            shape=(0, self.session.channel_count),
            maxshape=(None, self.session.channel_count),
            dtype=np.float64,
            chunks=(self.chunk_size, self.session.channel_count),
            compression="gzip",
            compression_opts=1,
            shuffle=True,
        )
        frames_group.attrs["layout"] = "rows=frames; columns=channel_index"
        h5.flush()

    def append_batch(self, frames: Iterable[SampleFrame]) -> int:
        batch = list(frames)
        if not batch:
            return 0
        if self._file is None:
            raise RuntimeError("O escritor HDF5 não está aberto.")
        assert self._sequence_dataset is not None
        assert self._timestamp_dataset is not None
        assert self._values_dataset is not None

        sequences = np.empty(len(batch), dtype=np.uint32)
        timestamps = np.empty(len(batch), dtype=np.uint64)
        values = np.empty((len(batch), self.session.channel_count), dtype=np.float64)

        for row, frame in enumerate(batch):
            if len(frame.values_in_order) != self.session.channel_count:
                raise ValueError(
                    f"Frame seq={frame.sequence_id} possui {len(frame.values_in_order)} valores; "
                    f"esperados {self.session.channel_count}."
                )
            sequences[row] = frame.sequence_id
            timestamps[row] = frame.timestamp_us
            values[row, :] = np.asarray(frame.values_in_order, dtype=np.float64)

        start = self._frames_written
        end = start + len(batch)
        self._sequence_dataset.resize((end,))
        self._timestamp_dataset.resize((end,))
        self._values_dataset.resize((end, self.session.channel_count))

        self._sequence_dataset[start:end] = sequences
        self._timestamp_dataset[start:end] = timestamps
        self._values_dataset[start:end, :] = values
        self._frames_written = end
        self._file.attrs["frames_written"] = self._frames_written
        return len(batch)

    def flush(self) -> None:
        if self._file is not None:
            self._file.attrs["frames_written"] = self._frames_written
            self._file.flush()

    def finalize(
        self,
        *,
        communication: CommunicationStats,
        end_reason: str,
    ) -> Path:
        if self._file is None:
            raise RuntimeError("O escritor HDF5 não está aberto.")

        ended_at = datetime.now()
        self._file.attrs["state"] = "completed"
        self._file.attrs["ended_at"] = ended_at.isoformat(timespec="milliseconds")
        self._file.attrs["end_reason"] = end_reason
        self._file.attrs["frames_written"] = self._frames_written
        self._file.attrs["duration_seconds"] = max(
            0.0,
            (ended_at - self._started_at).total_seconds(),
        )
        self._file.attrs["communication_json"] = json.dumps(
            self.communication_to_dict(communication),
            ensure_ascii=False,
        )
        self._file.flush()
        self._file.close()
        self._file = None

        os.replace(self.partial_path, self.final_path)
        return self.final_path

    def close_failed(
        self,
        *,
        error_message: str,
        communication: CommunicationStats | None = None,
    ) -> Path:
        if self._file is not None:
            ended_at = datetime.now()
            self._file.attrs["state"] = "failed"
            self._file.attrs["ended_at"] = ended_at.isoformat(timespec="milliseconds")
            self._file.attrs["end_reason"] = "recording_error"
            self._file.attrs["error_message"] = error_message
            self._file.attrs["frames_written"] = self._frames_written
            self._file.attrs["duration_seconds"] = max(
                0.0,
                (ended_at - self._started_at).total_seconds(),
            )
            if communication is not None:
                self._file.attrs["communication_json"] = json.dumps(
                    self.communication_to_dict(communication),
                    ensure_ascii=False,
                )
            self._file.flush()
            self._file.close()
            self._file = None
        return self.partial_path

    def cancel(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if self.partial_path.exists():
            self.partial_path.unlink()

    @staticmethod
    def communication_to_dict(stats: CommunicationStats) -> dict:
        return {
            "valid_frames": stats.valid_frames,
            "invalid_frames": stats.invalid_frames,
            "checksum_errors": stats.checksum_errors,
            "timestamp_regressions": stats.timestamp_regressions,
            "sequence": {
                "gap_events": stats.sequence.gap_events,
                "missing_items": stats.sequence.missing_items,
                "duplicate_items": stats.sequence.duplicate_items,
                "out_of_order_items": stats.sequence.out_of_order_items,
            },
        }
