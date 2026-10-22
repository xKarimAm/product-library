"""Build poc_city.html: index.html with project data baked in.

The skyscraper city, roster, traffic and day/night used to be spliced in here;
they now live in index.html itself, so the live app draws the same city. All
this does is make a standalone copy that opens from file:// with no server and
no token. Re-runnable: always rebuilds from the current index.html.

  py tools/build_poc.py
"""
import io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "index.html")
OUT = os.path.join(ROOT, "poc_city.html")
# A real scan (poc_data.json, never committed) wins; a clone without one gets the
# made-up sample projects in sample_data.json.
DATA = sys.argv[1] if len(sys.argv) > 1 else next(
    p for p in (os.path.join(HERE, "poc_data.json"), os.path.join(HERE, "sample_data.json"))
    if os.path.exists(p) or p.endswith("sample_data.json"))

src = io.open(SRC, encoding="utf-8").read()
projects = json.load(io.open(DATA, encoding="utf-8"))
blob = json.dumps(projects, ensure_ascii=False).replace("</", "<\\/")


def splice(old, new, count=1):
    """Replace `old` with `new`, and fail loudly if `old` is not there.

    A bare str.replace on a drifted anchor is a silent no-op: the build still
    "succeeds" and ships a POC with a mechanic missing. Every splice goes
    through here so a moved anchor stops the build instead.
    """
    global src
    n = src.count(old)
    # Exact, not at-least: an anchor that starts matching twice would splice
    # the first copy and leave the other untouched without a word.
    assert n == count, "anchor found %d times, wanted %d: %r" % (n, count, old[:70])
    src = src.replace(old, new, count)


# ---------------------------------------------------------------- 1. standalone
splice('nonce="{{NONCE}}"', 'nonce="poc"', 2)
# Sample data carries `age_h` (hours since last activity) instead of a date, so a
# sample page never goes stale: tier() measures age against Date.now(), and a
# baked date would push every sample project into the dormant comb within a week.
# Real scans carry no age_h, so for them this line does nothing.
splice('const TOKEN = "{{TOKEN}}";',
       'const TOKEN = "poc";\nconst POC_DATA = ' + blob + ';\n'
       'POC_DATA.forEach((p) => { if (typeof p.age_h === "number") '
       'p.last_activity = new Date(Date.now() - p.age_h * 3600e3).toISOString(); });')
# No server, so no token to go stale: a fake 200 keeps load()'s 403-reload path inert.
splice('try { res = await api("/api/projects"); data = await res.json(); }',
       'try { res = { status: 200 }; data = POC_DATA; }')

io.open(OUT, "w", encoding="utf-8").write(src)
print("wrote %s (%d bytes on disk) from %d projects" % (OUT, os.path.getsize(OUT), len(projects)))
