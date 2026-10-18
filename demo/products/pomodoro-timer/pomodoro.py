"""Pomodoro timer: 25-minute work blocks, 5-minute breaks, a long break after every 4th."""
import sys
import time
from datetime import datetime, timedelta


def schedule(rounds, work=25, short=5, long=15):
    """[(label, minutes)] for `rounds` work blocks, no break after the last one."""
    out = []
    for i in range(1, rounds + 1):
        out.append(("work", work))
        if i < rounds:
            out.append(("long break", long) if i % 4 == 0 else ("break", short))
    return out


def mmss(seconds):
    return "%02d:%02d" % divmod(int(seconds), 60)


def total(plan):
    """Minutes the whole plan takes, breaks included."""
    return sum(minutes for _label, minutes in plan)


if __name__ == "__main__":
    plan = schedule(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
    end = datetime.now() + timedelta(minutes=total(plan))
    print("%d minutes in all, done at %s" % (total(plan), end.strftime("%H:%M")))
    for label, minutes in plan:
        for left in range(minutes * 60, 0, -1):
            print("\r%-10s %s" % (label, mmss(left)), end="", flush=True)
            time.sleep(1)
        print("\r%-10s done " % label)
