"""QA J1 round 3 (docs/office/jarvis/j1_round3_agentic.md §2): retrieval-recall diagnosis + source-list audit.
QA's own code, standard library only; src/jarvis/ask.py is used only as a black box (`--search`, no model call).

  python3 -I src/validate/qa_j1_recall.py --recall      # top-8 recall for all 50 questions -> reports/j1_r3_recall.json/.md
  python3 -I src/validate/qa_j1_recall.py --sources     # list, per question, every allowed file that holds the facts
  python3 -I src/validate/qa_j1_recall.py --sources --apply   # add them to the three test sets (+ change_log)

Fact matching: case-insensitive, commas inside numbers ignored, word boundaries around alphanumeric ends
(so "43" does not match "143"). Source audit: a file "holds" a fact when a line contains the fact AND a
question-specific context term within +/-6 lines (QA judgement, listed in CONTEXT below), so generic tokens
such as "59" or "S02" are not counted where they mean something else.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETS = ["docs/office/jarvis/j1_testset.json", "docs/office/jarvis/j1_testset_holdout.json",
        "docs/office/jarvis/j1_testset_holdout2.json"]
R2 = {"docs/office/jarvis/j1_testset.json": "reports/j1_eval_r2_codex.json",
      "docs/office/jarvis/j1_testset_holdout.json": "reports/j1_eval_r2_codex_holdout.json",
      "docs/office/jarvis/j1_testset_holdout2.json": "reports/j1_eval_r2_codex_holdout2.json"}
ASK = os.path.join(ROOT, "src", "jarvis", "ask.py")
INDEX = os.path.join(ROOT, "data", "jarvis", "index.json")
OUT_JSON = os.path.join(ROOT, "reports", "j1_r3_recall.json")
OUT_MD = os.path.join(ROOT, "reports", "j1_r3_recall.md")
EVAL_EXCL = re.compile(r"^(reports/j1_eval|reports/j2_check|reports/j5_check|reports/j1_r3_recall|docs/office/jarvis/j1_testset)")

# question id -> {fact index: context regex}; missing entry = no context needed (distinctive fact)
CONTEXT = {
    "Q01": {0: r"dataset|flightops_g1_g12|g1–g12|g1-g12"}, "Q02": {0: r"step 6|leakage|m5"},
    "Q03": {0: r"predictor|feature"}, "Q04": {0: r"cancel"}, "Q05": {0: r"divert"},
    "Q07": {0: r"scheduled departure|cutoff|known", 1: r"24"}, "Q08": {0: r"predictor", 1: r"predictor", 2: r"predictor"},
    "Q09": {0: r"atcscc|advisor"}, "Q10": {0: r"\bg7\b"}, "Q11": {0: r"\bg2\b|bag"},
    "Q12": {0: r"\bg8\b|weather|forecast", 1: r"\bg8\b|weather|forecast|mos"}, "Q13": {0: r"nasr"},
    "Q14": {0: r"delay rate|completed"}, "Q15": {1: r"auc"}, "Q16": {0: r"territor"}, "Q17": {0: r"airport"},
    "Q18": {0: r"duckdb"}, "Q19": {0: r"dc-2|dc2|duckdb", 1: r"pass"}, "Q21": {0: r"master|f9\+ua\+wn|sum of"},
    "Q22": {0: r"9e|endeavor", 1: r"9e|endeavor"}, "Q23": {0: r"cutoff|run|issued"}, "Q25": {0: r"\bg3\b", 1: r"f9|\bg3\b"},
    "H04": {0: r"\bua\b|age"}, "H05": {0: r"duckdb|memory|duck"}, "H07": {1: r"on-time|prezip"},
    "H08": {1: r"\bg3\b|t-100"}, "K03": {0: r"mismatch|cross-check|arrival"}, "K04": {0: r"pass"},
    "K05": {0: r"tail"}, "K06": {0: r"airport|openflights", 1: r"airport"}, "K07": {2: r"9e|endeavor"},
    "K08": {0: r"tsa", 1: r"tsa", 2: r"\bg3\b"},
}
EXTRA_CONTEXT_FILES = {"K04": r"dc-1|dc1"}  # file-level context: the file must mention this too
# QA manual review: candidate files whose matching line is about something else (filled after reading the snippets)
REJECT = {
    # Q01 "final dataset": lines about other tables (factor tables, contracts, master, curated set) are not the final dataset
    "Q01": ["artifacts/decisions/D-dc1-signoff-dc2.json", "artifacts/decisions/D-next-after-floor2.json",
            "artifacts/decisions/D-step6-integration.json", "reports/dc1_qa.json", "reports/dc2_qa.md"],
    "Q03": ["docs/office/jarvis/jarvis_plan.md"],  # "Features (59)" = galaxy node plan, not the dataset statement
    # Q21 half 1 = master row count: lines about the Step 5 tables, Step 6 outputs or a requirement are not the master count
    "Q21": ["artifacts/decisions/D-step6-integration.json", "artifacts/decisions/D-step6-signoff.json",
            "docs/office/step6_work_order.md", "reports/m3_feature_qa.md", "reports/m5_leakage_audit.md"],
    "Q22": ["docs/office/issues/B2_directive39.md"],  # asks whether the sentence exists; does not state the cause
    "H05": ["artifacts/decisions/D-dc-duckdb.json"],  # proposal example "(e.g. 4 GB)" per job, not the built cap
    "H07": ["docs/registry/data_dictionary.csv"],  # G4 row lists S02 as an input; does not say what S02 is
}


def norm(s):
    return re.sub(r"(?<=\d),(?=\d)", "", str(s).lower())


def fact_rx(v):
    v = norm(v)
    pre = r"(?<![a-z0-9.])" if re.match(r"[a-z0-9]", v) else ""
    post = r"(?![a-z0-9])" if re.search(r"[a-z0-9]$", v) else ""
    return re.compile(pre + re.escape(v) + post)


def variants(f):
    return f if isinstance(f, list) else [f]


def fact_in(text_n, f):
    return any(fact_rx(v).search(text_n) for v in variants(f))


def load_set(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)


# ---------- 1. recall ----------
def search(question):
    p = subprocess.run([sys.executable, "-I", ASK, question, "--search"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    sel = []
    for ln in p.stdout.splitlines():
        m = re.match(r"\*\s+([\d.]+)\s+(\S+) § (.*)$", ln)
        if m:
            sel.append((m.group(2), m.group(3).rstrip()))
    return sel, p.returncode


def recall():
    with open(INDEX, encoding="utf-8") as f:
        idx = json.load(f)
    by_path = {}
    for c in idx["chunks"]:
        by_path.setdefault(c["path"], []).append(c)
    all_text = {c["id"]: norm(c["text"]) for c in idx["chunks"]}
    rows = []
    for sp in SETS:
        qs = load_set(sp)["questions"]
        r2 = {}
        rp = os.path.join(ROOT, R2[sp])
        if os.path.exists(rp):
            with open(rp, encoding="utf-8") as f:
                r2 = {r["id"]: r for r in json.load(f)["results"]}
        for q in qs:
            sel, rc = search(q["question"])
            texts, unresolved = [], []
            for path, sec in sel:
                cands = [c for c in by_path.get(path, []) if c["section"] == sec or c["section"].startswith(sec)]
                if not cands:
                    unresolved.append(f"{path} § {sec}")
                texts.extend(norm(c["text"]) for c in cands)
            facts = []
            for k, f in enumerate(q["expected_facts"]):
                ctx = CONTEXT.get(q["id"], {}).get(k)
                cre = re.compile(ctx) if ctx else None
                # a chunk counts only if it holds the fact AND (for generic facts) the same context term as the source audit
                hit = lambda t: fact_in(t, f) and (cre is None or bool(cre.search(t)))  # noqa: E731
                facts.append({"fact": f, "in_top8": any(hit(t) for t in texts),
                              "in_top8_without_context_rule": any(fact_in(t, f) for t in texts),
                              "in_index": any(hit(t) for t in all_text.values())})
            r = r2.get(q["id"], {})
            rows.append({"set": os.path.basename(sp), "id": q["id"], "type": q["type"], "answerable": q["answerable"],
                         "selected": [f"{p} § {s}" for p, s in sel], "n_selected": len(sel), "unresolved": unresolved,
                         "facts": facts, "all_facts_in_top8": all(x["in_top8"] for x in facts) if facts else None,
                         "r2_codex_correct": r.get("correct"), "r2_codex_reason": r.get("reason"), "search_exit": rc})
            print(q["id"], rows[-1]["all_facts_in_top8"], r.get("correct"), flush=True)
    return rows


def write_recall(rows):
    ans = [r for r in rows if r["answerable"]]
    fails = [r for r in ans if r["r2_codex_correct"] is False]
    fail_missing = [r for r in fails if not r["all_facts_in_top8"]]
    fail_present = [r for r in fails if r["all_facts_in_top8"]]
    ok_missing = [r for r in ans if r["r2_codex_correct"] and not r["all_facts_in_top8"]]
    full = sum(1 for r in ans if r["all_facts_in_top8"])
    fact_total = sum(len(r["facts"]) for r in ans)
    fact_hit = sum(sum(x["in_top8"] for x in r["facts"]) for r in ans)
    not_in_index = [(r["id"], x["fact"]) for r in ans for x in r["facts"] if not x["in_index"]]
    summary = {"checked_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "checker": "src/validate/qa_j1_recall.py --recall", "mode": "ask.py --search (current BM25, no model)",
               "answerable": len(ans), "all_facts_in_top8": full, "fact_recall": f"{fact_hit}/{fact_total}",
               "r2_codex_failures": len(fails), "failures_fact_missing_from_top8": [r["id"] for r in fail_missing],
               "failures_fact_present_in_top8": [r["id"] for r in fail_present],
               "correct_although_fact_not_in_top8": [r["id"] for r in ok_missing],
               "facts_not_in_index_at_all": not_in_index,
               "unresolved_sections": sum(len(r["unresolved"]) for r in rows)}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "questions": rows}, f, ensure_ascii=False, indent=1)
    L = ["# J1 round 3 · retrieval recall diagnosis (QA)", "",
         f"Checked {summary['checked_at']} with `src/validate/qa_j1_recall.py --recall`: for each question, the 8 chunks "
         "`ask.py --search` marks as selected (`*`) were looked up in `data/jarvis/index.json` (path + section) and every "
         "expected fact was searched in their text (case-insensitive, commas ignored, word boundaries). Correctness = "
         "round-2 codex grade (`reports/j1_eval_r2_codex*.json`, original source lists).", "",
         "| Item | Result |", "|---|---|",
         f"| Answerable questions with every expected fact in the top 8 | {full}/{len(ans)} |",
         f"| Expected facts found in the top 8 | {summary['fact_recall']} |",
         f"| Round-2 codex failures (answerable) | {len(fails)} |",
         f"| … of which a fact was missing from the top 8 (retrieval) | {len(fail_missing)}: {', '.join(r['id'] for r in fail_missing) or '—'} |",
         f"| … of which every fact was in the top 8 (model / answer / source list) | {len(fail_present)}: {', '.join(r['id'] for r in fail_present) or '—'} |",
         f"| Correct although a fact was not in the top 8 | {len(ok_missing)}: {', '.join(r['id'] for r in ok_missing) or '—'} |",
         f"| Facts not in any index chunk | {len(not_in_index)} {not_in_index if not_in_index else ''} |",
         f"| Selected sections that could not be resolved in the index | {summary['unresolved_sections']} |", "",
         "## Per question", "", "| set | id | type | facts in top 8 | r2 codex | r2 reason |", "|---|---|---|---|---|---|"]
    for r in rows:
        fx = "n/a (unanswerable)" if not r["answerable"] else ", ".join(
            ("✓ " if x["in_top8"] else "✗ ") + json.dumps(x["fact"], ensure_ascii=False) for x in r["facts"])
        L.append(f"| {r['set'].replace('.json', '')} | {r['id']} | {r['type']} | {fx.replace('|', '/')} | "
                 f"{'yes' if r['r2_codex_correct'] else 'no'} | {(r['r2_codex_reason'] or '').replace('|', '/')[:140]} |")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return summary


# ---------- 2. source audit ----------
def allowed_files():
    pats = ["docs/**/*.md", "docs/registry/*.csv", "reports/*.md", "reports/*.json", "reports/*.csv",
            "artifacts/progress.json", "artifacts/decisions/*.json", "src/jarvis/README.md", "CLAUDE.md"]
    out = set()
    for p in pats:
        for f in glob.glob(os.path.join(ROOT, p), recursive=True):
            r = os.path.relpath(f, ROOT).replace(os.sep, "/")
            if EVAL_EXCL.match(r) or os.path.getsize(f) > 2 * 1024 * 1024:
                continue
            out.add(r)
    return sorted(out)


WINDOW = {"Q10": 6, "H04": 0}  # lines around the hit searched for the context term (default 0 = same line / same sentence)


def file_holds(lines_n, ftxt_n, qid, k, f):
    rx = [fact_rx(v) for v in variants(f)]
    ctx = CONTEXT.get(qid, {}).get(k)
    cre = re.compile(ctx) if ctx else None
    w = WINDOW.get(qid, 0)
    for i, ln in enumerate(lines_n):
        for r in rx:
            for m in r.finditer(ln):
                if cre is None:
                    return i + 1
                if w:
                    if any(cre.search(x) for x in lines_n[max(0, i - w): i + w + 1]):
                        return i + 1
                else:  # same sentence-ish: 160 chars either side of the hit
                    if cre.search(ln[max(0, m.start() - 160): m.end() + 160]):
                        return i + 1
    return None


def snippet(fp, line_no, f):
    with open(os.path.join(ROOT, fp), encoding="utf-8", errors="replace") as fh:
        ln = fh.read().splitlines()[line_no - 1]
    n = norm(ln)
    for v in variants(f):
        m = fact_rx(v).search(n)
        if m:
            return ln[max(0, m.start() - 90): m.end() + 60].replace("\n", " ")
    return ln[:150]


def sources_audit(apply=False):
    files = allowed_files()
    cache = {}
    for fp in files:
        with open(os.path.join(ROOT, fp), encoding="utf-8", errors="replace") as f:
            t = f.read()
        cache[fp] = (norm(t).splitlines(), norm(t))
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = []
    for sp in SETS:
        ts = load_set(sp)
        changes = []
        for q in ts["questions"]:
            if not q["answerable"]:
                continue
            per_fact = []
            for k, f in enumerate(q["expected_facts"]):
                hits = {}
                for fp in files:
                    lines_n, all_n = cache[fp]
                    if q["id"] in EXTRA_CONTEXT_FILES and not re.search(EXTRA_CONTEXT_FILES[q["id"]], all_n):
                        continue
                    ln = file_holds(lines_n, all_n, q["id"], k, f)
                    if ln:
                        hits[fp] = ln
                per_fact.append(hits)
            if q["type"] == "multi":
                holders = set().union(*[set(h) for h in per_fact])  # any half of a multi-file question
            else:
                holders = set.intersection(*[set(h) for h in per_fact]) if per_fact else set()  # all facts in one file
            new = sorted(holders - set(q["sources"]) - set(REJECT.get(q["id"], [])))
            ev = {}
            for fp in new:
                ev[fp] = [(f"L{h[fp]}: …" + snippet(fp, h[fp], q["expected_facts"][k]) + "…") if h.get(fp) else None
                          for k, h in enumerate(per_fact)]
            report.append({"set": os.path.basename(sp), "id": q["id"], "old": q["sources"], "added": new, "evidence": ev,
                           "rejected_by_review": REJECT.get(q["id"], [])})
            if new:
                changes.append(f"{q['id']} +{new}")
                if apply:
                    q["sources"] = q["sources"] + new
        if apply and changes:
            ts.setdefault("change_log", []).append({
                "date": now, "by": "qa", "round": "J1 round 3 (docs/office/jarvis/j1_round3_agentic.md §2.2)",
                "change": "sources widened only (questions and expected_facts unchanged): " + "; ".join(changes),
                "reason": "every allowed file (j1_work_order.md §2 allowlist minus eval material) grepped for each expected "
                          "fact with a question-specific context term (src/validate/qa_j1_recall.py CONTEXT); every file "
                          "that really holds the fact added. Single questions: file must hold all facts; multi: any fact."})
            with open(os.path.join(ROOT, sp), "w", encoding="utf-8") as f:
                json.dump(ts, f, ensure_ascii=False, indent=1)
                f.write("\n")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recall", action="store_true")
    ap.add_argument("--sources", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.recall:
        print(json.dumps(write_recall(recall()), ensure_ascii=False))
    if a.sources:
        rep = sources_audit(a.apply)
        for r in rep:
            for fp in r["added"]:
                print(r["id"], fp, "|", " || ".join(e for e in r["evidence"][fp] if e))
        print("questions with added sources:", sum(1 for r in rep if r["added"]), "of", len(rep), "(applied)" if a.apply else "(dry run)")


if __name__ == "__main__":
    main()
