# Security Policy

BusyPipe is experimental networking software.

## Supported Versions

Only the latest `main` branch is currently supported.

## Reporting A Vulnerability

Please report vulnerabilities privately through GitHub security advisories when available, or by opening a minimal issue that does not include exploit details.

## Security Notes

- BusyPipe random padding is not encryption.
- Use TLS or another authenticated encryption layer on untrusted networks.
- Do not log raw frame payloads in production.
- Treat malformed frames as protocol errors and close the connection.
