from __future__ import annotations

import asyncio

from .session import BusyPipeConfig, BusyPipeSession


class BusyPipeClient:
    def __init__(self, *, config: BusyPipeConfig | None = None) -> None:
        self.config = config or BusyPipeConfig()

    async def connect(
        self,
        host: str,
        port: int,
    ) -> BusyPipeSession:
        reader, writer = await asyncio.open_connection(host, port)
        session = BusyPipeSession(reader, writer, config=self.config)
        await session.start()
        return session

    async def connect_with_retry(
        self,
        host: str,
        port: int,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> BusyPipeSession:
        delay = initial_delay
        while True:
            try:
                return await self.connect(host, port)
            except OSError:
                await asyncio.sleep(delay)
                delay = min(max_delay, delay * 2)
