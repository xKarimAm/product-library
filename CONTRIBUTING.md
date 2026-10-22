# Contributing to Product Library

Focused bug fixes, docs fixes, tests and platform reports (daily use on macOS and Linux is newest)
are welcome. For a bigger change, open an issue first and say what problem it solves.

## Ground rules

These are what the project is, so a PR that breaks one will not be merged:

- **Read-only.** Nothing may write, move or delete anything in a project folder or `~/.claude`.
  A feature that needs to write belongs in a skill (see `skills/`), not in `library.py`.
- **Standard library only.** No pip packages, no build step. `library.py` plus `index.html` is the app.
- **Nothing personal.** No real names, machine paths or real project scans in code, tests or
  screenshots. Use the sample city (`sample/make_sample.py`) for examples.
- **Every new parser or check gets a `selftest` case** that fails without the fix.

## Before you open a PR

```bash
python3 library.py --selftest
python3 tools/sync_public.py --selftest
python3 sample/make_sample.py
python3 tools/leakcheck.py
```

On Windows use `py` instead of `python3`. CI runs the same four, plus the skill installer, on Windows, macOS and Linux.

## Reporting issues

Use the issue form that fits. For bugs, give what you saw, the shortest steps you actually ran, and
your commit, OS and Python version. If you don't know something, write `NOT_ENOUGH_INFO` rather than
guessing. Intermittent bugs and reports without a fix are welcome. Security problems go through
[SECURITY.md](SECURITY.md), never a public issue.

## AI-assisted pull requests

AI-assisted contributions are welcome. Every PR needs a human owner (the author, unless someone
else on the PR accepts it) who has read the final diff, can explain it, and takes responsibility for
it, including the parts an AI wrote.

In the PR, say what you checked and what you saw. List only commands you actually ran, with their
result; never report an unrun check as passing. An AI agent must leave the **Author readiness**
boxes in the PR template to the human owner.

A PR may be closed if it is out of scope, has no evidence that it works, or its owner cannot
explain it.
