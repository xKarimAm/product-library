# Security policy

## Supported versions

Security fixes go into `main` only. There are no releases or packages: `git pull` to update, and
check the latest `main` before reporting something that may already be fixed.

## Reporting a vulnerability

Do not disclose vulnerabilities, proof-of-concept exploits, tokens or anyone's project data in a
public issue.

Open this repository's **Security** tab and choose **Report a vulnerability**. That creates a
private advisory only the maintainer can see. Do not open a public issue to ask for a private
contact channel.

Include the commit you tested (`git rev-parse HEAD`), your OS and Python version, what you found,
how to reproduce it and what an attacker could do with it. Remove real project names, home-folder
paths, transcript text and the session token from logs and screenshots.

The maintainer will acknowledge the report, assess it, and agree fix and disclosure timing with you.

## Security boundary

Product Library is a local, read-only tool:

- The server binds to `127.0.0.1` only and rejects any other `Host` header, which blocks DNS
  rebinding from a web page.
- Every `/api/*` call needs a per-session random token, and the page runs under a strict
  Content-Security-Policy with a per-request nonce.
- It never writes into project folders or `~/.claude`. The only write is the opt-in history file
  in its own data folder, and it refuses a folder inside `~/.claude` or any project. Separately,
  `skills/install.py`, which you run yourself, copies one skill folder into `~/.claude/skills`.
- The only action it takes is opening VS Code on a project chosen by id from its own scan; a path
  is never accepted. Git runs as a subprocess with list arguments, never a shell string.
- It makes no network calls and has no third-party dependencies.

This is not a sandbox. It does not protect against malicious processes already running as the same
operating-system user, which can read the same files it reads.

Reports about any of these guarantees failing are especially welcome.
