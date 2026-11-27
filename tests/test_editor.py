"""Behavior checks: uv run --no-project python tests/test_editor.py.

The Caddy checks run only against the throwaway server created by smoke.sh.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import http.client
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError


spec = importlib.util.spec_from_file_location("editor", Path(__file__).resolve().parents[1] / "server/editor.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("lantern.test", timeout=5)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(str(self.socket_path))


class LineDiffTests(unittest.TestCase):
    def test_small_change_in_a_long_document_has_only_nearby_context(self):
        old = [f"Line {index}" for index in range(1, 101)]
        new = old.copy()
        new[49] = "Changed 雪 <script>literal source</script>"
        diff = module.line_diff("\n".join(old), "\n".join(new))
        self.assertEqual((diff["additions"], diff["deletions"]), (1, 1))
        self.assertEqual(len(diff["hunks"]), 1)
        hunk = diff["hunks"][0]
        self.assertEqual((hunk["old_start"], hunk["old_count"], hunk["new_start"], hunk["new_count"]),
                         (47, 7, 47, 7))
        self.assertEqual([line["text"] for line in hunk["lines"] if line["kind"] == "delete"], ["Line 50"])
        self.assertEqual([line["text"] for line in hunk["lines"] if line["kind"] == "add"], [new[49]])
        self.assertEqual(len(hunk["lines"]), 8)
        self.assertNotIn("Line 1", [line["text"] for line in hunk["lines"]])
        for line in hunk["lines"]:
            if line["kind"] == "delete":
                self.assertEqual((line["old_line"], line["new_line"]), (50, None))
            elif line["kind"] == "add":
                self.assertEqual((line["old_line"], line["new_line"]), (None, 50))

    def test_far_apart_edits_are_separate_hunks(self):
        old = [f"Line {index}" for index in range(100)]
        new = old.copy()
        new[10], new[90] = "First change", "Second change"
        diff = module.line_diff("\n".join(old), "\n".join(new))
        self.assertEqual((diff["additions"], diff["deletions"]), (2, 2))
        self.assertEqual(len(diff["hunks"]), 2)
        self.assertNotIn("Line 50", [line["text"] for hunk in diff["hunks"] for line in hunk["lines"]])

    def test_empty_file_insert_delete_and_whitespace(self):
        added = module.line_diff("", "  indented\n\n")
        self.assertEqual((added["additions"], added["deletions"]), (2, 0))
        self.assertEqual(added["hunks"][0]["old_start"], 0)
        self.assertEqual([line["text"] for line in added["hunks"][0]["lines"]], ["  indented", ""])
        removed = module.line_diff("  indented\n\n", "")
        self.assertEqual((removed["additions"], removed["deletions"]), (0, 2))
        self.assertEqual(removed["hunks"][0]["new_start"], 0)

    def test_newline_only_changes_are_explained(self):
        for before, after in [("# README\r\nText\r\n", "# README\nText\n"), ("Text", "Text\n")]:
            with self.subTest(before=before, after=after):
                diff = module.line_diff(before, after)
                self.assertEqual(diff["hunks"], [])
                self.assertEqual((diff["additions"], diff["deletions"]), (0, 0))
                self.assertIn("line endings", diff["notice"])
        self.assertIsNone(module.line_diff("Same\n", "Same\n")["notice"])


class EditorTests(unittest.TestCase):
    def setUp(self):
        quiet = patch.object(module.EditorHandler, "log_message")
        quiet.start()
        self.addCleanup(quiet.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.root / "sites").mkdir()
        (self.root / "apps").mkdir()
        (self.root / "sites/demo").symlink_to(self.repo, target_is_directory=True)
        self.readme = self.repo / "README.md"
        self.original = b"---\r\ntitle: Demo\r\n---\r\n# Demo \xe9\x9b\xaa\r\n"
        self.readme.write_bytes(self.original)
        self.readme.chmod(0o640)
        self.editor = module.Editor(self.root)
        self.server = module.EditorServer(self.editor)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, endpoint="document", *, path="/demo/README.md", method="GET", data=None, headers=None, **query):
        connection = UnixConnection(self.editor.state / "editor.sock")
        request_headers = {"X-Lantern-Editor-IP": "192.168.0.69"}
        if headers:
            request_headers.update(headers)
        body = None
        if data is not None:
            body = json.dumps(data)
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, "/_editor/" + endpoint + "?" + urlencode({"path": path, **query}),
                           body, request_headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        connection.close()
        return result

    def save(self, content, revision=None, **kwargs):
        if revision is None:
            revision = module.revision(self.readme.read_bytes())
        return self.request(method="PUT", data={"content": content, "revision": revision}, **kwargs)

    def test_round_trip_preserves_source_and_stores_ip_and_both_versions(self):
        status, source = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(source["content"].encode(), self.original)
        self.assertEqual(source["editor_ip"], "192.168.0.69")
        content = "# Changed 雪\n<script>alert('history is plain text')</script>\n"
        status, saved = self.save(content)
        self.assertEqual(status, 200)
        self.assertEqual(self.readme.read_text(), content)
        self.assertEqual(self.readme.stat().st_mode & 0o777, 0o640)
        status, history = self.request("history")
        self.assertEqual(status, 200)
        self.assertEqual(len(history["edits"]), 1)
        entry = history["edits"][0]
        self.assertEqual(entry["editor_ip"], "192.168.0.69")
        self.assertTrue(entry["created_at"].endswith("+00:00"))
        status, detail = self.request("revision", id=saved["id"])
        self.assertEqual(status, 200)
        self.assertEqual(detail["before_content"].encode(), self.original)
        self.assertEqual(detail["content"], content)
        status, diff = self.request("diff", id=saved["id"])
        self.assertEqual(status, 200)
        self.assertEqual(diff["id"], saved["id"])
        self.assertGreater(diff["additions"], 0)
        self.assertGreater(diff["deletions"], 0)
        self.assertNotIn("before_content", diff)
        self.assertNotIn("content", diff)
        # Reading the display diff must not replace or trim the stored snapshots.
        with closing(sqlite3.connect(self.editor.database)) as db:
            self.assertEqual(db.execute("SELECT editor_ip, before_content, content FROM edits").fetchone(),
                             ("192.168.0.69", self.original.decode(), content))
        self.assertEqual(self.editor.database.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.editor.state / "editor.sock").stat().st_mode & 0o777, 0o600)

    def test_noop_and_stale_save_do_not_add_history(self):
        status, result = self.save(self.original.decode())
        self.assertEqual(status, 200)
        self.assertFalse(result["changed"])
        initial_revision = module.revision(self.original)
        self.assertEqual(self.save("First", initial_revision)[0], 200)
        self.assertEqual(self.save("Stale", initial_revision)[0], 409)
        self.assertEqual(self.readme.read_text(), "First")
        self.assertEqual(len(self.request("history")[1]["edits"]), 1)

    def test_simultaneous_saves_have_one_winner(self):
        initial_revision = module.revision(self.original)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda content: self.save(content, initial_revision)[0], ["One", "Two"]))
        self.assertEqual(sorted(outcomes), [200, 409])
        self.assertEqual(len(self.request("history")[1]["edits"]), 1)

    def test_other_filenames_hidden_paths_and_traversal_are_rejected(self):
        paths = ["/demo/index.md", "/demo/readme.md", "/demo/foo.txt", "/demo/../README.md",
                 "/demo/.git/README.md", "/demo/node_modules/README.md", "/demo/__pycache__/README.md",
                 "/demo//README.md", "/demo/dir\\README.md", "/_shared/README.md", "demo/README.md"]
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(self.request(path=path)[0], [400, 403])
                self.assertIn(self.save("Forbidden", path=path)[0], [400, 403])
                self.assertIn(self.request("history", path=path)[0], [400, 403])
        self.assertEqual(self.readme.read_bytes(), self.original)

    def test_nested_readme_allowed_but_symlink_escapes_and_other_targets_rejected(self):
        nested = self.repo / "notes"
        nested.mkdir()
        (nested / "README.md").write_text("Nested")
        self.assertEqual(self.save("Updated nested", module.revision(b"Nested"), path="/demo/notes/README.md")[0], 200)
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "README.md").write_text("Private")
        (self.repo / "escape").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.request(path="/demo/escape/README.md")[0], 403)
        (self.repo / "secret.txt").write_text("Secret")
        self.readme.unlink()
        self.readme.symlink_to(self.repo / "secret.txt")
        self.assertEqual(self.save("Forbidden")[0], 403)
        self.assertEqual((self.repo / "secret.txt").read_text(), "Secret")

    def test_apps_cannot_be_edited_even_with_a_matching_site(self):
        (self.root / "apps/demo").mkdir()
        self.assertEqual(self.request()[0], 403)
        self.assertEqual(self.save("Forbidden")[0], 403)

    def test_cross_origin_saves_and_form_posts_are_rejected(self):
        for headers in [{"Origin": "http://evil.test"}, {"Origin": "null"}, {"Origin": "http://["},
                        {"Sec-Fetch-Site": "cross-site"}, {"Content-Type": "text/plain"}]:
            with self.subTest(headers=headers):
                self.assertIn(self.save("Forbidden", headers=headers)[0], [403, 415])
        self.assertEqual(self.request(method="POST", data={"content": "Forbidden"})[0], 405)
        self.assertEqual(self.readme.read_bytes(), self.original)
        self.assertEqual(self.save("Allowed", headers={"Origin": "http://lantern.test"})[0], 200)

    def test_malformed_content_and_oversized_documents_are_rejected(self):
        for data in [[], {}, {"content": 42, "revision": "abc"}, {"content": "x", "revision": None},
                     {"content": "\ud800", "revision": "abc"}]:
            with self.subTest(data=data):
                self.assertEqual(self.request(method="PUT", data=data)[0], 400)
        self.assertEqual(self.save("x" * (module.MAX_DOCUMENT + 1))[0], 413)
        self.readme.write_bytes(b"\xff")
        self.assertEqual(self.request()[0], 422)
        self.readme.write_bytes(b"x" * (module.MAX_DOCUMENT + 1))
        self.assertEqual(self.request()[0], 413)

    def test_failed_file_write_or_history_insert_does_not_change_document(self):
        with patch.object(module.os, "replace", side_effect=PermissionError("test read-only")):
            self.assertEqual(self.save("Failed write")[0], 403)
        self.assertEqual(self.readme.read_bytes(), self.original)
        self.assertEqual(self.request("history")[1]["edits"], [])
        self.assertEqual(list(self.repo.glob(".lantern-readme-*")), [])
        with closing(sqlite3.connect(self.editor.database)) as db:
            db.execute("CREATE TRIGGER reject_edits BEFORE INSERT ON edits BEGIN SELECT RAISE(ABORT, 'test disk full'); END")
            db.commit()
        self.assertEqual(self.save("Failed insert")[0], 500)
        self.assertEqual(self.readme.read_bytes(), self.original)

    def test_external_change_is_detected_and_missing_readme_is_not_created(self):
        initial_revision = module.revision(self.original)
        self.readme.write_text("Changed in a local editor")
        self.assertEqual(self.save("Stale", initial_revision)[0], 409)
        self.assertEqual(self.readme.read_text(), "Changed in a local editor")
        self.readme.unlink()
        self.assertEqual(self.save("Not created", initial_revision)[0], 404)
        self.assertFalse(self.readme.exists())

    def test_history_pagination_and_revision_scoping(self):
        for index in range(53):
            self.assertEqual(self.save(str(index))[0], 200)
        _, page = self.request("history")
        self.assertEqual(len(page["edits"]), 50)
        self.assertEqual(page["edits"][0]["id"], 53)
        _, older = self.request("history", before=page["next_before"])
        self.assertEqual([entry["id"] for entry in older["edits"]], [3, 2, 1])
        self.assertIsNone(older["next_before"])
        for value in ["bad", "0", "-1", str(2 ** 80)]:
            self.assertEqual(self.request("history", before=value)[0], 400)
        nested = self.repo / "notes"
        nested.mkdir()
        (nested / "README.md").write_text("Nested")
        self.assertEqual(self.request("revision", path="/demo/notes/README.md", id=1)[0], 404)
        self.assertEqual(self.request("diff", path="/demo/notes/README.md", id=1)[0], 404)
        self.assertEqual(self.request("diff", id="bad")[0], 400)
        self.assertEqual(self.request("diff")[0], 400)

    def test_ip_header_required_and_ipv4_mapped_addresses_normalized(self):
        self.assertEqual(self.request(headers={"X-Lantern-Editor-IP": "forged"})[0], 400)
        _, result = self.request(headers={"X-Lantern-Editor-IP": "::ffff:192.168.0.69"})
        self.assertEqual(result["editor_ip"], "192.168.0.69")


@unittest.skipUnless(os.environ.get("LANTERN_TEST_URL"), "Only run against smoke.sh's throwaway server")
class CaddyEditorTests(unittest.TestCase):
    def request(self, endpoint, *, data=None, path="/_smoke/README.md"):
        url = os.environ["LANTERN_TEST_URL"] + "/_editor/" + endpoint + "?" + urlencode({"path": path})
        headers = {"X-Lantern-Editor-IP": "192.168.0.69", "X-Forwarded-For": "192.168.0.69"}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        request = Request(url, body, headers, method="PUT" if data else "GET")
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_caddy_save_history_and_real_peer_ip(self):
        status, doc = self.request("document")
        self.assertEqual(status, 200)
        self.assertEqual(doc["editor_ip"], "127.0.0.1")
        changed = doc["content"] + "\nSaved through Caddy.\n"
        status, saved = self.request("document", data={"content": changed, "revision": doc["revision"]})
        self.assertEqual(status, 200)
        self.assertEqual(saved["editor_ip"], "127.0.0.1")
        try:
            with urlopen(os.environ["LANTERN_TEST_URL"] + "/_smoke/", timeout=10) as page:
                self.assertIn(b"Saved through Caddy.", page.read())
            _, history = self.request("history")
            self.assertEqual(history["edits"][0]["editor_ip"], "127.0.0.1")
            diff_url = os.environ["LANTERN_TEST_URL"] + "/_editor/diff?" + urlencode({"path": "/_smoke/README.md", "id": saved["id"]})
            with urlopen(diff_url, timeout=10) as response:
                diff = json.load(response)
            self.assertEqual(diff["deletions"], 0)
            self.assertEqual(diff["additions"], 2)
            self.assertNotIn("before_content", diff)
            self.assertEqual(self.request("document", data={"content": "Stale", "revision": doc["revision"]})[0], 409)
        finally:
            self.assertEqual(self.request("document", data={"content": doc["content"], "revision": saved["revision"]})[0], 200)

    def test_caddy_rejects_apps_and_other_files(self):
        self.assertEqual(self.request("document", path="/_example-app/README.md")[0], 403)
        self.assertEqual(self.request("document", path="/_example/features.md")[0], 403)


if __name__ == "__main__":
    unittest.main()
