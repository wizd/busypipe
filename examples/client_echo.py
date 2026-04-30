from __future__ import annotations

import asyncio

from busypipe import BusyPipeClient


async def main() -> None:
    client = BusyPipeClient()
    session = await client.connect("127.0.0.1", 8765)
    await session.send(b"hello busypipe")
    print(await session.recv())
    await session.close()


if __name__ == "__main__":
    asyncio.run(main())
