# J1 evaluation (QA, independent)

Graded 2026-10-19T14:21:08Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset.json`. Index built_at 2026-10-19T14:09:41Z. Detail: `reports/j1_eval_r2_opencode.json`.

## Verdict: **FAIL**

Rule: >= 27/30 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | opencode |
| Time per question (mean / total s) | 6.0 / 179.4 |
| Score | 19/30 |
| single | 13/20 |
| multi | 1/5 |
| unanswerable | 5/5 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 7 |
| Numbers removed by the guard ('[number removed]' left in answers) | 7 |
| Answers that used a fallback brain | 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **Q03** (single) How many predictors does the final dataset have? — no expected source cited (cited: docs/office/direction_2026-10-19.md)
- **Q06** (single) How many flights arrived 15 or more minutes late? — missing facts [["1,526,473", "1526473"]]; no expected source cited (cited: artifacts/progress.json)
- **Q11** (single) What does the G2 ground handling proxy actually measure? — no expected source cited (cited: artifacts/progress.json)
- **Q12** (single) Which source do the G8 weather forecasts come from? — missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: artifacts/progress.json, docs/registry/g_factor_coverage.csv)
- **Q13** (single) How many FAA NASR cycles were used for G1? — no expected source cited (cited: artifacts/progress.json)
- **Q18** (single) What did I answer on the DuckDB install card? — refused an answerable question
- **Q20** (single) How many Southwest (WN) flights were in the 36 BTS monthly files? — refused an answerable question
- **Q21** (multi) Do the F9, UA and WN counts from the BTS download add up to the number of flights in the master table? — missing facts [["4,249,769", "4249769"]]
- **Q22** (multi) Why is Endeavor Air (9E) missing in 2025, and did I apply the 9E fix when I signed off Step 6? — missing facts ["voluntary"]
- **Q24** (multi) What did I tap on the Step 6 sign-off card, and how did the history features do in the past-flight-only check? — refused an answerable question
- **Q25** (multi) Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? — missing facts ["13.0%"]; no expected source cited (cited: artifacts/progress.json)

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| Q01 | single | yes | 4.2 | all facts present; expected source cited |
| Q02 | single | yes | 5.6 | all facts present; expected source cited |
| Q03 | single | no | 4.5 | no expected source cited (cited: docs/office/direction_2026-10-19.md) |
| Q04 | single | yes | 2.5 | all facts present; expected source cited |
| Q05 | single | yes | 4.3 | all facts present; expected source cited |
| Q06 | single | no | 4.5 | missing facts [["1,526,473", "1526473"]]; no expected source cited (cited: artifacts/progress.json) |
| Q07 | single | yes | 3.4 | all facts present; expected source cited |
| Q08 | single | yes | 9.0 | all facts present; expected source cited |
| Q09 | single | yes | 5.7 | all facts present; expected source cited |
| Q10 | single | yes | 3.5 | all facts present; expected source cited |
| Q11 | single | no | 5.6 | no expected source cited (cited: artifacts/progress.json) |
| Q12 | single | no | 9.8 | missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: artifacts/progress.json, docs/registry/g_factor_coverage.csv) |
| Q13 | single | no | 4.7 | no expected source cited (cited: artifacts/progress.json) |
| Q14 | single | yes | 4.3 | all facts present; expected source cited |
| Q15 | single | yes | 3.5 | all facts present; expected source cited |
| Q16 | single | yes | 7.6 | all facts present; expected source cited |
| Q17 | single | yes | 4.5 | all facts present; expected source cited |
| Q18 | single | no | 2.8 | refused an answerable question |
| Q19 | single | yes | 2.8 | all facts present; expected source cited |
| Q20 | single | no | 4.2 | refused an answerable question |
| Q21 | multi | no | 6.3 | missing facts [["4,249,769", "4249769"]] |
| Q22 | multi | no | 5.7 | missing facts ["voluntary"] |
| Q23 | multi | yes | 11.8 | all facts present; expected source cited |
| Q24 | multi | no | 4.4 | refused an answerable question |
| Q25 | multi | no | 15.5 | missing facts ["13.0%"]; no expected source cited (cited: artifacts/progress.json) |
| Q26 | unanswerable | yes | 13.8 | refused as expected |
| Q27 | unanswerable | yes | 2.6 | refused as expected |
| Q28 | unanswerable | yes | 2.8 | refused as expected |
| Q29 | unanswerable | yes | 7.1 | refused as expected |
| Q30 | unanswerable | yes | 12.4 | refused as expected |
