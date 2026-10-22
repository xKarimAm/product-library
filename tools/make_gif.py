"""Record the README tour GIF from the sample city. Harness only, never shipped.

    py sample/make_sample.py --serve      # in another terminal, then:
    py tools/make_gif.py                  # writes docs/tour.gif
    py tools/make_gif.py --selftest       # LZW round trip, no Chrome needed

Headless Chrome (via drive.py) opens the city at night, a drawn cursor clicks a
STALE project, opens its full view, then the Report page. Screenshots become one
looping GIF, encoded here with the standard library only: a median-cut palette per
frame and, after the first frame, only the rectangle that changed.
"""
import base64, json, os, struct, sys, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "tour.gif")
URL = "http://127.0.0.1:7777/?hour=21"
SIZE = (1280, 900)               # tall enough that the bubble's Full view button is on screen
TARGET = "habit-tracker"          # the sample project that goes STALE (gate fails on "fresh")
CLEAR, EOI, TRANSPARENT = 256, 257, 255
# The full view prints the sample's real folder. These never reach the GIF: each
# is shown as "~" and a frame that still shows one stops the run. leakcheck can't
# see inside a compressed image, so this is the only guard.
HIDE = [os.path.dirname(ROOT), os.path.expanduser("~")]


# ------------------------------------------------------------------ PNG in
def read_png(data):
    """Chrome screenshot PNG -> (w, h, [0xRRGGBB per pixel]). 8-bit RGB/RGBA only."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    i, idat = 8, []
    while i < len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        kind, body = data[i + 4:i + 8], data[i + 8:i + 8 + n]
        i += 12 + n
        if kind == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
            assert body[8] == 8 and body[9] in (2, 6) and body[12] == 0, "unsupported PNG"
            bpp = 3 if body[9] == 2 else 4
        elif kind == b"IDAT":
            idat.append(body)
    raw, stride = zlib.decompress(b"".join(idat)), w * bpp
    prev, rows, pos = bytearray(stride), [], 0
    for _ in range(h):
        f, line = raw[pos], bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if f == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif f in (1, 3, 4):
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                if f == 1:
                    p = a
                elif f == 3:
                    p = (a + b) >> 1
                else:
                    c = prev[x - bpp] if x >= bpp else 0
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    p = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + p) & 255
        rows.append(line)
        prev = line
    px = []
    for line in rows:
        px.extend((line[j] << 16) | (line[j + 1] << 8) | line[j + 2] for j in range(0, stride, bpp))
    return w, h, px


# ------------------------------------------------------------- palette
def key5(c):
    return ((c >> 19) & 31) << 10 | ((c >> 11) & 31) << 5 | ((c >> 3) & 31)


def palette(frames, n=255):
    """Median cut over 5-bit colour buckets sampled from every frame."""
    hist = {}
    for px in frames:
        for c in px[::7]:
            k = key5(c)
            hist[k] = hist.get(k, 0) + 1
    boxes = [[((k >> 10) & 31, (k >> 5) & 31, k & 31, cnt) for k, cnt in hist.items()]]
    while len(boxes) < n:
        best = max((b for b in boxes if len(b) > 1), default=None,
                   key=lambda b: max(max(e[ch] for e in b) - min(e[ch] for e in b) for ch in range(3)))
        if best is None:
            break
        ch = max(range(3), key=lambda ch: max(e[ch] for e in best) - min(e[ch] for e in best))
        best.sort(key=lambda e: e[ch])
        half, acc, total = 0, 0, sum(e[3] for e in best)
        while half < len(best) - 1 and acc + best[half][3] <= total / 2:
            acc += best[half][3]
            half += 1
        half = max(1, half)
        boxes.remove(best)
        boxes += [best[:half], best[half:]]
    pal = []
    for b in boxes:
        t = sum(e[3] for e in b)
        pal.append(tuple(round(sum(e[ch] * e[3] for e in b) / t * 8.225) for ch in range(3)))
    return pal


def mapper(pal):
    """5-bit bucket -> nearest palette index, computed once per bucket."""
    cache = {}

    def index(c):
        k = key5(c)
        i = cache.get(k)
        if i is None:
            r, g, b = ((k >> 10) & 31) * 8 + 4, ((k >> 5) & 31) * 8 + 4, (k & 31) * 8 + 4
            i = cache[k] = min(range(len(pal)), key=lambda j: (pal[j][0] - r) ** 2 * 3
                               + (pal[j][1] - g) ** 2 * 4 + (pal[j][2] - b) ** 2 * 2)
        return i
    return index


# ------------------------------------------------------------------ LZW
def lzw(indices):
    """GIF LZW, minimum code size 8. Code width grows exactly when a giflib-style
    decoder grows it (see selftest), and the table is cleared when full."""
    out, buf, nbits = bytearray(), 0, 0

    def emit(code, size):
        nonlocal buf, nbits
        buf |= code << nbits
        nbits += size
        while nbits >= 8:
            out.append(buf & 255)
            buf >>= 8
            nbits -= 8

    size, table, nxt = 9, {}, EOI + 1
    emit(CLEAR, size)
    prefix = indices[0]
    for k in indices[1:]:
        code = table.get((prefix << 8) | k)
        if code is not None:
            prefix = code
            continue
        emit(prefix, size)
        if nxt < 4096:
            table[(prefix << 8) | k] = nxt
            if nxt == (1 << size) and size < 12:
                size += 1
            nxt += 1
        else:
            emit(CLEAR, size)
            size, table, nxt = 9, {}, EOI + 1
        prefix = k
    emit(prefix, size)
    emit(EOI, size)
    if nbits:
        out.append(buf & 255)
    return bytes(out)


def unlzw(data):
    """Decoder for the selftest, written the way giflib grows the code width."""
    pos, size = 0, 9

    def read():
        nonlocal pos
        v = 0
        for b in range(size):
            v |= ((data[(pos + b) >> 3] >> ((pos + b) & 7)) & 1) << b
        pos += size
        return v
    out, table, prev = [], None, None
    while True:
        code = read()
        if code == CLEAR:
            size, table, prev = 9, {i: [i] for i in range(256)}, None
            continue
        if code == EOI:
            return out
        if prev is None:
            entry = table[code]
        else:
            entry = table[code] if code in table else table[prev] + table[prev][:1]
            if len(table) + 2 < 4096:
                table[len(table) + 2] = table[prev] + entry[:1]
                if len(table) + 2 == (1 << size) and size < 12:
                    size += 1
        out += entry
        prev = code


# ------------------------------------------------------------------ GIF out
def write_gif(path, w, h, frames):
    """frames: [(0xRRGGBB pixels, delay ms)]. Frame 1 whole, later ones as the
    rectangle that changed. Each frame gets its own palette: one shared palette
    spent its colours on the dark city and banded the cream sheets."""
    g = bytearray(b"GIF89a" + struct.pack("<HHBBB", w, h, 0, 0, 0))
    g += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"       # loop forever
    prev = None
    for px, ms in frames:
        keys = [key5(c) for c in px]
        if prev is None:
            x0, y0, x1, y1 = 0, 0, w, h
            same = None
        else:
            changed = [i for i in range(len(keys)) if keys[i] != prev[i]] or [0]
            ys = [i // w for i in changed]
            xs = [i % w for i in changed]
            x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
            same = prev
        cells = [y * w + x for y in range(y0, y1) for x in range(x0, x1)]
        fresh = [px[i] for i in cells if same is None or keys[i] != same[i]]
        pal = palette([fresh or [0]])     # an identical frame has nothing fresh
        index = mapper(pal)
        data = [index(px[i]) if same is None or keys[i] != same[i] else TRANSPARENT for i in cells]
        pal += [(0, 0, 0)] * (256 - len(pal))
        g += b"\x21\xF9\x04" + struct.pack("<BHBB", (1 << 2) | 1, max(2, ms // 10), TRANSPARENT, 0)
        g += b"\x2C" + struct.pack("<HHHHB", x0, y0, x1 - x0, y1 - y0, 0x87)
        g += bytes(v for c in pal for v in c) + b"\x08"
        body = lzw(data)
        for i in range(0, len(body), 255):
            g += bytes([len(body[i:i + 255])]) + body[i:i + 255]
        g += b"\x00"
        prev = keys
    g += b"\x3B"
    with open(path, "wb") as fh:
        fh.write(g)


# ------------------------------------------------------------------ recording
def record():
    from drive import attach, js
    proc, ws = attach(URL, "%d,%d" % SIZE)
    shots = []

    def snap(ms):
        js(ws, "(()=>{const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;"
               "while((n=w.nextNode()))for(const p of %s)if(n.nodeValue.includes(p))"
               "n.nodeValue=n.nodeValue.split(p).join('~');})()" % json.dumps(HIDE))
        assert not js(ws, "%s.some(p=>document.body.innerText.includes(p))" % json.dumps(HIDE)), \
            "a machine path is on screen; not recording it"
        data = ws.call("Page.captureScreenshot", format="png")["result"]["data"]
        shots.append((base64.b64decode(data), ms))

    def centre(sel):
        r = js(ws, "(()=>{const e=document.querySelector(%r);if(!e)return null;"
                   "const r=e.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()" % sel)
        assert r, "not on the page: " + sel
        # A click off-screen lands on nothing and the scene silently never appears.
        assert 0 <= r[0] < innerw and 0 <= r[1] < innerh, "%s is off screen at %s" % (sel, r)
        return r

    def glide(x, y, frames=4):
        js(ws, "(()=>{const s=document.getElementById('gifcursor').style;"
               "s.setProperty('left','%dpx');s.setProperty('top','%dpx')})()" % (x, y))
        for _ in range(frames):
            time.sleep(0.12)
            snap(120)

    def click(x, y):
        for kind in ("mousePressed", "mouseReleased"):
            ws.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)

    def sheet_open(title):
        """Wait for the sheet itself, not a guessed delay: the full view loads its
        record first and took over 1.2s, so a fixed sleep recorded the old bubble."""
        for _ in range(80):
            if js(ws, "document.getElementById('sheet')?.getAttribute('aria-label')===%s" % json.dumps(title)):
                time.sleep(0.8)        # the slide-in
                return
            time.sleep(0.1)
        raise SystemExit("the %r sheet never opened" % title)

    try:
        for _ in range(60):
            time.sleep(0.5)
            if js(ws, "typeof PROJECTS!=='undefined'&&PROJECTS.length>0&&document.querySelectorAll('.node').length>0"):
                break
        else:
            raise SystemExit("no city at %s: is `py sample/make_sample.py --serve` running?" % URL)
        time.sleep(3.2)        # let the arrival animation finish
        innerw, innerh = js(ws, "[innerWidth, innerHeight]")
        js(ws, "document.getElementById('legend')?.removeAttribute('open')")   # show the city, not the key
        # A drawn cursor, for the recording only: screenshots never include the real one.
        js(ws, """(()=>{const c=document.createElement('div');c.id='gifcursor';
          c.innerHTML='<svg width="24" height="30" viewBox="0 0 22 28"><path d="M2 2L2 22L7.5 17L11 26L14.5 24.5L11 15.5L18.5 15.5Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
          const s=c.style;[['position','fixed'],['left','%dpx'],['top','%dpx'],['z-index','99999'],
          ['pointer-events','none'],['transition','left .42s ease, top .42s ease']].forEach(([k,v])=>s.setProperty(k,v));
          document.body.appendChild(c)})()""" % (SIZE[0] * 0.55, SIZE[1] * 0.75))
        for _ in range(6):     # the city, alive
            time.sleep(0.15)
            snap(150)
        snap(1200)

        pid = js(ws, "PROJECTS.find(p=>p.name===%r).id" % TARGET)
        x, y = centre('.node[data-id="%s"]' % pid)
        glide(x, y)
        click(x, y)
        time.sleep(0.6)
        snap(3600)             # the bubble: STALE badge, gate failing on "fresh"

        x, y = centre('button[data-act="full"]')
        glide(x, y)
        click(x, y)
        sheet_open(TARGET)
        snap(4200)             # full view: why it is stale, the gate's gap list

        x, y = centre("#navreport")
        glide(x, y)
        click(x, y)
        sheet_open("Report")
        snap(4600)             # the report: every project by verdict, checked vs written
    finally:
        proc.terminate()
    return shots


def main():
    if "--selftest" in sys.argv:
        for case in ([1, 2, 3, 1, 2, 3, 1, 2, 3, 4] * 50, [7] * 9000,
                     [(i * 37 + i // 13) % 256 for i in range(60000)]):
            assert unlzw(lzw(case)) == case, "LZW round trip failed"
        print("make_gif selftest OK")
        return
    t = time.time()
    shots = record()
    print("captured %d frames in %.0fs; encoding..." % (len(shots), time.time() - t))
    decoded = [read_png(png) for png, _ in shots]
    w, h = decoded[0][0], decoded[0][1]
    write_gif(OUT, w, h, [(px, ms) for (_, _, px), (_, ms) in zip(decoded, shots)])
    print("wrote %s: %dx%d, %d frames, %d KB, %.0fs total"
          % (os.path.relpath(OUT, ROOT), w, h, len(shots), os.path.getsize(OUT) // 1024, time.time() - t))


if __name__ == "__main__":
    main()
