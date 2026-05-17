from __future__ import annotations

import contextlib
import time
import unittest

from busypipe import BusyPipeClient, BusyPipeConfig, BusyPipeServer
from busypipe.constants import FrameType


class ClientServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_server_echo(self) -> None:
        async def echo(session):
            with contextlib.suppress(ConnectionError):
                while not session.is_closed:
                    data = await session.recv()
                    await session.send(data)

        config = BusyPipeConfig(tick_ms=50, idle_timeout_ms=2000, warmup_ms=0)
        server = BusyPipeServer(config=config, on_session=echo)
        await server.start("127.0.0.1", 0)
        port = server.sockets()[0].getsockname()[1]

        client = BusyPipeClient(config=config)
        session = await client.connect("127.0.0.1", port)
        try:
            await session.send(b"hello over busypipe")
            response = await session.recv()
            self.assertEqual(response, b"hello over busypipe")
        finally:
            await session.close()
            await server.close()

    async def test_high_rate_path_sends_direct_data_frames(self) -> None:
        async def echo(session):
            with contextlib.suppress(ConnectionError):
                while not session.is_closed:
                    data = await session.recv()
                    await session.send(data)

        config = BusyPipeConfig(tick_ms=250, idle_timeout_ms=2000, warmup_ms=0)
        server = BusyPipeServer(config=config, on_session=echo)
        await server.start("127.0.0.1", 0)
        port = server.sockets()[0].getsockname()[1]

        client = BusyPipeClient(config=config)
        session = await client.connect("127.0.0.1", port)
        sent_types: list[FrameType] = []
        original_write_frame = session._write_frame

        async def traced_write_frame(frame_type, payload, *, record_rate=True):
            sent_types.append(frame_type)
            await original_write_frame(frame_type, payload, record_rate=record_rate)

        session._write_frame = traced_write_frame  # type: ignore[assignment]

        large_payload = b"a" * 512
        small_payload = b"data-path"
        try:
            await session.send(large_payload)
            self.assertEqual(session.scheduler.deficit, 0)

            await session.send(small_payload)

            self.assertEqual(await session.recv(), large_payload)
            self.assertEqual(await session.recv(), small_payload)

            self.assertIn(FrameType.MIXED, sent_types)
            self.assertIn(FrameType.DATA, sent_types)
        finally:
            await session.close()
            await server.close()

    async def test_warmup_blocks_send_until_window_ends(self) -> None:
        async def echo(session):
            with contextlib.suppress(ConnectionError):
                while not session.is_closed:
                    data = await session.recv()
                    await session.send(data)

        config = BusyPipeConfig(tick_ms=50, idle_timeout_ms=2000, warmup_ms=200)
        server = BusyPipeServer(config=config, on_session=echo)
        await server.start("127.0.0.1", 0)
        port = server.sockets()[0].getsockname()[1]

        client = BusyPipeClient(config=config)
        session = await client.connect("127.0.0.1", port)
        try:
            start = time.monotonic()
            await session.send(b"warmup-block")
            elapsed = time.monotonic() - start
            self.assertGreaterEqual(elapsed, 0.15)
            self.assertEqual(await session.recv(), b"warmup-block")
        finally:
            await session.close()
            await server.close()

    async def test_warmup_disabled_when_zero(self) -> None:
        async def echo(session):
            with contextlib.suppress(ConnectionError):
                while not session.is_closed:
                    data = await session.recv()
                    await session.send(data)

        config = BusyPipeConfig(tick_ms=50, idle_timeout_ms=2000, warmup_ms=0)
        server = BusyPipeServer(config=config, on_session=echo)
        await server.start("127.0.0.1", 0)
        port = server.sockets()[0].getsockname()[1]

        client = BusyPipeClient(config=config)
        session = await client.connect("127.0.0.1", port)
        try:
            start = time.monotonic()
            await session.send(b"no-warmup")
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 0.12)
            self.assertEqual(await session.recv(), b"no-warmup")
        finally:
            await session.close()
            await server.close()

    def test_warmup_negotiates_max(self) -> None:
        a = BusyPipeConfig(warmup_ms=1000)
        b = BusyPipeConfig(warmup_ms=5000)
        out = a.negotiate(b)
        self.assertEqual(out.warmup_ms, 5000)


if __name__ == "__main__":
    unittest.main()
