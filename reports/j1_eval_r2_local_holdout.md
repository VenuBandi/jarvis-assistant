# J1 evaluation (QA, independent)

Graded 2026-10-19T14:42:46Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset_holdout.json`. Index built_at 2026-10-19T14:09:41Z. Detail: `reports/j1_eval_r2_local_holdout.json`.

## Verdict: **FAIL**

Rule: >= 9/10 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | local |
| Time per question (mean / total s) | 17.5 / 174.7 |
| Score | 6/10 |
| single | 4/6 |
| multi | 0/2 |
| unanswerable | 2/2 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 0 |
| Numbers removed by the guard ('[number removed]' left in answers) | 0 |
| Answers that used a fallback brain | 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **H01** (single) How many F9, UA and WN departures were there in 2024 in the Endeavor Air impact study? — refused an answerable question
- **H05** (single) What memory cap does each DuckDB connection get? — refused an answerable question
- **H07** (multi) Which BTS table could add Endeavor Air back for 2025, and what is the source id of the BTS on-time monthly prezipped files? — missing facts ["Marketing Carrier On-Time Performance"]
- **H08** (multi) How many T-100 rows were downloaded for 2025, and how far back do the G3 demand features look? — refused an answerable question

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| H01 | single | no | 26.5 | refused an answerable question |
| H02 | single | yes | 13.1 | all facts present; expected source cited |
| H03 | single | yes | 13.7 | all facts present; expected source cited |
| H04 | single | yes | 22.1 | all facts present; expected source cited |
| H05 | single | no | 14.3 | refused an answerable question |
| H06 | single | yes | 10.3 | all facts present; expected source cited |
| H07 | multi | no | 31.9 | missing facts ["Marketing Carrier On-Time Performance"] |
| H08 | multi | no | 16.1 | refused an answerable question |
| H09 | unanswerable | yes | 17.8 | refused as expected |
| H10 | unanswerable | yes | 8.9 | refused as expected |
