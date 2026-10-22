"""Unit tests for Jarvis multi-brain (src/jarvis/brains.py). Fake brains and fake subprocess runners; no network."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "jarvis"))
import brains as br  # noqa: E402
import jarvis_core as jc  # noqa: E402

CHUNKS = [
    {"path": "docs/plan.md", "section": "Plan > Data", "text": "The final dataset has 7,121,934 flights (2023-2025)."},
    {"path": "reports/m2.md", "section": "Master", "text": "Pilot month: 538,837 rows. 21.7% of flights arrived late."},
    {"path": "docs/rules.md", "section": "Rules", "text": "Features must be known 24 hours before departure."},
]


def combined(quotes, answer):
    return json.dumps({"quotes": [{"chunk": n, "quote": q} for n, q in quotes], "answer": answer})


class FakeCombined(br.Brain):
    mode = "combined"

    def __init__(self, bid, reply=None, error=None, enabled=True):
        super().__init__({"enabled": enabled})
        self.id, self.reply, self.error, self.calls, self.model = bid, reply, error, [], "fake"

    def complete(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise br.BrainError(self.error)
        return self.reply


class FakeLocal(br.Brain):
    id = "local"
    mode = "two_step"

    def __init__(self, quotes_reply, answer_reply):
        super().__init__({"enabled": True})
        self.q, self.a, self.calls, self.model = quotes_reply, answer_reply, [], "qwen-fake"

    def chat(self, messages, json_mode=False):
        self.calls.append(json_mode)
        return self.q if json_mode else self.a


GOOD = combined([(1, "The final dataset has 7,121,934 flights")], "The final dataset has 7,121,934 flights [1].")
GOOD2 = combined([(1, "7,121,934 flights (2023-2025)")], "There are 7,121,934 flights for 2023-2025 [1].")
OTHER = combined([(2, "Pilot month: 538,837 rows")], "The pilot month had 538,837 rows [2].")
REFUSE = combined([], jc.REFUSAL)


class Proc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


class Adapters(unittest.TestCase):
    def test_codex_argv_empty_dir_and_output_file(self):
        seen = {}

        def runner(argv, input=None, capture_output=None, text=None, timeout=None, cwd=None):
            seen.update(argv=argv, input=input, timeout=timeout, cwd=cwd)
            self.assertEqual(list(Path(cwd).iterdir()), [])          # empty temp folder
            out = argv[argv.index("-o") + 1]
            Path(out).write_text('```json\n{"ok": 1}\n```')
            return Proc(stderr="model: gpt-test-1\nsession id: x\nsk-abcdefghijklmnopqrstuvwx")

        b = br.CodexBrain({"timeout_s": 7}, runner)
        with mock.patch.object(br.shutil, "which", return_value="/usr/bin/codex"):
            out = b.complete("PROMPT")
        argv = seen["argv"]
        for flag in ("exec", "-s", "read-only", "-C", "--skip-git-repo-check", "--ephemeral", "-o"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("-s") + 1], "read-only")
        self.assertEqual(argv[argv.index("-C") + 1], seen["cwd"])
        self.assertEqual(seen["input"], "PROMPT")
        self.assertEqual(seen["timeout"], 7)
        self.assertEqual(jc.extract_json(out), {"ok": 1})
        self.assertEqual(b.model, "gpt-test-1")
        self.assertFalse(Path(seen["cwd"]).exists())                 # temp folder removed

    def test_opencode_json_events(self):
        events = "\n".join(json.dumps(e) for e in [
            {"type": "step_start", "part": {"type": "step-start"}},
            {"type": "text", "part": {"type": "text", "text": 'Sure:\n{"answer": "x"}', "metadata": {"openai": {}}}},
            {"type": "step_finish", "part": {"type": "step-finish"}}])
        seen = {}

        def runner(argv, **kw):
            seen["argv"] = argv
            return Proc(stdout=events)

        b = br.OpenCodeBrain({}, runner)
        with mock.patch.object(br.shutil, "which", return_value="/usr/bin/opencode"):
            out = b.complete("PROMPT")
        self.assertEqual(seen["argv"][1:3], ["run", "--dir"])
        self.assertEqual(seen["argv"][-1], "PROMPT")
        self.assertEqual(jc.extract_json(out), {"answer": "x"})
        self.assertEqual(b.model, "openai/model-not-reported")

    def test_opencode_reports_model(self):
        ev = json.dumps({"type": "text", "part": {"type": "text", "text": "{}", "modelID": "gpt-x", "providerID": "openai"}})
        b = br.OpenCodeBrain({}, lambda argv, **kw: Proc(stdout=ev))
        with mock.patch.object(br.shutil, "which", return_value="/x"):
            b.complete("p")
        self.assertEqual(b.model, "openai/gpt-x")

    def test_timeout_nonzero_missing(self):
        def slow(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        with mock.patch.object(br.shutil, "which", return_value="/x"):
            with self.assertRaisesRegex(br.BrainError, "timeout"):
                br.CodexBrain({"timeout_s": 1}, slow).complete("p")
            with self.assertRaisesRegex(br.BrainError, "exit 3"):
                br.CodexBrain({}, lambda a, **k: Proc(stderr="boom token=abc123secret", returncode=3)).complete("p")
            with self.assertRaisesRegex(br.BrainError, "empty"):
                br.CodexBrain({}, lambda a, **k: Proc()).complete("p")
        with mock.patch.object(br.shutil, "which", return_value=None):
            with self.assertRaisesRegex(br.BrainError, "not found"):
                br.CodexBrain({}, lambda a, **k: Proc()).complete("p")

    def test_error_text_has_no_token(self):
        with mock.patch.object(br.shutil, "which", return_value="/x"):
            try:
                br.CodexBrain({}, lambda a, **k: Proc(stderr="failed Bearer abcdefghijklmnop1234", returncode=1)).complete("p")
            except br.BrainError as e:
                self.assertNotIn("abcdefghijklmnop1234", str(e))

    def test_claude_disabled_never_runs(self):
        calls = []
        cfg = br.load_config(Path("/nonexistent"))
        self.assertFalse(cfg["brains"]["claude"]["enabled"])
        b = br.ClaudeBrain(cfg["brains"]["claude"], lambda *a, **k: calls.append(a))
        with self.assertRaisesRegex(br.BrainError, "disabled"):
            b.complete("p")
        with self.assertRaises(br.BrainError):
            br.run_brain(b, "q", CHUNKS)
        self.assertEqual(calls, [])

    def test_secret_in_prompt_not_sent(self):
        calls = []
        with mock.patch.object(br.shutil, "which", return_value="/x"):
            with self.assertRaisesRegex(br.BrainError, "secret"):
                br.CodexBrain({}, lambda *a, **k: calls.append(a)).complete("key sb_secret_x")
        self.assertEqual(calls, [])

    def test_strip_tokens(self):
        s = br.strip_tokens("\x1b[31mok\x1b[0m sk-ABCDEFGHIJKLMNOPQRSTUV eyJhbGci.eyJzdWIi.sig password: hunter2")
        self.assertEqual(s.count("[redacted]"), 3)
        self.assertTrue(s.startswith("ok "))

    def test_local_brain_unavailable(self):
        def opener(req, timeout=None):
            raise OSError("connection refused")
        with self.assertRaisesRegex(br.BrainError, "local model unavailable"):
            br.LocalBrain({}, opener=opener).chat([{"role": "user", "content": "x"}])

    def test_config_file_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "brains.json"
            p.write_text(json.dumps({"order": ["local"], "brains": {"codex": {"timeout_s": 5}}}))
            cfg = br.load_config(p)
        self.assertEqual(cfg["order"], ["local"])
        self.assertEqual(cfg["brains"]["codex"]["timeout_s"], 5)
        self.assertEqual(cfg["council"], ["codex", "opencode"])

    def test_repo_brains_json(self):
        cfg = br.load_config()
        self.assertEqual(cfg["order"], ["codex", "opencode", "omniroute", "local"])
        om = cfg["brains"]["omniroute"]
        if om["enabled"]:  # 2026-10-20: only a pinned, Director-approved model via a localhost gateway
            approved = om.get("approved_models", [])
            self.assertIn(om["model"], approved)
            for m in approved:
                self.assertFalse(m.startswith(("auto/", "oc/", "aihorde/")) or "free" in m, m)
                # gemini/ = OmniRoute's direct Gemini connection (approved, also in FlightOps config/ai/brains.json)
                self.assertTrue(m.startswith(("ollama-local/", "antigravity/", "gemini/")), m)
            self.assertRegex(om["base_url"], r"^http://(127\.0\.0\.1|localhost)(:\d+)?$")
        else:
            self.assertIsNone(om["model"])
        self.assertFalse(cfg["brains"]["claude"]["enabled"])


class Combined(unittest.TestCase):
    def test_extract_json_variants(self):
        self.assertEqual(jc.extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(jc.extract_json('Here you go:\n```json\n{"a": 2}\n```\nbye'), {"a": 2})
        self.assertEqual(jc.extract_json('text {"a": {"b": 3}} more {"c": 4}'), {"a": {"b": 3}})
        self.assertIsNone(jc.extract_json("no json here"))

    def test_guards_apply_to_cli_brain(self):
        bad = combined([(1, "The final dataset has 7,121,934 flights"), (2, "made up quote")],
                       "The dataset has 7,500,000 flights [1]. Pilot was 538,837 [2].")
        r = br.run_brain(FakeCombined("codex", bad), "q", CHUNKS)
        self.assertEqual(r["rejected_quotes"], 1)
        self.assertIn("7500000", r["unsupported_numbers"])
        self.assertEqual(r["invalid_citations"], [2])     # chunk 2 had no verified quote
        self.assertTrue(r["answer"].endswith("(unverified)"))
        self.assertEqual(r["model"], "codex:fake")

    def test_refusal_and_mixed_refusal(self):
        self.assertTrue(br.run_brain(FakeCombined("codex", REFUSE), "q", CHUNKS)["refused"])
        mixed = combined([(1, "7,121,934 flights")], f"7,121,934 flights [1]. {jc.REFUSAL}")
        r = br.run_brain(FakeCombined("codex", mixed), "q", CHUNKS)
        self.assertTrue(r["refused"])
        self.assertEqual(r["answer"], jc.REFUSAL)

    def test_plain_text_refusal(self):
        self.assertTrue(br.run_brain(FakeCombined("codex", jc.REFUSAL), "q", CHUNKS)["refused"])

    def test_unparseable_is_brain_error(self):
        with self.assertRaisesRegex(br.BrainError, "unparseable"):
            br.run_brain(FakeCombined("codex", "I think it's about seven million."), "q", CHUNKS)

    def test_prompt_has_only_chunks_and_question(self):
        b = FakeCombined("codex", GOOD)
        br.run_brain(b, "How many flights?", CHUNKS)
        p = b.calls[0]
        self.assertIn("[1] docs/plan.md", p)
        self.assertIn("QUESTION: How many flights?", p)
        self.assertIn("Do not run commands", p)


class Auto(unittest.TestCase):
    def brains(self, **kw):
        return {"codex": kw.get("codex", FakeCombined("codex", GOOD)),
                "opencode": kw.get("opencode", FakeCombined("opencode", GOOD2)),
                "local": kw.get("local", FakeLocal(json.dumps({"quotes": [{"chunk": 1, "quote": "7,121,934 flights"}]}),
                                                   "7,121,934 flights [1]."))}

    def test_first_brain_answers(self):
        r = br.run_auto("q", CHUNKS, self.brains(), ["codex", "opencode", "local"])
        self.assertEqual(r["brain"], "codex")
        self.assertEqual(r["brains_tried"], ["codex"])
        self.assertEqual(r["fallbacks"], [])
        self.assertIn("codex", r["seconds_per_brain"])

    def test_fallback_chain_to_local(self):
        b = self.brains(codex=FakeCombined("codex", error="timeout after 120 s"),
                        opencode=FakeCombined("opencode", "garbage"))
        r = br.run_auto("q", CHUNKS, b, ["codex", "opencode", "local"])
        self.assertEqual(r["brain"], "local")
        self.assertEqual(r["brains_tried"], ["codex", "opencode", "local"])
        self.assertEqual([f["brain"] for f in r["fallbacks"]], ["codex", "opencode"])
        self.assertIn("timeout", r["fallbacks"][0]["reason"])
        self.assertEqual(b["local"].calls, [True, False])
        self.assertFalse(r["refused"])

    def test_refusal_is_not_a_fallback(self):
        b = self.brains(codex=FakeCombined("codex", REFUSE))
        r = br.run_auto("q", CHUNKS, b, ["codex", "opencode"])
        self.assertTrue(r["refused"])
        self.assertEqual(r["brain"], "codex")
        self.assertEqual(b["opencode"].calls, [])

    def test_disabled_skipped_and_all_fail(self):
        b = self.brains(codex=FakeCombined("codex", GOOD, enabled=False),
                        opencode=FakeCombined("opencode", error="exit 1"))
        r = br.run_auto("q", CHUNKS, b, ["codex", "opencode"])
        self.assertIn("error", r)
        self.assertEqual(r["fallbacks"][0], {"brain": "codex", "reason": "disabled"})
        self.assertEqual(b["codex"].calls, [])

    def test_ask_retrieves_once_and_modes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            (root / "docs" / "plan.md").write_text("# Plan\nThe final dataset has 7,121,934 flights (2023-2025).\n")
            index, _ = jc.build_index(root)
        cfg = br.load_config(Path("/nonexistent"))
        b = self.brains()
        r = br.ask("How many flights are in the final dataset?", index, "opencode", cfg, b)
        self.assertEqual(r["brain"], "opencode")
        self.assertEqual(b["codex"].calls, [])
        r = br.ask("the of and", index, "auto", cfg, b)
        self.assertTrue(r["refused"])
        self.assertEqual(r["brains_tried"], [])
        with self.assertRaises(ValueError):
            br.ask("flights", index, "nope", cfg, b)


class Council(unittest.TestCase):
    def run_c(self, a, b, spare=None, council=("codex", "opencode")):
        brains = {"codex": a, "opencode": b}
        if spare:
            brains["local"] = spare
        return br.run_council("q", CHUNKS, brains, list(council), ["codex", "opencode", "local"])

    def test_agree(self):
        r = self.run_c(FakeCombined("codex", GOOD), FakeCombined("opencode", GOOD2))
        self.assertEqual(r["council"]["agreement"], "agree")
        self.assertEqual(r["brain"], "codex+opencode")
        self.assertEqual(r["answer"], "The final dataset has 7,121,934 flights [1].")
        self.assertEqual(set(r["seconds_per_brain"]), {"codex", "opencode"})
        self.assertFalse(r["refused"])

    def test_disagree_numbers(self):
        r = self.run_c(FakeCombined("codex", GOOD), FakeCombined("opencode", OTHER))
        self.assertEqual(r["council"]["agreement"], "disagree")
        self.assertTrue(r["answer"].startswith("Brains disagree."))
        self.assertIn("7,121,934", r["answer"])
        self.assertIn("538,837", r["answer"])
        self.assertEqual([c["n"] for c in r["citations"]], [1, 2])

    def test_one_refused(self):
        r = self.run_c(FakeCombined("codex", REFUSE), FakeCombined("opencode", GOOD2))
        self.assertEqual(r["council"]["agreement"], "one brain refused")
        self.assertEqual(r["brain"], "opencode")
        self.assertIn("one brain refused", r["answer"])
        self.assertFalse(r["refused"])

    def test_both_refused(self):
        r = self.run_c(FakeCombined("codex", REFUSE), FakeCombined("opencode", REFUSE))
        self.assertTrue(r["refused"])
        self.assertEqual(r["answer"], jc.REFUSAL)

    def test_failed_member_replaced_by_spare(self):
        local = FakeLocal(json.dumps({"quotes": [{"chunk": 1, "quote": "7,121,934 flights"}]}), "7,121,934 flights [1].")
        r = self.run_c(FakeCombined("codex", error="timeout after 120 s"), FakeCombined("opencode", GOOD2), spare=local)
        self.assertEqual(r["brains_tried"], ["codex", "opencode", "local"])
        self.assertEqual(r["council"]["members"], ["opencode", "local"])
        self.assertEqual(r["council"]["agreement"], "agree")
        self.assertEqual(r["fallbacks"][0]["brain"], "codex")

    def test_single_survivor(self):
        r = self.run_c(FakeCombined("codex", error="exit 1"), FakeCombined("opencode", GOOD2))
        self.assertEqual(r["brain"], "opencode")
        self.assertIn("single", r["council"]["agreement"])

    def test_agreement_without_numbers_needs_common_citation(self):
        a = {"answer": "Rules apply [3].", "citations": [{"n": 3, "path": "r.md", "section": "Rules"}]}
        self.assertTrue(br.answers_agree(a, {"answer": "Yes [1].", "citations": [{"n": 1, "path": "r.md", "section": "Rules"}]}))
        self.assertFalse(br.answers_agree(a, {"answer": "No [1].", "citations": [{"n": 1, "path": "p.md", "section": "X"}]}))

    def test_agreement_numbers_subset(self):
        a = {"answer": "7,121,934 flights [1].", "citations": [{"n": 1}]}
        self.assertTrue(br.answers_agree(a, {"answer": "7121934 flights in 2023-2025 [1].", "citations": [{"n": 1}]}))
        self.assertFalse(br.answers_agree(a, {"answer": "7,500,000 flights in 2023 [1].", "citations": [{"n": 1}]}))


if __name__ == "__main__":
    unittest.main()
