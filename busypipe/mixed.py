from __future__ import annotations

import secrets
import struct

from .constants import MIXED_METADATA_LEN


MIXED_METADATA_FORMAT = "!HH4s"


class MixedPayloadError(Exception):
    """Raised when a MIXED payload cannot be built or parsed."""


class MixedPayloadBuilder:
    def __init__(self, *, min_jitter_bytes: int = 8) -> None:
        if min_jitter_bytes < 0:
            raise ValueError("min_jitter_bytes must be non-negative")
        self.min_jitter_bytes = min_jitter_bytes
        self.last_offset: int | None = None

    def build(self, data: bytes, target_payload_len: int) -> bytes:
        if not data:
            raise MixedPayloadError("MIXED payload requires non-empty data")
        if len(data) > 0xFFFF:
            raise MixedPayloadError("data is too large for MIXED payload metadata")
        if target_payload_len > 0xFFFF:
            raise MixedPayloadError("target payload is too large")

        min_offset = MIXED_METADATA_LEN
        max_offset = target_payload_len - len(data)
        offset = self._choose_offset(min_offset, max_offset)
        if offset is None:
            raise MixedPayloadError("unable to satisfy MIXED jitter constraints")

        prefix_len = offset - MIXED_METADATA_LEN
        suffix_len = target_payload_len - offset - len(data)
        if suffix_len < 0:
            raise MixedPayloadError("target payload is smaller than data")

        metadata = struct.pack(
            MIXED_METADATA_FORMAT,
            offset,
            len(data),
            secrets.token_bytes(4),
        )
        self.last_offset = offset
        return metadata + secrets.token_bytes(prefix_len) + data + secrets.token_bytes(suffix_len)

    def parse(self, payload: bytes) -> bytes:
        if len(payload) < MIXED_METADATA_LEN:
            raise MixedPayloadError("MIXED payload is too short")

        data_offset, data_length, _nonce = struct.unpack(
            MIXED_METADATA_FORMAT,
            payload[:MIXED_METADATA_LEN],
        )
        if data_offset < MIXED_METADATA_LEN:
            raise MixedPayloadError("MIXED data offset points into metadata")
        if data_length <= 0:
            raise MixedPayloadError("MIXED data length must be positive")

        data_end = data_offset + data_length
        if data_end > len(payload):
            raise MixedPayloadError("MIXED data range exceeds payload length")

        return payload[data_offset:data_end]

    def _choose_offset(self, min_offset: int, max_offset: int) -> int | None:
        if max_offset < min_offset:
            return None

        if self.last_offset is None:
            return secrets.randbelow(max_offset - min_offset + 1) + min_offset

        candidates = [
            offset
            for offset in range(min_offset, max_offset + 1)
            if abs(offset - self.last_offset) >= self.min_jitter_bytes
        ]
        if not candidates:
            return None

        return secrets.choice(candidates)
