"""Four-function calculator with parentheses and unary minus. No eval().

    py calculator.py "2 * (3 + 4)"
"""
import re
import sys

TOKEN = re.compile(r"\d+(?:\.\d+)?|\S")


def evaluate(expr):
    toks = TOKEN.findall(expr)
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        if pos >= len(toks):
            raise ValueError("unexpected end of expression")
        pos += 1
        return toks[pos - 1]

    def atom():
        t = take()
        if t == "(":
            v = sum_()
            if take() != ")":
                raise ValueError("missing )")
            return v
        if t == "-":
            return -atom()
        try:
            return float(t)
        except ValueError:
            raise ValueError("unexpected %r" % t) from None

    def product():
        v = atom()
        while peek() in ("*", "/"):
            op, r = take(), atom()
            if op == "/" and r == 0:
                raise ZeroDivisionError("division by zero")
            v = v * r if op == "*" else v / r
        return v

    def sum_():
        v = product()
        while peek() in ("+", "-"):
            op, r = take(), product()
            v = v + r if op == "+" else v - r
        return v

    v = sum_()
    if peek() is not None:
        raise ValueError("unexpected %r" % peek())
    return v


if __name__ == "__main__":
    try:
        print(evaluate(" ".join(sys.argv[1:]) or input("> ")))
    except (ValueError, ZeroDivisionError) as exc:
        sys.exit("error: %s" % exc)
