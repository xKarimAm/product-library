"""In-memory URL shortener on the standard library. Sketch: no persistence yet.

    py shortener.py                       # serves http://127.0.0.1:8099
    GET /new?url=https://example.com      -> short code
    GET /<code>                           -> 302 to the long URL
"""
import http.server
import secrets
from urllib.parse import parse_qs, urlparse

LINKS = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/new":
            target = (parse_qs(u.query).get("url") or [""])[0]
            if not target.startswith(("http://", "https://")):
                return self.reply(400, "url must start with http:// or https://")
            code = secrets.token_urlsafe(4)
            LINKS[code] = target
            return self.reply(200, code)
        target = LINKS.get(u.path.lstrip("/"))
        if not target:
            return self.reply(404, "unknown code")
        self.send_response(302)
        self.send_header("Location", target)
        self.end_headers()

    def reply(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
