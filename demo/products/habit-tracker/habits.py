"""Tiny habit tracker with streaks, stored in habits.json next to this file.

    py habits.py done reading
    py habits.py streaks
"""
import json
import os
import sys
from datetime import date, timedelta

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "habits.json")


def streak(days, today):
    """Consecutive days ending today (or yesterday, so an unchecked morning
    does not read as a broken streak)."""
    have = set(days)
    d = today if today.isoformat() in have else today - timedelta(days=1)
    n = 0
    while d.isoformat() in have:
        n += 1
        d -= timedelta(days=1)
    return n


def load():
    try:
        with open(STORE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def main(argv):
    data = load()
    if argv[:1] == ["done"] and len(argv) == 2:
        data.setdefault(argv[1], [])
        if date.today().isoformat() not in data[argv[1]]:
            data[argv[1]].append(date.today().isoformat())
        with open(STORE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    for name, days in sorted(data.items()):
        print("%-12s %3d day streak" % (name, streak(days, date.today())))


if __name__ == "__main__":
    main(sys.argv[1:])
