# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Minimal lantern app: proves the proxy round trip and path-prefix handling.

Caddy strips /<name> before proxying, so this server sees "/" and "/api/time".
All links below are relative, which is what keeps them working under the prefix.
"""

import html
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Example app</title>
<link rel="stylesheet" href="/_shared/style.css">
</head>
<body>
<header class="lantern-bar"><nav class="crumbs"><a class="home" href="/">lantern</a><span class="sep">/</span><span class="here">{name}</span></nav></header>
<main class="doc">
<h1>Example app</h1>
<p>Served by <code>app.py</code> on port {port}. This page was requested as
<code>{path}</code> (prefix stripped by Caddy; original prefix in
<code>X-Forwarded-Prefix: {prefix}</code>).</p>
<p><button id="t" type="button">Fetch ./api/time</button> <output id="o"></output></p>
<script>
document.getElementById("t").onclick = async () => {{
  const r = await fetch("api/time");  // relative: resolves to /{name}/api/time
  document.getElementById("o").textContent = (await r.json()).now;
}};
</script>
</main>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/api/time":
            body = json.dumps({"now": datetime.now(timezone.utc).isoformat()}).encode()
            self.reply(200, "application/json", body)
        elif self.path.split("?")[0] == "/":
            page = PAGE.format(
                name=html.escape(os.environ.get("APP_NAME", "app")),
                port=os.environ["PORT"],
                path=html.escape(self.path),
                prefix=html.escape(self.headers.get("X-Forwarded-Prefix", "(none)")),
            )
            self.reply(200, "text/html; charset=utf-8", page.encode())
        else:
            self.reply(404, "text/plain", b"not found\n")

    def do_HEAD(self):
        self.reply(200, "text/plain", b"")

    def reply(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    print(f"listening on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
