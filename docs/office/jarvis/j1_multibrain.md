# J1 round 2 — Jarvis multi-brain (work order)

Approved: Director in chat, 2026-10-19: "lets continue with jarvis brain lets dont constrain it to just u like multiple
brains any ai agent we have now". OmniRoute deferred (needs a security review + Mac install first).
Base: j1_work_order.md + j1_fix_round.md (index hygiene, retrieval, two-step quote→answer, guards: all kept).
Round-1 result: local qwen3 20/30 + holdout 6/10 (reports/j1_eval_r1.md). Weakness: multi-file 0/7, refuses answerable.

## 1. Brains (adapters; our code keeps retrieval + every guard, whichever brain answers)
| id | how | notes |
|---|---|---|
| `local` | Ollama qwen3-8b-32k (as now) | free, private, offline fallback |
| `codex` | `codex exec -s read-only -C <empty temp dir> --skip-git-repo-check --ephemeral -o <tmp file> "<prompt>"` | ChatGPT login; runs in an EMPTY temp folder so it can only use the chunks we give it |
| `opencode` | `opencode run [--dir <empty temp dir>] "<prompt>"` (default model; record which model it reports) | OpenAI login |
| `claude` | adapter written but **disabled**: this session's allow list does not include the claude CLI; the Director enables it at the Mac | never call it until enabled |
The brain sees only the question + the retrieved chunks (never file system access to the project). It must return the
same JSON as today (quotes with chunk ids, then answer). Timeouts (e.g. 120 s) → fall back to the next brain and record it.

## 2. Modes (`ask.py --brain <id|auto|council>`)
- `<id>`: that brain only.  `auto` (default): fallback order from `data/jarvis/brains.json` (start: codex → opencode → local).
- `council`: two brains answer independently; if both answer and the cited facts/numbers agree → answer (both listed);
  if they disagree → return both briefly with "brains disagree" (no silent pick); if one refuses → the other's answer,
  marked "one brain refused".
- Output adds `brain`, `brains_tried`, `fallbacks`, `seconds_per_brain`.

## 3. Rules
- Same guards for every brain (verbatim quotes, numbers in cited quotes, exact refusal).
- No secrets, keys or passwords in prompts or files; never print auth tokens. No flight data (data/ is not indexed).
- Data sent: question + retrieved project text only → OpenAI (codex/opencode). Logged per answer (`brain`).
- Phone-session tool rules. Do not edit tracker/. Tests with fake brains (no network) for adapters, fallback, council.
- Engineer must NOT read docs/office/jarvis/j1_testset*.json, reports/j1_eval*, data/jarvis/qa_raw*, src/validate/qa_j1_*.

## 4. QA
- New hidden set `j1_testset_holdout2.json` (10 questions, written before grading, never shown to the Engineer).
- Grade each brain (`--brain local|codex|opencode`) and `council` on main 30 + holdout + holdout2 → reports/j1_eval_r2_<brain>*.
- Pass (J1 done) for the chosen default: main ≥ 27/30, each holdout ≥ 9/10, 0 fabricated numbers, 0 secrets, 0 leaks.
  Report time per question per brain.
