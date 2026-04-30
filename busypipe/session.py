from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, asdict

from .constants import (
    DEFAULT_DIRECTION,
    DEFAULT_IDLE_TIMEOUT_MS,
    DEFAULT_MAX_FRAME_SIZE,
    DEFAULT_MIN_BPS,
    DEFAULT_MIN_JITTER_BYTES,
    DEFAULT_TICK_MS,
    HEADER_LEN,
    MIXED_METADATA_LEN,
    VERSION,
    FrameType,
)
from .frame import Frame, FrameCodec, ProtocolError
from .mixed import MixedPayloadBuilder, MixedPayloadError
from .scheduler import MinRateScheduler


@dataclass(frozen=True)
class BusyPipeConfig:
    version: int = VERSION
    min_bps: int = DEFAULT_MIN_BPS
    tick_ms: int = DEFAULT_TICK_MS
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE
    idle_timeout_ms: int = DEFAULT_IDLE_TIMEOUT_MS
    min_jitter_bytes: int = DEFAULT_MIN_JITTER_BYTES
    direction: str = DEFAULT_DIRECTION

    def to_json(self) -> bytes:
        return json.dumps(asdict(self), separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_json(cls, payload: bytes) -> "BusyPipeConfig":
        data = json.loads(payload.decode("utf-8"))
        return cls(**data)

    def negotiate(self, peer: "BusyPipeConfig") -> "BusyPipeConfig":
        if self.version != peer.version:
            raise ProtocolError("incompatible BusyPipe protocol version")
        return BusyPipeConfig(
            version=self.version,
            min_bps=max(self.min_bps, peer.min_bps),
            tick_ms=max(self.tick_ms, peer.tick_ms),
            max_frame_size=min(self.max_frame_size, peer.max_frame_size),
            idle_timeout_ms=min(self.idle_timeout_ms, peer.idle_timeout_ms),
            min_jitter_bytes=max(self.min_jitter_bytes, peer.min_jitter_bytes),
            direction=self.direction if self.direction == peer.direction else DEFAULT_DIRECTION,
        )


class BusyPipeSession:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        config: BusyPipeConfig | None = None,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.config = config or BusyPipeConfig()
        self.codec = FrameCodec(max_frame_size=self.config.max_frame_size)
        self.scheduler = MinRateScheduler(
            min_bps=self.config.min_bps,
            tick_ms=self.config.tick_ms,
        )
        self.mixer = MixedPayloadBuilder(min_jitter_bytes=self.config.min_jitter_bytes)
        self.recv_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._write_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._established = False
        self._closed = False
        self._last_received_at = time.monotonic()

    async def start(self) -> None:
        await self._handshake()
        self._established = True
        self._last_received_at = time.monotonic()
        self._tasks.add(asyncio.create_task(self._read_loop()))
        self._tasks.add(asyncio.create_task(self._keepalive_loop()))
        self._tasks.add(asyncio.create_task(self._idle_watch_loop()))

    async def send(self, data: bytes) -> None:
        if self._closed:
            raise ConnectionError("BusyPipe session is closed")
        if not data:
            return

        for chunk in self._split_for_mixed(data):
            await self._send_data_chunk(chunk)

    async def recv(self) -> bytes:
        if self._closed and self.recv_queue.empty():
            raise ConnectionError("BusyPipe session is closed")
        return await self.recv_queue.get()

    async def close(self) -> None:
        if self._closed:
            return
        with contextlib.suppress(Exception):
            if self._established:
                await self._write_frame(FrameType.CLOSE, b"")
        await self._shutdown()

    async def wait_closed(self) -> None:
        while not self._closed:
            await asyncio.sleep(0.05)

    async def _handshake(self) -> None:
        await self._write_frame(FrameType.HELLO, self.config.to_json(), record_rate=False)
        frame = await self.codec.read_frame(self.reader)
        if frame.frame_type != FrameType.HELLO:
            raise ProtocolError("expected HELLO frame")

        peer_config = BusyPipeConfig.from_json(frame.payload)
        negotiated = self.config.negotiate(peer_config)
        self.config = negotiated
        self.codec.max_frame_size = negotiated.max_frame_size
        self.scheduler = MinRateScheduler(
            min_bps=negotiated.min_bps,
            tick_ms=negotiated.tick_ms,
        )
        self.mixer = MixedPayloadBuilder(min_jitter_bytes=negotiated.min_jitter_bytes)

    async def _read_loop(self) -> None:
        try:
            while not self._closed:
                frame = await self.codec.read_frame(self.reader)
                self._last_received_at = time.monotonic()
                await self._handle_frame(frame)
        except (asyncio.IncompleteReadError, ConnectionError, ProtocolError, MixedPayloadError):
            await self._shutdown()

    async def _handle_frame(self, frame: Frame) -> None:
        if frame.frame_type == FrameType.DATA:
            await self.recv_queue.put(frame.payload)
        elif frame.frame_type == FrameType.MIXED:
            await self.recv_queue.put(self.mixer.parse(frame.payload))
        elif frame.frame_type == FrameType.PAD:
            return
        elif frame.frame_type == FrameType.PING:
            await self._write_frame(FrameType.PONG, frame.payload)
        elif frame.frame_type == FrameType.PONG:
            return
        elif frame.frame_type == FrameType.CLOSE:
            await self._shutdown()
        elif frame.frame_type == FrameType.HELLO:
            raise ProtocolError("unexpected HELLO after handshake")

    async def _keepalive_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self.config.tick_ms / 1000)
                deficit = self.scheduler.consume_deficit()
                if deficit > 0:
                    payload_len = max(0, min(deficit - HEADER_LEN, self.codec.max_payload_size))
                    await self._write_frame(FrameType.PAD, self._random_pad(payload_len))
        except (ConnectionError, ProtocolError, asyncio.CancelledError):
            if not self._closed:
                await self._shutdown()

    async def _idle_watch_loop(self) -> None:
        timeout = self.config.idle_timeout_ms / 1000
        try:
            while not self._closed:
                await asyncio.sleep(min(1.0, timeout))
                if time.monotonic() - self._last_received_at > timeout:
                    await self._shutdown()
        except asyncio.CancelledError:
            return

    async def _send_data_chunk(self, data: bytes) -> None:
        target_payload_len = min(
            self.codec.max_payload_size,
            max(MIXED_METADATA_LEN + len(data) + self.config.min_jitter_bytes, 64),
        )
        try:
            payload = self.mixer.build(data, target_payload_len)
        except MixedPayloadError:
            await self._write_frame(FrameType.DATA, data)
            return
        await self._write_frame(FrameType.MIXED, payload)

    async def _write_frame(
        self,
        frame_type: FrameType,
        payload: bytes,
        *,
        record_rate: bool = True,
    ) -> None:
        frame = self.codec.encode(frame_type, payload)
        async with self._write_lock:
            self.writer.write(frame)
            await self.writer.drain()
        if record_rate:
            self.scheduler.record_sent(len(frame))

    async def _shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current:
                task.cancel()
        self.writer.close()
        with contextlib.suppress(Exception):
            await self.writer.wait_closed()

    def _split_for_mixed(self, data: bytes) -> list[bytes]:
        max_mixed_data = self.codec.max_payload_size - MIXED_METADATA_LEN - self.config.min_jitter_bytes
        max_data = max(1, max_mixed_data)
        return [data[index : index + max_data] for index in range(0, len(data), max_data)]

    @staticmethod
    def _random_pad(size: int) -> bytes:
        if size <= 0:
            return b""
        import secrets

        return secrets.token_bytes(size)

    @property
    def is_closed(self) -> bool:
        return self._closed
