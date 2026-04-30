from __future__ import annotations

from enum import IntEnum


MAGIC = 0x4250
VERSION = 1
HEADER_LEN = 16

DEFAULT_MIN_BPS = 8000
DEFAULT_TICK_MS = 250
DEFAULT_MAX_FRAME_SIZE = 1400
DEFAULT_IDLE_TIMEOUT_MS = 15_000
DEFAULT_MIN_JITTER_BYTES = 8
DEFAULT_DIRECTION = "bidirectional"

MIXED_METADATA_LEN = 8


class FrameType(IntEnum):
    HELLO = 0x01
    DATA = 0x02
    PAD = 0x03
    PING = 0x04
    PONG = 0x05
    CLOSE = 0x06
    MIXED = 0x07
