"""Jarvis app Phase 1: storage, model manager (aliases, validation, switching, persistence), tool registry
(validation, permissions, confirmation, timeout), agent loop with the mock brain, API security and endpoints.
No network: providers are the mock or fakes. Each test uses a temporary data dir."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from jarvis_app.config.settings import Settings, load_settings  # noqa: E402
from jarvis_app.database.db import DB  # noqa: E402
from jarvis_app.main import create_app  # noqa: E402
from jarvis_app.models.base import ChatResult, Provider, ProviderError, ToolCall  # noqa: E402
from jarvis_app.models.manager import ModelManager  # noqa: E402
from jarvis_app.security.secrets import redact  # noqa: E402
from jarvis_app.tools.registry import Tool, ToolRegistry  # noqa: E402

PROVIDERS = """
active: mock
providers:
  mock: {type: mock}
  broken: {type: mock}
models:
  mock: {provider: mock, model: mock-1, label: Mock, capabilities: [tools]}
  other: {provider: mock, model: mock-2, label: Other Mock, capabilities: [tools]}
  down: {provider: broken, model: x, label: Down Model, capabilities: [tools]}
aliases:
  fable 5: other
"""


class Broken(Provider):
    def chat(self, *a, **k):
        raise ProviderError("HTTP 429: quota exhausted sk-ant-abcdefghijklmnop1234")


def make_settings(tmp):
    pf = Path(tmp) / "providers.yaml"
    pf.write_text(PROVIDERS)
    return Settings(data_dir=Path(tmp) / "data", providers_file=pf)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = make_settings(self.tmp.name)
        self.app = create_app(self.s)
        self.agent = self.app.state.agent
        self.agent.models._adapters["broken"] = Broken()
        self.c = TestClient(self.app)
        self.token = (self.s.data_dir / "api_token").read_text()
        self.h = {"X-Jarvis-Token": self.token}

    def tearDown(self):
        self.tmp.cleanup()

    def chat(self, text):
        r = self.c.post("/api/chat", json={"text": text}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def chat_history(self, conv="default"):
        return self.c.get("/api/conversation", params={"conv": conv}, headers=self.h).json()


class TestSecurity(Base):
    def test_api_requires_token(self):
        self.assertEqual(self.c.get("/api/state").status_code, 401)
        self.assertEqual(self.c.get("/api/state", headers={"X-Jarvis-Token": "wrong"}).status_code, 401)
        self.assertEqual(self.c.get("/api/state", headers=self.h).status_code, 200)

    def test_bad_host_refused(self):
        r = self.c.get("/api/state", headers={**self.h, "host": "evil.example.com"})
        self.assertEqual(r.status_code, 403)

    def test_token_file_mode_600(self):
        self.assertEqual(os.stat(self.s.data_dir / "api_token").st_mode & 0o777, 0o600)

    def test_non_loopback_host_needs_opt_in(self):
        with self.assertRaises(ValueError):
            load_settings({"JARVIS_HOST": "0.0.0.0"})
        self.assertTrue(load_settings({"JARVIS_HOST": "0.0.0.0", "JARVIS_ALLOW_REMOTE": "1"}).allow_remote)

    def test_redact(self):
        self.assertNotIn("sk-ant-abc", redact("key sk-ant-abcdefghijklmnop1234 here"))
        self.assertNotIn("123456789:", redact("bot 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawZ"))
        self.assertNotIn("nvapi-", redact("HTTP 401 key nvapi-AbCdEf123456_ghIJ-kl rejected"))

    def test_page_has_token_and_no_placeholder(self):
        html = self.c.get("/").text
        self.assertIn(self.token, html)
        self.assertNotIn("__JARVIS_TOKEN__", html)


class TestAgent(Base):
    def test_plain_reply(self):
        r = self.chat("hello")
        self.assertEqual(r["reply"], "Echo: hello")
        self.assertEqual(r["model"], "mock:mock-1")

    def test_read_tool_runs_and_result_is_real(self):
        r = self.chat('tool:get_time {}')
        self.assertEqual(r["steps"][0]["status"], "ok")
        self.assertTrue(r["reply"].startswith("Result: "))
        self.assertIn(time.strftime("%Y"), r["reply"])
        audit = self.c.get("/api/audit", headers=self.h).json()
        self.assertEqual(audit[0]["tool"], "get_time")
        self.assertEqual(audit[0]["status"], "ok")

    def test_unknown_tool_reported_not_run(self):
        r = self.chat('tool:delete_everything {}')
        self.assertEqual(r["steps"][0]["status"], "error")
        self.assertIn("TOOL NOT RUN", r["reply"])

    def test_invalid_args_rejected(self):
        r = self.chat('tool:remember {"text": ""}')
        self.assertEqual(r["steps"][0]["status"], "invalid")
        self.assertEqual(self.c.get("/api/memory", headers=self.h).json(), [])

    def test_write_tool_needs_confirmation_then_runs_once(self):
        r = self.chat('tool:remember {"text": "I prefer short answers"}')
        self.assertIsNotNone(r["pending"])
        self.assertEqual(self.c.get("/api/memory", headers=self.h).json(), [])  # nothing written yet
        pid = r["pending"]["id"]
        r2 = self.c.post("/api/confirm", json={"id": pid, "approve": True}, headers=self.h).json()
        self.assertEqual(r2["steps"][0]["status"], "ok")
        self.assertEqual(len(self.c.get("/api/memory", headers=self.h).json()), 1)
        again = self.c.post("/api/confirm", json={"id": pid, "approve": True}, headers=self.h)
        self.assertEqual(again.status_code, 409)  # no double execution
        self.assertEqual(len(self.c.get("/api/memory", headers=self.h).json()), 1)

    def test_declined_write_does_nothing(self):
        r = self.chat('tool:remember {"text": "secret plan"}')
        self.c.post("/api/confirm", json={"id": r["pending"]["id"], "approve": False}, headers=self.h)
        self.assertEqual(self.c.get("/api/memory", headers=self.h).json(), [])

    def test_new_message_supersedes_pending(self):
        r = self.chat('tool:remember {"text": "x y z"}')
        self.chat("never mind")
        self.assertEqual(self.c.get("/api/state", headers=self.h).json()["pending"], [])
        late = self.c.post("/api/confirm", json={"id": r["pending"]["id"], "approve": True}, headers=self.h)
        self.assertEqual(late.status_code, 409)

    def test_permission_off_blocks_tool(self):
        self.c.post("/api/permissions", json={"permission": "project_read", "enabled": False}, headers=self.h)
        r = self.chat('tool:flightops_status {}')
        self.assertEqual(r["steps"][0]["status"], "denied")
        self.assertEqual(self.c.get("/api/audit", headers=self.h).json()[0]["status"], "denied")

    def test_provider_failure_is_reported_and_redacted(self):
        self.agent.models.active = "down"
        r = self.chat("hi")
        self.assertIn("unavailable", r["reply"])
        self.assertNotIn("sk-ant-abc", json.dumps(r))


class TestModels(Base):
    def test_transcribed_chat_uses_selected_model_and_existing_guards(self):
        self.c.post("/api/model", json={"name": "other"}, headers=self.h)
        body = {"text": "recognized speech", "conv": "default"}
        self.assertEqual(self.c.post("/api/chat", json=body).status_code, 401)
        self.assertEqual(self.c.post("/api/chat", json=body,
                                    headers={**self.h, "host": "evil.example.com"}).status_code, 403)
        result = self.c.post("/api/chat", json=body, headers=self.h).json()
        self.assertEqual(result["model"], "mock:mock-2")
        self.assertEqual(result["reply"], "Echo: recognized speech")

    def test_spoken_request_asks_for_a_short_reply(self):
        seen = []
        mock = self.agent.models.adapter("mock")
        real = mock.chat
        mock.chat = lambda model, system, messages, tools: (seen.append(system), real(model, system, messages, tools))[1]
        self.c.post("/api/chat", json={"text": "typed"}, headers=self.h)
        self.c.post("/api/chat", json={"text": "spoken", "voice": True}, headers=self.h)
        self.assertNotIn("read aloud", seen[0])
        self.assertIn("at most 2 short sentences", seen[1])
        self.assertTrue(seen[1].startswith(seen[0][:200]))  # same safety rules, plus the voice note

    def test_chat_stream_sends_text_then_done(self):
        r = self.c.post("/api/chat/stream", json={"text": "hello there", "voice": True}, headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("application/x-ndjson"))
        items = [json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(items[-1]["type"], "done")
        self.assertEqual(items[-1]["reply"], "Echo: hello there")
        self.assertEqual("".join(i["delta"] for i in items if i["type"] == "text"), "Echo: hello there")
        self.assertEqual(self.chat_history()[-1]["content"], "Echo: hello there")   # stored like /api/chat

    def test_chat_stream_keeps_the_guards(self):
        body = {"text": "hi"}
        self.assertEqual(self.c.post("/api/chat/stream", json=body).status_code, 401)
        self.assertEqual(self.c.post("/api/chat/stream", json=body,
                                     headers={**self.h, "host": "evil.example.com"}).status_code, 403)

    def test_chat_stream_confirmation_still_required(self):
        r = self.c.post("/api/chat/stream", json={"text": 'tool:remember {"text": "likes tea"}'}, headers=self.h)
        done = [json.loads(x) for x in r.text.splitlines() if x.strip()][-1]
        self.assertTrue(done["pending"])                      # a write still waits for "yes"
        self.assertEqual(self.agent.db.memories(), [])

    def test_chat_stream_error_still_ends_with_done(self):
        self.c.post("/api/model", json={"name": "other"}, headers=self.h)
        self.agent.handle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom sk-ant-abcdefghijklmnop1234"))
        r = self.c.post("/api/chat/stream", json={"text": "hi"}, headers=self.h)
        done = [json.loads(x) for x in r.text.splitlines() if x.strip()][-1]
        self.assertEqual(done["type"], "done")
        self.assertNotIn("sk-ant-abcdefghijklmnop1234", done["error"])

    def test_voice_controls_and_script_are_served(self):
        html = self.c.get("/").text
        for control in ("micBtn", "muteBtn", "stopSpeakingBtn", "voiceStatus"):
            self.assertIn(f'id="{control}"', html)
        self.assertLess(html.index('/static/voice.js'), html.index('/static/app.js'))
        self.assertEqual(self.c.get("/static/voice.js").status_code, 200)

    def test_alias_and_switch_persist(self):
        r = self.c.post("/api/model", json={"name": "Fable 5"}, headers=self.h).json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["model"], "other")
        mm = ModelManager(self.s.providers_file, DB(self.s.db_path))  # fresh load reads the saved choice
        self.assertEqual(mm.active, "other")

    def test_unknown_model_explained(self):
        r = self.c.post("/api/model", json={"name": "GPT-9 Ultra"}, headers=self.h).json()
        self.assertFalse(r["ok"])
        self.assertIn("don't have a model", r["message"])

    def test_unreachable_model_not_switched(self):
        r = self.c.post("/api/model", json={"name": "Down Model"}, headers=self.h).json()
        self.assertFalse(r["ok"])
        self.assertEqual(self.agent.models.active, "mock")
        self.assertNotIn("sk-ant-abc", r["message"])

    def test_switch_by_voice_style_tool(self):
        r = self.chat('tool:switch_model {"name": "other mock"}')
        self.assertEqual(r["steps"][0]["status"], "ok")
        self.assertEqual(self.agent.models.active, "other")


class TestRegistry(unittest.TestCase):
    def test_write_tool_must_confirm(self):
        class A(BaseModel):
            pass
        reg = ToolRegistry()
        with self.assertRaises(ValueError):
            reg.register(Tool("w", "d", A, "t", lambda a, c: "x", read_only=False, confirm=False))

    def test_timeout(self):
        class A(BaseModel):
            pass
        reg = ToolRegistry()
        t = Tool("slow", "d", A, "t", lambda a, c: time.sleep(2) or "late", timeout_s=0.2)
        reg.register(t)
        out = reg.execute(t, A(), None)
        self.assertFalse(out.ok)
        self.assertIn("timed out", out.error)

    def test_read_tool_retries(self):
        class A(BaseModel):
            pass
        calls = []

        def flaky(a, c):
            calls.append(1)
            if len(calls) < 2:
                raise RuntimeError("temporary")
            return "fine"
        reg = ToolRegistry()
        t = Tool("flaky", "d", A, "t", flaky, retries=1)
        reg.register(t)
        self.assertTrue(reg.execute(t, A(), None).ok)
        self.assertEqual(len(calls), 2)


class TestAnthropicWireFormat(unittest.TestCase):
    """Checks the request body the Anthropic adapter builds (no network: _post is replaced)."""

    def test_tool_round_trip_format(self):
        from jarvis_app.models import adapters
        seen = {}

        def fake_post(url, headers, body):
            seen.update(url=url, headers=headers, body=body)
            return {"model": "m", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}
        orig = adapters._post
        adapters._post = fake_post
        try:
            p = adapters.AnthropicProvider("https://api.anthropic.com", lambda: "k-test-123456789")
            msgs = [{"role": "user", "content": "time?"},
                    {"role": "assistant", "content": "", "tool_calls": [ToolCall("tu1", "get_time", {})]},
                    {"role": "tool", "call_id": "tu1", "name": "get_time", "content": "12:00"}]
            r = p.chat("claude-x", "sys", msgs, [{"name": "get_time", "description": "d", "parameters": {"type": "object", "properties": {}}}])
        finally:
            adapters._post = orig
        self.assertEqual(r.text, "ok")
        self.assertTrue(seen["url"].endswith("/v1/messages"))
        self.assertEqual(seen["headers"]["anthropic-version"], "2023-06-01")
        b = seen["body"]
        self.assertEqual(b["messages"][1]["content"][0]["type"], "tool_use")
        self.assertEqual(b["messages"][2]["content"][0], {"type": "tool_result", "tool_use_id": "tu1", "content": "12:00"})
        self.assertEqual(b["tools"][0]["input_schema"]["type"], "object")

    def test_missing_key_message(self):
        from jarvis_app.models.adapters import AnthropicProvider
        with self.assertRaises(ProviderError) as cm:
            AnthropicProvider("https://api.anthropic.com", lambda: None).chat("m", "s", [{"role": "user", "content": "x"}], None)
        self.assertIn("no Anthropic API key", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
