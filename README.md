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

## TCP Daemon Wrap

`busypipe-wrap` can wrap an existing plain TCP daemon without changing that daemon.

Topology:

```text
plain TCP client
  -> local busypipe-wrap client
  -> BusyPipe connection
  -> remote busypipe-wrap server
  -> original plain TCP daemon
```

On the machine that can reach the original TCP daemon, start server mode:

```powershell
busypipe-wrap server --listen-host 0.0.0.0 --listen-port 9001 --target-host 127.0.0.1 --target-port 22
```

On the client side, listen locally and forward to the BusyPipe server:

```powershell
busypipe-wrap client --listen-host 127.0.0.1 --listen-port 9000 --remote-host server.example.com --remote-port 9001
```

Then connect existing TCP clients to `127.0.0.1:9000`.

Both modes support protocol tuning options:

```powershell
busypipe-wrap client --help
busypipe-wrap server --help
```

### Field Deployment Notes

This deployment was tested with:

- Client host: `wizard@192.168.3.11`
- Server host: `admin@18.183.135.254`
- Client listener: `0.0.0.0:4000`
- BusyPipe server listener: `0.0.0.0:4000`
- Server-side TCP target: `127.0.0.1:3306`

The remote hosts had Python `3.7.3` and `3.9.2`. Because `pyproject.toml` currently declares Python `3.11+`, the deployment runs directly from source instead of using `pip install`.

Source layout on both hosts:

```text
~/busypipe-app
```

Server command:

```sh
cd ~/busypipe-app
setsid /usr/bin/python3 -m busypipe.wrap server \
  --listen-host 0.0.0.0 \
  --listen-port 4000 \
  --target-host 127.0.0.1 \
  --target-port 3306 \
  > busypipe-wrap-server.log 2>&1 < /dev/null &
echo $! > busypipe-wrap-server.pid
```

Client command:

```sh
cd ~/busypipe-app
setsid /usr/bin/python3 -m busypipe.wrap client \
  --listen-host 0.0.0.0 \
  --listen-port 4000 \
  --remote-host 18.183.135.254 \
  --remote-port 4000 \
  > busypipe-wrap-client.log 2>&1 < /dev/null &
echo $! > busypipe-wrap-client.pid
```

Useful operations:

```sh
# Check listener and process.
ss -ltnp | awk 'NR==1 || /:4000/'
ps -p "$(cat busypipe-wrap-client.pid)" -o pid=,cmd=
ps -p "$(cat busypipe-wrap-server.pid)" -o pid=,cmd=

# Stop.
kill "$(cat busypipe-wrap-client.pid)"
kill "$(cat busypipe-wrap-server.pid)"

# Logs.
tail -n 100 busypipe-wrap-client.log
tail -n 100 busypipe-wrap-server.log
```

The hosts supported user-level systemd, but `loginctl show-user "$USER" -p Linger` returned `Linger=no`. In that environment, user services may stop when the SSH session ends, so this deployment uses `setsid` with pidfiles. For production, prefer a system-level service or enable user lingering with administrator approval.

Verification used a long-lived local TCP probe on the client:

```sh
python3 - <<'PY'
import socket, time
s = socket.create_connection(("127.0.0.1", 4000), timeout=5)
print("probe_connected")
time.sleep(10)
s.close()
print("probe_closed")
PY
```

While the probe was connected, the server showed an established BusyPipe connection on `:4000` and an established local target connection to `127.0.0.1:3306`.

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
