"""Unit tests for Jarvis round 3: corpus snapshot, access audit, agentic quote guard, fallback. Fake event logs only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "jarvis"))
import agentic as ag  # noqa: E402
import brains as br  # noqa: E402
import corpus_build as cb  # noqa: E402
import jarvis_core as jc  # noqa: E402


def make_root(root):
    def w(rel, txt):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(txt)
    w("docs/plan.md", "# Plan\n## Data\nThe final dataset has 7,121,934 flights (2023-2025).\n"
                      "Key: sb_secret_abcdef123 must never leak\n")
    w("reports/m2_master_qa.md", "# M2\n21.7% of completed flights arrived >= 15 min late.\n")
    w("reports/j1_eval.md", "eval answers")
    w("reports/j1_r3_recall.md", "qa recall answers")
    w("reports/j1_r3_recall.json", "{}")
    w("reports/j2_check.md", "check")
    w("docs/office/jarvis/j1_testset_holdout2.json", "{}")
    w("config/secret.yaml", "x")
    w("src/validate/qa_j1_grade.py", "x")
    w("CLAUDE.md", "# Rules\nNever fabricate data.\n")
    w("artifacts/progress.json", json.dumps({"project": {"name": "X"},
                                             "agent": {"galaxy": {"n": "galaxynode"}, "log": [{"t": i} for i in range(40)]}}))


class Corpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        make_root(self.root)
        self.corpus = Path(self.tmp.name) / "corpus"
        self.m = cb.build_corpus(self.root, self.corpus)

    def tearDown(self):
        self.tmp.cleanup()

    def test_allowlist_only(self):
        files = set(self.m["files"])
        self.assertEqual(files, {"docs/plan.md", "reports/m2_master_qa.md", "CLAUDE.md", "artifacts/progress.json"})
        for bad in ("reports/j1_eval.md", "reports/j1_r3_recall.md", "reports/j1_r3_recall.json", "reports/j2_check.md",
                    "docs/office/jarvis/j1_testset_holdout2.json", "config/secret.yaml", "src/validate/qa_j1_grade.py"):
            self.assertFalse((self.corpus / bad).exists(), bad)

    def test_secret_lines_removed(self):
        text = (self.corpus / "docs/plan.md").read_text()
        self.assertNotIn("sb_secret_", text)
        self.assertIn(cb.SECRET_LINE, text)
        self.assertIn("7,121,934", text)
        self.assertEqual(self.m["secret_lines_removed"], 1)

    def test_progress_pruned(self):
        obj = json.loads((self.corpus / "artifacts/progress.json").read_text())
        self.assertNotIn("galaxy", obj["agent"])
        self.assertEqual(len(obj["agent"]["log"]), jc.LOG_KEEP)

    def test_manifest_shas(self):
        f = self.m["files"]["CLAUDE.md"]
        self.assertEqual(f["source_sha256"], jc.sha256_file(self.root / "CLAUDE.md"))
        self.assertEqual(f["copy_sha256"], jc.sha256_file(self.corpus / "CLAUDE.md"))
        self.assertEqual(cb.load_manifest(self.corpus)["files_copied"], 4)

    def test_stale_copies_removed(self):
        (self.corpus / "reports" / "old.md").write_text("old")
        m = cb.build_corpus(self.root, self.corpus)
        self.assertIn("reports/old.md", m["removed_stale_copies"])
        self.assertFalse((self.corpus / "reports" / "old.md").exists())

    def test_index_excludes_all_j1_reports(self):
        _, man = jc.build_index(self.root)
        self.assertFalse([p for p in man["files"] if p.startswith("reports/j1_")])


class CommandAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = Path(self.tmp.name) / "corpus"
        (self.c / "docs").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def v(self, cmd, cwd=None):
        return ag.audit_command(cmd, str(cwd or self.c), str(self.c))

    def test_allowed(self):
        for cmd in ("/bin/zsh -lc ls", "/bin/zsh -lc 'head -n 3 CLAUDE.md'", "rg -n 'flights' docs reports",
                    "grep -rn total . 2>/dev/null | head -20", "cat docs/../CLAUDE.md", "sed -n '1,40p' docs/plan.md",
                    f"cat {self.c}/docs/plan.md", "ls -la && wc -l docs/*.md", "find . -name '*.md'",
                    "rg -n 'rate$' docs", "cd docs && ls", "rg -l x 2>&1 | sort | uniq"):
            self.assertEqual(self.v(cmd), [], cmd)

    def test_outside_paths(self):
        for cmd in ("cat /etc/passwd", "cat ../../config/project_config.yaml", "ls ..", "cat ~/.ssh/id_rsa",
                    "ls $HOME", "cat ${HOME}/x", "cd .. && ls", "cd /tmp", "rg x /Users", "head --file=/etc/hosts",
                    "/bin/zsh -lc 'cat /etc/hosts'", "cat $(echo /etc/hosts)", "cat `pwd`/../x"):
            self.assertTrue(self.v(cmd), cmd)

    def test_network_write_interpreters(self):
        for cmd in ("curl https://example.com", "wget x", "git log", "echo hi > out.txt", "cat a >> b",
                    "tee x.txt", "rm CLAUDE.md", "sed -i 's/a/b/' docs/plan.md", "find . -exec cat {} ;",
                    "find . -delete", "python3 -c 'print(1)'", "bash -c 'bash -c ls'", "awk '{print}' x", "FOO=1 ls",
                    "nc host 80", "ssh host", "cat <<EOF\nx\nEOF", "mv a b", "open https://x"):
            self.assertTrue(self.v(cmd), cmd)

    def test_cwd_outside(self):
        self.assertTrue(self.v("ls", cwd="/Users"))


CODEX_EVENTS = [
    {"type": "thread.started", "thread_id": "t"},
    {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "looking"}},
    {"type": "item.started", "item": {"id": "item_1", "type": "command_execution", "command": "/bin/zsh -lc 'rg -n flights docs'", "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution", "command": "/bin/zsh -lc 'rg -n flights docs'", "aggregated_output": "docs/plan.md:3:...", "exit_code": 0, "status": "completed"}},
]


def oc_tool(tool, inp, cid="c1"):
    return {"type": "tool_use", "part": {"type": "tool", "tool": tool, "callID": cid, "state": {"status": "completed", "input": inp}}}


class EventParsing(unittest.TestCase):
    corpus = "/x/corpus"

    def test_codex_dedup_and_ok(self):
        acts = ag.codex_actions(CODEX_EVENTS)
        self.assertEqual(len(acts), 1)
        viol, cmds = ag.audit_actions(acts, self.corpus)
        self.assertEqual(viol, [])
        self.assertEqual(cmds, ["rg -n flights docs"])

    def test_codex_bad_items(self):
        evs = CODEX_EVENTS + [
            {"type": "item.completed", "item": {"id": "i2", "type": "command_execution", "command": "/bin/zsh -lc 'cat /Users/me/flightops-ai/config/x'"}},
            {"type": "item.completed", "item": {"id": "i3", "type": "file_change", "changes": [{"path": "a.md"}]}},
            {"type": "item.completed", "item": {"id": "i4", "type": "web_search", "query": "flights"}},
            {"type": "item.completed", "item": {"id": "i5", "type": "mcp_tool_call", "server": "s"}}]
        viol, _ = ag.audit_actions(ag.codex_actions(evs), self.corpus)
        self.assertEqual(len(viol), 4)
        self.assertTrue(any("outside corpus" in v for v in viol))
        self.assertTrue(any(v.startswith("write") for v in viol))
        self.assertTrue(any(v.startswith("network") for v in viol))
        self.assertTrue(any(v.startswith("unknown") for v in viol))

    def test_opencode_tools(self):
        good = [oc_tool("bash", {"command": "ls && head -n 3 CLAUDE.md", "workdir": self.corpus}, "a"),
                oc_tool("read", {"filePath": f"{self.corpus}/docs/plan.md"}, "b"),
                oc_tool("grep", {"pattern": "flights$", "path": self.corpus}, "c"),
                oc_tool("glob", {"pattern": "**/*.md"}, "d")]
        viol, cmds = ag.audit_actions(ag.opencode_actions(good), self.corpus)
        self.assertEqual(viol, [])
        self.assertEqual(len(cmds), 4)
        bad = [oc_tool("read", {"filePath": "/x/config/secret.yaml"}, "e"),
               oc_tool("bash", {"command": "ls", "workdir": "/x"}, "f"),
               oc_tool("write", {"filePath": f"{self.corpus}/a.md", "content": "x"}, "g"),
               oc_tool("webfetch", {"url": "https://x"}, "h"),
               oc_tool("task", {"prompt": "x"}, "i"),
               oc_tool("list", {"path": "~/"}, "j")]
        for ev in bad:
            viol, _ = ag.audit_actions(ag.opencode_actions([ev]), self.corpus)
            self.assertTrue(viol, ev["part"]["tool"])


class QuoteGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        make_root(self.root)
        self.corpus = Path(self.tmp.name) / "corpus"
        self.m = cb.build_corpus(self.root, self.corpus)

    def tearDown(self):
        self.tmp.cleanup()

    def test_kept_and_dropped(self):
        items = [{"path": "docs/plan.md", "quote": "the final dataset has 7,121,934  flights"},
                 {"path": "./reports/m2_master_qa.md", "quote": "21.7% of completed flights arrived >= 15 min late."},
                 {"path": "docs/plan.md", "quote": "The final dataset has 8 million flights"},
                 {"path": "../proj/docs/plan.md", "quote": "The final dataset"},
                 {"path": cb.MANIFEST_NAME, "quote": "files_copied"},
                 {"path": "docs/nope.md", "quote": "x"},
                 {"path": str(self.corpus / "CLAUDE.md"), "quote": "Never fabricate data."}]
        chunks, kept, dropped = ag.check_quotes(items, self.corpus, self.m)
        self.assertEqual([k["n"] for k in kept], [1, 2, 7])
        reasons = {d["n"]: d["reason"] for d in dropped}
        self.assertEqual(reasons[3], "quote not verbatim in file")
        self.assertEqual(reasons[4], "path not inside corpus")
        self.assertEqual(reasons[5], "file not in corpus manifest")
        self.assertEqual(chunks[0]["section"], "Data")
        self.assertEqual(chunks[1]["path"], "reports/m2_master_qa.md")

    def test_sha_mismatch(self):
        p = self.corpus / "docs/plan.md"
        p.write_text(p.read_text() + "\ntampered\n")
        _, kept, dropped = ag.check_quotes([{"path": "docs/plan.md", "quote": "The final dataset"}], self.corpus, self.m)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "corpus file sha does not match manifest")


class Proc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


class AnswerAgentic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        make_root(self.root)
        self.corpus = Path(self.tmp.name) / "corpus"
        self.audit = Path(self.tmp.name) / "audit"
        cb.build_corpus(self.root, self.corpus)
        self.cfg = br.load_config(Path("/nonexistent"))

    def tearDown(self):
        self.tmp.cleanup()

    def codex_runner(self, events, reply):
        def runner(argv, input=None, capture_output=None, text=None, timeout=None, cwd=None):
            self.seen = {"argv": argv, "cwd": cwd, "timeout": timeout, "input": input}
            Path(argv[argv.index("-o") + 1]).write_text(reply)
            return Proc(stdout="\n".join(json.dumps(e) for e in events))
        return runner

    def run_ag(self, runner, brain="codex"):
        with mock.patch.object(ag.shutil, "which", return_value=f"/usr/bin/{brain}"):
            return ag.answer_agentic("How many flights?", brain, self.cfg, self.corpus, self.audit, runner)

    def test_accepted(self):
        reply = json.dumps({"quotes": [{"path": "docs/plan.md", "quote": "The final dataset has 7,121,934 flights (2023-2025)."},
                                       {"path": "docs/plan.md", "quote": "made up"}],
                            "answer": "The final dataset has 7,121,934 flights for 2023-2025 [1]. It is 9,999 big [2]."})
        r = self.run_ag(self.codex_runner(CODEX_EVENTS, reply))
        a = self.seen["argv"]
        self.assertEqual(a[a.index("-C") + 1], str(self.corpus))
        self.assertIn("--json", a)
        self.assertEqual(a[a.index("-s") + 1], "read-only")
        self.assertEqual(self.seen["cwd"], str(self.corpus))
        self.assertNotIn(str(self.corpus), a[a.index("-o") + 1])        # output file outside the corpus
        self.assertEqual(self.seen["timeout"], ag.AGENTIC_TIMEOUT)
        self.assertFalse(r["refused"])
        self.assertEqual(r["citations"], [{"n": 1, "path": "docs/plan.md", "section": "Data"}])
        self.assertEqual(r["invalid_citations"], [2])
        self.assertEqual(r["rejected_quotes"], 1)
        self.assertEqual(r["unsupported_numbers"], ["9999"])     # its quote [2] was dropped
        self.assertEqual(r["search"], "agentic")
        log = json.loads((jc.ROOT / r["audit"]["log"]).read_text()) if not Path(r["audit"]["log"]).is_absolute() \
            else json.loads(Path(r["audit"]["log"]).read_text())
        self.assertEqual(log["verdict"], "accepted")
        self.assertEqual(log["commands"], ["rg -n flights docs"])

    def test_number_not_in_quote_removed(self):
        reply = json.dumps({"quotes": [{"path": "docs/plan.md", "quote": "The final dataset has 7,121,934 flights"}],
                            "answer": "There are 7,121,934 flights in 2024 [1]."})
        r = self.run_ag(self.codex_runner(CODEX_EVENTS, reply))
        self.assertEqual(r["unsupported_numbers"], ["2024"])
        self.assertTrue(r["answer"].endswith("(unverified)"))

    def test_rejected_access_outside(self):
        evs = CODEX_EVENTS + [{"type": "item.completed", "item": {"id": "x", "type": "command_execution",
                                                                   "command": "/bin/zsh -lc 'cat ../../config/secret.yaml'"}}]
        reply = json.dumps({"quotes": [], "answer": jc.REFUSAL})
        with self.assertRaises(ag.AuditRejected) as cm:
            self.run_ag(self.codex_runner(evs, reply))
        e = cm.exception
        self.assertIn(ag.REJECT_ACCESS, str(e))
        logp = Path(e.audit_log) if Path(e.audit_log).is_absolute() else jc.ROOT / e.audit_log
        log = json.loads(logp.read_text())
        self.assertEqual(log["verdict"], "rejected")
        self.assertEqual(log["rejected_reason"], ag.REJECT_ACCESS)
        self.assertTrue(log["violations"])

    def test_refusal_and_unparseable(self):
        r = self.run_ag(self.codex_runner(CODEX_EVENTS, json.dumps({"quotes": [], "answer": jc.REFUSAL})))
        self.assertTrue(r["refused"])
        with self.assertRaises(br.BrainError):
            self.run_ag(self.codex_runner(CODEX_EVENTS, "no json here at all"))

    def test_opencode_agentic(self):
        evs = [oc_tool("bash", {"command": "rg -n flights", "workdir": str(self.corpus)}),
               {"type": "text", "part": {"type": "text", "text": json.dumps(
                   {"quotes": [{"path": "CLAUDE.md", "quote": "Never fabricate data."}], "answer": "Never fabricate data [1]."}),
                   "metadata": {"openai": {}}}}]
        seen = {}

        def runner(argv, input=None, **kw):
            seen["argv"] = argv
            return Proc(stdout="\n".join(json.dumps(e) for e in evs))
        r = self.run_ag(runner, "opencode")
        self.assertEqual(seen["argv"][1:4], ["run", "--dir", str(self.corpus)])
        self.assertFalse(r["refused"])
        self.assertEqual(r["model"], "opencode:openai/model-not-reported")

    def test_timeout(self):
        import subprocess

        def slow(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        with self.assertRaisesRegex(br.BrainError, "timeout"):
            self.run_ag(slow)


class FallbackModes(unittest.TestCase):
    """brains.ask with search='agentic' and a fake agentic function."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "docs").mkdir()
        (root / "docs" / "plan.md").write_text("# Plan\nThe final dataset has 7,121,934 flights.\n")
        self.index, _ = jc.build_index(root)
        self.cfg = br.load_config(Path("/nonexistent"))
        good = json.dumps({"quotes": [{"chunk": 1, "quote": "7,121,934 flights"}], "answer": "7,121,934 flights [1]."})
        self.brains = {"codex": FakeBM25("codex", good), "opencode": FakeBM25("opencode", good),
                       "local": FakeBM25("local", good)}
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def fake_agentic(self, behaviour):
        def fn(question, bid, cfg):
            self.calls.append(bid)
            b = behaviour.get(bid, "ok")
            if b == "reject":
                e = ag.AuditRejected(f"{ag.REJECT_ACCESS}: path outside corpus '/etc/x'")
                e.audit_log, e.violations = "data/jarvis/audit/x.json", ["path outside corpus '/etc/x'"]
                raise e
            if b == "timeout":
                raise br.BrainError("timeout after 180 s")
            r = jc.apply_guards(question, "7,121,934 flights [1].", [{"path": "docs/plan.md", "section": "Plan", "text": "x"}],
                                f"{bid}:m", [{"n": 1, "quote": "7,121,934 flights"}], header_numbers=False)
            r["audit"] = {"log": "data/jarvis/audit/ok.json", "commands": ["rg x"], "violations": []}
            return r
        return fn

    def ask(self, mode, behaviour):
        return br.ask("How many flights in the final dataset?", self.index, mode, self.cfg, self.brains,
                      search="agentic", agentic_fn=self.fake_agentic(behaviour))

    def test_agentic_accepted(self):
        r = self.ask("codex", {})
        self.assertEqual((r["brain"], r["search"]), ("codex", "agentic"))
        self.assertEqual(r["brains_tried"], ["codex:agentic"])
        self.assertEqual(self.brains["codex"].calls, [])

    def test_reject_falls_back_to_bm25_same_brain(self):
        r = self.ask("codex", {"codex": "reject"})
        self.assertEqual((r["brain"], r["search"]), ("codex", "bm25"))
        fb = r["fallbacks"][0]
        self.assertEqual(fb["brain"], "codex:agentic")
        self.assertEqual(fb["rejected_reason"], "access outside corpus")
        self.assertEqual(fb["audit_log"], "data/jarvis/audit/x.json")
        self.assertEqual(r["brains_tried"], ["codex:agentic", "codex"])

    def test_auto_order(self):
        r = self.ask("auto", {"codex": "reject", "opencode": "timeout"})
        self.assertEqual(r["brains_tried"], ["codex:agentic", "opencode:agentic", "codex"])
        self.assertEqual((r["brain"], r["search"]), ("codex", "bm25"))
        r = self.ask("auto", {"codex": "reject"})
        self.assertEqual((r["brain"], r["search"]), ("opencode", "agentic"))

    def test_local_has_no_agentic(self):
        r = self.ask("local", {})
        self.assertEqual((r["brain"], r["search"]), ("local", "bm25"))
        self.assertNotIn("local", self.calls)

    def test_council_agentic(self):
        r = self.ask("council", {"opencode": "reject"})
        self.assertEqual(r["council"]["members"], ["codex", "opencode"])
        self.assertEqual(r["council"]["agreement"], "agree")
        self.assertIn("opencode:agentic", [f["brain"] for f in r["fallbacks"]])
        self.assertEqual(r["search"], "agentic+bm25")
        self.assertTrue(all("brain" in c for c in r["citations"]))

    def test_bad_search(self):
        with self.assertRaises(ValueError):
            br.ask("q", self.index, "codex", self.cfg, self.brains, search="web")


class FakeBM25(br.Brain):
    mode = "combined"

    def __init__(self, bid, reply):
        super().__init__({"enabled": True})
        self.id, self.reply, self.calls, self.model = bid, reply, [], "fake"

    def complete(self, prompt):
        self.calls.append(prompt)
        return self.reply


class RefusalWithContext(unittest.TestCase):
    chunks = [{"path": "docs/dir.md", "section": "Diagnosis", "text": "x"}, {"path": "b.md", "section": "B", "text": "y"}]
    quotes = [{"n": 1, "quote": "Not done: M6 models (out of scope until approved)."},
              {"n": 2, "quote": "The dataset has 7,121,934 flights."}]

    def g(self, ans):
        return jc.apply_guards("What is the accuracy?", ans, self.chunks, "fake", self.quotes, header_numbers=False)

    def test_context_kept_and_refused(self):
        r = self.g(f"{jc.REFUSAL} The M6 models are not done yet [1]. Extra sentence two [2].")
        self.assertTrue(r["refused"])
        self.assertEqual(r["answer"], f"{jc.REFUSAL} The M6 models are not done yet [1].")
        self.assertEqual(r["citations"], [{"n": 1, "path": "docs/dir.md", "section": "Diagnosis"}])

    def test_dash_variants_and_number_guard(self):
        r = self.g("I don't know - it isn't in the project files. Training ran on 500 flights [1].")
        self.assertTrue(r["refused"])
        self.assertEqual(r["unsupported_numbers"], ["500"])
        self.assertIn(jc.REMOVED, r["answer"])
        self.assertTrue(r["answer"].startswith(jc.REFUSAL))

    def test_uncited_or_invalid_context_dropped(self):
        for ans in (f"{jc.REFUSAL} Models are not done yet.", f"{jc.REFUSAL} Not done [7].", jc.REFUSAL):
            r = self.g(ans)
            self.assertTrue(r["refused"], ans)
            self.assertEqual(r["answer"], jc.REFUSAL, ans)
            self.assertEqual(r["citations"], [], ans)

    def test_partial_multipart_not_refused(self):
        r = self.g("The dataset has 7,121,934 flights [2]. The files do not say the accuracy.")
        self.assertFalse(r["refused"])

    def test_refusal_not_at_start_is_plain_refusal(self):
        r = self.g(f"The dataset has 7,121,934 flights [2]. {jc.REFUSAL}")
        self.assertTrue(r["refused"])
        self.assertEqual(r["answer"], jc.REFUSAL)

    def test_prompts_have_rule(self):
        for p in (jc.COMBINED_SYSTEM, jc.ANSWER_SYSTEM, ag.AGENTIC_PROMPT):
            self.assertIn("MUST begin with exactly", p)
            self.assertIn("ONE short cited sentence", p)


class PromptsAndRefusal(unittest.TestCase):
    def test_parts_rule_in_prompts(self):
        for p in (jc.COMBINED_SYSTEM, jc.ANSWER_SYSTEM, ag.AGENTIC_PROMPT):
            self.assertIn("answer EVERY part", p)
            self.assertIn("full-period total", p)

    def test_partial_answer_is_not_refusal(self):
        self.assertFalse(jc.is_refusal("G8 is weather [1]. The files do not say who approved it."))
        self.assertFalse(jc.is_refusal("G8 is weather [1]. Part two isn't in the project files."))
        self.assertTrue(jc.is_refusal(f"G8 is weather [1]. {jc.REFUSAL}"))
        self.assertTrue(jc.is_refusal("I don't know."))


if __name__ == "__main__":
    unittest.main()
