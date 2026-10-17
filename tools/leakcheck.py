"""Refuse to let personal details into a public repo. Run before every push:

    py tools/leakcheck.py

Scans every tracked file for a user home folder, a personal email address and a
private network address. Words only you know to look for (your name, a real
project, a machine name) go in the LEAK_WORDS environment variable, comma
separated, so the list itself is never committed:

    $env:LEAK_WORDS="yourname,realproject"; py tools/leakcheck.py

Exits 1 and prints file:line for every hit.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = {
    "home folder": r"(?i)\b[a-z]:[/\\]{1,2}users[/\\]{1,2}(?!public\b)\w+|/home/\w+|/Users/\w+",
    "personal email": r"(?i)[\w.+-]+@(gmail|googlemail|outlook|hotmail|live|yahoo|icloud|proton(mail)?)\.\w+",
    "private address": r"\b(192\.168|10\.\d{1,3}|172\.(1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
}
words = [w.strip() for w in os.environ.get("LEAK_WORDS", "").split(",") if w.strip()]
if words:
    RULES["LEAK_WORDS"] = r"(?i)\b(" + "|".join(map(re.escape, words)) + r")\b"
SELF = os.path.relpath(os.path.abspath(__file__), ROOT).replace(os.sep, "/")


def hits():
    files = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True,
                           check=True).stdout.splitlines()
    for rel in files:
        if rel == SELF:                      # the rules themselves look like hits
            continue
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8", errors="strict") as fh:
                lines = fh.read().splitlines()
        except (UnicodeDecodeError, OSError):
            continue                         # binary: nothing readable to leak as text
        for n, line in enumerate(lines, 1):
            for name, pat in RULES.items():
                m = re.search(pat, line)
                if m:
                    yield "%s:%d  %s  %r" % (rel, n, name, m.group(0))


if __name__ == "__main__":
    found = list(hits())
    print("\n".join(found) if found else "leakcheck OK: nothing personal in tracked files")
    sys.exit(1 if found else 0)
