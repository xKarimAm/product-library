"""Four-function calculator with parentheses and unary minus. No eval().

    py calculator.py "2 * (3 + 4)"
    py calculator.py "2 + * 3"        # error, with a caret under the *
"""
import re
import sys

TOKEN = re.compile(r"\d+(?:\.\d+)?|\S")


class ParseError(ValueError):
    """A ValueError that knows which character of the input is to blame."""

    def __init__(self, message, at):
        super().__init__(message)
        self.at = at


def evaluate(expr):
    found = list(TOKEN.finditer(expr))
    toks = [m.group() for m in found]
    pos = 0

    def where():
        return found[pos].start() if pos < len(found) else len(expr)

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        if pos >= len(toks):
            raise ParseError("unexpected end of expression", len(expr))
        pos += 1
        return toks[pos - 1]

    def atom():
        at, t = where(), take()
        if t == "(":
            v = sum_()
            if peek() != ")":
                raise ParseError("missing )", where())
            take()
            return v
        if t == "-":
            return -atom()
        try:
            return float(t)
        except ValueError:
            raise ParseError("unexpected %r" % t, at) from None

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
        raise ParseError("unexpected %r" % peek(), where())
    return v


def caret(expr, exc):
    """The expression with a ^ under the character the error is about."""
    return "%s\n%s^ %s" % (expr, " " * exc.at, exc)


if __name__ == "__main__":
    expr = " ".join(sys.argv[1:]) or input("> ")
    try:
        result = evaluate(expr)
    except ParseError as exc:
        sys.exit(caret(expr, exc))
    except ZeroDivisionError as exc:
        sys.exit("error: %s" % exc)
    print(int(result) if result == int(result) else result)
