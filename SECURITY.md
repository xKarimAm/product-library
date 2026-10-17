# Security policy

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue:
open this repository's **Security** tab and choose **Report a vulnerability**.
That creates a private advisory only the maintainer can see.

Please include what you found, how to reproduce it, and what an attacker could do with it.
You'll get a reply as soon as the maintainer can look at it.

## Scope

Product Library is a local, read-only tool:

- The server binds to `127.0.0.1` only and rejects any other `Host` header.
- Every `/api/*` call needs a per-session token, and the page runs under a strict
  Content-Security-Policy with a per-request nonce.
- It never writes into project folders or `~/.claude`. The only action it takes is opening
  VS Code on a project chosen by id from its own scan; a path is never accepted.
- It has no third-party dependencies.

Reports about any of these guarantees failing are especially welcome.
