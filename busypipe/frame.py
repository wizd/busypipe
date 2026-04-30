from __future__ import annotations

import asyncio
import struct
import zlib
from dataclasses import dataclass

from .constants import HEADER_LEN, MAGIC, VERSION, FrameType


HEADER_FORMAT = "!HBBBBHII"


class ProtocolError(Exception):
    """Raised when a BusyPipe frame violates the wire protocol."""


@dataclass(frozen=True)
class Frame:
    frame_type: FrameType
    payload: bytes
    flags: int
    seq: int


class FrameCodec:
    def __init__(self, *, max_frame_size: int = 1400) -> None:
        if max_frame_size < HEADER_LEN:
            raise ValueError("max_frame_size must be at least HEADER_LEN")
        self.max_frame_size = max_frame_size
        self._next_seq = 0

    def encode(self, frame_type: FrameType | int, payload: bytes = b"", flags: int = 0) -> bytes:
        frame_type = FrameType(frame_type)
        if len(payload) > self.max_payload_size:
            raise ProtocolError("payload exceeds negotiated max frame size")

        seq = self._next_seq
        self._next_seq = (self._next_seq + 1) & 0xFFFFFFFF

        header_without_crc = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            VERSION,
            int(frame_type),
            flags,
            HEADER_LEN,
            len(payload),
            seq,
            0,
        )
        crc = zlib.crc32(header_without_crc) & 0xFFFFFFFF
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            VERSION,
            int(frame_type),
            flags,
            HEADER_LEN,
            len(payload),
            seq,
            crc,
        )
        return header + payload

    async def read_frame(self, reader: asyncio.StreamReader) -> Frame:
        header = await reader.readexactly(HEADER_LEN)
        magic, version, frame_type, flags, header_len, length, seq, crc = struct.unpack(
            HEADER_FORMAT, header
        )

        if magic != MAGIC:
            raise ProtocolError("invalid frame magic")
        if version != VERSION:
            raise ProtocolError("unsupported frame version")
        if header_len != HEADER_LEN:
            raise ProtocolError("unsupported frame header length")
        if header_len + length > self.max_frame_size:
            raise ProtocolError("frame exceeds negotiated max frame size")

        header_for_crc = struct.pack(
            HEADER_FORMAT,
            magic,
            version,
            frame_type,
            flags,
            header_len,
            length,
            seq,
            0,
        )
        expected_crc = zlib.crc32(header_for_crc) & 0xFFFFFFFF
        if crc != expected_crc:
            raise ProtocolError("invalid frame header crc")

        try:
            parsed_type = FrameType(frame_type)
        except ValueError as exc:
            raise ProtocolError("unknown frame type") from exc

        payload = await reader.readexactly(length)
        return Frame(frame_type=parsed_type, payload=payload, flags=flags, seq=seq)

    @property
    def max_payload_size(self) -> int:
        return self.max_frame_size - HEADER_LEN
