# J1 evaluation (QA, independent)

Graded 2026-10-19T06:44:36Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset.json`. Index built_at 2026-10-19T06:36:33Z. Detail: `reports/j1_eval.json`.

## Verdict: **FAIL**

Rule: >= 27/30 correct, 0 fabricated numbers, 0 secrets.

| Item | Result |
|---|---|
| Score | 18/30 |
| single | 12/20 |
| multi | 2/5 |
| unanswerable | 4/5 |
| Fabricated numbers (QA check vs cited chunk text) | 5 |
| unsupported_numbers reported by ask.py | 5 |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **Q01** (single) How many flights are in the final dataset? — no expected source cited (cited: artifacts/progress.json)
- **Q03** (single) How many predictors does the final dataset have? — no expected source cited (cited: reports/m5_build_report.json)
- **Q05** (single) How many flights were diverted? — no expected source cited (cited: artifacts/progress.json)
- **Q06** (single) How many flights arrived 15 or more minutes late? — refused an answerable question
- **Q12** (single) Which source do the G8 weather forecasts come from? — missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: docs/office/roles/atc_wx.md)
- **Q13** (single) How many FAA NASR cycles were used for G1? — no expected source cited (cited: docs/registry/data_dictionary.csv)
- **Q15** (single) Which single feature had the highest AUC in the leak screen, and what was it? — missing facts ["G10_sched_dep_hour_local", ["0.6478", "0.65"]]; no expected source cited (cited: reports/m5_leakage_audit.json)
- **Q20** (single) How many Southwest (WN) flights were in the 36 BTS monthly files? — missing facts [["4,249,769", "4249769"]]; no expected source cited (cited: reports/m5_leakage_audit.json)
- **Q21** (multi) Do the F9, UA and WN counts from the BTS download add up to the number of flights in the master table? — missing facts [["7,121,934", "7121934"], ["4,249,769", "4249769"]]; no expected source cited (cited: reports/m5_leakage_audit.md)
- **Q23** (multi) How early must a weather forecast run be before the cutoff, and how many MOS rows did we download? — no expected source cited (cited: artifacts/progress.json, docs/registry/g_factor_coverage.csv)
- **Q25** (multi) Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? — missing facts ["T-100"]
- **Q26** (unanswerable) What ROC-AUC did the baseline model get on the 2025 test set? — answered an unanswerable question (should refuse)

## Fabricated numbers

- **Q03**: 59 (not in any cited chunk's text)
- **Q11**: 1 (not in any cited chunk's text)
- **Q20**: 112430, 36 (not in any cited chunk's text)
- **Q26**: 2025 (not in any cited chunk's text)

## QA review notes (written by hand after the run; the verdict rule above is unchanged)

- **Test set too strict on sources (4):** Q01 (progress.json `project` has 7,121,934), Q05 (progress.json M2.3 has
  16,614), Q13 (data_dictionary.csv G1 rows say "43 cycles"), Q23 (progress.json M4.3 has 14,580,247 and "cutoff−6h").
  The answers are right and the cited files really hold the facts; my `sources` lists were too narrow. Counting these
  would give 22/30, which still fails.
- **Real failures:** Q06 refused (1,526,473 is in m2_master_qa.md, so retrieval missed it). Q12 named the role brief's
  "NWS MOS/LAMP/NBM" instead of the IEM GFS MOS archive. Q15 reported 0.6085 instead of the highest AUC, 0.6478. Q20 gave
  112,430, the Jan 2023 pilot count, instead of 4,249,769. Q21 wrongly said the counts do not add up. Q25 gave a parquet
  file name, not the T-100 source. Q26 answered at length and also printed the refusal sentence, but `refused` was false.
- **Fabricated numbers vs guard:** all 5 numbers my check flagged (Q03 59, Q11 1, Q20 112430 and 36, Q26 2025) are
  also listed in ask.py's `unsupported_numbers`, and each of those answers ends with "(unverified)". The guard caught
  every one; none slipped through unlabelled. Q03's "59" is the right count, but no cited chunk states it as text.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| Q01 | single | no | 0.9 | no expected source cited (cited: artifacts/progress.json) |
| Q02 | single | yes | 8.9 | all facts present; expected source cited |
| Q03 | single | no | 8.9 | no expected source cited (cited: reports/m5_build_report.json) |
| Q04 | single | yes | 14.1 | all facts present; expected source cited |
| Q05 | single | no | 14.7 | no expected source cited (cited: artifacts/progress.json) |
| Q06 | single | no | 9.4 | refused an answerable question |
| Q07 | single | yes | 11.4 | all facts present; expected source cited |
| Q08 | single | yes | 13.4 | all facts present; expected source cited |
| Q09 | single | yes | 11.4 | all facts present; expected source cited |
| Q10 | single | yes | 10.8 | all facts present; expected source cited |
| Q11 | single | yes | 11.0 | all facts present; expected source cited |
| Q12 | single | no | 8.5 | missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: docs/office/roles/atc_wx.md) |
| Q13 | single | no | 8.1 | no expected source cited (cited: docs/registry/data_dictionary.csv) |
| Q14 | single | yes | 8.8 | all facts present; expected source cited |
| Q15 | single | no | 21.9 | missing facts ["G10_sched_dep_hour_local", ["0.6478", "0.65"]]; no expected source cited (cited: reports/m5_leakage_audit.json) |
| Q16 | single | yes | 25.5 | all facts present; expected source cited |
| Q17 | single | yes | 12.5 | all facts present; expected source cited |
| Q18 | single | yes | 12.7 | all facts present; expected source cited |
| Q19 | single | yes | 15.2 | all facts present; expected source cited |
| Q20 | single | no | 14.4 | missing facts [["4,249,769", "4249769"]]; no expected source cited (cited: reports/m5_leakage_audit.json) |
| Q21 | multi | no | 17.5 | missing facts [["7,121,934", "7121934"], ["4,249,769", "4249769"]]; no expected source cited (cited: reports/m5_leakage_audit.md) |
| Q22 | multi | yes | 14.2 | all facts present; expected source cited |
| Q23 | multi | no | 13.2 | no expected source cited (cited: artifacts/progress.json, docs/registry/g_factor_coverage.csv) |
| Q24 | multi | yes | 11.7 | all facts present; expected source cited |
| Q25 | multi | no | 19.7 | missing facts ["T-100"] |
| Q26 | unanswerable | no | 18.5 | answered an unanswerable question (should refuse) |
| Q27 | unanswerable | yes | 8.2 | refused as expected |
| Q28 | unanswerable | yes | 13.5 | refused as expected |
| Q29 | unanswerable | yes | 32.0 | refused as expected |
| Q30 | unanswerable | yes | 9.0 | refused as expected |
