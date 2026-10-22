"""Turn a meeting transcript into action items, each with an owner.

    py main.py meeting.vtt
    py main.py --selftest

The summary length for the default view is still open (waiting on me), so
only the action items print for now.
"""
import re
import sys

TURN = re.compile(r"^(?:<v\s+)?([A-Z][\w .-]{0,30}?)(?:>|:)\s*(.+)$")
ASKS = re.compile(r"\b(I'll|I will|we'll|can you|could you|action:|todo:|let's)\b", re.I)
LENGTH = None        # "short" or "long": decided by me, see the blocker


def turns(text):
    """(speaker, words) per line of a .vtt or 'Name: words' transcript; cue lines are skipped."""
    for line in text.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        m = TURN.match(line)
        if m:
            yield m.group(1).strip(), re.sub(r"</v>$", "", m.group(2)).strip()


def actions(text):
    out = []
    for who, words in turns(text):
        if not ASKS.search(words):
            continue
        # "can you ..." hands the item to whoever is addressed, if the next words name them.
        to = re.match(r"(?i)(\w+),?\s+(?:can|could) you\b", words)
        out.append((to.group(1) if to else who, words.rstrip(".")))
    return out


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        vtt = ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\n<v Sam>I'll send the invoice list.</v>\n\n"
               "2\n00:00:05.000 --> 00:00:08.000\n<v Alex>Nice weather today.</v>\n")
        assert actions(vtt) == [("Sam", "I'll send the invoice list")], actions(vtt)
        assert actions("Alex: Priya, can you book the room?") == [("Priya", "Priya, can you book the room?")]
        print("OK")
    else:
        with open(sys.argv[1], encoding="utf-8") as fh:
            for who, what in actions(fh.read()):
                print("- [%s] %s" % (who, what))
