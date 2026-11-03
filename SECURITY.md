# Security and private data

Do not attach config.json, credential files, SQLite state, logs with task contents,
or infrastructure/chat exports to reports. Keep API tokens outside source control.
The Google Tasks permission is account-wide; this bridge's list allowlist is an
application restriction, not an OAuth per-list security boundary.

Run the worker under its dedicated non-login account, keep its code read-only to
that account, use private credential directories, and preserve the systemd limits.
Use trusted HTTPS when a service crosses a network boundary. This source review
and automated tests are not a penetration test or a security guarantee.

The repository is private and has no published reporting address. Report issues
privately to the repository owner through an agreed private channel. Do not create
a public issue containing sensitive information.
