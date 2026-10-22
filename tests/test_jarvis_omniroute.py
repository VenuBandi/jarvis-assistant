"""Unit tests for the OmniRoute brain (src/jarvis/brains.py). Fake local HTTP server on 127.0.0.1 (random port)."""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "jarvis"))
import brains as br  # noqa: E402
import jarvis_core as jc  # noqa: E402

KEY = "omr-test-KEY-9f8e7d6c5b4a"
CHUNKS = [{"path": "docs/plan.md", "section": "Plan > Data", "text": "The final dataset has 7,121,934 flights."}]
GOOD = json.dumps({"quotes": [{"chunk": 1, "quote": "The final dataset has 7,121,934 flights"}],
                   "answer": "The final dataset has 7,121,934 flights [1]."})


class Handler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Handler.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        model = body.get("model")
        if self.headers.get("Authorization") != f"Bearer {KEY}" or model == "m-401":
            return self._send(401, b'{"error": "unauthorized ' + KEY.encode() + b'"}')
        if model == "m-slow":
            time.sleep(2)
            return self._send(200, b"{}")
        if model == "m-badjson":
            return self._send(200, b"<html>not json</html>")
        if model == "m-redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.com/steal")
            self.end_headers()
            return
        if model == "m-echo-key":
            content = f"key is {KEY} " + GOOD
        else:
            content = GOOD
        self._send(200, json.dumps({"model": f"gw/{model}", "choices": [{"message": {"content": content}}]}).encode())

    def _send(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class OmniRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Path(self.tmp.name) / "omniroute_key"
        self.key.write_text(KEY + "\n")
        os.chmod(self.key, 0o600)
        Handler.seen.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def brain(self, model="m-good", enabled=True, url=None, timeout=5):
        return br.OmniRouteBrain({"enabled": enabled, "base_url": url or self.url, "model": model, "timeout": timeout},
                                 key_file=str(self.key))

    def assertNoKey(self, *objs):
        for o in objs:
            self.assertNotIn(KEY, o if isinstance(o, str) else json.dumps(o, default=str))

    def test_success_with_guards(self):
        b = self.brain()
        r = br.run_brain(b, "How many flights?", CHUNKS)
        self.assertFalse(r["refused"])
        self.assertEqual(r["citations"][0]["path"], "docs/plan.md")
        self.assertEqual(r["model"], "omniroute:gw/m-good")
        req = Handler.seen[0]
        self.assertEqual(req["path"], "/v1/chat/completions")
        self.assertEqual(req["auth"], f"Bearer {KEY}")
        self.assertIn("CHUNKS:", req["body"]["messages"][0]["content"])
        self.assertNoKey(r)
        self.assertIsNone(b._key)          # not kept after the call

    def test_key_echoed_by_server_is_scrubbed(self):
        r = br.run_brain(self.brain("m-echo-key"), "q", CHUNKS)
        self.assertNoKey(r)

    def test_401(self):
        with self.assertRaisesRegex(br.BrainError, "HTTP 401") as cm:
            self.brain("m-401").complete("p")
        self.assertNoKey(str(cm.exception))

    def test_timeout(self):
        with self.assertRaisesRegex(br.BrainError, "timeout"):
            self.brain("m-slow", timeout=0.5).complete("p")

    def test_bad_json_and_unparseable(self):
        with self.assertRaisesRegex(br.BrainError, "unexpected"):
            self.brain("m-badjson").complete("p")

    def test_redirect_refused(self):
        with self.assertRaisesRegex(br.BrainError, "302"):
            self.brain("m-redirect").complete("p")

    def test_unreachable(self):
        with self.assertRaisesRegex(br.BrainError, "unreachable|timeout"):
            self.brain(url="http://127.0.0.1:1").complete("p")

    def test_key_file_checks(self):
        os.chmod(self.key, 0o644)
        self.assertTrue(any("permissions are 644" in p for p in self.brain().problems()))
        with self.assertRaisesRegex(br.BrainError, "must be 600"):
            self.brain().complete("p")
        os.chmod(self.key, 0o600)
        self.key.write_text("  \n")
        os.chmod(self.key, 0o600)
        self.assertTrue(any("empty" in p for p in self.brain().problems()))
        self.key.unlink()
        self.assertTrue(any("missing" in p for p in self.brain().problems()))
        self.assertEqual(Handler.seen, [])     # nothing was called

    def test_not_enabled_no_model_non_local(self):
        self.assertTrue(any("not enabled" in p for p in self.brain(enabled=False).problems()))
        self.assertTrue(any("model not configured" in p for p in self.brain(model=None).problems()))
        for url in ("https://api.example.com", "http://10.0.0.5:20128", "http://user:pw@127.0.0.1:1", "file:///etc"):
            self.assertTrue(any("base_url" in p for p in self.brain(url=url).problems()), url)
        with self.assertRaises(br.BrainError):
            self.brain(url="http://example.com").complete("p")
        self.assertEqual(Handler.seen, [])

    def test_ready_has_no_problems(self):
        self.assertEqual(self.brain().problems(), [])

    def test_probe_not_configured_calls_nothing(self):
        cfg = br.load_config(Path("/nonexistent"))
        out = io.StringIO()
        with mock.patch.object(br, "load_config", return_value=cfg), redirect_stdout(out):
            rc = br._probe("omniroute")
        self.assertEqual(rc, 2)
        text = out.getvalue()
        self.assertIn("NOT READY", text)
        self.assertIn("not enabled", text)
        self.assertIn("model not configured", text)
        self.assertEqual(Handler.seen, [])

    def test_auto_fallback_and_disabled(self):
        cfg = br.load_config(Path("/nonexistent"))
        self.assertEqual(cfg["order"], ["codex", "opencode", "omniroute", "local"])
        brains = {"codex": _Fail("codex"), "opencode": _Fail("opencode"), "omniroute": self.brain(),
                  "local": _Fail("local")}
        r = br.run_auto("q", CHUNKS, brains, cfg["order"])
        self.assertEqual(r["brain"], "omniroute")
        self.assertNoKey(r)
        brains["omniroute"] = self.brain(enabled=False)
        r = br.run_auto("q", CHUNKS, brains, cfg["order"])
        self.assertIn({"brain": "omniroute", "reason": "disabled"}, r["fallbacks"])
        self.assertNotIn("omniroute", r["brains_tried"])

    def test_agentic_not_offered(self):
        self.assertNotIn("omniroute", br.AGENTIC_BRAINS)


class _Fail(br.Brain):
    mode = "combined"

    def __init__(self, bid):
        super().__init__({"enabled": True})
        self.id = bid

    def complete(self, prompt):
        raise br.BrainError("down")


if __name__ == "__main__":
    unittest.main()
