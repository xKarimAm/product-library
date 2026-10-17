"""Tiny CDP driver: stdlib only, enough to click things and grab screenshots.
Test harness - lives in the scratchpad, never in the deliverable."""
import base64, hashlib, json, os, socket, subprocess, sys, time, urllib.request

PORT = 9333
SP = os.path.dirname(os.path.abspath(__file__))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CRLF = "\r\n"


class WS:
    def __init__(self, url):
        _, rest = url.split("://", 1)
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.s = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET /" + path + " HTTP/1.1" + CRLF
               + "Host: " + hostport + CRLF
               + "Upgrade: websocket" + CRLF
               + "Connection: Upgrade" + CRLF
               + "Sec-WebSocket-Key: " + key + CRLF
               + "Sec-WebSocket-Version: 13" + CRLF + CRLF)
        self.s.sendall(req.encode())
        sep = (CRLF + CRLF).encode()
        buf = b""
        while sep not in buf:
            buf += self.s.recv(4096)
        head, self.buf = buf.split(sep, 1)
        assert b"101" in head.split(CRLF.encode())[0], head[:160]
        self.n = 0

    def send(self, method, **params):
        self.n += 1
        payload = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        frame = bytearray([0x81])
        ln = len(payload)
        if ln < 126:
            frame.append(0x80 | ln)
        elif ln < 65536:
            frame.append(0x80 | 126)
            frame += ln.to_bytes(2, "big")
        else:
            frame.append(0x80 | 127)
            frame += ln.to_bytes(8, "big")
        frame += mask
        frame += bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.s.sendall(bytes(frame))
        return self.n

    def _read(self, k):
        while len(self.buf) < k:
            chunk = self.s.recv(1 << 16)
            if not chunk:
                raise EOFError("socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:k], self.buf[k:]
        return out

    def recv(self):
        b0, b1 = self._read(2)
        ln = b1 & 0x7F
        if ln == 126:
            ln = int.from_bytes(self._read(2), "big")
        elif ln == 127:
            ln = int.from_bytes(self._read(8), "big")
        return json.loads(self._read(ln))

    def call(self, method, **params):
        want = self.send(method, **params)
        while True:
            msg = self.recv()
            if msg.get("id") == want:
                return msg


def js(ws, expr):
    r = ws.call("Runtime.evaluate", expression=expr,
                returnByValue=True, awaitPromise=True)
    res = r.get("result", {})
    if res.get("exceptionDetails"):
        return "ERROR: " + str(res["exceptionDetails"].get("text"))
    return res.get("result", {}).get("value")


def shot(ws, name):
    data = ws.call("Page.captureScreenshot", format="png").get("result", {}).get("data")
    if not data:
        print("  !! no screenshot data for " + name)
        return
    with open(os.path.join(SP, name), "wb") as fh:
        fh.write(base64.b64decode(data))
    print("  saved " + name)


def _free_port():
    """Let the OS hand out a port instead of fighting over a fixed one."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def attach(url, size, extra=None):
    """Launch a headless Chrome and attach to it.

    Every launch gets its OWN debugging port and its OWN profile directory.
    Sharing a fixed port 9333 and one `cprof2` profile meant that running two
    harnesses back to back - which is exactly how the suites are used - raced:
    the previous Chrome was still holding the profile lock, the new one failed
    to start, and attach() reported "could not attach to Chrome". That looked
    like a page fault every time and never was one. Retried once, because a
    machine under load can still lose the race.
    """
    last = None
    for attempt in range(2):
        port = _free_port()
        prof = os.path.join(SP, "cprof_%d_%d" % (os.getpid(), port))
        args = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--remote-debugging-port=" + str(port),
                "--user-data-dir=" + prof,
                "--window-size=" + size, "--hide-scrollbars"]
        if extra:
            args += extra
        # Headless Chrome inherits prefers-reduced-motion from the OS. With
        # Windows "Animation effects" off, every "normal" run was secretly a
        # reduced-motion run: spawnVehicle() returned null and pocprobe's traffic
        # checks failed on a correct page. Pin it unless a probe asks for reduce.
        if "--force-prefers-reduced-motion" not in args:
            args.append("--force-prefers-no-reduced-motion")
        args.append(url)
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(70):
            time.sleep(0.5)
            try:
                items = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:" + str(port) + "/json", timeout=3))
            except Exception:
                continue
            pages = [t for t in items
                     if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                ws = WS(pages[0]["webSocketDebuggerUrl"])
                ws.call("Runtime.enable")
                ws.call("Page.enable")
                return proc, ws
        proc.terminate()
        last = "port %d, profile %s" % (port, prof)
        time.sleep(1.5)
    raise SystemExit("could not attach to Chrome (last try: %s)" % last)


def sweep_profiles():
    """Drop profile dirs from earlier runs so they do not accumulate."""
    import shutil
    try:
        for n in os.listdir(SP):
            if n.startswith("cprof_") or n == "cprof2":
                shutil.rmtree(os.path.join(SP, n), ignore_errors=True)
    except OSError:
        pass


Q = chr(39)   # single quote, so JS snippets stay readable below


def run(ws):
    print("title            :", js(ws, "document.title"))
    print("projects         :", js(ws, "PROJECTS.length"))
    print("nodes rendered   :", js(ws, "document.querySelectorAll('.node').length"))
    print("bots in flight   :", js(ws, "document.querySelectorAll('.bot').length"))
    print("waiting header   :", js(ws, "document.getElementById('waitn').textContent"))
    print("tally            :", js(ws, "document.getElementById('tally').textContent"))

    # Does any node overlap the core? That was a real defect once.
    print("label overlaps   :", js(ws,
        "(()=>{const ns=[...document.querySelectorAll('.node')].map(n=>"
        "({k:n.getAttribute('aria-label').split(',')[0],r:n.getBoundingClientRect()}));"
        "let bad=[];for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){"
        "const a=ns[i].r,b=ns[j].r;"
        "if(a.right>b.left&&a.left<b.right&&a.bottom>b.top&&a.top<b.bottom)"
        "bad.push(ns[i].k+' / '+ns[j].k);}"
        "return bad.length?bad.length+' overlapping: '+bad.slice(0,4).join(' | '):'none';})()"))
    print("all nodes onscreen:", js(ws,
        "(()=>{let off=[];document.querySelectorAll('.node').forEach(n=>{"
        "const r=n.getBoundingClientRect();"
        "if(r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)"
        "off.push(n.getAttribute('aria-label').split(',')[0]);});"
        "return off.length?off.join(' / '):'yes, all inside';})()"))
    shot(ws, "v_canvas.png")

    print("")
    print("-- bubble --")
    print("click Project Alpha   :", js(ws,
        "(()=>{const n=[...document.querySelectorAll('.node')]"
        ".find(e=>e.getAttribute('aria-label').split(',')[0]==='Project Alpha');"
        "if(!n)return 'node not found';n.click();return 'clicked';})()"))
    time.sleep(0.8)
    print("present          :", js(ws, "!!document.getElementById('bubble')"))
    print("heading          :", js(ws, "document.querySelector('#bubble h2')?.textContent"))
    print("lead             :", js(ws, "document.querySelector('#bubble .lead')?.textContent"))
    print("says             :", js(ws, "document.querySelector('#bubble .say')?.textContent?.slice(0,64)"))
    print("badges           :", js(ws, "document.querySelector('#bubble .line')?.textContent"))
    print("flag line        :", js(ws, "document.querySelector('#bubble .flags li')?.textContent"))
    print("actions          :", js(ws, "[...document.querySelectorAll('#bubble .acts button')].map(b=>b.textContent).join(' | ')"))
    print("side + fits      :", js(ws,
        "(()=>{const b=document.getElementById('bubble');const r=b.getBoundingClientRect();"
        "return b.className+' fits='+(r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight);})()"))
    print("tail points at it:", js(ws,
        "(()=>{const b=document.getElementById('bubble').getBoundingClientRect();"
        "const n=document.querySelector('.node.open').getBoundingClientRect();"
        "const ty=parseFloat(getComputedStyle(document.getElementById('bubble'))"
        ".getPropertyValue('--ty'));const tailY=b.top+ty+8;"
        "return 'tail '+Math.round(Math.abs(tailY-(n.top+n.height/2)))+'px from node centre';})()"))
    shot(ws, "v_bubble.png")

    print("")
    print("-- edge flip --")
    print("rightmost node   :", js(ws,
        "(()=>{const p=PROJECTS.slice().sort((a,b)=>b._x-a._x)[0];"
        "document.querySelector('.node[data-id=\"'+p.id+'\"]').click();return p.name;})()"))
    time.sleep(0.7)
    print("side + fits      :", js(ws,
        "(()=>{const b=document.getElementById('bubble');const r=b.getBoundingClientRect();"
        "return b.className+' left='+Math.round(r.left)+' right='+Math.round(r.right)"
        "+' fits='+(r.left>=0&&r.right<=innerWidth);})()"))

    print("")
    print("-- keyboard + dismiss --")
    js(ws, "window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
    time.sleep(0.4)
    print("Esc closed       :", js(ws, "!document.getElementById('bubble')"))
    js(ws, "window.dispatchEvent(new KeyboardEvent('keydown',{key:'1'}))")
    time.sleep(0.5)
    print("key 1 opened     :", js(ws, "document.querySelector('#bubble h2')?.textContent"))
    js(ws, "document.getElementById('hive').click()")
    time.sleep(0.4)
    print("outside click    :", js(ws, "!document.getElementById('bubble')"))
    print("focus visible    :", js(ws,
        "(()=>{const n=document.querySelector('.node');n.focus();"
        "const s=getComputedStyle(n,':focus-visible');"
        "return document.activeElement===n?'node focusable':'not focusable';})()"))

    print("")
    print("-- search --")
    js(ws, "(()=>{const s=document.getElementById('search');s.value='zeta';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.4)
    print("'zeta' hits  :", js(ws,
        "[...document.querySelectorAll('.node')].filter(n=>!n.classList.contains('dim'))"
        ".map(n=>n.getAttribute('aria-label').split(',')[0]).join(' / ')"))
    js(ws, "(()=>{const s=document.getElementById('search');s.value='zzznope';"
           "s.dispatchEvent(new Event('input'));})()")
    time.sleep(0.4)
    print("empty state      :", js(ws, "document.getElementById('empty')?.textContent?.slice(0,60)"))
    js(ws, "(()=>{const s=document.getElementById('search');s.value='';"
           "s.dispatchEvent(new Event('input'));})()")

    print("")
    print("-- routes --")
    js(ws, "document.querySelector('.node').dataset.probe='keepme'")
    js(ws, "go('/p/'+encodeURIComponent(PROJECTS.find(p=>p.name==='Project Alpha').id))")
    time.sleep(1.6)
    print("sheet title      :", js(ws, "document.querySelector('#sheet h2')?.textContent"))
    print("sections         :", js(ws, "[...document.querySelectorAll('#sheet h3')].map(h=>h.textContent).join(' | ')"))
    print("stats            :", js(ws, "[...document.querySelectorAll('#sheet .stat')].map(s=>s.textContent).join('  ')"))
    print("url              :", js(ws, "location.pathname"))
    shot(ws, "v_sheet.png")

    js(ws, "history.back()")
    time.sleep(1.4)
    print("back -> url      :", js(ws, "location.pathname"))
    print("sheet gone       :", js(ws, "!document.getElementById('sheet')"))
    print("canvas preserved :", js(ws, "document.querySelector('.node')?.dataset.probe==='keepme'"))

    js(ws, "go('/blocked')")
    time.sleep(1.5)
    print("blocked title    :", js(ws, "document.querySelector('#sheet h2')?.textContent"))
    print("blocked items    :", js(ws, "document.querySelectorAll('#sheet ul.flags li').length"))
    shot(ws, "v_blocked.png")

    js(ws, "go('/plans')")
    time.sleep(1.5)
    print("plans title      :", js(ws, "document.querySelector('#sheet h2')?.textContent"))
    print("plans rows       :", js(ws, "document.querySelectorAll('#sheet .row').length"))
    shot(ws, "v_plans.png")

    js(ws, "go('/')")
    time.sleep(0.6)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7777/"
    size = sys.argv[2] if len(sys.argv) > 2 else "1600,1000"
    proc, ws = attach(url, size)
    try:
        time.sleep(3.5)
        run(ws)
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
