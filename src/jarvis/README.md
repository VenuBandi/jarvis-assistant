# Jarvis J1 — project brain (answers with sources)

Jarvis answers questions about FlightOps AI using only allowlisted project files, and names the file and section
for every claim. It runs fully local (Ollama `qwen3-8b-32k` at 127.0.0.1:11434). Standard library only.

## Usage (from the project root)
- Rebuild the index: `python3 -I src/jarvis/build_index.py`
- Ask: `python3 -I src/jarvis/ask.py "What is the T-24h rule?"` (add `--json` for machine output)
- Tests: `python3 -m unittest discover -s tests -q` (Jarvis tests: `tests/test_jarvis_core.py`, fake LLM, no network)

`--json` output: `{"question","answer","citations":[{"n","path","section"}],"refused","unsupported_numbers","model",
"invalid_citations","quotes":[{"n","quote"}],"rejected_quotes"}`. `python3 -I src/jarvis/ask.py --models` lists the
installed Ollama models (read-only `/api/tags`); `--search` prints the scored retrieval pool without calling the model;
`--debug` prints retrieved chunks and raw model output to stderr.
Exit code 2 with a clear error if the index is missing or the local model is unavailable (no fallback answer).
Two model calls per answered question (quotes, then answer); one when no verified quote is found.

## Brains (round 2, docs/office/jarvis/j1_multibrain.md; `brains.py`, config `data/jarvis/brains.json`)
`ask.py --brain <id|auto|council>` (default `auto`). Retrieval runs once; every brain gets only the question +
the 8 retrieved chunks, and every guard below applies to every brain.
- `local` — Ollama `qwen3-8b-32k`, two calls (quotes, then answer). Free, private, offline.
- `codex` — `codex exec -s read-only -C <empty temp dir> --skip-git-repo-check --ephemeral --color never -o <file in
  that dir> -` (prompt on stdin). One call returning `{"quotes", "answer"}`.
- `opencode` — `opencode run --dir <empty temp dir> --format json "<prompt>"`; text parts of the JSON events are the
  reply. Its events name the provider (`openai`) but not the model, so `model` shows `opencode:openai/model-not-reported`.
- `omniroute` — local OmniRoute gateway (docs/office/omniroute/setup.md, S3): OpenAI-compatible
  `POST <base_url>/v1/chat/completions` (stdlib urllib, no proxies, redirects refused), same one-call prompt and
  guards, bm25 mode only. Config `brains.omniroute` = `{"enabled": false, "base_url": "http://127.0.0.1:20128",
  "model": null, "timeout": 120}`; only http://127.0.0.1 / localhost allowed. Key read at call time from
  `~/.config/flightops/omniroute_key` (must exist, be non-empty, mode 600); never printed/logged/returned (scrubbed
  from errors and replies, dropped after the call). In `order` after codex/opencode, before local; disabled until the
  Director finishes S1–S2 and sets a model. `brains.py --probe omniroute` lists what is missing without calling
  anything. Tests: `tests/test_jarvis_omniroute.py` (fake 127.0.0.1 server).
- `claude` — adapter written, **disabled** (`enabled: false`); never called until the Director enables it.
- `auto` — try `order` (codex → opencode → local); timeout (120 s for CLIs, 300 s local), crash, missing CLI or a
  reply with no JSON → next brain, recorded in `fallbacks`. A refusal is an answer, not a failure.
- `council` — the two `council` brains (codex, opencode) run in parallel; a failed member is replaced by the next
  enabled brain in `order`. Both answer and agree (same numbers, or one answer's numbers a subset of the other's; with
  no numbers on one side, a common cited chunk) → first member's answer; disagree → "Brains disagree. a: … — b: …";
  one refused → the other's answer + "(one brain refused: <id>)"; both refused → the refusal. Details in `council`.
- Extra output keys: `brain`, `brains_tried`, `fallbacks` (`[{brain, reason}]`), `seconds_per_brain`, `council`.
- CLI output is cleaned of anything token-like (API keys, JWTs, bearer tokens, private keys) and colour codes; a
  prompt matching a secret pattern is never sent. Data sent to OpenAI (codex/opencode): the question + retrieved
  project text only (data/ is never indexed).
- Probe a brain: `python3 -I src/jarvis/brains.py --probe <local|codex|opencode>`.
- Tests: `tests/test_jarvis_brains.py` (fake brains and fake subprocess runners; no network).

## Agentic search (round 3, docs/office/jarvis/j1_round3_agentic.md; `agentic.py`, `corpus_build.py`)
`ask.py "<q>" --brain codex|opencode|auto|council --search agentic` (default stays `--search bm25`; a bare `--search`
with no value still prints the BM25 score listing).
- **Corpus** `python3 -I src/jarvis/corpus_build.py` → `data/jarvis/corpus/`: only the allowlist (same rules and
  exclusions as the index), progress.json pruned like the index, every line matching a secret pattern replaced by
  `[removed: secret pattern]`. Manifest `data/jarvis/corpus/_corpus_manifest.json`: sha256 of each source and copy,
  bytes, secret lines removed. Copies of files that left the allowlist are deleted. `ask.py --search agentic` warns
  when sources changed since the snapshot.
- **Run**: codex `exec -s read-only -C data/jarvis/corpus --skip-git-repo-check --ephemeral --color never --json -o
  <file in a temp dir outside the corpus> -`; opencode `run --dir data/jarvis/corpus --format json "<prompt>"`.
  Working dir = the corpus; timeout 180 s (`agentic_timeout_s`). The prompt allows only relative paths and read-only
  commands and asks for `{"quotes":[{"path","quote"}],"answer"}` with `[n]` = quote number.
- **Access audit (the real enforcement — Codex's read-only sandbox does not stop reads elsewhere)**: every
  command / tool call in the event log is parsed (`/bin/zsh -lc '…'` wrappers unwrapped, split on `; && || |`).
  Rejected: any path that resolves outside the corpus (absolute, `..`, symlinks resolved), `~`, `$VAR`/`${…}`/`$(…)`/
  backticks, heredocs, `cd` out, a working dir outside the corpus, programs not on the read-only list (ls, find, rg,
  grep, cat, head, tail, sed, wc, sort, uniq, cut, nl, tr, …), network tools (curl, wget, nc, ssh, git, pip, open, …),
  writes (`>`/`>>` except to /dev/null, tee, rm, mv, cp, touch, `sed -i`, `find -exec/-delete`), interpreters
  (python, node, awk, nested shells), codex `file_change`/`web_search`/unknown items, opencode write/edit/webfetch/
  task/unknown tools. Any violation → answer REJECTED (`rejected_reason: "access outside corpus"`), fallback, and the
  log `data/jarvis/audit/<UTC>_<brain>_<id>.json` (question, commands, violations, verdict, reply, events —
  token-scrubbed) is kept for every agentic answer, accepted or not.
- **Quote guard**: each quote's path must resolve inside the corpus, be in the manifest (not the manifest itself),
  the copy's sha must equal the manifest's, and the quote must occur verbatim (case/space/dash-normalised). Failing
  quotes are dropped (`dropped_quotes` with reasons); `[n]` to a dropped quote is removed; numbers must be in kept
  quotes (path/heading numbers do not count) else `[number removed]` + "(unverified)". Citation `section` = the
  Markdown heading above the quote, `(file)` otherwise.
- **Fallback**: `--brain codex` → codex agentic, then codex bm25. `auto` → codex agentic, opencode agentic, then
  codex/opencode/local bm25. `council` → each member's chain is agentic then bm25; agentic council citations carry
  `brain` (each brain numbers its own quotes). Keys: `search`, `audit` (log, commands), `brains_tried`
  (`codex:agentic`), `fallbacks` (with `audit_log`, `rejected_reason`).
- Probe: `python3 -I src/jarvis/agentic.py --probe codex|opencode` (raw event log → `data/jarvis/audit/probe_*.jsonl`).
- Tests: `tests/test_jarvis_agentic.py` (fake event logs: inside/outside access, network, writes, bad quotes, sha
  mismatch, fallback chains, council).
- All prompts (bm25 one-call, local, agentic) say: split multi-part questions and answer every part, say which part
  the files do not cover, refuse only if no part can be answered, prefer full-period totals with their scope. Only the
  full refusal sentence (or an answer starting "I don't know") counts as a refusal.
- Exclusions now cover all `reports/j1_*` (and `src/validate/qa_*`) in both the index and the corpus.
- **Not-in-files answers** (Lead rule, all prompts + code): if the asked value is not in the files (also when the
  files only say it does not exist yet), the answer must begin with the exact refusal sentence and may add ONE short
  cited context sentence. Code: such an answer → `refused: true`; the first context sentence after the refusal is
  kept only if it has a valid citation (quote-checked, number-guarded); anything after it is cut. A refusal sentence
  that is not at the start still gives the plain refusal. Multi-part answers that say one part is not in the files
  are not refusals.
- **Audit limit**: the audit sees only the agent's own commands/tool calls. The codex/opencode CLIs may load their
  own login/config files and instruction files (e.g. CLAUDE.md / AGENTS.md from the repo root, since the corpus is
  inside the repo) without an event; none of those contain project data beyond what the corpus already holds.

## How it works (fix round 1, docs/office/jarvis/j1_fix_round.md)
1. **Index** (`build_index.py` → `data/jarvis/index.json`, `data/jarvis/index_manifest.json`).
   Allowlist: `docs/**/*.md`, `docs/registry/*.csv`, `reports/*.md|json|csv` (files > 2 MB skipped),
   `artifacts/progress.json`, `artifacts/decisions/*.json`, `src/jarvis/README.md`, `CLAUDE.md`.
   Never indexed: `config/`, `supabase/`, `data/`, `ios/`, `tracker/`, `.claude/`, `artifacts/chat.jsonl`,
   `artifacts/answers.jsonl`, `*.docx`, logs, and evaluation material: `reports/j1_eval*`, `reports/j2_check*`,
   `reports/j5_check*`, `docs/office/jarvis/j1_testset*`, `data/**` (manifest `excluded_globs`).
   - progress.json is pruned before chunking: `agent.galaxy`, `agent.briefing`, `agent.log` older than the last 30
     entries, list values inside `agent.datacenter` (manifest `progress_pruned`).
   - Markdown: split by heading; `section` = heading path (`A > B`); chunks ≤ 1,500 chars, long sections split with
     200-char overlap. Headings inside code fences are ignored.
   - CSV: one row per chunk (`col: value; ...`); `section` = first column value.
   - JSON: one record per chunk as `key: value` lines (scalars, lists of scalars, small flat dicts); nested records
     get their own chunk. `section` is a readable path: `milestones › M5 › tasks › M5.3`; list items are labelled by
     `id`, `name`, `title`, `source_id`, `feature_id`, `factor`, `column`, `gate`, `t`/`timestamp`, else index. A
     decision file's root is labelled by its `id`.
   - Secrets guard: any chunk matching `sb_secret_`, `service_role`, `eyJ` or `BEGIN PRIVATE KEY` is dropped and
     counted (`skipped_secret_chunks` in the manifest, total and per file).
   - Aliases (stored in the index, count in manifest `alias_rules`), built from the project's own files:
     `Name (XX)` carrier mentions (XX in `project.airlines` or a name with "Air") → code ↔ name; factor ids ↔
     titles from `g_factor_coverage.csv` and progress.json `factors[]`; a small fixed delay vocabulary
     (late ↔ ArrDel15 / "15 minutes").
2. **Retrieve**: BM25 (k1 = 1.5, b = 0.75). The chunk's own heading (last Markdown heading, or last two JSON path
   parts / CSV first column) gets +2 per token; file path tokens count once. Tokenizer keeps ids (G1–G12,
   M0–M6, J1, C1, 9E, 24h), decision ids (`D-...`), numbers with commas removed (`7,121,934` = `7121934`),
   splits `snake_case` and strips simple plurals. Query terms weight 1, alias expansions 0.4. Top 20 candidates
   are re-ranked: each chunk already taken from a file scales that file's next score by 0.7, max 3 per file while
   other files have candidates → top 8. No embeddings (no embedding model installed in Ollama).
3. **Answer, two steps** (local `qwen3-8b-32k`): (a) JSON mode: copy verbatim quotes with chunk numbers; code keeps
   only quotes found word-for-word in their chunk (case/whitespace/dash-insensitive) — none left → refused, no
   second call; (b) answer only from the quotes, `[n]` after every sentence, copy numbers, prefer totals over
   samples/pilots, state scope (period, carrier) of each number.
4. **Guards (in code)**: `[n]` must point at a quoted chunk (others removed, listed in `invalid_citations`); no valid
   citation → refused. If the answer contains the refusal sentence (or starts with "I don't know") → exactly the
   refusal, `refused: true`, no citations. Every number in the answer must appear in a cited quote (or the cited
   chunk's path/section); otherwise it is replaced by `[number removed]`, listed in `unsupported_numbers`, and the
   answer ends with "(unverified)". Digits glued to a letter (G12, M5.3, S02) are ids, not numbers.
5. **Freshness**: `ask.py` warns on stderr if any indexed file's sha256 differs from the manifest. Rebuild to fix.

## Files
- `jarvis_core.py` — chunking, tokenizer, aliases, BM25 + re-rank, prompts, quote check, guards
- `build_index.py` — builds the index and manifest
- `ask.py` — CLI; Ollama call (same pattern as `tracker/agent_brain.py`, `think: false`; `format: json` for step a)

## Limits
- Lexical retrieval only (no embeddings): questions phrased very differently from the files may miss.
- The number guard checks digits only; numbers written as words are not checked.
- The model may still pick or paraphrase wrongly; quotes and citations let you check every sentence.

# Jarvis J2 — morning briefing (no language model)

Work order: `docs/office/jarvis/j2_work_order.md`. Plain deterministic code (standard library only); every line is
built from one field in one file and carries its source.

## Usage (from the project root)
- `python3 -I src/jarvis/briefing.py` — text briefing for the last 12 hours
- Options: `--since <ISO, UTC if no offset>` or `--hours N` (default 12); `--json`; `--out` (also writes
  `artifacts/briefing/latest.json` + `latest.md`); `--root <dir>` (default: project root from the script's location;
  used by tests/QA on fake project folders). Exit 2 on a bad `--since` or missing `--root` folder.
- Tests: `tests/test_jarvis_briefing.py` (temp folders: empty project, empty fields, paused, open/answered card,
  failed/finished/missing job logs, CLI writes only the two briefing files).

`--json`: `{"generated_at","since","sections":[{"title","lines":[{"text","source"}]}]}`.
Source formats: `<path>#<json key path>` (e.g. `artifacts/progress.json#agent.log[133]`), `<path>#L<n>` (line in a
text file), `<path>#mtime` (file modification time). Times are shown in UTC and America/New_York.

## Sections and fields read (read-only)
1. Mac / session — `control.json` `paused`, last `history[]` entry, count of `history` entries since `--since`;
   `progress.json` `agent.state`, `updated_at`.
2. Jobs — `progress.json` `jobs.<id>.title/log`; last non-empty line of each log: `traceback|error|failed|failure|
   exception` → failed, starts with `done|finished|complete(d)` → finished, otherwise "status not recorded"
   ("running" is never claimed: no process check). Log mtime vs `--since`. `agent.datacenter.last_job_runs[]` started
   since `--since`. Log paths outside the root are treated as not found.
3. Waiting for you — `progress.json` `decision` (id, gate, question, choices, created_at); a card whose id has an
   answer in `artifacts/answers.jsonl` is reported as answered (same rule as `tracker/agent.py`). Inbox:
   `agent.office.inbox[]` with `status` "open" (missing status is shown as "status not recorded").
4. What happened — `agent.log[]` entries with `t` ≥ `--since`, newest first, max 8 (kind + text).
5. Blocked items and warnings — top-level `blockers[]`, `warnings[]` (a missing field is said explicitly).
6. Next step — `agent.current_action`, `checkpoint.next_steps[0]` (with `checkpoint.written_at`).
7. Data health — `checkpoint.verified`, quoted, not re-measured.

Long texts are shortened to 280 characters (400 for the verified line) with "…"; the shown text is always a prefix of
the field (whitespace collapsed). Never writes progress.json, control.json or tracker/.

# Jarvis J5 — FlightOps Galaxy (3D project map)

Work order: `docs/office/jarvis/j5_work_order.md`. Standard library only; the layout is computed once in Python
(fixed seed), so the phone only draws.

## Usage (from the project root)
- `python3 -I src/jarvis/galaxy_build.py` — summary (counts by type, links, skipped references, size)
- `--json` prints the graph; `--root <dir>` builds from another folder (tests/QA);
  `--out` writes `artifacts/galaxy/galaxy.json`, then runs `python3 tracker/agent_update.py galaxy artifacts/galaxy/galaxy.json`
  (only if that script exists under `--root`), so the app gets it as `agent.galaxy`. Exit 2 if secret-like text
  (`sb_secret_`, `service_role`, `eyJ`, `BEGIN PRIVATE KEY`) would be written.
- Tests: `tests/test_jarvis_galaxy.py` (temp folders: node/link extraction, skipped counts, determinism,
  no `.parquet` file opened, `--out` + agent_update call, secret guard).

Output (`artifacts/galaxy/galaxy.json`, format `"compact-1"`):
`{"built_at","format":"compact-1","counts":{<type>: n, "links", "skipped_refs"},"skipped_by_kind":{<kind>: n},"nodes":[...],"links":[[i,j,kind,src],...]}`.
`i`, `j` are 0-based indexes into `nodes`; node order is fixed by the builder (records first, then files in sorted
order), so match nodes by `id`, not by index, across builds.

### compact-1 → full form (what `expand()` in `galaxy_build.py` does)
The full form of a node is `{"id","type","label","path","src","x","y","z","deg"}`. In the file a node always has
`id`, `type`, `x`, `y`, `z` (coordinates rounded to 1 decimal); the other fields are left out only when they equal
their default:

| field | file types: `data`, `script`, `doc`, `decision` | record types: `step`, `factor`, `feature`, `source`, `agent` |
|---|---|---|
| `path` | missing → `id` (the file's relative path) | missing → `""` (records have no file node of their own) |
| `label` | missing → file name of `id` (text after the last `/`) | always present |
| `src` | missing → `id + "#file"` | always present (`<file>#<where>`) |
| `deg` | never stored → number of links in which the node is `i` or `j` | same |

A field that is present is used as is (e.g. a decision's `src` is `<path>#id` and its `label` is the card id, so both
are stored).

Links: `src` is either a full `"<file>#<where>"`, or starts with `"#"`, meaning it is in the same file as the link's
first node `i`. Then the full src = `file_of(nodes[i]) + src`, where `file_of(node)` = the node's full `path` if not
empty, else the part of its full `src` before the first `#`. Example: `[28,265,"output","#agent.office.workers[0].outputs[1].path"]`
with node 28 an agent (src `artifacts/progress.json#agent.office.workers[0]`) → `artifacts/progress.json#agent.office.workers[0].outputs[1].path`.

`<where>` forms: `<json key path>` (e.g. `milestones[0].tasks[2].evidence[0]`), `<first column value>.<column>` for
CSV rows (e.g. `G3_lag_route_seats.g_category`), `L<n>` for a line in a text file, `file` for the file itself,
`id` for a decision's `id` field. `path` is set for file nodes only; record nodes keep their file in `src`.

## Nodes (type ← file)
step ← progress.json `milestones[]` + `agent.plan[]` · factor ← `factors[]` · agent ← `agent.office.workers[]` ·
feature ← `docs/registry/data_dictionary.csv` `feature_id` · source ← `docs/registry/source_registry.csv` `source_id` ·
data ← `data/features/*.parquet`, `data/processed/*.parquet` (file names only, never opened) · script ← `src/**/*.py`
(not `test_*.py`) · doc ← `docs/**/*.md`, `reports/*.md` · decision ← `artifacts/decisions/*.json`.

## Links (kind ← where the file says so; `src` names the field / row / line)
factor: feature → factor (`g_category`) · raw_source: feature → source (`raw_source` naming `S<nn>`) ·
source: factor → source (coverage `primary_sources`, registry `factors`) · evidence: step → task `evidence[]`,
factor → `factors[].evidence[]`, decision → `evidence[].path` · plan: plan item → milestone named "(M<n>)" in its title ·
output: agent → `outputs[].path` · uses: script → data file whose name appears in the script text (`#L<line>`) ·
names: doc → file it names (relative path, or a backticked bare file name that only one node has; `#L<line>`).
A reference that does not resolve to a node (missing file, or a file that is not in the map such as `reports/*.json`,
`tracker/…`, raw data) is skipped and counted per kind in `skipped_by_kind`. Two of these kinds go beyond the work
order's list: factor → evidence and plan → milestone (both read from progress.json fields).

## App (staged page `tracker/index_stage_galaxy.html`)
"Galaxy" card on Home and Data → full-screen canvas overlay (own 3D projection, no libraries): drag rotate,
wheel/pinch zoom, tap select; live force sim from the given x,y,z with Repel / Link length sliders (runs only while
open and visible); panel with search, inspector, Trace path (BFS shortest path), top hubs, type filter with counts;
Jarvis dial with `agent.state` and "brain: none (J1 not connected)". Each briefing line has "show in galaxy": flies to
the node whose `path` equals the source file; for files with no node of their own (e.g. progress.json) it highlights
the record nodes whose `src` is in that file.
