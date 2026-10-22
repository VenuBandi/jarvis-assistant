# J1 evaluation (QA, independent)

Graded 2026-10-19T14:31:26Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset_holdout2.json`. Index built_at 2026-10-19T14:09:41Z. Detail: `reports/j1_eval_r2_local_holdout2.json`.

## Verdict: **FAIL**

Rule: >= 9/10 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | local |
| Time per question (mean / total s) | 12.7 / 127.0 |
| Score | 5/10 |
| single | 2/5 |
| multi | 1/3 |
| unanswerable | 2/2 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 0 |
| Numbers removed by the guard ('[number removed]' left in answers) | 0 |
| Answers that used a fallback brain | 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **K01** (single) How many United flights in July 2024 does the DuckDB example query return? — no expected source cited (cited: reports/dc2_qa.json)
- **K04** (single) How many checks passed in the DC-1 QA? — no expected source cited (cited: artifacts/progress.json)
- **K05** (single) How many Endeavor Air tail numbers were flying in December 2024? — refused an answerable question
- **K07** (multi) How many Endeavor Air flights per month were there in 2023, and which counts does the 9E gap lower according to the coverage matrix? — refused an answerable question
- **K08** (multi) Which source id is the TSA checkpoint data and which factors use it, and what is G3's planned status in the coverage matrix? — missing facts ["Validated Proxy"]

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| K01 | single | no | 19.2 | no expected source cited (cited: reports/dc2_qa.json) |
| K02 | single | yes | 11.2 | all facts present; expected source cited |
| K03 | single | yes | 13.1 | all facts present; expected source cited |
| K04 | single | no | 7.7 | no expected source cited (cited: artifacts/progress.json) |
| K05 | single | no | 10.9 | refused an answerable question |
| K06 | multi | yes | 17.3 | all facts present; expected source cited |
| K07 | multi | no | 15.2 | refused an answerable question |
| K08 | multi | no | 15.9 | missing facts ["Validated Proxy"] |
| K09 | unanswerable | yes | 9.3 | refused as expected |
| K10 | unanswerable | yes | 7.2 | refused as expected |
