# J1 evaluation (QA, independent)

Graded 2026-10-19T14:23:20Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset_holdout2.json`. Index built_at 2026-10-19T14:09:41Z. Detail: `reports/j1_eval_r2_opencode_holdout2.json`.

## Verdict: **FAIL**

Rule: >= 9/10 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | opencode |
| Time per question (mean / total s) | 5.1 / 50.9 |
| Score | 6/10 |
| single | 2/5 |
| multi | 2/3 |
| unanswerable | 2/2 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 6 |
| Numbers removed by the guard ('[number removed]' left in answers) | 6 |
| Answers that used a fallback brain | 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **K01** (single) How many United flights in July 2024 does the DuckDB example query return? — no expected source cited (cited: reports/dc2_qa.json)
- **K04** (single) How many checks passed in the DC-1 QA? — no expected source cited (cited: artifacts/progress.json)
- **K05** (single) How many Endeavor Air tail numbers were flying in December 2024? — refused an answerable question
- **K07** (multi) How many Endeavor Air flights per month were there in 2023, and which counts does the 9E gap lower according to the coverage matrix? — missing facts [["14,633", "14633"], ["18,121", "18121"]]

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| K01 | single | no | 6.6 | no expected source cited (cited: reports/dc2_qa.json) |
| K02 | single | yes | 4.8 | all facts present; expected source cited |
| K03 | single | yes | 3.6 | all facts present; expected source cited |
| K04 | single | no | 5.4 | no expected source cited (cited: artifacts/progress.json) |
| K05 | single | no | 4.3 | refused an answerable question |
| K06 | multi | yes | 9.9 | all facts present; expected source cited |
| K07 | multi | no | 3.9 | missing facts [["14,633", "14633"], ["18,121", "18121"]] |
| K08 | multi | yes | 3.6 | all facts present; expected source cited |
| K09 | unanswerable | yes | 4.2 | refused as expected |
| K10 | unanswerable | yes | 4.6 | refused as expected |
