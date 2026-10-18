"""Kanban board: cards move between columns, the board prints side by side.

    py main.py                      # the sample board
    py main.py --selftest
"""
import sys

BOARD = {"columns": ["To do", "Doing", "Done"],
         "cards": {"To do": ["Save column order", "Card colours"],
                   "Doing": ["Drag between columns"],
                   "Done": ["Three columns", "Add a card"]}}


def move(board, card, to, index=None):
    """Move a card to column `to` (at `index`, default the bottom)."""
    if to not in board["columns"]:
        raise KeyError("no column %r" % to)
    for cards in board["cards"].values():
        if card in cards:
            cards.remove(card)
            break
    else:
        raise KeyError("no card %r" % card)
    target = board["cards"].setdefault(to, [])
    target.insert(len(target) if index is None else index, card)


def render(board, width=22):
    cols = board["columns"]
    rows = max(len(board["cards"].get(c, [])) for c in cols)
    out = [" | ".join(c.upper().ljust(width) for c in cols), "-+-".join("-" * width for _ in cols)]
    for i in range(rows):
        cells = [(board["cards"].get(c, [])[i:i + 1] or [""])[0] for c in cols]
        out.append(" | ".join(x[:width].ljust(width) for x in cells))
    return "\n".join(out)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        b = {"columns": ["A", "B"], "cards": {"A": ["x", "y"], "B": []}}
        move(b, "y", "B")
        move(b, "x", "B", 0)
        assert b["cards"] == {"A": [], "B": ["x", "y"]}, b
        assert render(b, 3).splitlines()[2] == "    | x  "   # A is empty now
        print("OK")
    else:
        print(render(BOARD))
