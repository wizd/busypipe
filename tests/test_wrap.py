from __future__ import annotations

import asyncio
import contextlib
import unittest

from busypipe.session import BusyPipeConfig
from busypipe.wrap import BusyPipeTcpClientWrap, BusyPipeTcpServerWrap, TcpEndpoint, create_parser


class WrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_wraps_plain_tcp_echo_service(self) -> None:
        async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                while data := await reader.read(1024):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

        echo_server = await asyncio.start_server(echo, "127.0.0.1", 0)
        echo_port = echo_server.sockets[0].getsockname()[1]

        config = BusyPipeConfig(tick_ms=50, idle_timeout_ms=3000)
        server_wrap = BusyPipeTcpServerWrap(
            listen=TcpEndpoint("127.0.0.1", 0),
            target=TcpEndpoint("127.0.0.1", echo_port),
            config=config,
        )
        await server_wrap.start()
        busypipe_port = server_wrap.sockets()[0].getsockname()[1]

        client_wrap = BusyPipeTcpClientWrap(
            listen=TcpEndpoint("127.0.0.1", 0),
            remote=TcpEndpoint("127.0.0.1", busypipe_port),
            config=config,
        )
        await client_wrap.start()
        local_port = client_wrap.sockets()[0].getsockname()[1]

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", local_port)
            writer.write(b"wrapped tcp payload")
            await writer.drain()

            response = await reader.readexactly(len(b"wrapped tcp payload"))
            self.assertEqual(response, b"wrapped tcp payload")

            writer.close()
            await writer.wait_closed()
        finally:
            await client_wrap.close()
            await server_wrap.close()
            echo_server.close()
            await echo_server.wait_closed()

    def test_cli_parser_accepts_client_and_server_modes(self) -> None:
        parser = create_parser()

        client_args = parser.parse_args(
            [
                "client",
                "--listen-port",
                "9000",
                "--remote-host",
                "example.com",
                "--remote-port",
                "9001",
            ]
        )
        self.assertEqual(client_args.mode, "client")
        self.assertEqual(client_args.listen_port, 9000)

        server_args = parser.parse_args(
            [
                "server",
                "--listen-port",
                "9001",
                "--target-host",
                "127.0.0.1",
                "--target-port",
                "22",
            ]
        )
        self.assertEqual(server_args.mode, "server")
        self.assertEqual(server_args.target_port, 22)


if __name__ == "__main__":
    unittest.main()
