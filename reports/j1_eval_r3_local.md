# J1 evaluation (QA, independent)

Graded 2026-10-21T07:13:59Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset.json`. Index built_at 2026-10-20T08:06:20Z. Detail: `reports/j1_eval_r3_local.json`.

## Verdict: **FAIL**

Rule: >= 27/30 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | local |
| Time per question (mean / total s) | 17.8 / 534.2 |
| Score | 19/30 |
| single | 14/20 |
| multi | 0/5 |
| unanswerable | 5/5 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 3 |
| Numbers removed by the guard ('[number removed]' left in answers) | 3 |
| Answers that used a fallback brain | 0  |
| Search mode / answers produced by agentic search | (ask.py default) / 0 |
| Attempts rejected by the access audit | 0 |
| Audit logs checked by QA / accepted answers with outside access | 0 / 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **Q03** (single) How many predictors does the final dataset have? — refused an answerable question
- **Q06** (single) How many flights arrived 15 or more minutes late? — refused an answerable question
- **Q12** (single) Which source do the G8 weather forecasts come from? — missing facts ["MOS", ["Iowa Environmental Mesonet", "IEM"]]
- **Q13** (single) How many FAA NASR cycles were used for G1? — refused an answerable question
- **Q18** (single) What did I answer on the DuckDB install card? — missing facts ["I installed it"]
- **Q20** (single) How many Southwest (WN) flights were in the 36 BTS monthly files? — refused an answerable question
- **Q21** (multi) Do the F9, UA and WN counts from the BTS download add up to the number of flights in the master table? — missing facts [["7,121,934", "7121934"], ["4,249,769", "4249769"]]; no expected source cited (cited: docs/day1_prompt.md)
- **Q22** (multi) Why is Endeavor Air (9E) missing in 2025, and did I apply the 9E fix when I signed off Step 6? — missing facts ["voluntary", ["NOT applied", "not applied"]]
- **Q23** (multi) How early must a weather forecast run be before the cutoff, and how many MOS rows did we download? — missing facts [["6 h", "6 hours"]]
- **Q24** (multi) What did I tap on the Step 6 sign-off card, and how did the history features do in the past-flight-only check? — missing facts ["Sign off Step 6"]
- **Q25** (multi) Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? — missing facts ["T-100", "13.0%"]

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| Q01 | single | yes | 19.2 | all facts present; expected source cited |
| Q02 | single | yes | 11.5 | all facts present; expected source cited |
| Q03 | single | no | 9.1 | refused an answerable question |
| Q04 | single | yes | 13.8 | all facts present; expected source cited |
| Q05 | single | yes | 12.7 | all facts present; expected source cited |
| Q06 | single | no | 13.8 | refused an answerable question |
| Q07 | single | yes | 17.8 | all facts present; expected source cited |
| Q08 | single | yes | 19.5 | all facts present; expected source cited |
| Q09 | single | yes | 17.2 | all facts present; expected source cited |
| Q10 | single | yes | 19.4 | all facts present; expected source cited |
| Q11 | single | yes | 15.9 | all facts present; expected source cited |
| Q12 | single | no | 19.0 | missing facts ["MOS", ["Iowa Environmental Mesonet", "IEM"]] |
| Q13 | single | no | 11.4 | refused an answerable question |
| Q14 | single | yes | 23.9 | all facts present; expected source cited |
| Q15 | single | yes | 21.5 | all facts present; expected source cited |
| Q16 | single | yes | 23.7 | all facts present; expected source cited |
| Q17 | single | yes | 19.1 | all facts present; expected source cited |
| Q18 | single | no | 24.6 | missing facts ["I installed it"] |
| Q19 | single | yes | 12.2 | all facts present; expected source cited |
| Q20 | single | no | 13.5 | refused an answerable question |
| Q21 | multi | no | 24.3 | missing facts [["7,121,934", "7121934"], ["4,249,769", "4249769"]]; no expected source cited (cited: docs/day1_prompt.md) |
| Q22 | multi | no | 34.7 | missing facts ["voluntary", ["NOT applied", "not applied"]] |
| Q23 | multi | no | 20.6 | missing facts [["6 h", "6 hours"]] |
| Q24 | multi | no | 17.9 | missing facts ["Sign off Step 6"] |
| Q25 | multi | no | 33.9 | missing facts ["T-100", "13.0%"] |
| Q26 | unanswerable | yes | 13.5 | refused as expected |
| Q27 | unanswerable | yes | 5.8 | refused as expected |
| Q28 | unanswerable | yes | 21.8 | refused as expected |
| Q29 | unanswerable | yes | 9.7 | refused as expected |
| Q30 | unanswerable | yes | 13.2 | refused as expected |
