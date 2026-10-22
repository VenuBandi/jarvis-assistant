# J1 evaluation (QA, independent)

Graded 2026-10-19T14:22:29Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset_holdout.json`. Index built_at 2026-10-19T14:09:41Z. Detail: `reports/j1_eval_r2_opencode_holdout.json`.

## Verdict: **FAIL**

Rule: >= 9/10 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | opencode |
| Time per question (mean / total s) | 7.7 / 77.0 |
| Score | 8/10 |
| single | 5/6 |
| multi | 1/2 |
| unanswerable | 2/2 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 0 |
| Numbers removed by the guard ('[number removed]' left in answers) | 0 |
| Answers that used a fallback brain | 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **H05** (single) What memory cap does each DuckDB connection get? — no expected source cited (cited: docs/platform/README.md)
- **H07** (multi) Which BTS table could add Endeavor Air back for 2025, and what is the source id of the BTS on-time monthly prezipped files? — refused an answerable question

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| H01 | single | yes | 15.6 | all facts present; expected source cited |
| H02 | single | yes | 8.0 | all facts present; expected source cited |
| H03 | single | yes | 3.1 | all facts present; expected source cited |
| H04 | single | yes | 11.1 | all facts present; expected source cited |
| H05 | single | no | 8.9 | no expected source cited (cited: docs/platform/README.md) |
| H06 | single | yes | 4.6 | all facts present; expected source cited |
| H07 | multi | no | 3.5 | refused an answerable question |
| H08 | multi | yes | 13.1 | all facts present; expected source cited |
| H09 | unanswerable | yes | 5.8 | refused as expected |
| H10 | unanswerable | yes | 3.3 | refused as expected |
