"""HTTP-layer checks for COC. Raw sockets, because the interesting cases are
malformed requests curl will not send (duplicate Host, negative Content-Length).

Run:  py http_battery.py            (starts its own server on 7778)
"""
import json
import os
import re
import socket
import subprocess
import sys
import time

PORT = int(os.environ.get("BATTERY_PORT", "7778"))
CRLF = "\r\n"
COC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []


def raw(request, timeout=6.0, body=b""):
    """Send a literal request; return (status_line, headers, body) or an error."""
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=timeout)
    except OSError as exc:
        return ("CONNECT-FAIL " + str(exc), "", "")
    try:
        s.sendall(request.encode() + body)
        buf = b""
        s.settimeout(timeout)
        while True:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                return ("TIMEOUT", "", buf.decode("utf-8", "replace"))
            if not chunk:
                break
            buf += chunk
            if b"\r\n\r\n" in buf:
                head, _, rest = buf.partition(b"\r\n\r\n")
                m = re.search(rb"Content-Length: (\d+)", head)
                if m and len(rest) >= int(m.group(1)):
                    buf = head + b"\r\n\r\n" + rest
                    break
        if not buf:
            return ("NO-RESPONSE (connection dropped)", "", "")
        head, _, bod = buf.partition(b"\r\n\r\n")
        lines = head.decode("utf-8", "replace").split(CRLF)
        return (lines[0], CRLF.join(lines[1:]), bod.decode("utf-8", "replace"))
    finally:
        s.close()


def get(path, host=None, token=None, extra=""):
    host = host or ("127.0.0.1:%d" % PORT)
    req = ("GET " + path + " HTTP/1.1" + CRLF + "Host: " + host + CRLF
           + ("X-COC-Token: " + token + CRLF if token else "")
           + extra + "Connection: close" + CRLF + CRLF)
    return raw(req)


def post(path, body, host=None, token=None, clen=None, extra=""):
    host = host or ("127.0.0.1:%d" % PORT)
    raw_body = body.encode() if isinstance(body, str) else body
    n = len(raw_body) if clen is None else clen
    req = ("POST " + path + " HTTP/1.1" + CRLF + "Host: " + host + CRLF
           + "Content-Type: application/json" + CRLF
           + ("X-COC-Token: " + token + CRLF if token else "")
           + "Content-Length: " + str(n) + CRLF
           + extra + "Connection: close" + CRLF + CRLF)
    return raw(req, body=raw_body)


def code(status_line):
    parts = status_line.split()
    return parts[1] if len(parts) > 1 and parts[1].isdigit() else status_line


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print("  %-52s %-28s %s" % (label, got, "ok" if ok else "EXPECTED " + str(want)))


def main():
    env = dict(os.environ, COC_PORT=str(PORT), PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(["py", "coc.py"], cwd=COC, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            time.sleep(0.25)
            if code(get("/")[0]) == "200":
                break
        page = get("/")[2]
        token = re.search(r'const TOKEN = "([A-Za-z0-9_-]+)"', page).group(1)
        nonce = re.search(r'nonce="([A-Za-z0-9_-]+)"', page).group(1)

        print("-- nonce vs token --")
        check("token and CSP nonce are different secrets", token != nonce, True)
        h1 = get("/")[1]
        n1 = re.search(r"nonce-([A-Za-z0-9_-]+)", h1).group(1)
        p2 = get("/")
        n2 = re.search(r"nonce-([A-Za-z0-9_-]+)", p2[1]).group(1)
        check("CSP nonce is fresh per response", n1 != n2, True)
        inpage2 = re.search(r'nonce="([A-Za-z0-9_-]+)"', p2[2]).group(1)
        check("page nonce matches its own CSP header", inpage2 == n2, True)
        t2 = re.search(r'const TOKEN = "([A-Za-z0-9_-]+)"', p2[2]).group(1)
        check("launch token is stable across responses", t2 == token, True)

        print("-- read endpoints need the custom header --")
        check("GET /api/projects without header", code(get("/api/projects")[0]), "403")
        check("GET /api/projects with header", code(get("/api/projects", token=token)[0]), "200")
        check("GET / needs no header (bootstrap)", code(get("/")[0]), "200")
        check("GET /api/blocked without header", code(get("/api/blocked")[0]), "403")
        check("wrong header value", code(get("/api/projects", token="nope")[0]), "403")
        check("non-ASCII header value", code(get("/api/projects", token="caf\u00e9")[0]), "403")

        print("-- host allowlist --")
        check("Host localhost:PORT", code(get("/", host="localhost:%d" % PORT)[0]), "200")
        check("Host UPPERCASE", code(get("/", host="LOCALHOST:%d" % PORT)[0]), "200")
        check("Host evil.com", code(get("/", host="evil.com")[0]), "403")
        check("Host 127.0.0.1 (no port)", code(get("/", host="127.0.0.1")[0]), "403")
        dup = raw("GET /api/projects HTTP/1.1" + CRLF + "Host: evil.com" + CRLF
                  + "Host: 127.0.0.1:%d" % PORT + CRLF + "X-COC-Token: " + token + CRLF
                  + "Connection: close" + CRLF + CRLF)
        check("two Host headers (evil first)", code(dup[0]), "403")
        dup2 = raw("GET /api/projects HTTP/1.1" + CRLF + "Host: 127.0.0.1:%d" % PORT + CRLF
                   + "Host: evil.com" + CRLF + "X-COC-Token: " + token + CRLF
                   + "Connection: close" + CRLF + CRLF)
        check("two Host headers (good first)", code(dup2[0]), "403")

        print("-- malformed bodies must answer, not die --")
        check("Content-Length: -1", code(post("/api/open", "", clen=-1)[0]), "400")
        check("Content-Length oversized", code(post("/api/open", "x" * 20000)[0]), "413")
        check("JSON array body", code(post("/api/open", "[1]")[0]), "400")
        check("JSON string body", code(post("/api/open", '"x"')[0]), "400")
        check("JSON null body", code(post("/api/open", "null")[0]), "400")
        check("non-ASCII token in body",
              code(post("/api/open", json.dumps({"token": "caf\u00e9"}))[0]), "403")
        check("not JSON at all", code(post("/api/open", "{oops")[0]), "400")
        check("server alive after all that", code(get("/", )[0]), "200")

        print("-- launch surface --")
        check("no token", code(post("/api/open", json.dumps({"id": "d--project"}))[0]), "403")
        check("path instead of id",
              code(post("/api/open", json.dumps({"path": "C:/Windows", "token": token}))[0]), "404")
        check("unknown id",
              code(post("/api/open", json.dumps({"id": "../../etc", "token": token}))[0]), "404")

        print("-- file exposure --")
        # Serving the app shell for an unmatched /p/<id> is intended - that is
        # what makes the route bookmarkable. The only real leak signal is
        # server SOURCE appearing in a response body.
        for p in ("/coc.py", "/index.html", "/../coc.py", "/api/../coc.py",
                  "/api/project/../../index.html", "/p/%2e%2e%2fcoc.py",
                  "/../../.claude/settings.json", "/%2e%2e/coc.py"):
            body = get(p, token=token)[2]
            leaked = ("import http.server" in body or "_find_vscode" in body
                      or "enabledPlugins" in body)
            check("no source or settings via " + p, leaked, False)

        print("-- bind scope --")
        lan = socket.gethostbyname(socket.gethostname())
        try:
            socket.create_connection((lan, PORT), timeout=3).close()
            check("LAN %s refused" % lan, "reachable", "refused")
        except OSError:
            check("LAN %s refused" % lan, "refused", "refused")
    finally:
        proc.terminate()

    print("")
    print("%d/%d checks passed" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
