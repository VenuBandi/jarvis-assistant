# J1 evaluation (QA, independent)

Graded 2026-10-19T15:14:39Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset.json`. Index built_at 2026-10-19T15:00:55Z. Detail: `reports/j1_eval_r3_opencode_agentic.json`.

## Verdict: **FAIL**

Rule: >= 27/30 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | opencode |
| Time per question (mean / total s) | 146.3 / 292.6 |
| Score | 0/30 |
| single | 0/20 |
| multi | 0/5 |
| unanswerable | 0/5 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 0 |
| Numbers removed by the guard ('[number removed]' left in answers) | 0 |
| Answers that used a fallback brain | 0  |
| Search mode / answers produced by agentic search | agentic / 0 |
| Attempts rejected by the access audit | 0 |
| Audit logs checked by QA / accepted answers with outside access | 0 / 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |
| Not run | Q03, Q04, Q05, Q06, Q07, Q08, Q09, Q10, Q11, Q12, Q13, Q14, Q15, Q16, Q17, Q18, Q19, Q20, Q21, Q22, Q23, Q24, Q25, Q26, Q27, Q28, Q29, Q30 |

## Failures

- **Q01** (single) How many flights are in the final dataset? — error from ask.py: exit=2; stderr: type":"error","timestamp":1792422735870,"sessionID":"ses_eab48b0feffeRL9nVvBChjWvUD","error":{"name":"APIError","data":{"message":"The usage limit has been reached","statusCode":429,"isRetryable":true,"responseHeaders":{"cf-cache-status":"DYNAMIC","cf-ray":"a4d0b850fc930f55-EWR","connection":"keep)
- **Q02** (single) What was QA's verdict on the Step 6 leakage audit? — error from ask.py: exit=2; stderr: type":"error","timestamp":1792422878978,"sessionID":"ses_eab467974ffea9KPNBUS2O7Mli","error":{"name":"APIError","data":{"message":"The usage limit has been reached","statusCode":429,"isRetryable":true,"responseHeaders":{"cf-cache-status":"DYNAMIC","cf-ray":"a4d0bbcf4c12ae4c-EWR","connection":"keep)
- **Q03** (single) How many predictors does the final dataset have? — not run
- **Q04** (single) How many flights in the master table were cancelled? — not run
- **Q05** (single) How many flights were diverted? — not run
- **Q06** (single) How many flights arrived 15 or more minutes late? — not run
- **Q07** (single) How far ahead of departure must every feature be known? — not run
- **Q08** (single) Which things are we never allowed to use as predictors? — not run
- **Q09** (single) How far back does the FAA ATCSCC advisories database go? — not run
- **Q10** (single) What is the status of factor G7 (ATC ground restrictions)? — not run
- **Q11** (single) What does the G2 ground handling proxy actually measure? — not run
- **Q12** (single) Which source do the G8 weather forecasts come from? — not run
- **Q13** (single) How many FAA NASR cycles were used for G1? — not run
- **Q14** (single) What is the delay rate on completed flights? — not run
- **Q15** (single) Which single feature had the highest AUC in the leak screen, and what was it? — not run
- **Q16** (single) How many rows are US-territory routes? — not run
- **Q17** (single) How many airports were mapped to a time zone? — not run
- **Q18** (single) What did I answer on the DuckDB install card? — not run
- **Q19** (single) What was the QA verdict on DC-2 and how many checks passed? — not run
- **Q20** (single) How many Southwest (WN) flights were in the 36 BTS monthly files? — not run
- **Q21** (multi) Do the F9, UA and WN counts from the BTS download add up to the number of flights in the master table? — not run
- **Q22** (multi) Why is Endeavor Air (9E) missing in 2025, and did I apply the 9E fix when I signed off Step 6? — not run
- **Q23** (multi) How early must a weather forecast run be before the cutoff, and how many MOS rows did we download? — not run
- **Q24** (multi) What did I tap on the Step 6 sign-off card, and how did the history features do in the past-flight-only check? — not run
- **Q25** (multi) Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? — not run
- **Q26** (unanswerable) What ROC-AUC did the baseline model get on the 2025 test set? — not run
- **Q27** (unanswerable) What is the project's total budget in dollars? — not run
- **Q28** (unanswerable) What was the average airfare on United flights in 2024? — not run
- **Q29** (unanswerable) How many bird strikes were reported at Denver in 2024? — not run
- **Q30** (unanswerable) How much carbon dioxide did Southwest flights emit in 2023? — not run

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| Q01 | single | no | 149.5 | error from ask.py: exit=2; stderr: type":"error","timestamp":1792422735870,"sessionID":"ses_eab48b0feffeRL9nVvBChjWvUD","error":{"name":"APIError","data":{"message":"The usage limit has been reached","statusCode":429,"isRetryable":true,"responseHeaders":{"cf-cache-status":"DYNAMIC","cf-ray":"a4d0b850fc930f55-EWR","connection":"keep) |
| Q02 | single | no | 143.1 | error from ask.py: exit=2; stderr: type":"error","timestamp":1792422878978,"sessionID":"ses_eab467974ffea9KPNBUS2O7Mli","error":{"name":"APIError","data":{"message":"The usage limit has been reached","statusCode":429,"isRetryable":true,"responseHeaders":{"cf-cache-status":"DYNAMIC","cf-ray":"a4d0bbcf4c12ae4c-EWR","connection":"keep) |
| Q03 | single | no | None | not run |
| Q04 | single | no | None | not run |
| Q05 | single | no | None | not run |
| Q06 | single | no | None | not run |
| Q07 | single | no | None | not run |
| Q08 | single | no | None | not run |
| Q09 | single | no | None | not run |
| Q10 | single | no | None | not run |
| Q11 | single | no | None | not run |
| Q12 | single | no | None | not run |
| Q13 | single | no | None | not run |
| Q14 | single | no | None | not run |
| Q15 | single | no | None | not run |
| Q16 | single | no | None | not run |
| Q17 | single | no | None | not run |
| Q18 | single | no | None | not run |
| Q19 | single | no | None | not run |
| Q20 | single | no | None | not run |
| Q21 | multi | no | None | not run |
| Q22 | multi | no | None | not run |
| Q23 | multi | no | None | not run |
| Q24 | multi | no | None | not run |
| Q25 | multi | no | None | not run |
| Q26 | unanswerable | no | None | not run |
| Q27 | unanswerable | no | None | not run |
| Q28 | unanswerable | no | None | not run |
| Q29 | unanswerable | no | None | not run |
| Q30 | unanswerable | no | None | not run |
