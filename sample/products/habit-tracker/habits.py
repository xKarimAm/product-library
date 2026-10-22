"""Tiny habit tracker with streaks, stored in habits.json next to this file.

    py habits.py done reading
    py habits.py streaks
    py habits.py week                 # the last seven days, one row per habit
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


def week(days, today):
    """The last seven days, oldest first: '#' done, '.' missed."""
    have = set(days)
    return "".join("#" if (today - timedelta(days=k)).isoformat() in have else "."
                   for k in range(6, -1, -1))


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
        if argv[:1] == ["week"]:
            print("%-12s %s" % (name, week(days, date.today())))
        else:
            print("%-12s %3d day streak" % (name, streak(days, date.today())))


if __name__ == "__main__":
    main(sys.argv[1:])
