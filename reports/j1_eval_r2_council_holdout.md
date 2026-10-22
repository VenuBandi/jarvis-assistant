# J1 evaluation (QA, independent)

Graded 2026-10-19T14:27:39Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset_holdout.json`. Index built_at 2026-10-19T14:09:41Z. Detail: `reports/j1_eval_r2_council_holdout.json`.

## Verdict: **FAIL**

Rule: >= 9/10 correct, 0 fabricated numbers, 0 secrets. Council rule: 'Brains disagree.' counts as correct only if EACH side (a and b) contains every expected fact (and an expected source is cited); a side missing a fact = contradicting itself on the asked fact = not correct; for an unanswerable question it is not a refusal = not correct.

| Item | Result |
|---|---|
| Brain | council |
| Time per question (mean / total s) | 6.4 / 63.6 |
| Score | 8/10 |
| single | 5/6 |
| multi | 1/2 |
| unanswerable | 2/2 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 5 |
| Numbers removed by the guard ('[number removed]' left in answers) | 2 |
| Answers that used a fallback brain | 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **H05** (single) What memory cap does each DuckDB connection get? — no expected source cited (cited: docs/platform/README.md)
- **H07** (multi) Which BTS table could add Endeavor Air back for 2025, and what is the source id of the BTS on-time monthly prezipped files? — missing facts ["Marketing Carrier On-Time Performance"]

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| H01 | single | yes | 6.2 | all facts present; expected source cited |
| H02 | single | yes | 5.0 | all facts present; expected source cited |
| H03 | single | yes | 4.7 | all facts present; expected source cited |
| H04 | single | yes | 5.0 | all facts present; expected source cited |
| H05 | single | no | 6.1 | no expected source cited (cited: docs/platform/README.md) |
| H06 | single | yes | 6.7 | all facts present; expected source cited |
| H07 | multi | no | 11.6 | missing facts ["Marketing Carrier On-Time Performance"] |
| H08 | multi | yes | 9.3 | all facts present; expected source cited |
| H09 | unanswerable | yes | 4.6 | refused as expected |
| H10 | unanswerable | yes | 4.4 | refused as expected |
