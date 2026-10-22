"""Ollama streaming (OllamaProvider.chat_stream): text pieces arrive in order, tool calls are still recognised, errors
are redacted. A fake Ollama on 127.0.0.1 with a random port; no real model, no port 8770."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jarvis_app.models.adapters import OllamaProvider  # noqa: E402
from jarvis_app.models.base import ProviderError  # noqa: E402

REPLIES = {}


class FakeOllama(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.last = body
        status, lines = REPLIES[body["messages"][-1]["content"]]
        self.send_response(status)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for line in lines:
            self.wfile.write((json.dumps(line) if isinstance(line, dict) else line).encode() + b"\n")

    def log_message(self, *a):
        pass


def piece(text, done=False, **extra):
    return {"model": "qwen-test", "message": {"role": "assistant", "content": text, **extra}, "done": done,
            **({"done_reason": "stop"} if done else {})}


class Streaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.p = OllamaProvider(f"http://127.0.0.1:{cls.srv.server_address[1]}")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def run_stream(self, prompt, tools=None):
        got = []
        r = self.p.chat_stream("qwen-test", "sys", [{"role": "user", "content": prompt}], tools, got.append)
        return r, got

    def test_text_pieces_in_order(self):
        REPLIES["a"] = (200, [piece("The project "), piece("is on step 6. "), piece("One decision waits."), piece("", True)])
        r, got = self.run_stream("a")
        self.assertEqual(got, ["The project ", "is on step 6. ", "One decision waits."])
        self.assertEqual(r.text, "The project is on step 6. One decision waits.")
        self.assertEqual(r.model, "qwen-test")
        self.assertEqual(r.stop, "stop")
        self.assertTrue(FakeOllama.last["stream"])
        self.assertFalse(FakeOllama.last["think"])

    def test_tool_call_in_stream(self):
        call = {"function": {"name": "flightops_status", "arguments": {}}}
        REPLIES["b"] = (200, [piece("", tool_calls=[call]), piece("", True)])
        r, got = self.run_stream("b", tools=[{"name": "flightops_status", "parameters": {}}])
        self.assertEqual(got, [])
        self.assertEqual([t.name for t in r.tool_calls], ["flightops_status"])

    def test_http_error_is_redacted(self):
        REPLIES["c"] = (500, ['{"error": "bad key sk-abcdefghijklmnopqrstuv"}'])
        with self.assertRaises(ProviderError) as e:
            self.run_stream("c")
        self.assertIn("HTTP 500", str(e.exception))
        self.assertNotIn("sk-abcdefghijklmnopqrstuv", str(e.exception))

    def test_same_request_as_non_streaming(self):
        REPLIES["d"] = (200, [piece("ok", True)])
        self.run_stream("d")
        streamed = dict(FakeOllama.last)
        body = self.p._body("qwen-test", "sys", [{"role": "user", "content": "d"}], None, False)
        streamed.pop("stream"), body.pop("stream")
        self.assertEqual(streamed, body)


if __name__ == "__main__":
    unittest.main()
