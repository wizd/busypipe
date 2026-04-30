from __future__ import annotations

import asyncio
import contextlib
from typing import Awaitable, Callable

from .session import BusyPipeConfig, BusyPipeSession


SessionHandler = Callable[[BusyPipeSession], Awaitable[None]]


class BusyPipeServer:
    def __init__(
        self,
        *,
        config: BusyPipeConfig | None = None,
        on_session: SessionHandler | None = None,
    ) -> None:
        self.config = config or BusyPipeConfig()
        self.on_session = on_session
        self._server: asyncio.AbstractServer | None = None
        self._sessions: set[BusyPipeSession] = set()

    async def start(self, host: str, port: int) -> None:
        self._server = await asyncio.start_server(self._handle_connection, host, port)

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("server has not been started")
        async with self._server:
            await self._server.serve_forever()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        sessions = list(self._sessions)
        await asyncio.gather(*(session.close() for session in sessions), return_exceptions=True)

    def sockets(self):
        if self._server is None:
            return ()
        return self._server.sockets or ()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        session = BusyPipeSession(reader, writer, config=self.config)
        self._sessions.add(session)
        try:
            await session.start()
            if self.on_session is not None:
                await self.on_session(session)
            else:
                await session.wait_closed()
        finally:
            self._sessions.discard(session)
            with contextlib.suppress(Exception):
                await session.close()
