"""Ask Jarvis a question about the project. Answers only from indexed project files, with citations.

Run from the project root:  python3 -I src/jarvis/ask.py "<question>" [--json] [--brain local|codex|opencode|auto|council]
Brains are configured in data/jarvis/brains.json (see brains.py). If no brain can answer: error, exit code 2.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_core as jc  # noqa: E402
import brains  # noqa: E402

TAGS = "http://127.0.0.1:11434/api/tags"


def list_models(timeout=10):
    """Names of the models installed in the local Ollama (read-only, /api/tags)."""
    with urllib.request.urlopen(TAGS, timeout=timeout) as r:
        return [m.get("name") for m in json.loads(r.read()).get("models", [])]


def load_index():
    if not jc.INDEX_FILE.is_file() or not jc.MANIFEST_FILE.is_file():
        raise FileNotFoundError("index missing - run: python3 -I src/jarvis/build_index.py")
    index = json.loads(jc.INDEX_FILE.read_text(encoding="utf-8"))
    manifest = json.loads(jc.MANIFEST_FILE.read_text(encoding="utf-8"))
    return index, manifest


def format_text(r):
    lines = [r["answer"]]
    if r["citations"]:
        lines.append("")
        lines.append("Sources:")
        lines += [f"  [{c['n']}] {c['path']} § {c['section']}" for c in r["citations"]]
    if r["unsupported_numbers"]:
        lines.append(f"Unsupported numbers (not in cited chunks): {', '.join(r['unsupported_numbers'])}")
    if r.get("brain") or r.get("model"):
        secs = ", ".join(f"{k} {v}s" for k, v in (r.get("seconds_per_brain") or {}).items())
        lines.append(f"Brain: {r.get('brain')} ({r.get('model')}){'; ' + secs if secs else ''}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ask Jarvis (project files only, with citations).")
    ap.add_argument("question", nargs="?")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--models", action="store_true", help="list the locally installed Ollama models and exit")
    ap.add_argument("--debug", action="store_true", help="print retrieved chunks and raw model output to stderr")
    ap.add_argument("--search", nargs="?", const="scores", default="bm25",
                    help="bm25 (default: shared top-8 chunks) | agentic (codex/opencode search data/jarvis/corpus "
                         "themselves, audited) | no value: retrieval only, print the scored BM25 pool, no model")
    ap.add_argument("--brain", default="auto",
                    help="local | codex | opencode | claude (disabled) | auto (default, order in data/jarvis/brains.json) | council")
    args = ap.parse_args(argv)
    if args.search not in ("bm25", "agentic", "scores"):
        if args.question is None:            # `--search "<question>"`: bare flag followed by the question
            args.question, args.search = args.search, "scores"
        else:
            ap.error("--search must be bm25 or agentic (or given without a value for the score listing)")
    if args.models:
        try:
            print("\n".join(list_models()))
            return 0
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f"ERROR: Ollama not reachable at {TAGS}: {e}", file=sys.stderr)
            return 2
    if not args.question:
        ap.error("question is required")
    try:
        index, manifest = load_index()
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if args.search == "scores":
        weights = jc.expand_query(list(dict.fromkeys(jc.tokenize(args.question))), index.get("aliases"))
        by_id = {c["id"]: c for c in index["chunks"]}
        print(f"query weights: {weights}")
        picked = {c["id"] for c in jc.bm25_search(index, args.question)}
        for s, cid in jc.bm25_scores(index, weights)[:jc.POOL_K]:
            c = by_id[cid]
            print(f"{'*' if cid in picked else ' '} {s:7.3f}  {c['path']} § {c['section'][:90]}")
        return 0
    stale = jc.stale_files(manifest, jc.FLIGHTOPS_ROOT)
    if stale:
        print(f"WARNING: index is stale - {len(stale)} file(s) changed since {manifest.get('built_at')}: "
              f"{', '.join(stale[:5])}{' ...' if len(stale) > 5 else ''}. Rebuild: python3 -I src/jarvis/build_index.py",
              file=sys.stderr)
    if args.search == "agentic":
        import corpus_build as cb
        try:
            cstale = cb.stale_sources(cb.load_manifest(), jc.FLIGHTOPS_ROOT)
        except (OSError, ValueError):
            cstale = ["(corpus missing - run: python3 -I src/jarvis/corpus_build.py)"]
        if cstale:
            print(f"WARNING: corpus is stale - {len(cstale)} file(s): {', '.join(cstale[:5])}"
                  f"{' ...' if len(cstale) > 5 else ''}. Rebuild: python3 -I src/jarvis/corpus_build.py", file=sys.stderr)
    trace = {}
    try:
        result = brains.ask(args.question, index, args.brain, brains.load_config(), trace=trace, search=args.search)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if args.debug:
        print("DEBUG " + brains.strip_tokens(json.dumps(trace, ensure_ascii=False, indent=1)), file=sys.stderr)
    if result.get("error"):
        reasons = "; ".join(f"{f['brain']}: {f['reason']}" for f in result.get("fallbacks", []))
        msg = f"no brain could answer ({reasons})"
        print(f"ERROR: {msg}", file=sys.stderr)
        if args.json:
            out = {"question": args.question, "error": msg, "answer": "", "citations": [], "refused": False,
                   "unsupported_numbers": [], "model": None}
            out.update({k: result.get(k) for k in ("brain", "brains_tried", "fallbacks", "seconds_per_brain")})
            print(json.dumps(out, ensure_ascii=False))
        return 2
    for f in result.get("fallbacks", []):
        print(f"NOTE: brain {f['brain']} skipped: {f['reason']}"
              + (f" (audit log {f['audit_log']})" if f.get("audit_log") else ""), file=sys.stderr)
    if result.get("invalid_citations"):
        print(f"WARNING: model cited chunks that do not exist (removed): {result['invalid_citations']}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=1) if args.json else format_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
