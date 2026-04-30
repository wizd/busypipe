from __future__ import annotations

import asyncio

from busypipe import BusyPipeServer


async def echo(session):
    while not session.is_closed:
        data = await session.recv()
        await session.send(data)


async def main() -> None:
    server = BusyPipeServer(on_session=echo)
    await server.start("127.0.0.1", 8765)
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
