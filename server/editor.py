#!/usr/bin/env python3
"""README-only editor. Caddy connects over a private Unix socket; no dependencies."""

import argparse
import difflib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socketserver
import sqlite3
import stat
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


MAX_DOCUMENT = 1024 * 1024
MAX_REQUEST = MAX_DOCUMENT * 6 + 4096  # JSON may escape each Unicode character.
PAGE_SIZE = 50


class EditorError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def revision(content):
    return hashlib.sha256(content).hexdigest()


def line_diff(before, after):
    """Compact display data only; full source snapshots remain in the history row."""
    old, new = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(None, old, new)
    additions = deletions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deletions += i2 - i1
        if tag in {"replace", "insert"}:
            additions += j2 - j1
    hunks = []
    for group in matcher.get_grouped_opcodes(n=3):
        old_start, old_end = group[0][1], group[-1][2]
        new_start, new_end = group[0][3], group[-1][4]
        lines = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                lines.extend({"kind": "context", "old_line": i + 1,
                              "new_line": j1 + i - i1 + 1, "text": old[i]}
                             for i in range(i1, i2))
            if tag in {"replace", "delete"}:
                lines.extend({"kind": "delete", "old_line": i + 1,
                              "new_line": None, "text": old[i]} for i in range(i1, i2))
            if tag in {"replace", "insert"}:
                lines.extend({"kind": "add", "old_line": None,
                              "new_line": j + 1, "text": new[j]} for j in range(j1, j2))
        hunks.append({"old_start": old_start + 1 if old_end > old_start else old_start,
                      "old_count": old_end - old_start,
                      "new_start": new_start + 1 if new_end > new_start else new_start,
                      "new_count": new_end - new_start, "lines": lines})
    return {"additions": additions, "deletions": deletions, "hunks": hunks,
            "notice": "Only line endings or the final newline changed." if before != after and not hunks else None}


def atomic_write(path, content, mode):
    """Replace the resolved file in its own directory, preserving its permissions."""
    fd, name = tempfile.mkstemp(prefix=".lantern-readme-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), stat.S_IMODE(mode))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Editor:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.state = self.root / ".state"
        self.state.mkdir(mode=0o700, exist_ok=True)
        self.database = self.state / "readme-history.sqlite3"
        with closing(self.connect()) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    editor_ip TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    before_revision TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    before_content TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS edits_path_id ON edits(path, id DESC)")
            db.commit()
        self.database.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def document_path(self, document):
        if not isinstance(document, str) or not document.startswith("/"):
            raise EditorError(400, "A site README path is required.")
        parts = document[1:].split("/")
        if (len(parts) < 2 or parts[-1] != "README.md" or
                any(not p or p.startswith(".") or p in {"node_modules", "__pycache__"}
                    or "\\" in p or "\0" in p for p in parts) or
                parts[0] in {"_shared", "_editor", "_status"}):
            raise EditorError(403, "Only README.md files inside sites can be edited.")
        if (self.root / "apps" / parts[0]).exists():
            raise EditorError(403, "Apps cannot be edited here.")
        try:
            site = (self.root / "sites" / parts[0]).resolve(strict=True)
            path = site.joinpath(*parts[1:]).resolve(strict=True)
            relative = path.relative_to(site)
        except (FileNotFoundError, NotADirectoryError):
            raise EditorError(404, "README.md was not found.") from None
        except (ValueError, RuntimeError):
            raise EditorError(403, "The README must stay inside its site.") from None
        if (not path.is_file() or path.name != "README.md" or
                any(p.startswith(".") or p in {"node_modules", "__pycache__"}
                    for p in relative.parts)):
            raise EditorError(403, "Only README.md files inside sites can be edited.")
        return path

    @staticmethod
    def read(path):
        with path.open("rb") as stream:
            content = stream.read(MAX_DOCUMENT + 1)
        if len(content) > MAX_DOCUMENT:
            raise EditorError(413, "This README exceeds the 1 MiB editing limit.")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise EditorError(422, "The README must use UTF-8 text.") from None
        return content

    def get(self, document, editor_ip):
        content = self.read(self.document_path(document))
        return {"path": document, "content": content.decode("utf-8"),
                "revision": revision(content), "editor_ip": editor_ip}

    def save(self, document, content, expected_revision, editor_ip):
        if not isinstance(content, str) or not isinstance(expected_revision, str):
            raise EditorError(400, "Content and its original revision are required.")
        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError:
            raise EditorError(400, "Content must be valid UTF-8 text.") from None
        if len(encoded) > MAX_DOCUMENT:
            raise EditorError(413, "This README exceeds the 1 MiB editing limit.")
        with closing(self.connect()) as db:
            # Serializes saves, including different browser tabs and service processes.
            db.execute("BEGIN IMMEDIATE")
            path = self.document_path(document)
            before = self.read(path)
            if revision(before) != expected_revision:
                raise EditorError(409, "This README changed since you opened it. Copy your edits, then reopen it to load the latest version.")
            if before == encoded:
                return {"revision": expected_revision, "changed": False}
            now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            current_revision = revision(encoded)
            cursor = db.execute("""
                INSERT INTO edits
                (path, editor_ip, created_at, before_revision, revision, before_content, content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (document, editor_ip, now, expected_revision, current_revision,
                  before.decode("utf-8"), content))
            mode = path.stat().st_mode
            atomic_write(path, encoded, mode)
            try:
                db.commit()
            except sqlite3.Error:
                # A failed history commit must not leave an unrecorded edit on disk.
                atomic_write(path, before, mode)
                raise
            return {"id": cursor.lastrowid, "revision": current_revision,
                    "editor_ip": editor_ip, "created_at": now, "changed": True}

    def history(self, document, before=None):
        self.document_path(document)
        with closing(self.connect()) as db:
            rows = db.execute("""
                SELECT id, editor_ip, created_at, before_revision, revision
                FROM edits WHERE path = ? AND id < ? ORDER BY id DESC LIMIT ?
            """, (document, before or 9223372036854775807, PAGE_SIZE + 1)).fetchall()
        return {"edits": [dict(row) for row in rows[:PAGE_SIZE]],
                "next_before": rows[PAGE_SIZE - 1]["id"] if len(rows) > PAGE_SIZE else None}

    def history_entry(self, document, entry_id):
        self.document_path(document)
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM edits WHERE path = ? AND id = ?",
                             (document, entry_id)).fetchone()
        if row is None:
            raise EditorError(404, "This history entry was not found.")
        return dict(row)

    def history_diff(self, document, entry_id):
        entry = self.history_entry(document, entry_id)
        return {"id": entry["id"], **line_diff(entry["before_content"], entry["content"])}


class EditorServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, editor):
        self.editor = editor
        super().__init__(str(editor.state / "editor.sock"), EditorHandler)
        os.chmod(self.server_address, 0o600)


class EditorHandler(BaseHTTPRequestHandler):
    server_version = "LanternEditor"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt, *args):
        print("editor: " + fmt % args, file=sys.stderr, flush=True)

    def respond(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.dispatch()

    def do_PUT(self):
        self.dispatch()

    def do_POST(self):
        self.respond(405, {"error": "Use GET or PUT."})

    do_DELETE = do_POST
    do_PATCH = do_POST
    do_OPTIONS = do_POST

    def dispatch(self):
        try:
            result = self.route()
            self.respond(200, result)
        except EditorError as exc:
            self.respond(exc.status, {"error": exc.message})
        except PermissionError:
            self.respond(403, {"error": "Lantern does not have permission to edit this README."})
        except (OSError, sqlite3.Error) as exc:
            self.log_error("Could not read or save the README/history: %s", exc)
            self.respond(500, {"error": "Could not read or save the README/history. Check the editor service logs."})

    def route(self):
        url = urlsplit(self.path)
        if self.command == "GET" and url.path == "/_editor/health":
            return {"ok": True}
        try:
            # Caddy OVERWRITES this header; the socket is only accessible to its user.
            address = ipaddress.ip_address(self.headers.get("X-Lantern-Editor-IP", ""))
            editor_ip = str(getattr(address, "ipv4_mapped", None) or address)
        except ValueError:
            raise EditorError(400, "The request must come through Lantern's proxy.") from None
        query = parse_qs(url.query)
        document = query.get("path", [None])[0]
        editor = self.server.editor
        if self.command == "GET":
            if url.path == "/_editor/document":
                return editor.get(document, editor_ip)
            if url.path in {"/_editor/history", "/_editor/revision", "/_editor/diff"}:
                key = "before" if url.path.endswith("history") else "id"
                value = query.get(key, [None])[0]
                try:
                    number = int(value) if value is not None else None
                    if number is not None and not 0 < number < 9223372036854775807:
                        raise ValueError
                    if key == "id" and number is None:
                        raise ValueError
                except ValueError:
                    raise EditorError(400, "Invalid history entry.") from None
                if key == "before":
                    return editor.history(document, number)
                if url.path == "/_editor/diff":
                    return editor.history_diff(document, number)
                return editor.history_entry(document, number)
        elif url.path == "/_editor/document":
            origin = self.headers.get("Origin")
            try:
                origin_url = urlsplit(origin) if origin is not None else None
            except ValueError:
                raise EditorError(403, "Save requests must come from this Lantern site.") from None
            if (self.headers.get("Sec-Fetch-Site") not in {None, "same-origin", "none"} or
                    origin_url is not None and (origin_url.scheme not in {"http", "https"} or
                                                origin_url.netloc != self.headers.get("Host"))):
                raise EditorError(403, "Save requests must come from this Lantern site.")
            if self.headers.get_content_type() != "application/json":
                raise EditorError(415, "Save requests must use application/json.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise EditorError(400, "Invalid request length.") from None
            if not 0 < length <= MAX_REQUEST:
                raise EditorError(413, "The save request is too large or empty.")
            try:
                payload = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                raise EditorError(400, "Invalid JSON content.") from None
            if not isinstance(payload, dict):
                raise EditorError(400, "A JSON object is required.")
            return editor.save(document, payload.get("content"), payload.get("revision"), editor_ip)
        raise EditorError(404, "Unknown editor endpoint.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.environ.get("LANTERN_ROOT", Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    os.umask(0o077)
    editor = Editor(args.root)
    socket_path = editor.state / "editor.sock"
    if socket_path.exists():
        socket_path.unlink()  # systemd runs a single instance; remove a stale socket.
    with EditorServer(editor) as server:
        print(f"README editor listening on {socket_path}", flush=True)
        try:
            server.serve_forever()
        finally:
            socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
