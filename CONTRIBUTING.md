# Contributing

Thanks for your interest in BusyPipe.

## Development

Use Python 3.11 or newer.

```powershell
python -m pip install -e .
python -m unittest discover -s tests
```

## Pull Requests

- Keep changes focused and small.
- Add or update tests for behavior changes.
- Update `protocol.md` when wire-format behavior changes.
- Do not log or commit real payload data, credentials, or local environment files.

## Protocol Changes

BusyPipe has a binary wire format. Any incompatible protocol change must update the protocol version and include migration notes in `protocol.md`.
