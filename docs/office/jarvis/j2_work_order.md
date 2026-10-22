# Work order J2 — Jarvis morning briefing

Approved: Director in chat, 2026-10-19 ("lets go to next step"; J2 is on the agreed infra checklist).
Plan: docs/office/jarvis/jarvis_plan.md §4 (J2). J1 fix round deferred by the Director; J2 does not use J1.
Team: Engineer (Claude subagent) builds; QA (separate Claude subagent) checks every line against the files.

## 1. What J2 delivers
A short briefing the Director can read (later: hear, J3) — "Good morning. Here's FlightOps since <time>":
1. Mac / session: paused or running, last control action (artifacts/control.json).
2. Jobs: running / finished / failed since `--since` (progress.json `jobs` + their log files' last lines).
3. Waiting for you: the open decision card (id, question, choices) and open office inbox items (E-ids).
4. What happened: agent log entries since `--since` (kind + text), newest first, max 8.
5. Blocked items and warnings (progress.json `blockers`, `warnings`).
6. Next step: progress.json `agent.current_action` and checkpoint `next_steps[0]`.
7. Data health line: the last verified checkpoint line (`checkpoint.verified`): quoted, not re-measured.

## 2. Rules
- **No language model.** Plain deterministic code: every line is built from a field in a file.
- Every line carries its source: `{"text", "source": "<path>#<json key path or line>"}`.
- Missing / empty field → say so ("no open decision"), never guess. Times shown in UTC and New York time (Mac is UTC−4).
- Read-only: never writes progress.json, control.json or anything in tracker/.

## 3. Files (Engineer)
- `src/jarvis/briefing.py [--since <ISO UTC> | --hours N (default 12)] [--json] [--out]`
  → prints the briefing; `--json` prints `{"generated_at","since","sections":[{"title","lines":[{"text","source"}]}]}`;
  `--out` also writes `artifacts/briefing/latest.json` + `latest.md`.
- Tests `tests/test_jarvis_briefing.py` (unittest, temp folder fake project files: empty, paused, open card, failed job).
- Add a J2 section to `src/jarvis/README.md`.
- Phone-session tool rules as in J1 (python3 -I src/..., unittest discover, no inline python, no tracker/ edits).

## 4. QA (independent)
- Own checker `src/validate/qa_j2_check.py`: run `briefing.py --json --hours 48`; for EVERY line, open the cited source
  and confirm the text's facts (ids, numbers, statuses, times) are in that field. Also check: nothing invented when a field
  is empty (run against a copy with fields removed, in a temp folder, if the script supports a `--root` option).
- Report `reports/j2_check.md` + `.json`: lines checked, lines traced, mismatches. PASS = 100% lines traced, 0 mismatches,
  unit tests pass.

## 5. Not in J2
Showing it in the phone app (needs a render check of tracker/index.html: next small step after PASS), voice (J3),
Gmail/Calendar (not planned).
