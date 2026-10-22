"""Unit tests for Jarvis J1 (src/jarvis/jarvis_core.py). Fake LLM only; no network."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "jarvis"))
import jarvis_core as jc  # noqa: E402


def make_tree(root):
    def w(rel, txt):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(txt)

    w("docs/plan.md", "# Plan\nIntro text.\n## Rules\nFeatures must be known 24 hours before departure (T-24h).\n"
                      "## Data\nThe final dataset has 7,121,934 flights for G1 to G12. The pilot month had 538,837 rows.\n")
    w("docs/carriers.md", "# Carriers\nWe study Frontier Airlines (F9), United (UA) and Southwest (WN). "
                          "Endeavor Air (9E) is excluded. The Director (QA) reviews.\n")
    w("docs/registry/source_registry.csv", "source_id,name,publisher\nS01,On-Time Performance,BTS\nS02,MOS forecasts,NOAA\n")
    w("docs/registry/g_factor_coverage.csv", "factor,category\nG8,Ground weather\nG1,Airport infrastructure\n")
    w("reports/m2_master_qa.json", json.dumps({"rows": 500, "checks": {"dupes": 0, "late": "ok"}}))
    w("reports/j1_eval.md", "# Eval\nsecret answers")
    w("reports/j1_eval_r1.json", "{}")
    w("reports/j2_check.md", "# check")
    w("reports/j5_check.json", "{}")
    w("docs/office/jarvis/j1_testset.json", "{}")
    w("docs/office/jarvis/j1_testset_holdout.json", "{}")
    w("docs/office/jarvis/j1_work_order.md", "# WO\nfine")
    progress = {"project": {"name": "FlightOps", "airlines": ["UA", "WN", "F9"]},
                "milestones": [{"id": "M5", "title": "Integration", "tasks": [
                    {"id": "M5.3", "title": "Leakage audit", "status": "completed", "evidence": ["reports/m5.json"]}]}],
                "factors": [{"id": "G5", "title": "Maintenance", "status": "PROXY_VALIDATED"}],
                "agent": {"state": "working", "galaxy": {"nodes": [{"id": "galaxynode"}]},
                          "briefing": {"sections": [{"title": "briefingsection"}]},
                          "log": [{"t": f"2026-10-{i:02d}", "kind": "act", "text": f"logentry{i}"} for i in range(1, 41)],
                          "datacenter": {"dataset_count": 16, "last_job_runs": [{"name": "rawjobrun"}],
                                         "catalog": {"mb": 0.9, "files": ["rawlistfile"]}}}}
    w("artifacts/progress.json", json.dumps(progress))
    w("artifacts/decisions/D-x.json", json.dumps({"id": "D-x", "question": "Approve step?"}))
    w("CLAUDE.md", "# Rules\nNever fabricate data.\n")
    w("docs/secret.md", "# Keys\nkey = sb_secret_abc123\n# Fine\nnothing here\n")
    w("config/notes.md", "should never be indexed")
    w("tracker/notes.md", "should never be indexed")
    w("data/jarvis/qa_raw/x.md", "should never be indexed")
    w("artifacts/chat.jsonl", "{}")
    w("docs/big.docx", "binary")
    w("reports/huge.md", "# Huge\n" + "a " * (1024 * 1024 + 10))


class Chunking(unittest.TestCase):
    def test_markdown_heading_path(self):
        ch = jc.chunk_markdown("# A\none\n## B\ntwo\n### C\nthree\n## D\nfour\n")
        self.assertEqual([s for s, _ in ch], ["A", "A > B", "A > B > C", "A > D"])

    def test_markdown_ignores_headings_in_code_fence(self):
        ch = jc.chunk_markdown("# A\n```\n# not a heading\n```\nend\n")
        self.assertEqual([s for s, _ in ch], ["A"])

    def test_markdown_long_section_split_with_overlap(self):
        body = "\n".join(f"line {i} " + "w" * 60 for i in range(80))
        ch = jc.chunk_markdown("# Long\n" + body)
        self.assertGreater(len(ch), 1)
        self.assertTrue(all(len(t) <= jc.MAX_CHARS for _, t in ch))
        self.assertIn(ch[0][1][-50:].split("\n")[-1], ch[1][1])

    def test_csv_one_row_per_chunk(self):
        ch = jc.chunk_csv("id,name\nG1,Weather\nG2,Staffing\n")
        self.assertEqual(ch, [("G1", "id: G1; name: Weather"), ("G2", "id: G2; name: Staffing")])

    def test_json_one_record_per_chunk_readable_section(self):
        val = {"milestones": [{"id": "M5", "title": "Integration",
                               "tasks": [{"id": "M5.3", "title": "Audit", "evidence": ["a", "b"]}]}]}
        ch = dict(jc.chunk_json_value(val))
        self.assertIn("milestones › M5", ch)
        self.assertIn("milestones › M5 › tasks › M5.3", ch)
        self.assertIn("evidence: a; b", ch["milestones › M5 › tasks › M5.3"])
        self.assertNotIn("M5.3", ch["milestones › M5"])  # child record not packed into the parent

    def test_json_label_fallbacks_and_flat_dicts(self):
        val = {"log": [{"t": "2026-10-19T01:00", "text": "x"}, {"text": "y"}], "contracts": {"passed": 16, "n": 16}}
        ch = dict(jc.chunk_json_value(val))
        self.assertIn("log › 2026-10-19T01:00", ch)
        self.assertIn("log › 1", ch)
        self.assertIn("contracts.passed: 16", ch["(root)"])

    def test_json_decision_root_uses_id(self):
        ch = jc.chunk_json(json.dumps({"id": "D-x", "question": "Q?", "checks": [{"name": "rows", "passed": True}]}))
        secs = [s for s, _ in ch]
        self.assertEqual(secs, ["D-x", "D-x › checks › rows"])

    def test_prune_progress(self):
        obj = {"agent": {"galaxy": {}, "briefing": {}, "log": list(range(50)),
                         "datacenter": {"n": 1, "runs": [1], "catalog": {"tables": {"a": 1}, "files": ["x"]}}}}
        pruned = jc.prune_progress(obj)
        self.assertNotIn("galaxy", obj["agent"])
        self.assertNotIn("briefing", obj["agent"])
        self.assertEqual(obj["agent"]["log"], list(range(20, 50)))
        self.assertEqual(obj["agent"]["datacenter"], {"n": 1, "catalog": {"tables": {"a": 1}}})
        self.assertIn("agent.datacenter.runs", pruned)


class Tokens(unittest.TestCase):
    def test_ids_and_numbers_kept(self):
        toks = jc.tokenize("G12 and M5 in D-step6-signoff had 7,121,934 rows, J1 C1 9E 24h")
        for t in ("g12", "m5", "d-step6-signoff", "7121934", "j1", "c1", "row", "9e", "24h", "24"):
            self.assertIn(t, toks)
        self.assertNotIn("and", toks)

    def test_number_forms_equal(self):
        self.assertEqual(jc.tokenize("7,121,934"), jc.tokenize("7121934"))

    def test_underscore_and_plural(self):
        toks = jc.tokenize("source_registry flights categories")
        for t in ("source_registry", "source", "registry", "flight", "category"):
            self.assertIn(t, toks)

    def test_leaf_section(self):
        self.assertEqual(jc.leaf_section("Doc title > 7. Final deliverables"), "7. Final deliverables")
        self.assertEqual(jc.leaf_section("milestones › M5 › tasks › M5.3"), "tasks › M5.3")
        self.assertEqual(jc.leaf_section("S02"), "S02")

    def test_numbers_exclude_ids(self):
        self.assertEqual(jc.numbers_in("G12 M5.3 S02 F9: 7,121,934 and 2.50 and 15"), {"7121934", "2.5", "15"})


class Aliases(unittest.TestCase):
    def test_carriers_factors_domain(self):
        rules = jc.build_aliases(["We study Frontier Airlines (F9) and Endeavor Air (9E). The Director (QA) reviews."],
                                 airlines=["F9"], factor_titles=[("G8", "Ground weather")])
        d = {tuple(p): e for p, e in rules}
        self.assertIn("frontier", d[("f9",)])
        self.assertIn("f9", d[("frontier",)])
        self.assertIn("9e", d[("endeavor",)])
        self.assertNotIn(("qa",), d)  # not a carrier code
        self.assertEqual(d[("ground", "weather")], ["g8"])
        self.assertIn("arrdel15", d[("late",)])

    def test_expand_query_weights(self):
        w = jc.expand_query(["late", "flight"], [[["late"], ["arrdel15"]], [["ground", "weather"], ["g8"]]])
        self.assertEqual(w, {"late": 1.0, "flight": 1.0, "arrdel15": jc.ALIAS_WEIGHT})


class IndexAndSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_tree(self.root)
        self.index, self.manifest = jc.build_index(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_allowlist_and_eval_exclusions(self):
        files = set(self.manifest["files"])
        for rel in ("docs/plan.md", "docs/registry/source_registry.csv", "reports/m2_master_qa.json",
                    "artifacts/progress.json", "artifacts/decisions/D-x.json", "CLAUDE.md",
                    "docs/office/jarvis/j1_work_order.md"):
            self.assertIn(rel, files)
        for rel in ("reports/j1_eval.md", "reports/j1_eval_r1.json", "reports/j2_check.md", "reports/j5_check.json",
                    "docs/office/jarvis/j1_testset.json", "docs/office/jarvis/j1_testset_holdout.json",
                    "data/jarvis/qa_raw/x.md", "config/notes.md", "tracker/notes.md", "docs/big.docx"):
            self.assertNotIn(rel, files)
        self.assertFalse(any(c["path"].startswith(("config/", "tracker/", "data/")) for c in self.index["chunks"]))

    def test_progress_bulky_sections_not_indexed(self):
        text = " ".join(c["text"] for c in self.index["chunks"] if c["path"] == "artifacts/progress.json")
        for bad in ("galaxynode", "briefingsection", "rawjobrun", "rawlistfile", "logentry10"):
            self.assertNotIn(bad, text)
        self.assertIn("logentry40", text)
        self.assertIn("logentry11", text)
        self.assertTrue(self.manifest["progress_pruned"])
        secs = {c["section"] for c in self.index["chunks"]}
        self.assertIn("milestones › M5 › tasks › M5.3", secs)

    def test_large_file_skipped(self):
        self.assertIn("reports/huge.md", self.manifest["skipped_large_files"])

    def test_secret_chunk_skipped_and_counted(self):
        self.assertEqual(self.manifest["skipped_secret_chunks"], 1)
        self.assertFalse(any("sb_secret_" in c["text"] for c in self.index["chunks"]))
        self.assertTrue(any(c["section"] == "Fine" for c in self.index["chunks"]))

    def test_manifest_fields(self):
        for k in ("built_at", "files_indexed", "chunk_count", "skipped_secret_chunks", "files", "alias_rules"):
            self.assertIn(k, self.manifest)
        self.assertEqual(self.manifest["chunk_count"], len(self.index["chunks"]))
        self.assertEqual(len(self.manifest["files"]["CLAUDE.md"]["sha256"]), 64)

    def test_aliases_built_from_files(self):
        d = {tuple(p): e for p, e in self.index["aliases"]}
        self.assertIn("frontier", d[("f9",)])
        self.assertIn(("maintenance",), d)          # progress.json factor title
        self.assertIn("g8", d[("ground", "weather")])  # coverage csv category

    def test_bm25_ranks_relevant_chunk_first(self):
        self.assertEqual(jc.bm25_search(self.index, "How many flights are in the final dataset?")[0]["section"],
                         "Plan > Data")
        self.assertEqual(jc.bm25_search(self.index, "Which publisher provides MOS forecasts?")[0]["section"], "S02")

    def test_field_boost_section_match(self):
        top = jc.bm25_search(self.index, "leakage audit task status")
        self.assertEqual(top[0]["section"], "milestones › M5 › tasks › M5.3")

    def test_alias_retrieval(self):
        top = jc.bm25_search(self.index, "Which carriers: Frontier?")
        self.assertEqual(top[0]["path"], "docs/carriers.md")

    def test_bm25_no_terms(self):
        self.assertEqual(jc.bm25_search(self.index, "the of and"), [])

    def test_stale_detection(self):
        self.assertEqual(jc.stale_files(self.manifest, self.root), [])
        (self.root / "CLAUDE.md").write_text("changed")
        self.assertEqual(jc.stale_files(self.manifest, self.root), ["CLAUDE.md"])


class Diversify(unittest.TestCase):
    def test_one_file_cannot_take_every_slot(self):
        chunks = {i: {"id": i, "path": "big.json" if i < 10 else f"r{i}.md"} for i in range(16)}
        scored = [(100 - i, i) for i in range(10)] + [(50 - i, 10 + i) for i in range(6)]
        picked = jc.diversify(scored, chunks, k=8)
        self.assertEqual(len(picked), 8)
        self.assertEqual(sum(c["path"] == "big.json" for c in picked), jc.MAX_PER_FILE)
        self.assertEqual(picked[0]["id"], 0)

    def test_fill_when_only_capped_file_left(self):
        chunks = {i: {"id": i, "path": "big.json" if i < 10 else "r.md"} for i in range(11)}
        scored = [(100 - i, i) for i in range(10)] + [(1, 10)]
        picked = jc.diversify(scored, chunks, k=8)
        self.assertEqual(len(picked), 8)
        self.assertIn(10, [c["id"] for c in picked])
        self.assertEqual([c["id"] for c in picked][:3], [0, 1, 2])

    def test_fewer_candidates(self):
        chunks = {0: {"id": 0, "path": "a"}, 1: {"id": 1, "path": "a"}}
        self.assertEqual([c["id"] for c in jc.diversify([(2, 0), (1, 1)], chunks)], [0, 1])


def C(path, section, text):
    return {"path": path, "section": section, "text": text}


class Quotes(unittest.TestCase):
    chunks = [C("docs/plan.md", "Plan > Data", "The final dataset has 7,121,934 flights.\nThe pilot had 538,837 rows."),
              C("docs/rules.md", "Rules", "Features must be known 24 hours before departure.")]

    def test_verbatim_quotes_kept_others_rejected(self):
        raw = json.dumps({"quotes": [{"chunk": 1, "quote": "the final dataset has 7,121,934  flights"},
                                     {"chunk": 2, "quote": "Features are known 48 hours early"},
                                     {"chunk": 9, "quote": "x"}, {"chunk": "[2]", "quote": "known 24 hours"},
                                     "junk"]})
        q, rejected = jc.parse_quotes(raw, self.chunks)
        self.assertEqual([x["n"] for x in q], [1, 2])
        self.assertEqual(rejected, 3)

    def test_quote_dash_normalization_and_wrapped_json(self):
        chunks = [C("a.md", "A", "cutoff T−24h for every flight")]
        q, _ = jc.parse_quotes('Here: {"quotes": [{"chunk": 1, "quote": "cutoff T-24h"}]}', chunks)
        self.assertEqual(len(q), 1)

    def test_bad_json(self):
        self.assertEqual(jc.parse_quotes("not json", self.chunks), ([], 0))


class Guards(unittest.TestCase):
    chunks = Quotes.chunks
    quotes = [{"n": 1, "quote": "The final dataset has 7,121,934 flights."},
              {"n": 2, "quote": "Features must be known 24 hours before departure."}]

    def g(self, answer, quotes=quotes):
        return jc.apply_guards("q?", answer, self.chunks, "fake", quotes)

    def test_good_answer(self):
        r = self.g("The final dataset has 7,121,934 flights [1].")
        self.assertFalse(r["refused"])
        self.assertEqual(r["unsupported_numbers"], [])
        self.assertEqual(r["citations"], [{"n": 1, "path": "docs/plan.md", "section": "Plan > Data"}])
        for k in ("question", "answer", "citations", "refused", "unsupported_numbers", "model"):
            self.assertIn(k, r)

    def test_unsupported_number_removed_and_marked(self):
        r = self.g("The final dataset has 7,500,000 flights [1].")
        self.assertEqual(r["unsupported_numbers"], ["7500000"])
        self.assertNotIn("7,500,000", r["answer"])
        self.assertIn(jc.REMOVED, r["answer"])
        self.assertTrue(r["answer"].endswith("(unverified)"))

    def test_number_in_chunk_but_not_in_cited_quote_removed(self):
        r = self.g("The pilot had 538,837 rows [1].")   # in chunk 1 text, not in its quote
        self.assertEqual(r["unsupported_numbers"], ["538837"])

    def test_number_must_be_in_cited_quote_not_other_quote(self):
        r = self.g("Features need 7,121,934 hours [2].")
        self.assertIn("7121934", r["unsupported_numbers"])

    def test_citation_to_unquoted_chunk_invalid(self):
        r = self.g("Rule [2].", quotes=[self.quotes[0]])
        self.assertTrue(r["refused"])
        self.assertEqual(r["invalid_citations"], [2])

    def test_ids_not_treated_as_numbers(self):
        r = self.g("G12 and M5.3 are listed [1].")
        self.assertEqual(r["unsupported_numbers"], [])

    def test_no_citation_refused(self):
        r = self.g("The dataset has 7,121,934 flights.")
        self.assertTrue(r["refused"])
        self.assertEqual(r["answer"], jc.REFUSAL)
        self.assertEqual(r["citations"], [])

    def test_invalid_citation_removed(self):
        r = self.g("It has 7,121,934 flights [1][42].")
        self.assertEqual([c["n"] for c in r["citations"]], [1])
        self.assertEqual(r["invalid_citations"], [42])
        self.assertNotIn("[42]", r["answer"])

    def test_grouped_citation_and_citation_digits_not_claims(self):
        r = self.g("Known 24 hours before departure; 7,121,934 flights [2, 1].")
        self.assertEqual([c["n"] for c in r["citations"]], [2, 1])
        self.assertEqual(r["unsupported_numbers"], [])

    def test_refusal_exact(self):
        self.assertTrue(self.g(jc.REFUSAL)["refused"])

    def test_refusal_mixed_with_other_text(self):
        for txt in (f"The dataset has 7,121,934 flights [1]. {jc.REFUSAL}",
                    "Partly: 24 hours [2]. I don't know - it isn't in the project files.",
                    "I don't know the accuracy [1]."):
            r = self.g(txt)
            self.assertTrue(r["refused"], txt)
            self.assertEqual(r["answer"], jc.REFUSAL)
            self.assertEqual(r["citations"], [])

    def test_single_step_mode_uses_chunk(self):
        r = jc.apply_guards("q?", "The pilot had 538,837 rows [1].", self.chunks, "fake", None)
        self.assertEqual(r["unsupported_numbers"], [])


class TwoStep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_tree(self.root)
        self.index, _ = jc.build_index(self.root)
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, quotes_reply, answer_reply):
        def llm(messages, json_mode=False):
            self.calls.append((json_mode, messages))
            return quotes_reply if json_mode else answer_reply
        return llm

    def ask(self, q, quotes_reply, answer_reply):
        return jc.answer_question(q, self.index, self.fake(quotes_reply, answer_reply), "fake-model")

    def quote_for(self, q, needle):
        top = jc.bm25_search(self.index, q)
        n = next(i for i, c in enumerate(top, 1) if needle in c["text"])
        return n, json.dumps({"quotes": [{"chunk": n, "quote": needle}]})

    def test_two_calls_and_answer_from_quotes(self):
        q = "How many flights are in the final dataset?"
        n, qr = self.quote_for(q, "The final dataset has 7,121,934 flights")
        r = self.ask(q, qr, f"The final dataset has 7,121,934 flights [{n}].")
        self.assertFalse(r["refused"])
        self.assertEqual([c["path"] for c in r["citations"]], ["docs/plan.md"])
        self.assertEqual([j for j, _ in self.calls], [True, False])
        step1 = self.calls[0][1]
        self.assertIn("prefer full-dataset totals", step1[0]["content"].lower())
        step2 = self.calls[1][1]
        self.assertIn("QUOTES:", step2[1]["content"])
        self.assertIn("7,121,934", step2[1]["content"])
        self.assertNotIn("538,837", step2[1]["content"])   # only quotes go to step 2
        self.assertIn("scope", step2[0]["content"])
        self.assertEqual(r["quotes"][0]["n"], n)
        trace = {}
        jc.answer_question(q, self.index, self.fake(qr, f"x [{n}]."), "fake", trace)
        self.assertEqual(set(trace), {"retrieved", "raw_quotes", "raw_answer"})

    def test_no_quotes_refuses_without_second_call(self):
        r = self.ask("What is the model's accuracy on these flights?", '{"quotes": []}', "should not be used [1]")
        self.assertTrue(r["refused"])
        self.assertEqual(len(self.calls), 1)

    def test_fabricated_quotes_refuse(self):
        r = self.ask("How many flights are in the final dataset?",
                     '{"quotes": [{"chunk": 1, "quote": "accuracy is 91%"}]}', "Accuracy is 91% [1].")
        self.assertTrue(r["refused"])
        self.assertEqual(r["rejected_quotes"], 1)
        self.assertEqual(len(self.calls), 1)

    def test_no_retrieval_no_model_call(self):
        r = self.ask("the of and", "{}", "x [1]")
        self.assertTrue(r["refused"])
        self.assertEqual(self.calls, [])

    def test_step2_refusal_mixed_text(self):
        q = "How many flights are in the final dataset?"
        n, qr = self.quote_for(q, "The final dataset has 7,121,934 flights")
        r = self.ask(q, qr, f"It has 7,121,934 flights [{n}]. {jc.REFUSAL}")
        self.assertTrue(r["refused"])
        self.assertEqual(r["citations"], [])

    def test_llm_error_propagates(self):
        def boom(messages, json_mode=False):
            raise OSError("connection refused")
        with self.assertRaises(OSError):
            jc.answer_question("How many flights?", self.index, boom, "fake")


if __name__ == "__main__":
    unittest.main()
