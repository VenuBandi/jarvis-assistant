"""Jarvis J1 round 3: corpus snapshot for agentic search (brains grep/open files themselves).

Copies ONLY the J1 allowlist (same rules and exclusions as build_index) into data/jarvis/corpus/, with progress.json
pruned like the index and every line matching a secret pattern replaced by "[removed: secret pattern]".
Manifest: data/jarvis/corpus/_corpus_manifest.json (sha256 of every source file and of its copy).

Run from the project root:  python3 -I src/jarvis/corpus_build.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_core as jc  # noqa: E402

CORPUS_DIR = jc.INDEX_DIR / "corpus"
MANIFEST_NAME = "_corpus_manifest.json"
SECRET_LINE = "[removed: secret pattern]"


def scrub(text):
    """Replace every line that matches a secret pattern. Returns (text, n_removed)."""
    out, n = [], 0
    for line in text.split("\n"):
        if jc.SECRET_RE.search(line):
            out.append(SECRET_LINE)
            n += 1
        else:
            out.append(line)
    return "\n".join(out), n


def snapshot_text(rel, raw):
    """Text written to the corpus for one allowlisted file (progress.json pruned). Returns (text, pruned_list)."""
    if rel == jc.PROGRESS:
        obj = json.loads(raw)
        pruned = jc.prune_progress(obj)
        return json.dumps(obj, ensure_ascii=False, indent=1) + "\n", pruned
    return raw, []


def build_corpus(root=jc.FLIGHTOPS_ROOT, corpus_dir=None):
    """Write the corpus and its manifest. Returns the manifest dict."""
    root = Path(root)
    corpus_dir = Path(corpus_dir) if corpus_dir else CORPUS_DIR
    corpus_dir.mkdir(parents=True, exist_ok=True)
    files, skipped_large, errors, total_bytes, total_secret = {}, [], [], 0, 0
    pruned_all = []
    for rel in jc.allowed_files(root):
        src = root / rel
        if src.stat().st_size > jc.MAX_FILE_BYTES:
            skipped_large.append(rel)
            continue
        raw = src.read_text(encoding="utf-8", errors="replace")
        try:
            text, pruned = snapshot_text(rel, raw)
        except ValueError as e:
            errors.append({"path": rel, "error": str(e)[:200]})
            continue
        pruned_all += pruned
        text, n_secret = scrub(text)
        dst = corpus_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        size = dst.stat().st_size
        total_bytes += size
        total_secret += n_secret
        files[rel] = {"source_sha256": jc.sha256_file(src), "copy_sha256": jc.sha256_file(dst), "bytes": size,
                      "secret_lines_removed": n_secret}
    # remove copies of files that are no longer in the allowlist (only inside the corpus folder)
    removed_stale = []
    for p in sorted(corpus_dir.rglob("*"), reverse=True):
        rel = p.relative_to(corpus_dir).as_posix()
        if p.is_file() and rel != MANIFEST_NAME and rel not in files:
            p.unlink()
            removed_stale.append(rel)
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    manifest = {"built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "files_copied": len(files), "total_bytes": total_bytes, "secret_lines_removed": total_secret,
                "skipped_large_files": skipped_large, "parse_errors": errors, "progress_pruned": pruned_all,
                "excluded_globs": list(jc.EXCLUDE_GLOBS), "removed_stale_copies": removed_stale, "files": files}
    (corpus_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def stale_sources(manifest, root=jc.FLIGHTOPS_ROOT):
    """Allowlisted source files whose sha differs from the corpus manifest, plus new/removed allowlist files."""
    root = Path(root)
    files = manifest.get("files", {})
    out = [rel for rel, m in files.items()
           if not (root / rel).is_file() or jc.sha256_file(root / rel) != m.get("source_sha256")]
    out += [rel + " (new)" for rel in jc.allowed_files(root) if rel not in files
            and (root / rel).stat().st_size <= jc.MAX_FILE_BYTES]
    return out


def load_manifest(corpus_dir=CORPUS_DIR):
    return json.loads((Path(corpus_dir) / MANIFEST_NAME).read_text(encoding="utf-8"))


def main():
    m = build_corpus()
    print(f"files copied: {m['files_copied']}")
    print(f"total bytes: {m['total_bytes']}")
    print(f"secret lines removed: {m['secret_lines_removed']}")
    print(f"skipped large files: {len(m['skipped_large_files'])}; parse errors: {len(m['parse_errors'])}")
    print(f"progress.json pruned: {', '.join(m['progress_pruned']) or 'nothing'}")
    print(f"stale copies removed: {len(m['removed_stale_copies'])}")
    print(f"wrote: {CORPUS_DIR.relative_to(jc.ROOT)}/ and {MANIFEST_NAME}")


if __name__ == "__main__":
    main()
