"""Brain-switch checklist: every brain Jarvis had before the move is still configured and can be selected.
App models (src/jarvis_app/config/providers.yaml) and project Q&A brains (data/jarvis/brains.json) are read from the
real files; every ping / brain call is faked (no network, no keys, no port 8770)."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "jarvis"))
import brains as br  # noqa: E402
import jarvis_core as jc  # noqa: E402
from jarvis_app.config.settings import APP_DIR  # noqa: E402
from jarvis_app.database.db import DB  # noqa: E402
from jarvis_app.models.adapters import AnthropicProvider, OllamaProvider, OpenAICompatProvider  # noqa: E402
from jarvis_app.models.base import ProviderError  # noqa: E402
from jarvis_app.models.manager import ModelManager  # noqa: E402

PROVIDERS = APP_DIR / "config" / "providers.yaml"
# what the running Jarvis (FlightOps copy) had on 2026-10-22; a missing brain fails here
APP_MODELS = {
    "claude-sonnet": "anthropic", "claude-opus": "anthropic", "claude-haiku": "anthropic", "claude-fable": "anthropic",
    "gemini-flash": "omniroute",
    "nv-nemotron-ultra": "nvidia", "nv-nemotron-lightning": "nvidia", "nv-glm": "nvidia", "nv-gpt-oss": "nvidia",
    "nv-glimmer": "nvidia",
    "mi-codestral": "mistral", "mi-ministral": "mistral",
    "local-qwen": "ollama",
}
QA_ORDER = ["codex", "opencode", "omniroute", "local"]
OMNIROUTE_MODELS = ["antigravity/claude-sonnet-4-6", "antigravity/claude-opus-4-6-thinking", "antigravity/gemini-3-flash",
                    "antigravity/gemini-3.5-flash-lite", "gemini/gemini-3.8-flash", "ollama-local/qwen3-8b-32k"]
GOOD = json.dumps({"quotes": [{"chunk": 1, "quote": "The final dataset has 7,121,934 flights"}],
                   "answer": "The final dataset has 7,121,934 flights [1]."})


class FakePing:
    last_ping_model_reported = True

    def __init__(self, ok=True):
        self.ok, self.pinged = ok, []

    def ping(self, model):
        self.pinged.append(model)
        if not self.ok:
            raise ProviderError("HTTP 503: down")
        return model


class AppModels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "jarvis.sqlite"
        self.mm = self.manager()

    def tearDown(self):
        self.tmp.cleanup()

    def manager(self, failing=()):
        mm = ModelManager(PROVIDERS, DB(self.db_path))
        for p in mm.providers_cfg:
            mm._adapters[p] = FakePing(ok=p not in failing)
        return mm

    def test_all_previous_models_configured(self):
        got = {k: m["provider"] for k, m in self.mm.models.items() if k != "mock"}
        self.assertEqual(got, APP_MODELS)
        self.assertEqual(self.mm.active, "local-qwen")

    def test_every_provider_adapter_builds(self):
        kinds = {"anthropic": AnthropicProvider, "openai_compat": OpenAICompatProvider, "ollama": OllamaProvider}
        mm = ModelManager(PROVIDERS, DB(self.db_path))
        for p in set(APP_MODELS.values()):
            self.assertIsInstance(mm.adapter(p), kinds[mm.providers_cfg[p]["type"]], p)

    def test_switch_to_every_model_by_key_label_and_alias(self):
        for key, m in self.mm.models.items():
            if key == "mock":
                continue
            names = [key, m["label"]] + [a for a, k in self.mm.aliases.items() if k == key]
            for name in names:
                with self.subTest(model=key, name=name):
                    self.mm.switch("local-qwen" if key != "local-qwen" else "claude-sonnet")
                    r = self.mm.switch(name)
                    self.assertTrue(r["ok"], r)
                    self.assertEqual(self.mm.active, key)
                    self.assertIn(m["model"], self.mm._adapters[m["provider"]].pinged)

    def test_round_trip_through_all_models_persists(self):
        keys = list(APP_MODELS) + ["local-qwen"]
        for key in keys:
            self.assertTrue(self.mm.switch(key)["ok"], key)
            self.assertEqual(self.manager().active, key)  # a restart reads the saved choice

    def test_unreachable_model_keeps_current(self):
        for provider in set(APP_MODELS.values()):
            mm = self.manager(failing={provider})
            key = next(k for k, p in APP_MODELS.items() if p == provider)
            start = "claude-sonnet" if provider != "anthropic" else "local-qwen"
            self.assertTrue(mm.switch(start)["ok"])
            with self.subTest(provider=provider):
                r = mm.switch(key)
                self.assertFalse(r["ok"])
                self.assertEqual(mm.active, start)


class Handler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Handler.seen.append(body.get("model"))
        data = json.dumps({"model": body.get("model"), "choices": [{"message": {"content": GOOD}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeBrain(br.Brain):
    mode = "combined"

    def __init__(self, bid):
        super().__init__({"enabled": True})
        self.id, self.model, self.calls = bid, "fake", 0

    def complete(self, prompt):
        self.calls += 1
        return GOOD


class QaBrains(unittest.TestCase):
    def test_all_previous_brains_configured(self):
        cfg = br.load_config()
        self.assertEqual(cfg["order"], QA_ORDER)
        for bid in QA_ORDER:
            self.assertTrue(cfg["brains"][bid]["enabled"], bid)
        self.assertEqual(cfg["brains"]["omniroute"]["approved_models"], OMNIROUTE_MODELS)
        self.assertEqual(set(br.make_brains(cfg)), set(br.ADAPTERS))

    def test_select_each_brain(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "docs").mkdir()
            (Path(d) / "docs" / "plan.md").write_text("# Plan\nThe final dataset has 7,121,934 flights (2023-2025).\n")
            index, _ = jc.build_index(d)
        cfg = br.load_config()
        for bid in QA_ORDER:
            with self.subTest(brain=bid):
                fakes = {b: FakeBrain(b) for b in br.ADAPTERS}
                r = br.ask("How many flights are in the final dataset?", index, bid, cfg, fakes)
                self.assertEqual(r["brain"], bid)
                self.assertEqual([b for b, f in fakes.items() if f.calls], [bid])

    def test_omniroute_sends_each_approved_model(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                key = Path(d) / "omniroute_key"
                key.write_text("omr-test-key\n")
                key.chmod(0o600)
                base = br.load_config()["brains"]["omniroute"]
                for m in OMNIROUTE_MODELS:
                    with self.subTest(model=m):
                        cfg = dict(base, model=m, base_url=f"http://127.0.0.1:{srv.server_address[1]}")
                        r = br.run_brain(br.OmniRouteBrain(cfg, key_file=str(key)), "How many flights?",
                                         [{"path": "docs/plan.md", "section": "Plan",
                                           "text": "The final dataset has 7,121,934 flights."}])
                        self.assertFalse(r["refused"], r)
                        self.assertEqual(Handler.seen[-1], m)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
