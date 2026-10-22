"""Tetris core: the well, the pieces, collisions and the ghost piece.

    py main.py                      # one frame: a T piece and where it would land
    py main.py --selftest
"""
import sys

W, H = 10, 20
LOCK_DELAY = 0.5     # seconds a landed piece can still slide; still feels too short
PIECES = {"I": [(0, 0), (1, 0), (2, 0), (3, 0)], "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
          "T": [(0, 0), (1, 0), (2, 0), (1, 1)], "L": [(0, 0), (0, 1), (0, 2), (1, 2)]}


def cells(piece, x, y):
    return [(x + dx, y + dy) for dx, dy in PIECES[piece]]


def fits(well, piece, x, y):
    return all(0 <= cx < W and cy < H and (cy < 0 or not well[cy][cx]) for cx, cy in cells(piece, x, y))


def ghost_y(well, piece, x, y):
    """Where the piece lands if dropped straight down: the ghost the player sees."""
    while fits(well, piece, x, y + 1):
        y += 1
    return y


def clear_lines(well):
    kept = [row for row in well if not all(row)]
    return [[0] * W for _ in range(H - len(kept))] + kept, H - len(kept)


def frame(well, piece, x, y):
    now = set(cells(piece, x, y))
    shadow = set(cells(piece, x, ghost_y(well, piece, x, y))) - now
    return "\n".join("|" + "".join("#" if well[r][c] else "@" if (c, r) in now else "." if (c, r) in shadow
                                   else " " for c in range(W)) + "|" for r in range(H)) + "\n+" + "-" * W + "+"


if __name__ == "__main__":
    well = [[0] * W for _ in range(H)]
    well[H - 1] = [1] * 6 + [0] * 4
    if "--selftest" in sys.argv:
        assert ghost_y(well, "O", 0, 0) == H - 3            # rests on the filled bottom row
        assert ghost_y(well, "O", 7, 0) == H - 2            # falls into the gap on the right
        full = [row[:] for row in well]
        full[H - 1] = [1] * W
        assert clear_lines(full)[1] == 1 and not any(clear_lines(full)[0][H - 1])
        print("OK")
    else:
        print(frame(well, "T", 3, 2))
