from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np

from serial_monitor.domain.enums import ProtocolMode, SignalType
from serial_monitor.domain.models import (
    AcquisitionSnapshot,
    ChannelBufferSnapshot,
    SessionConfig,
    SignalChannelConfig,
)


@dataclass(frozen=True, slots=True)
class StoredSessionSummary:
    session_id: str
    created_at: str
    frames_received: int
    sequence_gaps: int
    channel_count: int
    base_sample_rate_hz: int
    channel_labels: List[str]
    metadata_path: Path
    data_path: Path


@dataclass(frozen=True, slots=True)
class StoredSessionData:
    summary: StoredSessionSummary
    session: SessionConfig
    snapshot: AcquisitionSnapshot
    active_filters: Dict[int, List[str]]


class SessionRepository:
    """Repositório de sessões salvas em disco.

    A etapa 7 usa dois arquivos por sessão:
    - JSON: metadados legíveis e indexáveis;
    - NPZ: arrays NumPy com valores, timestamps e sequências de cada canal.
    """

    METADATA_SUFFIX = ".json"
    DATA_SUFFIX = ".npz"

    def __init__(self, base_dir: str | Path = "data/sessions") -> None:
        self.base_dir = Path(base_dir)

    def save(
        self,
        session: SessionConfig,
        snapshot: AcquisitionSnapshot,
        active_filters: Dict[int, List[str]] | None = None,
    ) -> StoredSessionSummary:
        if not snapshot.configured:
            raise ValueError("A aquisição ainda não foi configurada.")
        if snapshot.frames_received <= 0:
            raise ValueError("Não há frames recebidos para salvar.")
        if not snapshot.channels:
            raise ValueError("Não há canais com dados para salvar.")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        session_id = now.strftime("session_%Y%m%d_%H%M%S_%f")[:-3]
        metadata_path = self.base_dir / f"{session_id}{self.METADATA_SUFFIX}"
        data_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"

        active_filters = active_filters or {}
        metadata = self._build_metadata(
            session_id=session_id,
            created_at=now.isoformat(timespec="seconds"),
            session=session,
            snapshot=snapshot,
            active_filters=active_filters,
            data_filename=data_path.name,
        )

        arrays: Dict[str, np.ndarray] = {}
        for channel_index, channel_snapshot in snapshot.channels.items():
            arrays[f"ch{channel_index}_values"] = np.asarray(channel_snapshot.values, dtype=float)
            arrays[f"ch{channel_index}_timestamps_ms"] = np.asarray(
                channel_snapshot.timestamps_ms,
                dtype=np.int64,
            )
            arrays[f"ch{channel_index}_sequence_ids"] = np.asarray(
                channel_snapshot.sequence_ids,
                dtype=np.int64,
            )

        np.savez_compressed(data_path, allow_pickle=False, **arrays)
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return self._summary_from_metadata(metadata, metadata_path)

    def list_sessions(self) -> List[StoredSessionSummary]:
        if not self.base_dir.exists():
            return []

        summaries: List[StoredSessionSummary] = []
        for metadata_path in self.base_dir.glob(f"*{self.METADATA_SUFFIX}"):
            try:
                metadata = self._read_metadata(metadata_path)
                summary = self._summary_from_metadata(metadata, metadata_path)
                if summary.data_path.exists():
                    summaries.append(summary)
            except Exception:
                # Arquivos corrompidos ou incompletos são ignorados na listagem.
                continue

        return sorted(summaries, key=lambda item: item.created_at, reverse=True)

    def load(self, session_id: str) -> StoredSessionData:
        metadata_path = self.base_dir / f"{session_id}{self.METADATA_SUFFIX}"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadados da sessão não encontrados: {metadata_path}")

        metadata = self._read_metadata(metadata_path)
        summary = self._summary_from_metadata(metadata, metadata_path)
        if not summary.data_path.exists():
            raise FileNotFoundError(f"Dados da sessão não encontrados: {summary.data_path}")

        session = self._session_from_metadata(metadata)
        active_filters = {
            int(index): list(filters)
            for index, filters in metadata.get("active_filters", {}).items()
        }

        with np.load(summary.data_path) as data:
            channel_snapshots: Dict[int, ChannelBufferSnapshot] = {}
            for channel in session.channels:
                values = np.asarray(data.get(f"ch{channel.index}_values", np.array([], dtype=float)), dtype=float)
                timestamps_ms = np.asarray(
                    data.get(f"ch{channel.index}_timestamps_ms", np.array([], dtype=np.int64)),
                    dtype=np.int64,
                )
                sequence_ids = np.asarray(
                    data.get(f"ch{channel.index}_sequence_ids", np.array([], dtype=np.int64)),
                    dtype=np.int64,
                )
                if len(timestamps_ms) and len(values) == len(timestamps_ms):
                    x_seconds = (timestamps_ms - timestamps_ms[0]) / 1000.0
                    last_value = float(values[-1])
                    last_timestamp_ms = int(timestamps_ms[-1])
                else:
                    x_seconds = np.array([], dtype=float)
                    last_value = None
                    last_timestamp_ms = None

                channel_snapshots[channel.index] = ChannelBufferSnapshot(
                    channel=channel,
                    sample_count=int(len(values)),
                    x_seconds=x_seconds,
                    values=values,
                    timestamps_ms=timestamps_ms,
                    sequence_ids=sequence_ids,
                    last_value=last_value,
                    last_timestamp_ms=last_timestamp_ms,
                )

        snapshot = AcquisitionSnapshot(
            configured=True,
            running=False,
            frames_received=int(metadata.get("frames_received", 0)),
            sequence_gaps=int(metadata.get("sequence_gaps", 0)),
            last_sequence_id=metadata.get("last_sequence_id"),
            last_timestamp_ms=metadata.get("last_timestamp_ms"),
            channels=channel_snapshots,
        )

        return StoredSessionData(
            summary=summary,
            session=session,
            snapshot=snapshot,
            active_filters=active_filters,
        )

    def _build_metadata(
        self,
        *,
        session_id: str,
        created_at: str,
        session: SessionConfig,
        snapshot: AcquisitionSnapshot,
        active_filters: Dict[int, List[str]],
        data_filename: str,
    ) -> dict:
        return {
            "version": 1,
            "session_id": session_id,
            "created_at": created_at,
            "data_filename": data_filename,
            "frames_received": snapshot.frames_received,
            "sequence_gaps": snapshot.sequence_gaps,
            "last_sequence_id": snapshot.last_sequence_id,
            "last_timestamp_ms": snapshot.last_timestamp_ms,
            "active_filters": {str(index): list(filters) for index, filters in active_filters.items()},
            "session": {
                "port": session.port,
                "baudrate": session.baudrate,
                "base_sample_rate_hz": session.base_sample_rate_hz,
                "window_size": session.window_size,
                "protocol_mode": session.protocol_mode.value,
                "channels": [
                    {
                        "index": channel.index,
                        "signal_type": channel.signal_type.value,
                        "display_name": channel.display_name,
                        "unit": channel.unit,
                        "sample_rate_hz": channel.sample_rate_hz,
                        "scale": channel.scale,
                        "offset": channel.offset,
                        "default_filters": list(channel.default_filters),
                        "sample_count": snapshot.channels[channel.index].sample_count
                        if channel.index in snapshot.channels
                        else 0,
                    }
                    for channel in session.channels
                ],
            },
        }

    def _read_metadata(self, metadata_path: Path) -> dict:
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def _summary_from_metadata(self, metadata: dict, metadata_path: Path) -> StoredSessionSummary:
        session_metadata = metadata.get("session", {})
        channels = session_metadata.get("channels", [])
        data_filename = metadata.get("data_filename", metadata_path.with_suffix(self.DATA_SUFFIX).name)
        labels = [
            f"ch{channel.get('index')}:{channel.get('display_name', channel.get('signal_type', 'sinal'))}"
            for channel in channels
        ]
        return StoredSessionSummary(
            session_id=str(metadata.get("session_id", metadata_path.stem)),
            created_at=str(metadata.get("created_at", "")),
            frames_received=int(metadata.get("frames_received", 0)),
            sequence_gaps=int(metadata.get("sequence_gaps", 0)),
            channel_count=len(channels),
            base_sample_rate_hz=int(session_metadata.get("base_sample_rate_hz", 0)),
            channel_labels=labels,
            metadata_path=metadata_path,
            data_path=metadata_path.parent / data_filename,
        )

    def _session_from_metadata(self, metadata: dict) -> SessionConfig:
        session_metadata = metadata["session"]
        channels = []
        for channel_metadata in session_metadata.get("channels", []):
            channels.append(
                SignalChannelConfig(
                    index=int(channel_metadata["index"]),
                    signal_type=SignalType.from_text(str(channel_metadata["signal_type"])),
                    display_name=str(channel_metadata["display_name"]),
                    unit=str(channel_metadata["unit"]),
                    sample_rate_hz=float(channel_metadata["sample_rate_hz"]),
                    scale=float(channel_metadata.get("scale", 1.0)),
                    offset=float(channel_metadata.get("offset", 0.0)),
                    default_filters=list(channel_metadata.get("default_filters", [])),
                )
            )

        return SessionConfig(
            port=str(session_metadata.get("port", "stored-session")),
            baudrate=int(session_metadata.get("baudrate", 1)),
            base_sample_rate_hz=int(session_metadata["base_sample_rate_hz"]),
            window_size=int(session_metadata["window_size"]),
            protocol_mode=ProtocolMode(str(session_metadata.get("protocol_mode", ProtocolMode.FRAME_CSV.value))),
            channels=channels,
        )
