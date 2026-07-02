from __future__ import annotations

import hashlib
from typing import Protocol

import h5py
import numpy as np


class HashLike(Protocol):
    def update(self, data: bytes) -> None: ...
    def hexdigest(self) -> str: ...


def update_content_hash(
    hasher: HashLike,
    sequence_ids: np.ndarray,
    timestamps_us: np.ndarray,
    raw_values: np.ndarray,
) -> None:
    """Atualiza o hash de conteúdo com representação binária canônica."""

    hasher.update(np.asarray(sequence_ids, dtype="<u4").tobytes(order="C"))
    hasher.update(np.asarray(timestamps_us, dtype="<u8").tobytes(order="C"))
    hasher.update(np.asarray(raw_values, dtype="<f8").tobytes(order="C"))


def calculate_content_sha256(h5: h5py.File, *, chunk_size: int = 8192) -> str:
    """Calcula SHA-256 dos datasets de frames sem carregar a sessão inteira."""

    sequences = h5["frames/sequence_id"]
    timestamps = h5["frames/timestamp_us"]
    values = h5["frames/raw_values"]
    frame_count = min(int(sequences.shape[0]), int(timestamps.shape[0]), int(values.shape[0]))

    hasher = hashlib.sha256()
    for start in range(0, frame_count, max(1, int(chunk_size))):
        end = min(frame_count, start + max(1, int(chunk_size)))
        update_content_hash(
            hasher,
            np.asarray(sequences[start:end], dtype=np.uint32),
            np.asarray(timestamps[start:end], dtype=np.uint64),
            np.asarray(values[start:end, :], dtype=np.float64),
        )
    return hasher.hexdigest()
