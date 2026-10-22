"""Jarvis J1 core: chunking, BM25 retrieval, two-step prompts (quotes -> answer) and post-model guards.

Standard library only. Used by build_index.py and ask.py (same folder) and by tests/test_jarvis_*.py.
"""
import csv
import fnmatch
import hashlib
import io
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLIGHTOPS_ROOT = Path(os.environ.get("FLIGHTOPS_ROOT") or Path.home() / "flightops-ai").expanduser()  # indexed, read-only
INDEX_DIR = ROOT / "data" / "jarvis"
INDEX_FILE = INDEX_DIR / "index.json"
MANIFEST_FILE = INDEX_DIR / "index_manifest.json"

MAX_CHARS = 1500
OVERLAP = 200
MAX_FILE_BYTES = 2 * 1024 * 1024
TOP_K = 8
POOL_K = 20            # BM25 candidate pool before re-ranking
MAX_PER_FILE = 3       # diversity cap in the final top-K
SAME_FILE_DECAY = 0.7  # score multiplier per chunk already picked from the same file
FIELD_BOOST = 2        # extra count for the chunk's own heading / record-label tokens (path counts once)
ALIAS_WEIGHT = 0.4     # query weight of alias-expanded terms
MAX_QUOTES = 8
REFUSAL = "I don't know — it isn't in the project files."
REMOVED = "[number removed]"
PARTS_RULE = (
    "If the question has several parts (e.g. 'X and Y', 'which ... and why'), split it and answer EVERY part; for a "
    "part the material does not cover, say so in a short sentence (e.g. 'The files do not say ...') instead of "
    "refusing the whole question. For counts and totals, prefer the full-period total and state its scope (period, "
    "carriers, table). If the value asked for is not in the material (including when the material only says it "
    f"does not exist yet) and no part can be answered, the answer MUST begin with exactly \"{REFUSAL}\" and may add "
    "at most ONE short cited sentence of context (e.g. why it does not exist yet)."
)
REFUSAL_PREFIX_RE = re.compile(r"^\s*i\s+(?:don't|do not)\s+know\s*[-—–−:,]*\s*it\s+(?:isn't|is not)\s+in\s+"
                               r"the\s+project\s+files\s*\.?", re.I)

# one shared list for the input gate (SECRET_RE) and the output scrubber (brains.strip_tokens); QA H2 2026-10-20
SECRET_PATTERNS = (
    r"sb_secret_", r"service_role", r"eyJ", r"sk-ant-", r"sk-[A-Za-z0-9_\-]{16,}", r"AKIA[0-9A-Z]{16}",
    r"AIza[0-9A-Za-z_\-]{35}", r"gh[pousr]_[A-Za-z0-9]{20,}", r"xox[abprs]-[A-Za-z0-9\-]{10,}",
    r"(?i:bearer\s+[A-Za-z0-9._\-]{12,})", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i:\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret[_-]?key|password)\s*[:=]\s*['\"]?"
    r"[A-Za-z0-9_\-./+]{8,})")
SECRET_RE = re.compile("|".join(SECRET_PATTERNS))
EXCLUDE_PREFIXES = ("config/", "supabase/", "data/", "ios/", "tracker/", ".claude/")
EXCLUDE_FILES = {"artifacts/chat.jsonl", "artifacts/answers.jsonl"}
# evaluation material must never be in the index (fix round 1, item 1)
EXCLUDE_GLOBS = ("reports/j1_*", "reports/j2_check*", "reports/j5_check*",
                 "docs/office/jarvis/j1_testset*", "data/*", "src/validate/qa_*")
PROGRESS = "artifacts/progress.json"
LOG_KEEP = 30


# ------------------------------------------------------------------ file selection
def is_excluded(rel):
    return (rel.startswith(EXCLUDE_PREFIXES) or rel in EXCLUDE_FILES
            or any(fnmatch.fnmatch(rel, g) for g in EXCLUDE_GLOBS))


def allowed_files(root=FLIGHTOPS_ROOT):
    """Return sorted relative paths (posix) of files in the J1 allowlist."""
    root = Path(root)
    out = set()

    def add(p):
        if not p.is_file():
            return
        rel = p.relative_to(root).as_posix()
        if is_excluded(rel):
            return
        if p.suffix.lower() in (".docx", ".log", ".jsonl") or ".bak" in p.name:
            return
        out.add(rel)

    if (root / "docs").is_dir():
        for p in (root / "docs").rglob("*.md"):
            add(p)
        for p in (root / "docs" / "registry").glob("*.csv"):
            add(p)
    for pat in ("*.md", "*.json", "*.csv"):
        for p in (root / "reports").glob(pat):
            add(p)
    add(root / PROGRESS)
    for p in (root / "artifacts" / "decisions").glob("*.json"):
        add(p)
    add(root / "src" / "jarvis" / "README.md")
    add(root / "CLAUDE.md")
    return sorted(out)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _drop_lists(d):
    """Remove list values from a dict tree (datacenter raw lists). Returns removed key paths."""
    removed = []
    for k in list(d):
        if isinstance(d[k], list):
            removed.append(k)
            del d[k]
        elif isinstance(d[k], dict):
            removed += [f"{k}.{r}" for r in _drop_lists(d[k])]
    return removed


def prune_progress(obj):
    """Drop bulky machine sections of progress.json in place. Returns a list of what was pruned."""
    pruned = []
    agent = obj.get("agent") if isinstance(obj, dict) else None
    if not isinstance(agent, dict):
        return pruned
    for k in ("galaxy", "briefing"):
        if k in agent:
            del agent[k]
            pruned.append(f"agent.{k}")
    log = agent.get("log")
    if isinstance(log, list) and len(log) > LOG_KEEP:
        pruned.append(f"agent.log ({len(log) - LOG_KEEP} older entries; kept last {LOG_KEEP})")
        agent["log"] = log[-LOG_KEEP:]
    if isinstance(agent.get("datacenter"), dict):
        pruned += [f"agent.datacenter.{r}" for r in _drop_lists(agent["datacenter"])]
    return pruned


# ------------------------------------------------------------------ text splitting
def split_long(text, limit=MAX_CHARS, overlap=OVERLAP):
    """Split text into pieces <= limit chars with `overlap` chars repeated, preferring line breaks."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    pieces, start = [], 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + limit // 2, end)
            if cut == -1:
                cut = text.rfind(" ", start + limit // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


# ------------------------------------------------------------------ chunkers
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def chunk_markdown(text):
    """Split Markdown by headings. Returns [(section, text)]; section = heading path joined by ' > '."""
    sections, stack, buf, in_fence = [], [], [], False
    current = ""

    def flush():
        body = "\n".join(buf).strip()
        if body:
            for piece in split_long(body):
                sections.append((current or "(top)", piece))

    for line in text.splitlines():
        if line.strip().startswith(("```", "~~~")):
            in_fence = not in_fence
        m = None if in_fence else HEADING_RE.match(line)
        if m:
            flush()
            buf = [line]
            level, title = len(m.group(1)), m.group(2).strip()
            stack = [(lv, t) for lv, t in stack if lv < level] + [(level, title)]
            current = " > ".join(t for _, t in stack)
        else:
            buf.append(line)
    flush()
    return sections


def chunk_csv(text):
    """One chunk per data row. section = first column value. Text = 'col: value' pairs."""
    out = []
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return out
    for row in reader:
        if not any(c.strip() for c in row):
            continue
        section = (row[0].strip() if row else "") or "(row)"
        body = "; ".join(f"{h}: {v}" for h, v in zip(header, row) if v.strip())
        for piece in split_long(body):
            out.append((section, piece))
    return out


SEP = " › "  # " › "
LABEL_KEYS = ("id", "name", "title", "source_id", "feature_id", "factor", "column", "gate", "t", "timestamp")


def _scalar(v):
    return not isinstance(v, (dict, list))


def _fmt(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _label(item, idx):
    if isinstance(item, dict):
        for k in LABEL_KEYS:
            v = item.get(k)
            if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v).strip():
                s = " ".join(str(v).split())
                return s if len(s) <= 50 else s[:47] + "..."
    return str(idx)


def _flat_small(v):
    return isinstance(v, dict) and all(_scalar(x) for x in v.values()) and len(json.dumps(v, ensure_ascii=False)) <= 300


def chunk_json_value(value, parts=()):
    """One record per chunk. A dict's scalar fields (and lists of scalars, small flat dicts) form its chunk as
    'key: value' lines; nested records become their own chunks. section = readable path ('milestones › M5 › tasks › M5.3')."""
    out = []
    sec = SEP.join(parts) or "(root)"

    def add_list(key_parts, lst):
        for i, x in enumerate(lst):
            if isinstance(x, (dict, list)):
                out.extend(chunk_json_value(x, key_parts + (_label(x, i),)))
            else:
                out.append((SEP.join(key_parts), _fmt(x)))

    if isinstance(value, dict):
        lines, children = [], []
        for k, v in value.items():
            if _scalar(v):
                lines.append(f"{k}: {_fmt(v)}")
            elif isinstance(v, list) and all(_scalar(x) for x in v):
                lines.append(f"{k}: " + ("; ".join(_fmt(x) for x in v) if v else "(empty)"))
            elif _flat_small(v):
                if not v:
                    lines.append(f"{k}: (empty)")
                lines += [f"{k}.{kk}: {_fmt(vv)}" for kk, vv in v.items()]
            else:
                children.append((k, v))
        for piece in split_long("\n".join(lines)):
            out.append((sec, piece))
        for k, v in children:
            if isinstance(v, dict):
                out.extend(chunk_json_value(v, parts + (str(k),)))
            else:
                add_list(parts + (str(k),), v)
    elif isinstance(value, list):
        if all(_scalar(x) for x in value):
            for piece in split_long("; ".join(_fmt(x) for x in value)):
                out.append((sec, piece))
        else:
            add_list(parts, value)
    else:
        for piece in split_long(_fmt(value)):
            out.append((sec, piece))
    return out


def chunk_json(text, rel=""):
    value = json.loads(text)
    if rel == PROGRESS:
        prune_progress(value)
    parts = ()
    if isinstance(value, dict) and _scalar(value.get("id")) and value.get("id") not in (None, ""):
        parts = (str(value["id"]),)
    return chunk_json_value(value, parts)


def chunk_file(rel, text):
    suffix = Path(rel).suffix.lower()
    if suffix == ".md":
        return chunk_markdown(text)
    if suffix == ".csv":
        return chunk_csv(text)
    if suffix == ".json":
        return chunk_json(text, rel)
    return [("(text)", p) for p in split_long(text)]


# ------------------------------------------------------------------ tokens + numbers
STOP = set("""a an the and or of to in on for by with is are was were be been it its this that these those as at from
what which who whom how when where why do does did has have had not no yes can could should would will shall may
i you we they he she me my our your their there here than then so if into about over under any all each per vs via
much many more most some such only also just""".split())
TOKEN_RE = re.compile(r"\bd-[a-z0-9][a-z0-9-]*|\b\d+[a-z][a-z0-9]*|\d+(?:[.,]\d+)*|[a-z][a-z0-9_]*")
# a number claim: digits not glued to a preceding letter/digit (so ids like G12, M5.3, S02, F9 are not numbers)
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.,_])\d+(?:[.,]\d+)*")
CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def norm_number(s):
    s = s.replace(",", "")
    if re.fullmatch(r"\d+\.\d+", s):
        s = s.rstrip("0").rstrip(".")
    return s


def stem(t):
    if any(ch.isdigit() for ch in t):
        return t
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def _word(t, out):
    if len(t) > 1 and t not in STOP:
        out.append(stem(t))


def tokenize(text):
    out = []
    for t in TOKEN_RE.findall(text.lower()):
        if t.startswith("d-"):
            out.append(t)
            for p in t.split("-")[1:]:
                _word(p, out)
        elif t[0].isdigit() and re.search(r"[a-z]", t):   # 24h, 9e
            out.append(t)
            out.append(re.match(r"\d+", t).group())
        elif t[0].isdigit():
            out.append(norm_number(t))
        elif "_" in t:
            parts = [p for p in t.split("_") if p]
            if len(parts) > 1:
                out.append(t)
            for p in parts:
                _word(p, out)
        else:
            _word(t, out)
    return out


def numbers_in(text):
    return {norm_number(n) for n in NUMBER_RE.findall(text)}


# ------------------------------------------------------------------ aliases (built from the project's own files)
CARRIER_RE = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,2}) \(([A-Z0-9]{2})\)")
NAME_FILLER = {"airline", "air", "airway", "inc", "corp"}
DOMAIN_ALIASES = [  # generic delay vocabulary of this dataset (target = ArrDel15)
    (["late"], ["arrdel15", "del15", "delay", "delayed"]),
    (["delayed"], ["late", "arrdel15", "delay"]),
    (["arrdel15"], ["late", "15", "minute"]),
    (["15", "minute"], ["late", "arrdel15"]),
]


def build_aliases(texts, airlines=(), factor_titles=()):
    """Alias rules [(phrase_tokens, expansion_tokens)] from project text: 'Name (XX)' carrier mentions
    (XX in the project airlines or name containing 'Air'), factor ids <-> titles, plus DOMAIN_ALIASES."""
    rules = {}

    def add(phrase, exp):
        phrase, exp = tuple(phrase), [e for e in exp if e not in phrase]
        if phrase and exp:
            cur = rules.setdefault(phrase, [])
            cur += [e for e in exp if e not in cur]

    airlines = {a.upper() for a in airlines}
    for text in texts:
        for name, code in CARRIER_RE.findall(text):
            if not re.search(r"[A-Z]", code):
                continue
            if code not in airlines and not re.search(r"\bAir", name):
                continue
            name_toks = [t for t in tokenize(name) if t not in NAME_FILLER]
            code_tok = code.lower()
            if not name_toks:
                continue
            add([code_tok], name_toks)
            add(name_toks[:1], [code_tok])
    for fid, title in factor_titles:
        fid_tok = fid.strip().lower()
        title_toks = [t for t in tokenize(title)]
        if re.fullmatch(r"g\d{1,2}", fid_tok) and title_toks:
            add([fid_tok], title_toks)
            add(title_toks, [fid_tok])
    for phrase, exp in DOMAIN_ALIASES:
        add(phrase, exp)
    return [[list(p), e] for p, e in sorted(rules.items())]


def expand_query(tokens, aliases):
    """Return {term: weight}: query terms weight 1, alias expansions ALIAS_WEIGHT."""
    weights = {t: 1.0 for t in tokens}
    present = set(tokens)
    for phrase, exp in aliases or []:
        if all(p in present for p in phrase):
            for e in exp:
                weights.setdefault(e, ALIAS_WEIGHT)
    return weights


# ------------------------------------------------------------------ index
def leaf_section(section):
    """The chunk's own heading / record part of a section path: last Markdown heading, or last two JSON parts."""
    if " > " in section:
        return section.rsplit(" > ", 1)[1]
    parts = section.split(SEP)
    return SEP.join(parts[-2:])


def chunk_display(chunk):
    return f"{chunk['path']} § {chunk['section']}\n{chunk['text']}"


def _factor_titles(root):
    out = []
    p = Path(root) / "docs" / "registry" / "g_factor_coverage.csv"
    if p.is_file():
        for r in csv.DictReader(io.StringIO(p.read_text(encoding="utf-8", errors="replace"))):
            if r.get("factor") and r.get("category"):
                out.append((r["factor"], r["category"]))
    airlines = []
    p = Path(root) / PROGRESS
    if p.is_file():
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
            out += [(f.get("id", ""), f.get("title", "")) for f in st.get("factors", []) if isinstance(f, dict)]
            airlines = [a for a in (st.get("project") or {}).get("airlines", []) if isinstance(a, str)]
        except ValueError:
            pass
    return out, airlines


def build_index(root=FLIGHTOPS_ROOT):
    """Return (index_dict, manifest_dict) for the allowlisted files under root."""
    root = Path(root)
    chunks, files_meta, skipped_large, skipped_secret, errors, texts = [], {}, [], 0, [], []
    pruned = []
    for rel in allowed_files(root):
        p = root / rel
        if p.stat().st_size > MAX_FILE_BYTES:
            skipped_large.append(rel)
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            pieces = chunk_file(rel, text)
            if rel == PROGRESS:
                pruned = prune_progress(json.loads(text))
        except (ValueError, csv.Error) as e:
            errors.append({"path": rel, "error": str(e)[:200]})
            continue
        n_kept = n_secret = 0
        for section, body in pieces:
            if SECRET_RE.search(body) or SECRET_RE.search(section):
                n_secret += 1
                continue
            tf = Counter(tokenize(body))
            tf.update(tokenize(rel))                      # file path: weight 1
            for t in tokenize(leaf_section(section)):     # own heading / record label: boosted
                tf[t] += FIELD_BOOST
            chunks.append({"id": len(chunks), "path": rel, "section": section, "text": body,
                           "tf": dict(tf), "len": sum(tf.values())})
            texts.append(body)
            n_kept += 1
        skipped_secret += n_secret
        files_meta[rel] = {"sha256": sha256_file(p), "chunks": n_kept, "skipped_secret_chunks": n_secret}
    df = Counter()
    for c in chunks:
        df.update(c["tf"].keys())
    avgdl = (sum(c["len"] for c in chunks) / len(chunks)) if chunks else 0.0
    titles, airlines = _factor_titles(root)
    aliases = build_aliases(texts, airlines, titles)
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index = {"built_at": built_at, "n_chunks": len(chunks), "avgdl": avgdl, "df": dict(df),
             "aliases": aliases, "chunks": chunks}
    manifest = {"built_at": built_at, "files_indexed": len(files_meta), "chunk_count": len(chunks),
                "skipped_secret_chunks": skipped_secret, "skipped_large_files": skipped_large,
                "excluded_globs": list(EXCLUDE_GLOBS), "progress_pruned": pruned, "alias_rules": len(aliases),
                "parse_errors": errors, "files": files_meta}
    return index, manifest


def bm25_scores(index, weights, k1=1.5, b=0.75):
    n = index["n_chunks"] or 1
    avgdl = index["avgdl"] or 1.0
    df = index["df"]
    idf = {t: math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5)) for t in weights}
    scored = []
    for c in index["chunks"]:
        tf = c["tf"]
        s = 0.0
        for t, w in weights.items():
            f = tf.get(t)
            if f:
                s += w * idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * c["len"] / avgdl))
        if s > 0:
            scored.append((s, c["id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def diversify(scored, chunks_by_id, k=TOP_K, max_per_file=MAX_PER_FILE, decay=SAME_FILE_DECAY):
    """Greedy re-rank of the candidate pool: each chunk already taken from a file multiplies the next chunk's
    score from that file by `decay`; at most `max_per_file` per file while other files still have candidates
    (left-over slots are then filled in score order)."""
    pool = list(scored)
    picked, per_file = [], Counter()
    while pool and len(picked) < k:
        best_i, best_s = None, -1.0
        for i, (s, cid) in enumerate(pool):
            path = chunks_by_id[cid]["path"]
            if per_file[path] >= max_per_file:
                continue
            adj = s * (decay ** per_file[path])
            if adj > best_s:
                best_i, best_s = i, adj
        if best_i is None:   # only capped files left: fill in score order
            best_i = 0
        _, cid = pool.pop(best_i)
        picked.append(chunks_by_id[cid])
        per_file[chunks_by_id[cid]["path"]] += 1
    return picked


def bm25_search(index, query, k=TOP_K, pool_k=POOL_K):
    q_terms = list(dict.fromkeys(tokenize(query)))
    if not q_terms:
        return []
    weights = expand_query(q_terms, index.get("aliases"))
    scored = bm25_scores(index, weights)[:pool_k]
    by_id = {c["id"]: c for c in index["chunks"]}
    return diversify(scored, by_id, k)


def stale_files(manifest, root=FLIGHTOPS_ROOT):
    """Files whose sha256 differs from the manifest (or that disappeared)."""
    out = []
    for rel, meta in manifest.get("files", {}).items():
        p = Path(root) / rel
        if not p.is_file():
            out.append(rel + " (missing)")
        elif sha256_file(p) != meta.get("sha256"):
            out.append(rel)
    return out


# ------------------------------------------------------------------ step 1: quotes
QUOTE_SYSTEM = (
    "You extract evidence for the FlightOps AI project assistant. From the numbered CHUNKS, copy word for word the "
    "short passages (a sentence, a line or a 'key: value' field) that answer the QUESTION. Copy text exactly as it "
    "appears in the chunk, do not reword, do not combine text from two chunks in one quote. Prefer full-dataset "
    "totals over samples, pilots or partial counts unless the question asks for those. Include the passages that say "
    "the scope (period, carrier, table) of any number. At most 8 quotes. Reply with JSON only: "
    "{\"quotes\": [{\"chunk\": <number>, \"quote\": \"<exact text>\"}]}. If no chunk answers the question, reply "
    "{\"quotes\": []}."
)


def build_quote_messages(question, chunks):
    blocks = [f"[{i}] {chunk_display(c)}" for i, c in enumerate(chunks, 1)]
    user = "CHUNKS:\n\n" + "\n\n".join(blocks) + f"\n\nQUESTION: {question}"
    return [{"role": "system", "content": QUOTE_SYSTEM}, {"role": "user", "content": user}]


_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "‘": "'", "’": "'",
                         "“": '"', "”": '"', " ": " "})


def norm_text(s):
    return " ".join(s.translate(_DASHES).lower().split())


def extract_json(text):
    """First JSON object found in text: plain JSON, inside ```code fences```, or embedded in prose. None if none."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    candidates = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S) + [text]
    dec = json.JSONDecoder()
    for cand in candidates:
        for m in re.finditer(r"\{", cand):
            try:
                obj, _ = dec.raw_decode(cand[m.start():])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    return None


def parse_quotes(raw, chunks):
    """Parse the step-1 JSON. Keep only quotes that occur verbatim (whitespace/case/dash-insensitive) in their chunk.
    `raw` may be text (JSON, possibly wrapped) or an already parsed object. Returns (quotes [{"n","quote"}], rejected)."""
    data = raw if isinstance(raw, (dict, list)) else (extract_json(raw) or {})
    items = data.get("quotes", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    quotes, rejected, seen = [], 0, set()
    for it in items:
        if not isinstance(it, dict):
            rejected += 1
            continue
        m = re.search(r"\d+", str(it.get("chunk", "")))
        q = str(it.get("quote", "")).strip().strip('"').strip()
        q = re.sub(r"^(\.\.\.|…)\s*|\s*(\.\.\.|…)$", "", q).strip()
        if not m or not q:
            rejected += 1
            continue
        n = int(m.group())
        if not 1 <= n <= len(chunks) or norm_text(q) not in norm_text(chunk_display(chunks[n - 1])):
            rejected += 1
            continue
        if (n, norm_text(q)) in seen:
            continue
        seen.add((n, norm_text(q)))
        quotes.append({"n": n, "quote": q})
        if len(quotes) >= MAX_QUOTES:
            break
    return quotes, rejected


# ------------------------------------------------------------------ step 2: answer from quotes
ANSWER_SYSTEM = (
    "You are Jarvis, the FlightOps AI project assistant. Calm and short. Answer the QUESTION using ONLY the QUOTES "
    "(exact text from project files; [n] is the quote's chunk number). Rules: (1) use only facts stated in the "
    "quotes; never invent numbers, files or results; (2) put the chunk number in square brackets, like [2], after "
    "EVERY sentence; (3) copy numbers exactly as written in the quotes; do not compute new numbers; (4) prefer "
    "full-dataset totals over samples, pilots or partial counts unless the question asks for those; (5) say the scope "
    "(period, carrier, table) of each number when the quotes give it; (6) when comparing, check each value against "
    f"its quote before choosing; (7) full sentences, at most 120 words, no preamble; (8) {PARTS_RULE} "
    f"(9) if the quotes answer no part of the question, begin with exactly \"{REFUSAL}\" (at most one short cited "
    "context sentence may follow)."
)


def build_answer_messages(question, quotes, chunks):
    lines = []
    for q in quotes:
        c = chunks[q["n"] - 1]
        lines.append(f"[{q['n']}] ({c['path']} § {c['section']}) \"{q['quote']}\"")
    user = "QUOTES:\n" + "\n".join(lines) + f"\n\nQUESTION: {question}"
    return [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": user}]


def is_refusal(text):
    """Refusal = starts with "I don't know" or contains the full refusal sentence (dash/case/space-normalised).
    A partial answer saying one part is not in the files is NOT a refusal."""
    t = norm_text(text)
    return t.startswith(("i don't know", "i do not know")) or norm_text(REFUSAL) in t


def _refused(question, model, quotes=None):
    return {"question": question, "answer": REFUSAL, "citations": [], "refused": True,
            "unsupported_numbers": [], "model": model, "invalid_citations": [], "quotes": quotes or []}


def apply_guards(question, raw_answer, chunks, model, quotes=None, header_numbers=True):
    """Validate the model output. If quotes is given (two-step mode), citations must point at quoted chunks and
    numbers must appear in a cited quote (or the cited chunk's path/section); otherwise the cited chunk.
    Unsupported numbers are removed from the answer, listed, and the answer is marked (unverified)."""
    answer = (raw_answer or "").strip()
    m = REFUSAL_PREFIX_RE.match(answer)
    if m:
        # "not in the files" answer: refused=true; keep at most ONE cited context sentence (guarded like any answer)
        rest = answer[m.end():].strip()
        cm = re.match(r"(.+?[.!?](?:\s*\[\d+(?:\s*,\s*\d+)*\])*)(?=\s|$)", rest, flags=re.S)
        context = (cm.group(1) if cm else rest).strip()
        r = _refused(question, model, quotes)
        if context and not is_refusal(context):
            g = apply_guards(question, context, chunks, model, quotes, header_numbers)
            if not g["refused"]:
                r.update(answer=f"{REFUSAL} {g['answer']}", citations=g["citations"],
                         unsupported_numbers=g["unsupported_numbers"], invalid_citations=g["invalid_citations"])
        return r
    if not answer or is_refusal(answer):
        return _refused(question, model, quotes)
    valid = {q["n"] for q in quotes} if quotes is not None else set(range(1, len(chunks) + 1))
    cited, invalid = [], []

    def repl(m):
        keep = []
        for s in m.group(1).split(","):
            n = int(s.strip())
            if n in valid:
                keep.append(n)
                if n not in cited:
                    cited.append(n)
            else:
                invalid.append(n)
        return "".join(f"[{n}]" for n in keep)

    answer = CITE_RE.sub(repl, answer)
    answer = re.sub(r"[ \t]+([.,;:])", r"\1", answer).strip()
    if not cited:
        r = _refused(question, model, quotes)
        r["invalid_citations"] = invalid
        return r
    allowed = set()
    for n in cited:
        c = chunks[n - 1]
        if header_numbers:
            allowed |= numbers_in(f"{c['path']} § {c['section']}")
        if quotes is None:
            allowed |= numbers_in(c["text"])
        else:
            for q in quotes:
                if q["n"] == n:
                    allowed |= numbers_in(q["quote"])
    unsupported = []
    pieces = re.split(r"(\[\d+(?:\s*,\s*\d+)*\])", answer)   # keep citation markers untouched
    for i in range(0, len(pieces), 2):
        def num_repl(m):
            v = norm_number(m.group())
            if v in allowed:
                return m.group()
            if v not in unsupported:
                unsupported.append(v)
            return REMOVED
        pieces[i] = NUMBER_RE.sub(num_repl, pieces[i])
    answer = "".join(pieces)
    if unsupported:
        answer = answer.rstrip() + " (unverified)"
    return {"question": question, "answer": answer, "refused": False,
            "citations": [{"n": n, "path": chunks[n - 1]["path"], "section": chunks[n - 1]["section"]} for n in cited],
            "unsupported_numbers": unsupported, "model": model, "invalid_citations": invalid,
            "quotes": quotes if quotes is not None else []}


COMBINED_SYSTEM = (
    "You are Jarvis, the FlightOps AI project assistant. Do not run commands, open files or browse: everything you "
    "may use is in the numbered CHUNKS below (exact text from project files). Do two things. (A) QUOTES: copy word "
    "for word the short passages (a sentence, a line or a 'key: value' field) that answer the QUESTION, each with "
    "its chunk number; never reword a quote; one chunk per quote; at most 8. (B) ANSWER from those quotes only: "
    "put the chunk number in square brackets, like [2], after EVERY sentence; copy numbers exactly as written; do "
    "not compute new numbers; prefer full-dataset totals over samples, pilots or partial counts unless the question "
    "asks for those; say the scope (period, carrier, table) of each number; when the question needs facts from "
    f"several chunks, combine them and cite each; full sentences, at most 150 words. {PARTS_RULE} If the chunks "
    f"answer no part of the question, the answer begins with exactly \"{REFUSAL}\" (optionally one short cited context "
    "sentence, whose quote goes in quotes; otherwise quotes is []). Reply with ONE JSON object only, no other "
    "text: {\"quotes\": [{\"chunk\": <number>, \"quote\": \"<exact text>\"}], \"answer\": \"<answer with [n]>\"}"
)


def build_combined_prompt(question, chunks):
    blocks = [f"[{i}] {chunk_display(c)}" for i, c in enumerate(chunks, 1)]
    return COMBINED_SYSTEM + "\n\nCHUNKS:\n\n" + "\n\n".join(blocks) + f"\n\nQUESTION: {question}"


class UnparseableOutput(ValueError):
    """The brain's reply had no usable JSON object (treated as a brain failure, not a refusal)."""


def answer_combined(question, chunks, complete, model, trace=None):
    """One call: complete(prompt) -> JSON {"quotes", "answer"}; then the same quote check and guards."""
    trace = trace if trace is not None else {}
    raw = complete(build_combined_prompt(question, chunks))
    trace["raw"] = raw
    data = extract_json(raw)
    if not isinstance(data, dict) or ("quotes" not in data and "answer" not in data):
        if isinstance(raw, str) and is_refusal(raw):
            return _refused(question, model)
        raise UnparseableOutput("reply had no JSON object with quotes/answer")
    quotes, rejected = parse_quotes({"quotes": data.get("quotes") or []}, chunks)
    if not quotes:
        r = _refused(question, model)
        r["rejected_quotes"] = rejected
        return r
    r = apply_guards(question, str(data.get("answer") or ""), chunks, model, quotes)
    r["rejected_quotes"] = rejected
    return r


def answer_two_step(question, chunks, llm, model, trace=None):
    """Step 1 llm(messages, json_mode=True) -> quotes, step 2 llm(messages, json_mode=False) -> answer, guards."""
    trace = trace if trace is not None else {}
    raw_quotes = llm(build_quote_messages(question, chunks), json_mode=True)
    trace["raw_quotes"] = raw_quotes
    quotes, rejected = parse_quotes(raw_quotes, chunks)
    if not quotes:
        r = _refused(question, model)
        r["rejected_quotes"] = rejected
        return r
    raw = llm(build_answer_messages(question, quotes, chunks), json_mode=False)
    trace["raw_answer"] = raw
    r = apply_guards(question, raw, chunks, model, quotes)
    r["rejected_quotes"] = rejected
    return r


def answer_question(question, index, llm, model, trace=None):
    """Retrieve, then the two-step answer with llm (local brain path). llm errors propagate to the caller.
    If `trace` is a dict, retrieval and raw model output go in it."""
    trace = trace if trace is not None else {}
    chunks = bm25_search(index, question)
    trace["retrieved"] = [f"{c['path']} § {c['section']}" for c in chunks]
    if not chunks:
        return _refused(question, model)
    return answer_two_step(question, chunks, llm, model, trace)
