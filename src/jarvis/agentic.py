"""Jarvis J1 round 3: agentic search. codex/opencode run with data/jarvis/corpus as working dir and find the answer
themselves; our code then (1) audits every command/path in the event log (anything outside the corpus, network,
writes -> REJECTED) and (2) checks every quote verbatim against the corpus file (sha must match the manifest), then
applies the usual number guard.

Probe (raw event log -> data/jarvis/audit/probe_<brain>.jsonl):  python3 -I src/jarvis/agentic.py --probe codex
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_core as jc  # noqa: E402
import brains as br  # noqa: E402
import corpus_build as cb  # noqa: E402

AUDIT_DIR = jc.INDEX_DIR / "audit"
AGENTIC_TIMEOUT = 180
REJECT_ACCESS = "access outside corpus"
MAX_EVENT_CHARS = 4000

AGENTIC_PROMPT = (
    "You are Jarvis, the FlightOps AI project assistant. The CURRENT FOLDER is a read-only snapshot of the project's "
    "documents. Find the answer to the QUESTION yourself by listing, searching and opening files IN THE CURRENT FOLDER "
    "ONLY. Strict rules: use relative paths only (no absolute paths, no '..', no '~', no environment variables); "
    "allowed commands: ls, find, rg, grep, cat, head, tail, sed -n, wc, sort, uniq, cut; never write, create, move or "
    "delete files, never use redirection ('>'), never use the network; ignore the file _corpus_manifest.json. "
    "Check several files when the question needs facts from more than one place. Prefer full-dataset totals over "
    "samples, pilots or partial counts unless the question asks for those, and say the scope (period, carrier, table) "
    "of each number. " + jc.PARTS_RULE + " "
    "Then reply with ONE JSON object only, no other text: "
    "{\"quotes\": [{\"path\": \"<relative file path>\", \"quote\": \"<text copied exactly from that file>\"}], "
    "\"answer\": \"<answer>\"}. Quotes: short passages (a sentence, a line or a 'key: value' / JSON field) copied "
    "word for word from ONE file each, at most 8. Answer: full sentences, at most 150 words, put the quote number "
    "(1 = first quote) in square brackets after EVERY sentence, like [1]; copy numbers exactly as written in the "
    f"quotes; do not compute new numbers. If the files answer no part of the question, the answer begins with exactly \"{jc.REFUSAL}\" "
    "(optionally one short cited context sentence, whose quote goes in quotes; otherwise quotes is [])."
)

# ------------------------------------------------------------------ command audit
READ_TOOLS = {"ls", "find", "rg", "grep", "egrep", "fgrep", "cat", "head", "tail", "sed", "wc", "sort", "uniq",
              "cut", "nl", "tr", "pwd", "echo", "printf", "true", "file", "stat", "tree", "jq", "cd", "basename",
              "dirname", "xargs", "test", "["}
NETWORK_TOOLS = {"curl", "wget", "nc", "ncat", "netcat", "ssh", "scp", "sftp", "ftp", "telnet", "rsync", "ping",
                 "dig", "nslookup", "host", "http", "https", "socat", "git", "pip", "pip3", "npm", "npx", "brew",
                 "open", "osascript"}
WRITE_TOOLS = {"rm", "mv", "cp", "touch", "mkdir", "rmdir", "chmod", "chown", "ln", "tee", "dd", "truncate",
               "install", "patch", "apply_patch"}
SHELLS = {"bash", "sh", "zsh", "/bin/bash", "/bin/sh", "/bin/zsh", "/usr/bin/bash", "/usr/bin/zsh"}
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n"}
SAFE_ABS = {"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr"}
VAR_RE = re.compile(r"\$(\{|\(|[A-Za-z_])")


def _within(path_str, cwd, corpus):
    """True if path (absolute or relative to cwd) resolves inside the corpus."""
    p = Path(path_str)
    full = p if p.is_absolute() else Path(cwd) / p
    try:
        full = Path(os.path.realpath(full))
    except (OSError, ValueError):
        return False
    corpus = Path(os.path.realpath(corpus))
    return full == corpus or corpus in full.parents


def _unwrap(cmd):
    """['bash','-lc','inner'] -> inner string; returns a command string."""
    if isinstance(cmd, list):
        if len(cmd) >= 3 and cmd[0] in SHELLS and cmd[1] in ("-c", "-lc", "-l", "-ic"):
            return cmd[-1]
        return " ".join(shlex.quote(c) for c in cmd)
    s = str(cmd).strip()
    try:
        parts = shlex.split(s)
    except ValueError:
        return s
    if len(parts) >= 3 and parts[0] in SHELLS and parts[1] in ("-c", "-lc", "-l", "-ic"):
        return parts[-1]
    return s


def _path_violation(tok, cwd, corpus):
    if tok in SAFE_ABS:
        return None
    if tok.startswith("~"):
        return f"home path '{tok}'"
    if VAR_RE.search(tok):
        return f"variable/command substitution '{tok}'"
    if "`" in tok:
        return f"command substitution '{tok}'"
    looks_path = tok.startswith("/") or ".." in tok.split("/") or tok.startswith("../") or tok == ".."
    if "=" in tok and tok.startswith("-"):           # --flag=/abs/path
        val = tok.split("=", 1)[1]
        return _path_violation(val, cwd, corpus) if val else None
    if looks_path and not _within(tok, cwd, corpus):
        return f"path outside corpus '{tok}'"
    return None


def audit_command(cmd, cwd, corpus):
    """Violations (list of str) for one shell command run with working dir cwd."""
    v = []
    if cwd and not _within(cwd, corpus, corpus):
        v.append(f"working dir outside corpus '{cwd}'")
    inner = _unwrap(cmd)
    if "$(" in inner or "`" in inner:
        v.append("command substitution")
    if "<<" in inner:
        v.append("heredoc")
    try:
        lex = shlex.shlex(inner, posix=True, punctuation_chars=";&|()<>")
        lex.whitespace_split = True
        lex.commenters = ""
        toks = list(lex)
    except ValueError as e:
        return v + [f"unparseable command ({e})"]
    start = True
    prog = None
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in SEPARATORS or set(t) <= set(";&|()"):
            start, prog = True, None
            i += 1
            continue
        if t and set(t) <= set("<>"):
            target = toks[i + 1] if i + 1 < len(toks) else ""
            prev = toks[i - 1] if i > 0 else ""
            if ">" in t:
                # allow N>/dev/null and N>&M; anything else is a write
                if target in SAFE_ABS or target.startswith("&") or target.isdigit() or (prev.isdigit() and target == "&"):
                    i += 2
                    continue
                v.append(f"write redirection to '{target}'")
            else:
                pv = _path_violation(target, cwd, corpus)
                if pv:
                    v.append(pv)
            i += 2
            continue
        if start:
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t):   # VAR=value prefix
                v.append(f"environment assignment '{t.split('=')[0]}'")
                i += 1
                continue
            prog = os.path.basename(t)
            start = False
            if prog in NETWORK_TOOLS:
                v.append(f"network tool '{prog}'")
            elif prog in WRITE_TOOLS:
                v.append(f"write tool '{prog}'")
            elif prog in SHELLS or prog in {"python", "python3", "node", "perl", "ruby", "awk", "env", "sudo",
                                             "exec", "eval", "source", "."}:
                v.append(f"interpreter/shell '{prog}'")
            elif prog not in READ_TOOLS:
                v.append(f"command not allowed '{prog}'")
            if t.startswith("/") and t not in SAFE_ABS:
                v.append(f"absolute program path '{t}'")
            i += 1
            continue
        # argument
        if prog == "sed" and (t == "-i" or t.startswith("-i") or t.startswith("--in-place")):
            v.append("sed in-place write")
        if prog == "find" and t in ("-exec", "-execdir", "-delete", "-fprint", "-fprintf", "-fls", "-ok", "-okdir"):
            v.append(f"find {t}")
        if prog == "rg" and t in ("--pre",):
            v.append("rg --pre")
        if prog == "cd":
            pv = _path_violation(t, cwd, corpus) or (None if _within(t, cwd, corpus) else f"cd outside corpus '{t}'")
            if pv:
                v.append(pv)
            i += 1
            continue
        pv = _path_violation(t, cwd, corpus)
        if pv:
            v.append(pv)
        i += 1
    return v


# ------------------------------------------------------------------ event parsing
def _jsonl(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


CODEX_OK_ITEMS = {"reasoning", "agent_message", "todo_list", "error"}


def codex_actions(events):
    """Actions from `codex exec --json` events: [{"kind","detail","command"?,"cwd"?}]."""
    acts = []
    for ev in events:
        item = ev.get("item")
        if not isinstance(item, dict):
            continue
        if ev.get("type") not in ("item.completed", "item.started", "item.updated"):
            continue
        it = item.get("type") or item.get("item_type")
        if it == "command_execution":
            if ev.get("type") == "item.started" and any(a.get("id") == item.get("id") for a in acts):
                continue
            acts.append({"kind": "command", "id": item.get("id"), "command": item.get("command"),
                         "cwd": item.get("cwd"), "status": item.get("status"), "exit_code": item.get("exit_code")})
        elif it in CODEX_OK_ITEMS:
            continue
        elif it in ("file_change", "patch", "apply_patch"):
            acts.append({"kind": "write", "id": item.get("id"), "detail": _short(item.get("changes") or item)})
        elif it in ("web_search", "web_fetch"):
            acts.append({"kind": "network", "id": item.get("id"), "detail": _short(item.get("query") or item)})
        else:
            acts.append({"kind": "other", "id": item.get("id"), "detail": f"item type '{it}': {_short(item)}"})
    # de-duplicate started/completed pairs (keep last)
    seen, out = {}, []
    for a in acts:
        key = (a["kind"], a.get("id")) if a.get("id") else None
        if key and key in seen:
            out[seen[key]] = a
        else:
            if key:
                seen[key] = len(out)
            out.append(a)
    return out


OPENCODE_READ_TOOLS = {"read", "grep", "glob", "list", "ls"}
OPENCODE_PATH_KEYS = ("filePath", "path", "file", "dir", "directory", "cwd", "workdir", "include")


def opencode_actions(events):
    """Actions from `opencode run --format json` tool events."""
    acts = []
    for ev in events:
        part = ev.get("part")
        if not isinstance(part, dict) or part.get("type") != "tool":
            continue
        tool = str(part.get("tool") or "")
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        inp = state.get("input") if isinstance(state.get("input"), dict) else {}
        a = {"id": part.get("callID") or part.get("id"), "tool": tool, "input": inp, "status": state.get("status")}
        if tool == "bash":
            a.update(kind="command", command=inp.get("command"), cwd=inp.get("workdir") or inp.get("cwd"))
        elif tool in OPENCODE_READ_TOOLS:
            a.update(kind="read", paths=[str(inp[k]) for k in OPENCODE_PATH_KEYS if inp.get(k)])
        elif tool in ("write", "edit", "patch", "multiedit", "apply_patch"):
            a.update(kind="write", detail=_short(inp))
        elif tool in ("webfetch", "websearch", "fetch", "codesearch"):
            a.update(kind="network", detail=_short(inp))
        else:
            a.update(kind="other", detail=f"tool '{tool}': {_short(inp)}")
        acts.append(a)
    seen, out = {}, []
    for a in acts:
        key = a.get("id")
        if key and key in seen:
            out[seen[key]] = a
        else:
            if key:
                seen[key] = len(out)
            out.append(a)
    return out


def _short(o, n=300):
    s = o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)
    return br.strip_tokens(s)[:n]


def audit_actions(actions, corpus):
    """Return (violations [str], commands [str]) for parsed actions."""
    violations, commands = [], []
    corpus = str(corpus)
    for a in actions:
        k = a.get("kind")
        if k == "command":
            cmd = a.get("command")
            commands.append(_short(_unwrap(cmd) if cmd else "", 500))
            if not cmd:
                violations.append("command without text")
                continue
            violations += [f"{x} (in: {_short(_unwrap(cmd), 160)})" for x in audit_command(cmd, a.get("cwd") or corpus, corpus)]
        elif k == "read":
            commands.append(f"{a.get('tool')} {_short(a.get('input'), 300)}")
            for p in a.get("paths", []):
                pv = _path_violation(p, corpus, corpus)
                if p.startswith("~") or pv:
                    violations.append(f"{a.get('tool')}: {pv or 'home path'}")
            for key, val in (a.get("input") or {}).items():
                if isinstance(val, str) and (val.startswith("~") or VAR_RE.search(val)) and key not in ("pattern",):
                    violations.append(f"{a.get('tool')}: suspicious {key} '{_short(val, 80)}'")
        elif k == "write":
            commands.append(f"WRITE {a.get('detail')}")
            violations.append(f"write: {a.get('detail', '')[:160]}")
        elif k == "network":
            commands.append(f"NETWORK {a.get('detail')}")
            violations.append(f"network: {a.get('detail', '')[:160]}")
        else:
            commands.append(f"OTHER {a.get('detail')}")
            violations.append(f"unknown action: {a.get('detail', '')[:160]}")
    return violations, commands


# ------------------------------------------------------------------ quote guard
def _rel_in_corpus(p, corpus):
    s = str(p or "").strip().strip("`'\"")
    if not s:
        return None
    full = Path(s) if Path(s).is_absolute() else Path(corpus) / s
    real, root = Path(os.path.realpath(full)), Path(os.path.realpath(corpus))
    if root not in real.parents:
        return None
    return real.relative_to(root).as_posix()


def _section_for(text, quote_norm, rel):
    """Markdown heading above the quote (for citations); '(file)' otherwise."""
    if not rel.endswith(".md"):
        return "(file)"
    heading, pos_lines = "(top)", []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = jc.HEADING_RE.match(line)
        if m:
            heading = m.group(2).strip()
        pos_lines.append(heading)
    norm_acc = ""
    for i, line in enumerate(lines):
        norm_acc = jc.norm_text(norm_acc + " " + line)
        if quote_norm[:60] and quote_norm[:60] in norm_acc:
            return pos_lines[i]
    return heading


def check_quotes(items, corpus, manifest):
    """Verify agentic quotes. Returns (chunks, kept [{"n","quote"}], dropped [{"n","path","reason"}]).
    chunks[i] corresponds to quote number i+1 (pseudo-chunks: path, section, text=quote)."""
    chunks, kept, dropped = [], [], []
    files = manifest.get("files", {})
    for i, it in enumerate(items if isinstance(items, list) else [], 1):
        it = it if isinstance(it, dict) else {}
        q = str(it.get("quote", "")).strip().strip('"').strip()
        q = re.sub(r"^(\.\.\.|…)\s*|\s*(\.\.\.|…)$", "", q).strip()
        rel = _rel_in_corpus(it.get("path"), corpus)
        chunk = {"path": rel or str(it.get("path", "")), "section": "(file)", "text": q}
        chunks.append(chunk)
        reason = None
        if not q:
            reason = "empty quote"
        elif rel is None:
            reason = "path not inside corpus"
        elif rel == cb.MANIFEST_NAME or rel not in files:
            reason = "file not in corpus manifest"
        else:
            p = Path(corpus) / rel
            if not p.is_file():
                reason = "file missing"
            elif jc.sha256_file(p) != files[rel].get("copy_sha256"):
                reason = "corpus file sha does not match manifest"
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
                qn = jc.norm_text(q)
                if qn not in jc.norm_text(text):
                    reason = "quote not verbatim in file"
                else:
                    chunk["section"] = _section_for(text, qn, rel)
        if reason:
            dropped.append({"n": i, "path": chunk["path"], "reason": reason})
        else:
            kept.append({"n": i, "quote": q})
    return chunks, kept, dropped


# ------------------------------------------------------------------ running
class AuditRejected(br.BrainError):
    pass


def _argv(brain_id, corpus, out_file, model=None):
    if brain_id == "codex":
        return ["exec", "-s", "read-only", "-C", str(corpus), "--skip-git-repo-check", "--ephemeral",
                "--color", "never", "--json", "-o", out_file, "-"], True
    if brain_id == "opencode":
        args = ["run", "--dir", str(corpus), "--format", "json"]
        if model:
            args += ["-m", model]
        return args, False
    raise br.BrainError(f"brain '{brain_id}' has no agentic mode")


def run_cli(brain_id, prompt, corpus, timeout, runner=None, model=None):
    """Run the CLI with cwd = corpus. Returns (reply_text, events, stdout, stderr, model_name)."""
    runner = runner or subprocess.run
    exe = shutil.which(brain_id)
    if not exe:
        raise br.BrainError(f"'{brain_id}' not found on PATH")
    with tempfile.TemporaryDirectory(prefix=f"jarvis_ag_{brain_id}_") as tmp:   # -o file lives OUTSIDE the corpus
        out_file = str(Path(tmp) / "last_message.txt")
        args, stdin = _argv(brain_id, corpus, out_file, model)
        argv = [exe] + args + ([] if stdin else [prompt])
        try:
            proc = runner(argv, input=prompt if stdin else None, capture_output=True, text=True, timeout=timeout,
                          cwd=str(corpus))
        except subprocess.TimeoutExpired:
            raise br.BrainError(f"timeout after {timeout:.0f} s")
        except OSError as e:
            raise br.BrainError(f"could not start {brain_id}: {e}")
        stdout, stderr = br.strip_tokens(proc.stdout), br.strip_tokens(proc.stderr)
        events = _jsonl(stdout)
        if brain_id == "codex":
            p = Path(out_file)
            reply = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            if not reply:
                msgs = [e["item"].get("text", "") for e in events if isinstance(e.get("item"), dict)
                        and e["item"].get("type") == "agent_message"]
                reply = msgs[-1] if msgs else ""
            model_name = None
            for e in events:
                for k in ("model", "model_slug"):
                    if isinstance(e.get(k), str):
                        model_name = e[k]
            m = re.search(r"(?mi)^\s*model:\s*([A-Za-z0-9._\-/:]+)", stderr)
            model_name = model_name or (m.group(1) if m else None)
        else:
            texts = [t for e in events for t in br._event_texts(e)]
            reply = texts[-1] if texts else ""
            model_name = None
            for e in events:
                model_name = br._event_model(e) or model_name
            if not model_name:
                for e in events:
                    meta = e.get("part", {}).get("metadata") if isinstance(e.get("part"), dict) else None
                    if isinstance(meta, dict) and len(meta) == 1:
                        model_name = f"{next(iter(meta))}/model-not-reported"
        if proc.returncode != 0:
            tail = (stderr or stdout).strip().splitlines()[-3:]
            raise br.BrainError(f"{brain_id} exit {proc.returncode}: {' | '.join(tail)[:300]}")
    return br.strip_tokens(reply), events, stdout, stderr, model_name


def _write_audit(audit_dir, record):
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = audit_dir / f"{ts}_{record['brain']}_{uuid.uuid4().hex[:6]}.json"
    text = br.strip_tokens(json.dumps(record, ensure_ascii=False, indent=1))
    text, _ = cb.scrub(text)
    path.write_text(text, encoding="utf-8")
    try:
        return path.relative_to(jc.ROOT).as_posix()
    except ValueError:
        return str(path)


def answer_agentic(question, brain_id, cfg=None, corpus=None, audit_dir=None, runner=None, manifest=None):
    """Agentic answer by one brain. Returns the guarded result; raises AuditRejected (access outside corpus) or
    BrainError (timeout, crash, unparseable). An audit log is written in both success and reject cases."""
    cfg = cfg or br.load_config()
    bcfg = cfg["brains"].get(brain_id, {})
    if not bcfg.get("enabled", True):
        raise br.BrainError(f"brain '{brain_id}' is disabled")
    corpus = Path(corpus or cb.CORPUS_DIR)
    audit_dir = audit_dir or AUDIT_DIR
    if not (corpus / cb.MANIFEST_NAME).is_file():
        raise br.BrainError("corpus missing - run: python3 -I src/jarvis/corpus_build.py")
    manifest = manifest or cb.load_manifest(corpus)
    timeout = float(bcfg.get("agentic_timeout_s", AGENTIC_TIMEOUT))
    prompt = AGENTIC_PROMPT + f"\n\nQUESTION: {question}"
    t0 = time.monotonic()
    reply, events, stdout, stderr, model_name = run_cli(brain_id, prompt, corpus, timeout, runner, bcfg.get("model"))
    secs = round(time.monotonic() - t0, 1)
    actions = codex_actions(events) if brain_id == "codex" else opencode_actions(events)
    violations, commands = audit_actions(actions, corpus)
    model_label = f"{brain_id}:{model_name or 'model-not-reported'}"
    record = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "question": question,
              "brain": brain_id, "model": model_label, "search": "agentic", "corpus": str(corpus),
              "seconds": secs, "n_events": len(events), "commands": commands, "violations": violations,
              "verdict": "rejected" if violations else "accepted", "reply": reply[:MAX_EVENT_CHARS],
              "events": [_short(e, MAX_EVENT_CHARS) for e in events]}
    if violations:
        record["rejected_reason"] = REJECT_ACCESS
        log = _write_audit(audit_dir, record)
        err = AuditRejected(f"{REJECT_ACCESS}: {violations[0]}")
        err.audit_log, err.violations, err.commands = log, violations, commands
        raise err
    data = jc.extract_json(reply)
    if not isinstance(data, dict) or ("quotes" not in data and "answer" not in data):
        if jc.is_refusal(reply):
            data = {"quotes": [], "answer": jc.REFUSAL}
        else:
            record["verdict"] = "unparseable"
            log = _write_audit(audit_dir, record)
            err = br.BrainError("unparseable reply (no JSON with quotes/answer)")
            err.audit_log = log
            raise err
    chunks, kept, dropped = check_quotes(data.get("quotes") or [], corpus, manifest)
    if not kept:
        result = jc._refused(question, model_label)
    else:
        result = jc.apply_guards(question, str(data.get("answer") or ""), chunks, model_label, kept,
                                 header_numbers=False)
    result["quotes"] = [{"n": k["n"], "path": chunks[k["n"] - 1]["path"], "quote": k["quote"]} for k in kept]
    result["rejected_quotes"] = len(dropped)
    result["dropped_quotes"] = dropped
    record.update(kept_quotes=result["quotes"], dropped_quotes=dropped, answer=result["answer"],
                  refused=result["refused"], unsupported_numbers=result["unsupported_numbers"])
    result["audit"] = {"log": _write_audit(audit_dir, record), "commands": commands, "violations": []}
    result["search"] = "agentic"
    result["seconds"] = secs
    return result


def _probe(brain_id):
    corpus = cb.CORPUS_DIR
    prompt = ("List the files in the current folder (ls), then show the first 3 lines of CLAUDE.md with head. "
              "Do not write anything. Then reply with exactly this JSON: {\"ok\": true}")
    t0 = time.monotonic()
    try:
        reply, events, stdout, stderr, model = run_cli(brain_id, prompt, corpus, AGENTIC_TIMEOUT)
    except br.BrainError as e:
        print(f"ERROR: {e}")
        return 2
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out = AUDIT_DIR / f"probe_{brain_id}.jsonl"
    out.write_text("\n".join(cb.scrub(br.strip_tokens(json.dumps(e, ensure_ascii=False)))[0] for e in events) + "\n",
                   encoding="utf-8")
    acts = codex_actions(events) if brain_id == "codex" else opencode_actions(events)
    viol, cmds = audit_actions(acts, corpus)
    print(f"brain={brain_id} model={model} seconds={time.monotonic() - t0:.1f} events={len(events)}")
    print(f"reply: {reply[:300]}")
    print(f"commands: {cmds}")
    print(f"violations: {viol}")
    print(f"raw events: {out.relative_to(jc.ROOT)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--probe" and sys.argv[2] in ("codex", "opencode"):
        sys.exit(_probe(sys.argv[2]))
    print("usage: python3 -I src/jarvis/agentic.py --probe <codex|opencode>", file=sys.stderr)
    sys.exit(2)
