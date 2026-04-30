from __future__ import annotations

import contextlib
import unittest

from busypipe import BusyPipeClient, BusyPipeConfig, BusyPipeServer


class ClientServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_server_echo(self) -> None:
        async def echo(session):
            with contextlib.suppress(ConnectionError):
                while not session.is_closed:
                    data = await session.recv()
                    await session.send(data)

        config = BusyPipeConfig(tick_ms=50, idle_timeout_ms=2000)
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


if __name__ == "__main__":
    unittest.main()
