from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import socket
from dataclasses import dataclass

from .client import BusyPipeClient
from .server import BusyPipeServer
from .session import BusyPipeConfig, BusyPipeSession


LOGGER = logging.getLogger(__name__)
BUFFER_SIZE = 64 * 1024


@dataclass(frozen=True)
class TcpEndpoint:
    host: str
    port: int

    def __post_init__(self) -> None:
        host = self.host
        if host.startswith("[") and host.endswith("]"):
            object.__setattr__(self, "host", host[1:-1])


class BusyPipeTcpClientWrap:
    """Listen as a normal TCP server and forward each connection over BusyPipe."""

    def __init__(
        self,
        *,
        listen: TcpEndpoint,
        remote: TcpEndpoint,
        config: BusyPipeConfig | None = None,
    ) -> None:
        self.listen = listen
        self.remote = remote
        self.config = config or BusyPipeConfig()
        self._servers: list[asyncio.AbstractServer] = []

    async def start(self) -> None:
        sock = _create_dualstack_socket(self.listen.host, self.listen.port)
        server = await asyncio.start_server(
            self._handle_local_connection,
            sock=sock,
        )
        self._servers.append(server)

    async def serve_forever(self) -> None:
        if not self._servers:
            raise RuntimeError("client wrap has not been started")
        await asyncio.gather(*(server.serve_forever() for server in self._servers))

    async def close(self) -> None:
        for server in self._servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in self._servers))
        self._servers = []

    def sockets(self):
        sockets = []
        for server in self._servers:
            sockets.extend(server.sockets or ())
        return tuple(sockets)

    async def _handle_local_connection(
        self,
        local_reader: asyncio.StreamReader,
        local_writer: asyncio.StreamWriter,
    ) -> None:
        session: BusyPipeSession | None = None
        try:
            client = BusyPipeClient(config=self.config)
            session = await client.connect(
                self.remote.host,
                self.remote.port,
            )
            await relay_tcp_and_busypipe(local_reader, local_writer, session)
        except Exception:
            LOGGER.exception("local TCP to BusyPipe relay failed")
        finally:
            if session is not None:
                with contextlib.suppress(Exception):
                    await session.close()
            _close_writer(local_writer)


class BusyPipeTcpServerWrap:
    """Accept BusyPipe sessions and forward real data to a normal TCP server."""

    def __init__(
        self,
        *,
        listen: TcpEndpoint,
        target: TcpEndpoint,
        config: BusyPipeConfig | None = None,
    ) -> None:
        self.listen = listen
        self.target = target
        self.config = config or BusyPipeConfig()
        self._servers: list[BusyPipeServer] = []

    async def start(self) -> None:
        sock = _create_dualstack_socket(self.listen.host, self.listen.port)
        server = BusyPipeServer(config=self.config, on_session=self._handle_session)
        await server.start(sock=sock)
        self._servers.append(server)

    async def serve_forever(self) -> None:
        if not self._servers:
            raise RuntimeError("server wrap has not been started")
        await asyncio.gather(*(server.serve_forever() for server in self._servers))

    async def close(self) -> None:
        await asyncio.gather(*(server.close() for server in self._servers), return_exceptions=True)
        self._servers = []

    def sockets(self):
        sockets = []
        for server in self._servers:
            sockets.extend(server.sockets())
        return tuple(sockets)

    async def _handle_session(self, session: BusyPipeSession) -> None:
        target_reader: asyncio.StreamReader | None = None
        target_writer: asyncio.StreamWriter | None = None
        try:
            target_reader, target_writer = await asyncio.open_connection(
                self.target.host,
                self.target.port,
            )
            await relay_tcp_and_busypipe(target_reader, target_writer, session)
        except Exception:
            LOGGER.exception("BusyPipe to target TCP relay failed")
        finally:
            if target_writer is not None:
                _close_writer(target_writer)
            with contextlib.suppress(Exception):
                await session.close()


async def relay_tcp_and_busypipe(
    tcp_reader: asyncio.StreamReader,
    tcp_writer: asyncio.StreamWriter,
    session: BusyPipeSession,
) -> None:
    tcp_to_busy = asyncio.create_task(_tcp_to_busypipe(tcp_reader, session))
    busy_to_tcp = asyncio.create_task(_busypipe_to_tcp(session, tcp_writer))
    tasks = {tcp_to_busy, busy_to_tcp}

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, (ConnectionError, asyncio.IncompleteReadError, asyncio.CancelledError)):
            continue
        if isinstance(result, Exception):
            raise result


async def _tcp_to_busypipe(
    reader: asyncio.StreamReader,
    session: BusyPipeSession,
) -> None:
    while not session.is_closed:
        data = await reader.read(BUFFER_SIZE)
        if not data:
            return
        await session.send(data)


async def _busypipe_to_tcp(
    session: BusyPipeSession,
    writer: asyncio.StreamWriter,
) -> None:
    while not session.is_closed:
        data = await session.recv()
        writer.write(data)
        await writer.drain()


def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()


def build_config(args: argparse.Namespace) -> BusyPipeConfig:
    return BusyPipeConfig(
        min_bps=args.min_bps,
        tick_ms=args.tick_ms,
        max_frame_size=args.max_frame_size,
        idle_timeout_ms=args.idle_timeout_ms,
        min_jitter_bytes=args.min_jitter_bytes,
    )


def _normalize_dualstack_host(host: str) -> str:
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host in ("0.0.0.0", "127.0.0.1", ""):
        return "::"
    with contextlib.suppress(OSError):
        socket.inet_pton(socket.AF_INET, host)
        return "::"
    return host


def _create_dualstack_socket(host: str, port: int) -> socket.socket:
    bind_host = _normalize_dualstack_host(host)
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind((bind_host, port, 0, 0))
        sock.listen(100)
        sock.setblocking(False)
        return sock
    except Exception:
        sock.close()
        raise


def format_endpoint(endpoint: TcpEndpoint) -> str:
    host = endpoint.host
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{endpoint.port}"


async def run_client_wrap(args: argparse.Namespace) -> None:
    wrap = BusyPipeTcpClientWrap(
        listen=TcpEndpoint(args.listen_host, args.listen_port),
        remote=TcpEndpoint(args.remote_host, args.remote_port),
        config=build_config(args),
    )
    await wrap.start()
    LOGGER.info(
        "listening on %s and forwarding to BusyPipe server %s",
        format_endpoint(wrap.listen),
        format_endpoint(wrap.remote),
    )
    await wrap.serve_forever()


async def run_server_wrap(args: argparse.Namespace) -> None:
    wrap = BusyPipeTcpServerWrap(
        listen=TcpEndpoint(args.listen_host, args.listen_port),
        target=TcpEndpoint(args.target_host, args.target_port),
        config=build_config(args),
    )
    await wrap.start()
    LOGGER.info(
        "listening for BusyPipe on %s and forwarding to TCP target %s",
        format_endpoint(wrap.listen),
        format_endpoint(wrap.target),
    )
    await wrap.serve_forever()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="busypipe-wrap",
        description="Wrap an existing TCP daemon with the BusyPipe protocol.",
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    subparsers = parser.add_subparsers(dest="mode", required=True)

    client = subparsers.add_parser("client", help="listen locally and forward to a BusyPipe server")
    _add_common_config(client)
    client.add_argument("--listen-host", default="127.0.0.1")
    client.add_argument("--listen-port", type=int, required=True)
    client.add_argument("--remote-host", required=True)
    client.add_argument("--remote-port", type=int, required=True)
    client.set_defaults(handler=run_client_wrap)

    server = subparsers.add_parser("server", help="accept BusyPipe and forward to a TCP server")
    _add_common_config(server)
    server.add_argument("--listen-host", default="0.0.0.0")
    server.add_argument("--listen-port", type=int, required=True)
    server.add_argument("--target-host", required=True)
    server.add_argument("--target-port", type=int, required=True)
    server.set_defaults(handler=run_server_wrap)

    return parser


def _add_common_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-bps", type=int, default=8000)
    parser.add_argument("--tick-ms", type=int, default=250)
    parser.add_argument("--max-frame-size", type=int, default=1400)
    parser.add_argument("--idle-timeout-ms", type=int, default=15_000)
    parser.add_argument("--min-jitter-bytes", type=int, default=8)


async def amain(argv: list[str] | None = None) -> None:
    parser = create_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
    await args.handler(args)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
