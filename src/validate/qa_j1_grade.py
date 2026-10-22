"""QA grader for J1 (Jarvis project brain). QA's own code, standard library only.

Runs src/jarvis/ask.py --json as a black box for each question in docs/office/jarvis/j1_testset.json,
saves raw outputs to data/jarvis/qa_raw/Qxx.json, grades all saved outputs, and writes
reports/j1_eval.json + reports/j1_eval.md.

Usage (project root):
  python3 -I src/validate/qa_j1_grade.py                 # ask all 30, then grade
  python3 -I src/validate/qa_j1_grade.py --start 1 --end 10   # ask Q01..Q10 only, then grade every saved output
  python3 -I src/validate/qa_j1_grade.py --grade-only    # no ask.py calls; grade saved outputs
  python3 -I src/validate/qa_j1_grade.py --testset docs/office/jarvis/j1_testset_holdout.json --out reports/j1_eval_r1_holdout
      # other test set; raw outputs go to data/jarvis/qa_raw_<set name>/; pass mark defaults to ceil(0.9*n) (27 for 30)
  --raw-dir DIR and --pass-min N override the defaults.

Rules (fixed before results, from the work order section 4 and the coordinator's brief):
- answerable: correct = every expected fact present in the answer (nested list = any variant; case-insensitive;
  commas inside numbers ignored) AND at least one cited path is in the question's sources.
- unanswerable: correct = refused is true and there is no error.
- fabricated number: a number in the answer (citation markers [n] removed) that is not found in the text of any
  cited chunk (looked up in data/jarvis/index.json by path + section; all chunks sharing that path + section are used).
- secrets: occurrences of sb_secret_ | service_role | eyJ | BEGIN PRIVATE KEY in data/jarvis/index.json.
- verdict PASS = correct >= 27/30 AND 0 fabricated numbers AND 0 secrets.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTSET = os.path.join(ROOT, "docs", "office", "jarvis", "j1_testset.json")
INDEX = os.path.join(ROOT, "data", "jarvis", "index.json")
ASK = os.path.join(ROOT, "src", "jarvis", "ask.py")
RAW_DIR = os.path.join(ROOT, "data", "jarvis", "qa_raw")
OUT_JSON = os.path.join(ROOT, "reports", "j1_eval.json")
OUT_MD = os.path.join(ROOT, "reports", "j1_eval.md")
SECRET_PATTERNS = ["sb_secret_", "service_role", "eyJ", "BEGIN PRIVATE KEY"]
TIMEOUT_S = 300
PASS_MIN = 27
BRAIN = None  # passed to ask.py as --brain <id> when set
SEARCH = None  # passed to ask.py as --search <mode> when set (bm25 | agentic)
OUTSIDE_RX = re.compile(r"(^|[\s='\"(])(/|~)|\.\.(/|$|\s)|\$\(|\$\{|\$[A-Za-z_]|`|<<")


def qa_audit_check(log_path):
    """QA's own look at an audit log: verdict/violations as recorded, plus an independent scan of the commands
    for absolute paths, ~, .., $VAR/$(…), backticks, heredocs."""
    p = log_path if os.path.isabs(log_path) else os.path.join(ROOT, log_path)
    if not os.path.exists(p):
        return {"log": log_path, "found": False}
    with open(p, encoding="utf-8") as f:
        a = json.load(f)
    cmds = a.get("commands") or []
    suspicious = [c for c in cmds if OUTSIDE_RX.search(c)]
    return {"log": os.path.relpath(p, ROOT), "found": True, "verdict": a.get("verdict"),
            "violations": a.get("violations") or [], "n_commands": len(cmds), "qa_suspicious_commands": suspicious}

NUM_RE = re.compile(r"(?<![A-Za-z0-9_])\d+(?:,\d{3})*(?:\.\d+)?")
CITE_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def utc_now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_text(s):
    s = s.lower()
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    return s


def numbers_in(s):
    out = set()
    for m in NUM_RE.findall(s):
        out.add(m.replace(",", ""))
    return out


def same_number(a, b):
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def load_testset(path=None):
    with open(path or TESTSET, encoding="utf-8") as f:
        ts = json.load(f)  # raises on a JSON error
    qs = ts["questions"]
    ids = [q["id"] for q in qs]
    if len(set(ids)) != len(ids):
        raise SystemExit("duplicate question ids in test set")
    return qs


def run_ask(q):
    t0 = time.time()
    try:
        cmd = [sys.executable, "-I", ASK, q["question"], "--json"] + (["--brain", BRAIN] if BRAIN else []) + \
              (["--search", SEARCH] if SEARCH else [])
        p = subprocess.run(cmd, cwd=ROOT,
                           capture_output=True, text=True, timeout=TIMEOUT_S)
        secs = round(time.time() - t0, 1)
        rec = {"id": q["id"], "exit": p.returncode, "stdout": p.stdout, "stderr": p.stderr[-4000:], "seconds": secs}
    except subprocess.TimeoutExpired:
        rec = {"id": q["id"], "exit": None, "stdout": "", "stderr": f"timeout after {TIMEOUT_S} s",
               "seconds": round(time.time() - t0, 1)}
    rec["ran_at"] = utc_now()
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(os.path.join(RAW_DIR, q["id"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return rec


def load_index():
    with open(INDEX, encoding="utf-8") as f:
        raw = f.read()
    idx = json.loads(raw)
    by_key = {}
    for c in idx["chunks"]:
        by_key.setdefault((c["path"], c["section"]), []).append(c["text"])
    secrets = {p: raw.count(p) for p in SECRET_PATTERNS}
    return by_key, secrets, idx.get("built_at")


def fact_present(answer_n, fact):
    variants = fact if isinstance(fact, list) else [fact]
    return any(norm_text(v) in answer_n for v in variants)


def grade_one(q, rec, by_key):
    res = {"id": q["id"], "type": q["type"], "question": q["question"], "correct": False, "reason": "",
           "answer": None, "citations": [], "refused": None, "fabricated_numbers": [],
           "unsupported_numbers_reported": [], "seconds": None, "error": None}
    if rec is None:
        res["reason"] = "not run"
        return res
    res["seconds"] = rec.get("seconds")
    out = None
    if rec.get("stdout", "").strip():
        try:
            out = json.loads(rec["stdout"])
        except json.JSONDecodeError:
            out = None
    if rec.get("exit") != 0 or out is None:
        res["error"] = f"exit={rec.get('exit')}; stderr: {rec.get('stderr', '')[-300:].strip()}"
        res["reason"] = "error from ask.py: " + res["error"]
        return res
    if out.get("error"):
        res["error"] = str(out["error"])
    answer = out.get("answer") or ""
    cits = out.get("citations") or []
    res.update(answer=answer, citations=cits, refused=bool(out.get("refused")),
               unsupported_numbers_reported=out.get("unsupported_numbers") or [],
               removed_numbers=answer.count("[number removed]"),
               brain_used=out.get("brain"), brains_tried=out.get("brains_tried"), fallbacks=out.get("fallbacks"),
               seconds_per_brain=out.get("seconds_per_brain"), search=out.get("search"))
    # agentic audit: logs of the answer itself and of every rejected/fallen-back attempt
    logs = []
    au = out.get("audit")
    if isinstance(au, dict) and au.get("log"):
        logs.append(("answer", au["log"]))
    elif isinstance(au, list):
        logs += [("answer", x.get("log")) for x in au if isinstance(x, dict) and x.get("log")]
    for fb in out.get("fallbacks") or []:
        if isinstance(fb, dict) and fb.get("audit_log"):
            logs.append(("fallback", fb["audit_log"]))
    res["audit_checks"] = [dict(qa_audit_check(lp), role=role) for role, lp in logs]
    res["rejected_by_audit"] = sum(1 for fb in (out.get("fallbacks") or [])
                                   if isinstance(fb, dict) and "outside" in str(fb.get("rejected_reason", "")))
    # an accepted answer must come from an attempt whose audit is clean
    res["accepted_with_outside_access"] = any(
        c.get("role") == "answer" and c.get("found") and (c.get("violations") or c.get("qa_suspicious_commands")
                                                          or c.get("verdict") not in ("accepted",))
        for c in res["audit_checks"])
    # a single-brain run must be answered by that brain; a fallback answer is not that brain's answer
    if BRAIN and BRAIN not in ("auto", "council") and out.get("brain") not in (None, BRAIN):
        res["error"] = f"answered by {out.get('brain')!r}, not {BRAIN!r} (fallbacks: {out.get('fallbacks')})"

    # fabrication check (independent): numbers in the answer vs text of the cited chunks
    body = CITE_RE.sub(" ", answer)
    cited_text = []
    missing_chunks = []
    for c in cits:
        texts = by_key.get((c.get("path"), c.get("section")))
        if texts is None:
            # agentic citations name a corpus file (no index section): use that file's corpus copy as the cited text
            fp = os.path.join(ROOT, "data", "jarvis", "corpus", str(c.get("path", "")))
            if c.get("path") and os.path.isfile(fp) and os.path.realpath(fp).startswith(
                    os.path.realpath(os.path.join(ROOT, "data", "jarvis", "corpus")) + os.sep):
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    cited_text.append(fh.read())
                res.setdefault("cited_whole_corpus_file", []).append(c.get("path"))
            else:
                missing_chunks.append(f"{c.get('path')} :: {c.get('section')}")
        else:
            cited_text.extend(texts)
    cited_nums = numbers_in(norm_text("\n".join(cited_text)))
    if not res["refused"]:
        res["fabricated_numbers"] = sorted(n for n in numbers_in(body)
                                           if not any(same_number(n, m) for m in cited_nums))
    if missing_chunks:
        res["cited_chunks_not_in_index"] = missing_chunks

    if res["error"]:
        res["reason"] = "error field: " + res["error"]
        return res
    if not q["answerable"]:
        res["correct"] = res["refused"]
        res["reason"] = "refused as expected" if res["refused"] else "answered an unanswerable question (should refuse)"
        return res
    if res["refused"]:
        res["reason"] = "refused an answerable question"
        return res
    ans_n = norm_text(answer)
    missing = [f for f in q["expected_facts"] if not fact_present(ans_n, f)]
    cited_paths = {c.get("path") for c in cits}
    src_hit = bool(cited_paths & set(q["sources"]))
    res["missing_facts"] = missing
    res["source_cited"] = src_hit
    # Council "Brains disagree." rule (fixed before grading): correct only if EACH side (a and b) contains every
    # expected fact. If a side lacks a fact, the answer contradicts itself on the asked fact -> not correct.
    # 'compatible' = both sides contain every expected fact (the disagreement was not about the asked facts).
    if answer.strip().startswith("Brains disagree."):
        # sides are labelled "a:"/"b:" (README) or by brain id, e.g. "codex: … — opencode: …" (seen in output)
        m = re.match(r"\s*Brains disagree\.\s*([\w-]+):\s*(.*?)\s+—\s+([\w-]+):\s*(.*)$", answer, re.S)
        res["council_disagree"] = True
        if not m:
            res["council_compatible"] = False
            res["reason"] = "council 'Brains disagree.' answer could not be split into two sides"
            return res
        res["council_sides"] = [m.group(1), m.group(3)]
        side_ok = [all(fact_present(norm_text(s), f) for f in q["expected_facts"]) for s in (m.group(2), m.group(4))]
        res["council_compatible"] = all(side_ok)
        if all(side_ok) and src_hit:
            res["correct"] = True
            res["reason"] = "council disagree, but both sides contain every expected fact; expected source cited"
        else:
            res["reason"] = ("council disagree: side(s) " + ",".join(s for s, ok in zip("ab", side_ok) if not ok) +
                             " lack an expected fact" if not all(side_ok) else "council disagree; no expected source cited")
        return res
    if not missing and src_hit:
        res["correct"] = True
        res["reason"] = "all facts present; expected source cited"
    else:
        parts = []
        if missing:
            parts.append("missing facts " + json.dumps(missing, ensure_ascii=False))
        if not src_hit:
            parts.append("no expected source cited (cited: " + ", ".join(sorted(p for p in cited_paths if p)) + ")")
        res["reason"] = "; ".join(parts)
    return res


def write_reports(results, secrets, built_at):
    by_type = {}
    for r in results:
        t = by_type.setdefault(r["type"], [0, 0])
        t[1] += 1
        t[0] += 1 if r["correct"] else 0
    score = sum(1 for r in results if r["correct"])
    fab_total = sum(len(r["fabricated_numbers"]) for r in results)
    unsup_total = sum(len(r["unsupported_numbers_reported"]) for r in results)
    removed_total = sum(r.get("removed_numbers", 0) for r in results)
    disagree = [r["id"] for r in results if (r.get("answer") or "").strip().startswith("Brains disagree.")]
    compatible = [r["id"] for r in results if r.get("council_compatible")]
    fallback_used = [r["id"] for r in results if r.get("fallbacks")]
    rejected_audit = sum(r.get("rejected_by_audit", 0) for r in results)
    outside_accepted = [r["id"] for r in results if r.get("accepted_with_outside_access")]
    answered_agentic = sum(1 for r in results if r.get("search") == "agentic")
    n_logs = sum(len(r.get("audit_checks", [])) for r in results)
    sec_total = sum(secrets.values())
    not_run = [r["id"] for r in results if r["reason"] == "not run"]
    verdict = "PASS" if (score >= PASS_MIN and fab_total == 0 and sec_total == 0 and not not_run) else "FAIL"
    summary = {"graded_at": utc_now(), "grader": "src/validate/qa_j1_grade.py", "index_built_at": built_at,
               "score": score, "total": len(results), "by_type": {k: {"correct": v[0], "total": v[1]} for k, v in by_type.items()},
               "fabricated_numbers_total": fab_total, "unsupported_numbers_reported_total": unsup_total,
               "removed_numbers_total": removed_total,
               "council_disagree": disagree, "council_disagree_but_compatible": compatible,
               "answers_with_fallbacks": fallback_used, "search": SEARCH or "(ask.py default)",
               "rejected_by_audit_total": rejected_audit, "accepted_with_outside_access": outside_accepted,
               "answers_from_agentic_search": answered_agentic, "audit_logs_checked": n_logs,
               "council_rule": "'Brains disagree.' counts as correct only if EACH side (a and b) contains every expected "
                               "fact (and an expected source is cited); a side missing a fact = contradicting itself on "
                               "the asked fact = not correct; for an unanswerable question it is not a refusal = not correct",
               "secret_counts": secrets, "secrets_total": sec_total, "not_run": not_run,
               "testset": os.path.relpath(TESTSET, ROOT), "brain": BRAIN or "(ask.py default)",
               "seconds_total": round(sum(r["seconds"] or 0 for r in results), 1),
               "seconds_mean": round(sum(r["seconds"] or 0 for r in results) / max(1, sum(1 for r in results if r["seconds"])), 1),
               "pass_rule": f">= {PASS_MIN}/{len(results)} correct, 0 fabricated numbers, 0 secrets", "verdict": verdict}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=1)

    L = ["# J1 evaluation (QA, independent)", "",
         f"Graded {summary['graded_at']} by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). "
         f"Test set: `{os.path.relpath(TESTSET, ROOT)}`. Index built_at {built_at}. Detail: `{os.path.relpath(OUT_JSON, ROOT)}`.", "",
         f"## Verdict: **{verdict}**", "",
         f"Rule: {summary['pass_rule']}." + (f" Council rule: {summary['council_rule']}." if BRAIN == "council" else "")
         + (" Single-brain run: an answer produced by a different (fallback) brain is counted as an error." if BRAIN and BRAIN not in ("auto", "council") else ""), "",
         "| Item | Result |", "|---|---|",
         f"| Brain | {summary['brain']} |",
         f"| Time per question (mean / total s) | {summary['seconds_mean']} / {summary['seconds_total']} |",
         f"| Score | {score}/{len(results)} |"]
    for k in ("single", "multi", "unanswerable"):
        if k in by_type:
            L.append(f"| {k} | {by_type[k][0]}/{by_type[k][1]} |")
    L += [f"| Fabricated numbers (QA check vs cited chunk text) | {fab_total} |",
          f"| unsupported_numbers reported by ask.py | {unsup_total} |",
          f"| Numbers removed by the guard ('[number removed]' left in answers) | {removed_total} |",
          f"| Answers that used a fallback brain | {len(fallback_used)} {fallback_used if fallback_used else ''} |",
          f"| Search mode / answers produced by agentic search | {summary['search']} / {answered_agentic} |",
          f"| Attempts rejected by the access audit | {rejected_audit} |",
          f"| Audit logs checked by QA / accepted answers with outside access | {n_logs} / {len(outside_accepted)} {outside_accepted if outside_accepted else ''} |",
          f"| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | "
          f"{len(disagree)} / {len(compatible)} {disagree if disagree else ''} |",
          f"| Secrets in data/jarvis/index.json | {sec_total} ({', '.join(f'{k}: {v}' for k, v in secrets.items())}) |"]
    if not_run:
        L.append(f"| Not run | {', '.join(not_run)} |")
    L += ["", "## Failures", ""]
    fails = [r for r in results if not r["correct"]]
    if not fails:
        L.append("None.")
    for r in fails:
        L.append(f"- **{r['id']}** ({r['type']}) {r['question']} — {r['reason']}")
    fabs = [r for r in results if r["fabricated_numbers"]]
    L += ["", "## Fabricated numbers", ""]
    if not fabs:
        L.append("None.")
    for r in fabs:
        L.append(f"- **{r['id']}**: {', '.join(r['fabricated_numbers'])} (not in any cited chunk's text)")
    L += ["", "## Per question", "", "| id | type | correct | s | reason |", "|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['id']} | {r['type']} | {'yes' if r['correct'] else 'no'} | {r['seconds']} | {r['reason'].replace('|', '/')} |")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return summary


def main():
    global RAW_DIR, OUT_JSON, OUT_MD, PASS_MIN, TESTSET, BRAIN, SEARCH
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", default=None, help="passed through to ask.py as --search <mode> (bm25 | agentic)")
    ap.add_argument("--brain", default=None, help="passed through to ask.py as --brain <id> (e.g. local, codex, opencode, council)")
    ap.add_argument("--timeout", type=int, default=None, help="seconds per ask.py call (default 300)")
    ap.add_argument("--testset", default=None, help="test set JSON path (default docs/office/jarvis/j1_testset.json)")
    ap.add_argument("--out", default=None, help="report path prefix, e.g. reports/j1_eval_r1 (writes .json + .md)")
    ap.add_argument("--raw-dir", default=None, help="folder for raw ask.py outputs (default data/jarvis/qa_raw[_<set name>])")
    ap.add_argument("--pass-min", type=int, default=None, help="correct answers needed (default 27 for 30; else ceil(0.9*n))")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=10**6)
    ap.add_argument("--grade-only", action="store_true")
    a = ap.parse_args()
    global TIMEOUT_S
    BRAIN = a.brain
    SEARCH = a.search
    if a.timeout:
        TIMEOUT_S = a.timeout
    if a.testset:
        TESTSET = os.path.abspath(os.path.join(ROOT, a.testset))
    name = os.path.splitext(os.path.basename(TESTSET))[0]
    if a.raw_dir:
        RAW_DIR = os.path.abspath(os.path.join(ROOT, a.raw_dir))
    elif name != "j1_testset" or BRAIN or SEARCH:
        RAW_DIR = os.path.join(ROOT, "data", "jarvis", "qa_raw_" + name + (f"_{BRAIN}" if BRAIN else "")
                               + (f"_{SEARCH}" if SEARCH else ""))
    if a.out:
        base = os.path.abspath(os.path.join(ROOT, a.out))
        OUT_JSON, OUT_MD = base + ".json", base + ".md"
    qs = load_testset(TESTSET)
    PASS_MIN = a.pass_min if a.pass_min is not None else (27 if len(qs) == 30 else -(-9 * len(qs) // 10))
    print(f"test set parsed: {len(qs)} questions ({os.path.relpath(TESTSET, ROOT)}); raw -> {os.path.relpath(RAW_DIR, ROOT)}; "
          f"reports -> {os.path.relpath(OUT_JSON, ROOT)} / .md; pass >= {PASS_MIN}", flush=True)
    if not a.grade_only:
        for i, q in enumerate(qs, 1):
            if a.start <= i <= a.end:
                rec = run_ask(q)
                print(f"{q['id']} exit={rec['exit']} {rec['seconds']}s", flush=True)
    by_key, secrets, built_at = load_index()
    results = []
    for q in qs:
        p = os.path.join(RAW_DIR, q["id"] + ".json")
        rec = None
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
        results.append(grade_one(q, rec, by_key))
    s = write_reports(results, secrets, built_at)
    print(json.dumps({k: s[k] for k in ("score", "by_type", "fabricated_numbers_total", "secrets_total", "not_run", "verdict")}))


if __name__ == "__main__":
    main()
