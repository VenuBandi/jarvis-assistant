# Work order J1 — Jarvis project brain (answers with sources)

Approved: Director in chat, 2026-10-19 ("yes list is good start J1 now"). Plan: docs/office/jarvis/jarvis_plan.md §4.
Defaults chosen by the Lead (Director can change): local model only (Ollama `qwen3-8b-32k`, as tracker/agent_brain.py);
personality calm + short; no humor yet.
Team: Engineer (Claude subagent) builds; QA (separate Claude subagent) writes the test set and grades. QA never
reuses Engineer code; the Engineer never reads the test set.

## 1. What J1 delivers
A question → answer tool that uses only project files and names the file + section for every claim.
- `src/jarvis/build_index.py` → `data/jarvis/index.json` + `data/jarvis/index_manifest.json`
  (files indexed, chunk count, sha256 per file, built_at UTC).
- `src/jarvis/ask.py "<question>" [--json]` → answer text + citations; `--json` prints
  `{"question","answer","citations":[{"n","path","section"}],"refused":bool,"unsupported_numbers":[...],"model"}`.
- `src/jarvis/README.md` (how it works, how to rebuild).
- Unit tests `tests/test_jarvis_*.py` (unittest, fake LLM; no network).

## 2. Knowledge allowed (allowlist) — everything else is excluded
- `docs/**/*.md`, `docs/registry/*.csv`
- `reports/*.md`, `reports/*.json`, `reports/*.csv` (skip any file > 2 MB)
- `artifacts/progress.json` (split by section: project, each milestone, each factor, agent plan/notes/log, decision,
  checkpoint, office), `artifacts/decisions/*.json`
- `src/jarvis/README.md`, `CLAUDE.md` (read-only; never edited)
Never index: `config/`, `supabase/`, `data/`, `ios/`, `tracker/`, `.claude/`, `artifacts/chat.jsonl`, `artifacts/answers.jsonl`, `*.docx`, logs, anything
matching key/secret patterns (`sb_secret_`, `service_role`, `eyJ`, `BEGIN PRIVATE KEY`) → skip the chunk and count it
in the manifest.

## 3. How (Engineer)
- Chunking: Markdown by heading (keep heading path as `section`, ≤ 1,500 chars, split long sections with overlap);
  CSV one row per chunk (`section` = first column value); JSON by key path (`section` = key path).
- Retrieval: BM25 in pure Python standard library (no new packages). Top 8 chunks. Keep factor ids (G1–G12), step ids
  (M0–M6, J1, C1), decision ids (D-…) and numbers as tokens.
- Answer: send the numbered chunks to the local model with rules: answer only from chunks, put `[n]` after every
  sentence, if the chunks don't contain the answer reply exactly "I don't know — it isn't in the project files." and nothing else.
- Guards after the model (in code, not trust): every `[n]` must exist; every number in the answer must appear in a
  cited chunk, otherwise list it in `unsupported_numbers` and append "(unverified)"; no citation at all → refused.
- Model unavailable → clear error, no fallback answer.
- Freshness: `ask.py` warns if any indexed file's sha256 differs from the manifest.
- Phone-session rules: write scripts to files; run `python3 -I src/...`; tests `python3 -m unittest discover -s tests -q`;
  no `cd &&`, no inline python, no pip installs.
- Do NOT edit tracker/ (live chat). Integration into tracker/agent_brain.py is a separate step after QA passes.

## 4. QA (independent)
- Before reading any Engineer code: write `docs/office/jarvis/j1_testset.json` — 30 questions from the allowed files:
  20 single-fact (numbers, statuses, sources, rules), 5 multi-file, 5 not answerable from the files.
  Each: `id`, `question`, `expected_facts` (short strings that must appear), `sources` (paths), `answerable`.
- Grader `src/validate/qa_j1_grade.py` (QA's own code): runs `src/jarvis/ask.py --json` per question → `reports/j1_eval.json`
  + `reports/j1_eval.md`.
- Pass (J1 done): ≥ 27/30 correct (answerable: all expected facts present AND at least one expected source cited;
  not answerable: refused); **0 fabricated numbers** (a number not in any cited chunk, after the guard); 0 secrets in the index.

## 5. Done when
QA verdict PASS in reports/j1_eval.md, unit tests pass, Lead review, Director sees the result card.
