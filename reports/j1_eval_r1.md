# J1 evaluation (QA, independent)

Graded 2026-10-19T13:52:18Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset.json`. Index built_at 2026-10-19T13:43:48Z. Detail: `reports/j1_eval_r1.json`.

## Verdict: **FAIL**

Rule: >= 27/30 correct, 0 fabricated numbers, 0 secrets.

| Item | Result |
|---|---|
| Score | 20/30 |
| single | 15/20 |
| multi | 0/5 |
| unanswerable | 5/5 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 2 |
| Numbers removed by the guard ('[number removed]' left in answers) | 2 |
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
- **Q25** (multi) Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? — missing facts ["T-100", "13.0%"]; no expected source cited (cited: artifacts/decisions/D-step6-integration.json, docs/registry/data_dictionary.csv)

## Fabricated numbers

None.

## Round-1 overall (QA, written by hand after the run; rule from docs/office/jarvis/j1_fix_round.md §3)

- Main set 20/30 (need ≥ 27) · holdout 6/10 (need ≥ 9; reports/j1_eval_r1_holdout.md) · 0 fabricated numbers left in
  answers (2 removed by the guard, in Q22 and Q25) · 0 secrets · no eval material in the index → **J1 round 1: FAIL**.
- Index leak check (data/jarvis/index.json built 2026-10-19T13:43:48Z, grep): 0 of the 40 question texts (30 main + 10
  holdout) appear; no chunk's path is under reports/j1_eval*, reports/j2_check*, reports/j5_check*,
  docs/office/jarvis/j1_testset* or data/. File-name mentions only (expected and OK): `j1_testset*`, `j1_eval*`,
  `j2_check`, `j5_check` appear in work orders and log/checkpoint text; the words `expected_facts`/`answerable` come
  only from j1_work_order.md §4 and j1_fix_round.md §2 (format descriptions, no questions or answers).
  Expected answer values (e.g. 7,121,934) naturally appear because they are facts in the source files.
- Change vs round 0 (18/30): refusals of unanswerables fixed (5/5); 0 numbers left unsupported. New main problem:
  answerable questions refused (Q03, Q06, Q13, Q20, Q23; holdout H01, H05, H08) — 8 of the 14 failures across both sets.
- Guard side effect: it removed the "6" from "Step 6" in Q22 (an id, not a measured number). Reported as removed,
  not fabricated.
- Strictness review: Q21 says the counts add up to 7,121,934 but gives no carrier count; the key asks for the
  WN count too, so it stays a fail under the fixed rule. No other expected fact looked too strict.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| Q01 | single | yes | 4.3 | all facts present; expected source cited |
| Q02 | single | yes | 12.3 | all facts present; expected source cited |
| Q03 | single | no | 8.3 | refused an answerable question |
| Q04 | single | yes | 13.2 | all facts present; expected source cited |
| Q05 | single | yes | 12.6 | all facts present; expected source cited |
| Q06 | single | no | 10.0 | refused an answerable question |
| Q07 | single | yes | 12.2 | all facts present; expected source cited |
| Q08 | single | yes | 20.9 | all facts present; expected source cited |
| Q09 | single | yes | 15.0 | all facts present; expected source cited |
| Q10 | single | yes | 17.9 | all facts present; expected source cited |
| Q11 | single | yes | 15.0 | all facts present; expected source cited |
| Q12 | single | no | 21.2 | missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: artifacts/progress.json) |
| Q13 | single | no | 9.6 | refused an answerable question |
| Q14 | single | yes | 22.7 | all facts present; expected source cited |
| Q15 | single | yes | 21.3 | all facts present; expected source cited |
| Q16 | single | yes | 15.6 | all facts present; expected source cited |
| Q17 | single | yes | 19.1 | all facts present; expected source cited |
| Q18 | single | yes | 11.5 | all facts present; expected source cited |
| Q19 | single | yes | 15.7 | all facts present; expected source cited |
| Q20 | single | no | 13.4 | refused an answerable question |
| Q21 | multi | no | 23.1 | missing facts [["4,249,769", "4249769"]] |
| Q22 | multi | no | 33.5 | missing facts ["voluntary"]; no expected source cited (cited: artifacts/decisions/D-next-after-floor2.json, artifacts/decisions/D-step6-signoff.json) |
| Q23 | multi | no | 12.3 | refused an answerable question |
| Q24 | multi | no | 22.3 | missing facts ["Sign off Step 6"] |
| Q25 | multi | no | 28.2 | missing facts ["T-100", "13.0%"]; no expected source cited (cited: artifacts/decisions/D-step6-integration.json, docs/registry/data_dictionary.csv) |
| Q26 | unanswerable | yes | 10.9 | refused as expected |
| Q27 | unanswerable | yes | 6.1 | refused as expected |
| Q28 | unanswerable | yes | 21.6 | refused as expected |
| Q29 | unanswerable | yes | 8.8 | refused as expected |
| Q30 | unanswerable | yes | 13.1 | refused as expected |
