# BusyPipe

BusyPipe is a Python implementation of a TCP application protocol that keeps a minimum amount of traffic flowing through a connection.

It is designed for unstable networks where an idle TCP connection may be dropped by middleboxes or network equipment. When there is no application data, BusyPipe sends random padding. When application data exists, BusyPipe wraps it in randomized padding and jitters the real data position inside each mixed frame.

## Features

- TCP-based application protocol.
- Async Python client and server built on `asyncio`.
- Minimum per-direction traffic target, defaulting to `8kbps`.
- Random `PAD` frames when there is no application data.
- `MIXED` frames that place real data between random prefix and suffix bytes.
- At least `8 byte` offset jitter between adjacent mixed data frames when space allows.
- Binary frame codec with header CRC validation.
- Unit and local integration tests using the Python standard library.

## Status

BusyPipe is experimental. The protocol and Python API may change before a stable release.

BusyPipe padding is not encryption. Use TLS when deploying over untrusted networks.

## Requirements

- Python 3.11+

The runtime implementation uses only the Python standard library.

## Install For Development

```powershell
cd c:\apps\busypipe
python -m pip install -e .
```

## Run Tests

```powershell
python -m unittest discover -s tests
```

## Echo Example

Start the server:

```powershell
python examples\server_echo.py
```

Run the client in another terminal:

```powershell
python examples\client_echo.py
```

## Basic Usage

```python
import asyncio

from busypipe import BusyPipeClient


async def main() -> None:
    client = BusyPipeClient()
    session = await client.connect("127.0.0.1", 8765)
    await session.send(b"hello")
    response = await session.recv()
    print(response)
    await session.close()


asyncio.run(main())
```

## Protocol

See [`protocol.md`](protocol.md) for the full BusyPipe protocol design, including frame format, handshake parameters, mixed payload layout, minimum-rate scheduling, and client/server implementation notes.

## Project Layout

```text
busypipe/
  busypipe/          Python package
  examples/          Echo client/server examples
  tests/             Unit and integration tests
  protocol.md        Protocol design document
```

## License

BusyPipe is released under the MIT License. See [`LICENSE`](LICENSE).
