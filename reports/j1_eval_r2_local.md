# J1 evaluation (QA, independent)

Graded 2026-10-19T14:39:51Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset.json`. Index built_at 2026-10-19T14:09:41Z. Detail: `reports/j1_eval_r2_local.json`.

## Verdict: **FAIL**

Rule: >= 27/30 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | local |
| Time per question (mean / total s) | 16.5 / 494.7 |
| Score | 20/30 |
| single | 15/20 |
| multi | 0/5 |
| unanswerable | 5/5 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 1 |
| Numbers removed by the guard ('[number removed]' left in answers) | 1 |
| Answers that used a fallback brain | 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **Q03** (single) How many predictors does the final dataset have? — refused an answerable question
- **Q06** (single) How many flights arrived 15 or more minutes late? — refused an answerable question
- **Q12** (single) Which source do the G8 weather forecasts come from? — missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: artifacts/progress.json)
- **Q13** (single) How many FAA NASR cycles were used for G1? — refused an answerable question
- **Q20** (single) How many Southwest (WN) flights were in the 36 BTS monthly files? — refused an answerable question
- **Q21** (multi) Do the F9, UA and WN counts from the BTS download add up to the number of flights in the master table? — missing facts [["4,249,769", "4249769"]]
- **Q22** (multi) Why is Endeavor Air (9E) missing in 2025, and did I apply the 9E fix when I signed off Step 6? — missing facts ["voluntary"]; no expected source cited (cited: artifacts/decisions/D-next-after-floor2.json, artifacts/decisions/D-step6-signoff.json)
- **Q23** (multi) How early must a weather forecast run be before the cutoff, and how many MOS rows did we download? — refused an answerable question
- **Q24** (multi) What did I tap on the Step 6 sign-off card, and how did the history features do in the past-flight-only check? — missing facts ["Sign off Step 6"]
- **Q25** (multi) Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? — refused an answerable question

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| Q01 | single | yes | 13.4 | all facts present; expected source cited |
| Q02 | single | yes | 12.9 | all facts present; expected source cited |
| Q03 | single | no | 8.8 | refused an answerable question |
| Q04 | single | yes | 13.7 | all facts present; expected source cited |
| Q05 | single | yes | 13.3 | all facts present; expected source cited |
| Q06 | single | no | 10.3 | refused an answerable question |
| Q07 | single | yes | 12.3 | all facts present; expected source cited |
| Q08 | single | yes | 20.9 | all facts present; expected source cited |
| Q09 | single | yes | 15.1 | all facts present; expected source cited |
| Q10 | single | yes | 17.9 | all facts present; expected source cited |
| Q11 | single | yes | 15.1 | all facts present; expected source cited |
| Q12 | single | no | 20.6 | missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: artifacts/progress.json) |
| Q13 | single | no | 9.6 | refused an answerable question |
| Q14 | single | yes | 22.7 | all facts present; expected source cited |
| Q15 | single | yes | 21.3 | all facts present; expected source cited |
| Q16 | single | yes | 17.7 | all facts present; expected source cited |
| Q17 | single | yes | 19.1 | all facts present; expected source cited |
| Q18 | single | yes | 11.4 | all facts present; expected source cited |
| Q19 | single | yes | 15.7 | all facts present; expected source cited |
| Q20 | single | no | 18.9 | refused an answerable question |
| Q21 | multi | no | 23.3 | missing facts [["4,249,769", "4249769"]] |
| Q22 | multi | no | 34.0 | missing facts ["voluntary"]; no expected source cited (cited: artifacts/decisions/D-next-after-floor2.json, artifacts/decisions/D-step6-signoff.json) |
| Q23 | multi | no | 13.2 | refused an answerable question |
| Q24 | multi | no | 22.3 | missing facts ["Sign off Step 6"] |
| Q25 | multi | no | 29.2 | refused an answerable question |
| Q26 | unanswerable | yes | 10.9 | refused as expected |
| Q27 | unanswerable | yes | 6.7 | refused as expected |
| Q28 | unanswerable | yes | 21.6 | refused as expected |
| Q29 | unanswerable | yes | 9.7 | refused as expected |
| Q30 | unanswerable | yes | 13.1 | refused as expected |
