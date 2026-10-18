"""Pull the total and the due date out of an invoice's text.

    py main.py invoice.txt          # text from a PDF, pages split by form feeds
    py main.py --selftest

Only page one is read for now: some invoices put the total on page two.
"""
import re
import sys
from datetime import datetime

TOTAL = re.compile(r"(?im)^\s*(?:amount due|total due|total)\b[^\d\n]*([\d.,]+\d)")
DUE = re.compile(r"(?im)\b(?:due date|payment due|due)\b\D{0,12}(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})")


def amount(text):
    """'1,234.50' and '1.234,50' both mean 1234.50: a comma before two last digits is the decimal one."""
    if re.search(r",\d{2}$", text):
        text = text.replace(".", "").replace(",", ".")
    return float(text.replace(",", ""))


def due(text):
    if "/" in text:
        return datetime.strptime(text, "%d/%m/%Y").date().isoformat()
    return text


def parse(text):
    page = text.split("\f")[0]
    t, d = TOTAL.search(page), DUE.search(page)
    return {"total": amount(t.group(1)) if t else None, "due": due(d.group(1)) if d else None}


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        assert parse("ACME Ltd\nSubtotal 90.00\nTotal: 1,234.50 EUR\nDue date: 2026-11-01\n") == \
            {"total": 1234.5, "due": "2026-11-01"}
        assert parse("Payment due 30/11/2026\nAmount due 1.234,50") == {"total": 1234.5, "due": "2026-11-30"}
        assert parse("page one\f\nTotal 99.00") == {"total": None, "due": None}   # page two: not yet
        print("OK")
    else:
        with open(sys.argv[1], encoding="utf-8") as fh:
            print(parse(fh.read()))
