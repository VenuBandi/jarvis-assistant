"""Jarvis J1 round 2: brain adapters (local, codex, opencode, claude[disabled]) + auto fallback + council.

Our code keeps retrieval and every guard; a brain only turns (question + retrieved chunks) into JSON quotes + answer.
External CLIs run in an EMPTY temporary folder, so they can only use the chunks in the prompt.
Probe a brain:  python3 -I src/jarvis/brains.py --probe codex
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_core as jc  # noqa: E402

CONFIG_FILE = jc.INDEX_DIR / "brains.json"
OLLAMA = "http://127.0.0.1:11434/api/chat"
DEFAULT_CONFIG = {
    "order": ["codex", "opencode", "omniroute", "local"],
    "council": ["codex", "opencode"],
    "brains": {
        "local": {"enabled": True, "timeout_s": 300, "model": "qwen3-8b-32k"},
        "omniroute": {"enabled": False, "base_url": "http://127.0.0.1:20128", "model": None, "timeout": 120},
        "codex": {"enabled": True, "timeout_s": 120},
        "opencode": {"enabled": True, "timeout_s": 120},
        "claude": {"enabled": False, "timeout_s": 120,
                   "note": "disabled: the claude CLI is not in this session's allow list; the Director enables it"},
    },
}

TOKEN_RES = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_\-]{16,}", r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*", r"sb_secret_[A-Za-z0-9_\-]+",
    r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}", r"gh[pousr]_[A-Za-z0-9]{20,}", r"xox[abprs]-[A-Za-z0-9\-]{10,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password)\s*[:=]\s*\S+",
    r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_\-]{35}", r"sk-ant-[A-Za-z0-9_\-]*",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[^\n]*")]
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_tokens(text):
    """Remove anything that looks like a credential, plus terminal colour codes."""
    if not text:
        return ""
    text = ANSI_RE.sub("", text)
    for r in TOKEN_RES:
        text = r.sub("[redacted]", text)
    return text


class BrainError(Exception):
    """A brain could not answer (missing, disabled, timeout, crash, unparseable). Triggers fallback."""


def load_config(path=CONFIG_FILE):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        user = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    for k in ("order", "council"):
        if isinstance(user.get(k), list):
            cfg[k] = [str(x) for x in user[k]]
    for bid, b in (user.get("brains") or {}).items():
        if isinstance(b, dict):
            cfg["brains"].setdefault(bid, {}).update(b)
    cfg["brains"]["claude"]["enabled"] = bool(cfg["brains"]["claude"].get("enabled", False))
    return cfg


# ------------------------------------------------------------------ adapters
class Brain:
    id = "?"
    mode = "combined"   # "combined": complete(prompt) -> JSON; "two_step": chat(messages, json_mode) -> text

    def __init__(self, cfg=None, runner=None):
        self.cfg = cfg or {}
        self.timeout = float(self.cfg.get("timeout_s", 120))
        self.runner = runner or subprocess.run
        self.model = self.cfg.get("model") or "unknown"

    @property
    def enabled(self):
        return bool(self.cfg.get("enabled", True))

    def label(self):
        return f"{self.id}:{self.model}"


class LocalBrain(Brain):
    id = "local"
    mode = "two_step"

    def __init__(self, cfg=None, runner=None, opener=None):
        super().__init__(cfg, runner)
        self.model = self.cfg.get("model", "qwen3-8b-32k")
        self.opener = opener or urllib.request.urlopen

    def chat(self, messages, json_mode=False):
        payload = {"model": self.model, "messages": messages, "stream": False, "think": False,
                   "options": {"num_ctx": 32768, "temperature": 0.1}}
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener(req, timeout=self.timeout) as r:
                out = json.loads(r.read())["message"]["content"]
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            raise BrainError(f"local model unavailable ({self.model} at {OLLAMA}): {type(e).__name__}: {e}")
        return re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()


class CliBrain(Brain):
    """Runs a CLI agent in an empty temp folder; subclasses build argv and read the reply."""
    exe = None

    def argv(self, tmp, out_file, prompt):
        raise NotImplementedError

    def stdin_text(self, prompt):
        return None

    def read_reply(self, proc, out_file):
        return proc.stdout or ""

    def find_model(self, text):
        return None

    def complete(self, prompt):
        if not self.enabled:
            raise BrainError(f"brain '{self.id}' is disabled in data/jarvis/brains.json")
        if jc.SECRET_RE.search(prompt):
            raise BrainError("prompt contains a secret-like pattern; not sent")
        exe = shutil.which(self.exe)
        if not exe:
            raise BrainError(f"'{self.exe}' not found on PATH")
        with tempfile.TemporaryDirectory(prefix=f"jarvis_{self.id}_") as tmp:
            out_file = str(Path(tmp) / "last_message.txt")
            argv = [exe] + self.argv(tmp, out_file, prompt)
            try:
                proc = self.runner(argv, input=self.stdin_text(prompt), capture_output=True, text=True,
                                   timeout=self.timeout, cwd=tmp)
            except subprocess.TimeoutExpired:
                raise BrainError(f"timeout after {self.timeout:.0f} s")
            except OSError as e:
                raise BrainError(f"could not start {self.exe}: {e}")
            stdout, stderr = strip_tokens(proc.stdout), strip_tokens(proc.stderr)
            model = self.find_model(stdout + "\n" + stderr)
            if model:
                self.model = model
            if proc.returncode != 0:
                tail = (stderr or stdout).strip().splitlines()[-3:]
                raise BrainError(f"{self.exe} exit {proc.returncode}: {' | '.join(tail)[:300]}")
            proc.stdout, proc.stderr = stdout, stderr
            reply = strip_tokens(self.read_reply(proc, out_file))
        if not reply.strip():
            raise BrainError(f"{self.exe} returned an empty reply")
        return reply


class CodexBrain(CliBrain):
    id = "codex"
    exe = "codex"

    def argv(self, tmp, out_file, prompt):
        return ["exec", "-s", "read-only", "-C", tmp, "--skip-git-repo-check", "--ephemeral", "--color", "never",
                "-o", out_file, "-"]

    def stdin_text(self, prompt):
        return prompt

    def read_reply(self, proc, out_file):
        p = Path(out_file)
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""

    def find_model(self, text):
        m = re.search(r"(?mi)^\s*model:\s*([A-Za-z0-9._\-/:]+)", text)
        return m.group(1) if m else None


class OpenCodeBrain(CliBrain):
    id = "opencode"
    exe = "opencode"

    def argv(self, tmp, out_file, prompt):
        args = ["run", "--dir", tmp, "--format", "json"]
        if self.cfg.get("model"):
            args += ["-m", str(self.cfg["model"])]
        return args + [prompt]

    def read_reply(self, proc, out_file):
        texts, raw_lines = [], []
        self.event_shapes = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                raw_lines.append(line)
                continue
            if isinstance(ev, dict):
                part = ev.get("part") if isinstance(ev.get("part"), dict) else {}
                meta = part.get("metadata")
                meta_s = strip_tokens(json.dumps(meta))[:200] if meta is not None else ""
                self.event_shapes.append(f"{ev.get('type')}: keys={sorted(ev)} part_keys={sorted(part)} metadata={meta_s}")
            texts += _event_texts(ev)
            model = _event_model(ev)
            if model:
                self.model = model
            elif self.model == "unknown" and isinstance(ev, dict) and isinstance(ev.get("part"), dict):
                meta = ev["part"].get("metadata")
                if isinstance(meta, dict) and len(meta) == 1:   # e.g. {"openai": {...}} -> provider only
                    self.model = f"{next(iter(meta))}/model-not-reported"
        return "\n".join(texts) if texts else "\n".join(raw_lines)

    def find_model(self, text):
        m = re.search(r'"modelID"\s*:\s*"([^"]+)"', text)
        if m:
            p = re.search(r'"providerID"\s*:\s*"([^"]+)"', text)
            return f"{p.group(1)}/{m.group(1)}" if p else m.group(1)
        return None


def _event_texts(ev):
    """Text parts of an opencode JSON event (type 'text' parts; other part types are ignored)."""
    out = []
    if isinstance(ev, dict):
        part = ev.get("part") if isinstance(ev.get("part"), dict) else None
        if part is not None:
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                out.append(part["text"])
        elif ev.get("type") == "text" and isinstance(ev.get("text"), str):
            out.append(ev["text"])
    return out


def _event_model(ev):
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("modelID", "providerID") and isinstance(v, str):
                    found.setdefault(k, v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(ev)
    if "modelID" in found:
        return f"{found['providerID']}/{found['modelID']}" if "providerID" in found else found["modelID"]
    return None


class ClaudeBrain(CliBrain):
    """Written but DISABLED by default (enabled only by the Director in data/jarvis/brains.json)."""
    id = "claude"
    exe = "claude"

    def argv(self, tmp, out_file, prompt):
        return ["-p", "--output-format", "text", prompt]


OMNIROUTE_KEY_FILE = "~/.config/flightops/omniroute_key"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused (key must not leave 127.0.0.1)", headers, fp)


class OmniRouteBrain(Brain):
    """Local OmniRoute gateway (OpenAI-compatible /v1/chat/completions). bm25 mode only (plain chat, no files).
    Key read at call time from ~/.config/flightops/omniroute_key (must exist, be non-empty, mode 600); it is never
    printed, logged or returned. Only http://127.0.0.1 / localhost base URLs; no proxies, no redirects."""
    id = "omniroute"
    mode = "combined"

    def __init__(self, cfg=None, runner=None, key_file=None):
        super().__init__(cfg, runner)
        self.base_url = (self.cfg.get("base_url") or "").rstrip("/")
        self.model = self.cfg.get("model") or "not-configured"
        self.timeout = float(self.cfg.get("timeout") or self.cfg.get("timeout_s") or 120)
        self.key_file = Path(os.path.expanduser(key_file or self.cfg.get("key_file") or OMNIROUTE_KEY_FILE))
        self._key = None

    def problems(self, check_enabled=True):
        """What is missing, without calling anything (empty list = ready)."""
        out = []
        if check_enabled and not self.enabled:
            out.append("not enabled (data/jarvis/brains.json brains.omniroute.enabled is false; Director finishes S1-S2 first)")
        if not self.cfg.get("model"):
            out.append("model not configured (brains.omniroute.model is null)")
        u = urllib.parse.urlsplit(self.base_url or "")
        if u.scheme != "http" or (u.hostname or "") not in LOCAL_HOSTS or u.username or u.password:
            out.append(f"base_url must be http://127.0.0.1 or http://localhost (got '{self.base_url or 'none'}')")
        p = self.key_file
        if not p.is_file():
            out.append(f"key file missing ({OMNIROUTE_KEY_FILE})")
        else:
            mode = p.stat().st_mode & 0o777
            if mode != 0o600:
                out.append(f"key file permissions are {oct(mode)[2:]}, must be 600 (chmod 600 {OMNIROUTE_KEY_FILE})")
            elif not p.read_text(encoding="utf-8", errors="replace").strip():
                out.append(f"key file is empty ({OMNIROUTE_KEY_FILE})")
        return out

    def _scrub(self, text):
        text = str(text)
        if self._key:
            text = text.replace(self._key, "[redacted]")
        return strip_tokens(text)

    def complete(self, prompt):
        probs = self.problems()
        if probs:
            raise BrainError("omniroute not configured: " + "; ".join(probs))
        if jc.SECRET_RE.search(prompt):
            raise BrainError("prompt contains a secret-like pattern; not sent")
        self._key = self.key_file.read_text(encoding="utf-8", errors="replace").strip()
        try:
            body = json.dumps({"model": self.cfg["model"], "temperature": 0.1, "stream": False,
                               "messages": [{"role": "user", "content": prompt}]}).encode()
            req = urllib.request.Request(self.base_url + "/v1/chat/completions", data=body, method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": "Bearer " + self._key})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
            try:
                with opener.open(req, timeout=self.timeout) as r:
                    raw = r.read()
            except urllib.error.HTTPError as e:
                raise BrainError(self._scrub(f"omniroute HTTP {e.code}: {e.reason}"))
            except (TimeoutError, OSError) as e:   # URLError, socket.timeout, connection refused
                kind = "timeout" if "timed out" in str(e).lower() or isinstance(e, TimeoutError) else "unreachable"
                raise BrainError(self._scrub(f"omniroute {kind} ({self.base_url}): {type(e).__name__}"))
            try:
                data = json.loads(raw)
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                raise BrainError("omniroute returned an unexpected (non OpenAI-format) reply")
            if isinstance(data.get("model"), str):
                self.model = self._scrub(data["model"])
            if not isinstance(content, str) or not content.strip():
                raise BrainError("omniroute returned an empty reply")
            return self._scrub(re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip())
        finally:
            self._key = None


ADAPTERS = {"local": LocalBrain, "codex": CodexBrain, "opencode": OpenCodeBrain, "claude": ClaudeBrain,
            "omniroute": OmniRouteBrain}


def make_brains(cfg, runner=None, opener=None):
    out = {}
    for bid, cls in ADAPTERS.items():
        bcfg = cfg["brains"].get(bid, {})
        out[bid] = cls(bcfg, runner, opener) if cls is LocalBrain else cls(bcfg, runner)
    return out


# ------------------------------------------------------------------ running
def run_brain(brain, question, chunks, trace=None):
    """One brain on the shared chunks. Returns the guarded result dict; raises BrainError on failure."""
    if not brain.enabled:
        raise BrainError(f"brain '{brain.id}' is disabled in data/jarvis/brains.json")
    try:
        if brain.mode == "two_step":
            return jc.answer_two_step(question, chunks, brain.chat, brain.label(), trace)
        r = jc.answer_combined(question, chunks, brain.complete, None, trace)
    except jc.UnparseableOutput as e:
        raise BrainError(f"unparseable reply: {e}")
    r["model"] = brain.label()
    return r


def _timed(brain, question, chunks, trace):
    t0 = time.monotonic()
    try:
        return run_brain(brain, question, chunks, trace), None, round(time.monotonic() - t0, 1)
    except BrainError as e:
        return None, str(e), round(time.monotonic() - t0, 1)


def _meta(r, brain, tried, fallbacks, secs):
    r.update(brain=brain, brains_tried=tried, fallbacks=fallbacks, seconds_per_brain=secs)
    return r


AGENTIC_BRAINS = ("codex", "opencode")


class Engine:
    """Runs (brain, search) steps. search 'bm25' = shared retrieved chunks; 'agentic' = the brain searches
    data/jarvis/corpus itself (agentic.answer_agentic, audited). Keys in brains_tried / seconds_per_brain are the
    brain id for bm25 steps and '<id>:agentic' for agentic steps."""

    def __init__(self, question, brains, cfg, chunks_fn, trace=None, agentic_fn=None):
        self.question, self.brains, self.cfg, self.chunks_fn = question, brains, cfg, chunks_fn
        self.trace = trace if trace is not None else {}
        self.agentic_fn = agentic_fn
        self.lock = threading.Lock()

    def step(self, bid, search):
        """Returns (result|None, fallback_entry|None, key, seconds|None)."""
        key = bid if search == "bm25" else f"{bid}:agentic"
        b = self.brains.get(bid)
        if b is None:
            return None, {"brain": key, "reason": "unknown brain"}, key, None
        if not b.enabled:
            return None, {"brain": key, "reason": "disabled"}, key, None
        t0 = time.monotonic()
        try:
            if search == "agentic":
                fn = self.agentic_fn
                if fn is None:
                    import agentic  # noqa: E402  (lazy: agentic imports this module)
                    fn = agentic.answer_agentic
                r = fn(self.question, bid, self.cfg)
            else:
                chunks = self.chunks_fn()
                if not chunks:
                    r = jc._refused(self.question, "none (no chunk matched; no brain called)")
                else:
                    with self.lock:
                        t = self.trace.setdefault(bid, {})
                    r = run_brain(b, self.question, chunks, t)
        except BrainError as e:
            fb = {"brain": key, "reason": str(e)}
            for attr in ("audit_log", "violations"):
                if getattr(e, attr, None):
                    fb[attr] = getattr(e, attr)
            if type(e).__name__ == "AuditRejected":
                fb["rejected_reason"] = "access outside corpus"
            return None, fb, key, round(time.monotonic() - t0, 1)
        r["search"] = search
        return r, None, key, round(time.monotonic() - t0, 1)

    def chain(self, steps):
        """Try steps in order. Returns (result|None, key|None, tried, fallbacks, secs)."""
        tried, fallbacks, secs = [], [], {}
        for bid, search in steps:
            r, fb, key, s = self.step(bid, search)
            if s is not None:
                tried.append(key)
                secs[key] = s
            if r is not None:
                return r, key, tried, fallbacks, secs
            fallbacks.append(fb)
        return None, None, tried, fallbacks, secs


def _steps(ids, search):
    out = []
    if search == "agentic":
        out += [(b, "agentic") for b in ids if b in AGENTIC_BRAINS]
    return out + [(b, "bm25") for b in ids]


def run_chain(engine, steps):
    r, key, tried, fallbacks, secs = engine.chain(steps)
    if r is None:
        return _meta({"question": engine.question, "error": "no brain could answer"}, None, tried, fallbacks, secs)
    return _meta(r, key.split(":")[0], tried, fallbacks, secs)


def run_auto(question, chunks, brains, order, trace=None):
    """Try brains in order (bm25 chunks); a failure (not a refusal) falls back to the next one."""
    eng = Engine(question, brains, load_config(Path("/nonexistent")), lambda: chunks, trace)
    return run_chain(eng, _steps(order, "bm25"))


def answers_agree(a, b):
    """Two non-refused results agree if they both state numbers and one answer's numbers are a subset of the other's
    (the extra ones being added detail such as the period); if only one or neither states numbers, they must cite
    at least one common chunk. Any other case is a disagreement."""
    na, nb = jc.numbers_in(jc.CITE_RE.sub(" ", a["answer"])), jc.numbers_in(jc.CITE_RE.sub(" ", b["answer"]))
    if na and nb:
        return na <= nb or nb <= na
    ca = {(c.get("path"), c.get("section")) for c in a["citations"]}
    cb = {(c.get("path"), c.get("section")) for c in b["citations"]}
    return bool(ca & cb)


def _merge_citations(*results):
    """bm25: same chunk numbers for both brains -> merge by n. agentic: [n] is each brain's own quote number ->
    keep both lists, each citation tagged with its brain."""
    if any(r.get("search") == "agentic" for r in results):
        return [dict(c, brain=r.get("brain_id", "?")) for r in results for c in r["citations"]]
    seen, out = set(), []
    for r in results:
        for c in r["citations"]:
            if c["n"] not in seen:
                seen.add(c["n"])
                out.append(c)
    return sorted(out, key=lambda c: c["n"])


def run_council(question, chunks, brains, council, order, trace=None, search="bm25", engine=None):
    """Two brains answer independently (in parallel). A member's chain is [agentic, bm25] in agentic search, else
    [bm25]. Failed members are replaced by the next enabled brain in `order`. agree -> first member's answer (both
    listed); disagree -> both answers, 'Brains disagree'; one refused -> the other's answer marked 'one brain
    refused'; both refused -> refusal."""
    eng = engine or Engine(question, brains, load_config(Path("/nonexistent")), lambda: chunks, trace)
    members = [b for b in council if b in brains and brains[b].enabled][:2]
    spare = [b for b in order if b in brains and brains[b].enabled and b not in members]
    fallbacks = [{"brain": b, "reason": "disabled"} for b in council if b in brains and not brains[b].enabled]
    tried, secs, results, order_done = [], {}, {}, []

    def run(ids):
        out = {}

        def work(bid):
            out[bid] = eng.chain(_steps([bid], search))
        ths = [threading.Thread(target=work, args=(bid,)) for bid in ids]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        return out

    pending = list(members)
    while pending:
        out = run(pending)
        for bid in pending:
            r, key, t, fbs, s = out[bid]
            tried += t
            secs.update(s)
            fallbacks += fbs
            order_done.append(bid)
            if r is not None:
                results[bid] = r
        need = 2 - len(results)
        pending = []
        while need > 0 and spare:
            pending.append(spare.pop(0))
            need -= 1
    ids = [b for b in order_done if b in results]
    if not ids:
        return _meta({"question": question, "error": "no brain could answer"}, None, tried, fallbacks, secs)
    if len(ids) == 1:
        r = dict(results[ids[0]])
        r["council"] = {"members": ids, "agreement": "single (other brain failed)"}
        return _meta(r, ids[0], tried, fallbacks, secs)
    a, b = results[ids[0]], results[ids[1]]
    label = "+".join(ids)
    if a["refused"] and b["refused"]:
        r = dict(a)
        r["council"] = {"members": ids, "agreement": "both refused"}
        return _meta(r, label, tried, fallbacks, secs)
    if a["refused"] or b["refused"]:
        ok_id, ref_id = (ids[1], ids[0]) if a["refused"] else (ids[0], ids[1])
        r = dict(results[ok_id])
        r["answer"] = f"{r['answer']} (one brain refused: {ref_id})"
        r["council"] = {"members": ids, "agreement": "one brain refused", "refused": ref_id, "answered": ok_id}
        return _meta(r, ok_id, tried, fallbacks, secs)
    merged = {"question": question, "refused": False, "citations": _merge_citations(dict(a, brain_id=ids[0]), dict(b, brain_id=ids[1])),
              "unsupported_numbers": sorted(set(a["unsupported_numbers"]) | set(b["unsupported_numbers"])),
              "invalid_citations": a.get("invalid_citations", []) + b.get("invalid_citations", []),
              "quotes": a.get("quotes", []) + [q for q in b.get("quotes", []) if q not in a.get("quotes", [])],
              "model": f"{a['model']}+{b['model']}", "search": f"{a.get('search')}+{b.get('search')}"}
    if answers_agree(a, b):
        merged["answer"] = a["answer"]
        merged["council"] = {"members": ids, "agreement": "agree", "answers": {ids[0]: a["answer"], ids[1]: b["answer"]}}
    else:
        merged["answer"] = f"Brains disagree. {ids[0]}: {a['answer']} — {ids[1]}: {b['answer']}"
        merged["council"] = {"members": ids, "agreement": "disagree", "answers": {ids[0]: a["answer"], ids[1]: b["answer"]}}
    return _meta(merged, label, tried, fallbacks, secs)


def ask(question, index, mode="auto", cfg=None, brains=None, trace=None, search="bm25", agentic_fn=None):
    """Full pipeline. mode: a brain id, 'auto' or 'council'. search: 'bm25' (retrieve once, shared chunks) or
    'agentic' (codex/opencode search the corpus themselves; on reject/failure fall back to the next brain, then to
    bm25). Returns the result dict (with 'error' if no brain could answer)."""
    if search not in ("bm25", "agentic"):
        raise ValueError(f"unknown search '{search}' (bm25 or agentic)")
    if mode not in ("auto", "council") and mode not in (brains or ADAPTERS):
        raise ValueError(f"unknown brain '{mode}' (choose {', '.join(brains or ADAPTERS)}, auto, council)")
    cfg = cfg or load_config()
    brains = brains or make_brains(cfg)
    trace = trace if trace is not None else {}
    cache = {}

    def chunks_fn():
        if "c" not in cache:
            cache["c"] = jc.bm25_search(index, question)
            trace["retrieved"] = [f"{c['path']} § {c['section']}" for c in cache["c"]]
        return cache["c"]

    if search == "bm25" and not chunks_fn():
        r = jc._refused(question, "none (no chunk matched; no brain called)")
        r["search"] = "bm25"
        return _meta(r, None, [], [], {})
    eng = Engine(question, brains, cfg, chunks_fn, trace, agentic_fn)
    if mode == "council":
        return run_council(question, None, brains, cfg["council"], cfg["order"], trace, search, eng)
    ids = cfg["order"] if mode == "auto" else [mode]
    return run_chain(eng, _steps(ids, search))


def _probe(bid):
    cfg = load_config()
    b = make_brains(cfg)[bid]
    if isinstance(b, OmniRouteBrain):
        probs = b.problems()
        if probs:
            print(f"brain=omniroute NOT READY (nothing was called): " + "; ".join(probs))
            return 2
    t0 = time.monotonic()
    try:
        if b.mode == "two_step":
            out = b.chat([{"role": "user", "content": 'Reply with exactly {"ok": true}'}], json_mode=True)
        else:
            out = b.complete('Do not run any commands. Reply with exactly this JSON and nothing else: {"ok": true}')
        print(f"brain={bid} model={b.model} seconds={time.monotonic() - t0:.1f}")
        print(f"reply: {strip_tokens(out)[:500]}")
        print(f"parsed: {jc.extract_json(out)}")
        for s in getattr(b, "event_shapes", [])[:10]:
            print(f"event {s}")
        return 0
    except BrainError as e:
        print(f"brain={bid} ERROR after {time.monotonic() - t0:.1f}s: {e}")
        return 2


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--probe" and sys.argv[2] in ADAPTERS and sys.argv[2] != "claude":
        sys.exit(_probe(sys.argv[2]))
    print("usage: python3 -I src/jarvis/brains.py --probe <local|codex|opencode|omniroute>", file=sys.stderr)
    sys.exit(2)
