# J1 evaluation (QA, independent)

Graded 2026-10-19T15:16:47Z by `src/validate/qa_j1_grade.py` (QA's own code; ask.py run as a black box). Test set: `docs/office/jarvis/j1_testset.json`. Index built_at 2026-10-19T15:00:55Z. Detail: `reports/j1_eval_r3_codex_agentic.json`.

## Verdict: **FAIL**

Rule: >= 27/30 correct, 0 fabricated numbers, 0 secrets. Single-brain run: an answer produced by a different (fallback) brain is counted as an error.

| Item | Result |
|---|---|
| Brain | codex |
| Time per question (mean / total s) | 11.0 / 329.0 |
| Score | 20/30 |
| single | 19/20 |
| multi | 1/5 |
| unanswerable | 0/5 |
| Fabricated numbers (QA check vs cited chunk text) | 0 |
| unsupported_numbers reported by ask.py | 13 |
| Numbers removed by the guard ('[number removed]' left in answers) | 13 |
| Answers that used a fallback brain | 0  |
| Search mode / answers produced by agentic search | agentic / 22 |
| Attempts rejected by the access audit | 0 |
| Audit logs checked by QA / accepted answers with outside access | 22 / 0  |
| Council 'Brains disagree.' answers / of which compatible (both sides had all expected facts) | 0 / 0  |
| Secrets in data/jarvis/index.json | 0 (sb_secret_: 0, service_role: 0, eyJ: 0, BEGIN PRIVATE KEY: 0) |

## Failures

- **Q01** (single) How many flights are in the final dataset? — no expected source cited (cited: CLAUDE.md, reports/dc2_qa.md)
- **Q22** (multi) Why is Endeavor Air (9E) missing in 2025, and did I apply the 9E fix when I signed off Step 6? — missing facts ["voluntary", ["NOT applied", "not applied"]]
- **Q23** (multi) How early must a weather forecast run be before the cutoff, and how many MOS rows did we download? — error from ask.py: exit=2; stderr: ESTION: How early must a weather forecast run be before the cutoff, and how many MOS rows did we download? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. | ERROR: You)
- **Q24** (multi) What did I tap on the Step 6 sign-off card, and how did the history features do in the past-flight-only check? — error from ask.py: exit=2; stderr: ESTION: What did I tap on the Step 6 sign-off card, and how did the history features do in the past-flight-only check? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. )
- **Q25** (multi) Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? — error from ask.py: exit=2; stderr: ESTION: Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. | ERROR: You’ve hit your)
- **Q26** (unanswerable) What ROC-AUC did the baseline model get on the 2025 test set? — error from ask.py: exit=2; stderr: ESTION: What ROC-AUC did the baseline model get on the 2025 test set? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. | ERROR: You’ve hit your usage limit. Upgrade to )
- **Q27** (unanswerable) What is the project's total budget in dollars? — error from ask.py: exit=2; stderr: ESTION: What is the project's total budget in dollars? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://ch)
- **Q28** (unanswerable) What was the average airfare on United flights in 2024? — error from ask.py: exit=2; stderr: ESTION: What was the average airfare on United flights in 2024? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. | ERROR: You’ve hit your usage limit. Upgrade to Pro (h)
- **Q29** (unanswerable) How many bird strikes were reported at Denver in 2024? — error from ask.py: exit=2; stderr: ESTION: How many bird strikes were reported at Denver in 2024? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. | ERROR: You’ve hit your usage limit. Upgrade to Pro (ht)
- **Q30** (unanswerable) How much carbon dioxide did Southwest flights emit in 2023? — error from ask.py: exit=2; stderr: ESTION: How much carbon dioxide did Southwest flights emit in 2023? | ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. | ERROR: You’ve hit your usage limit. Upgrade to Pr)

## Fabricated numbers

None.

## Per question

| id | type | correct | s | reason |
|---|---|---|---|---|
| Q01 | single | no | 15.9 | no expected source cited (cited: CLAUDE.md, reports/dc2_qa.md) |
| Q02 | single | yes | 9.5 | all facts present; expected source cited |
| Q03 | single | yes | 11.6 | all facts present; expected source cited |
| Q04 | single | yes | 13.2 | all facts present; expected source cited |
| Q05 | single | yes | 12.9 | all facts present; expected source cited |
| Q06 | single | yes | 18.3 | all facts present; expected source cited |
| Q07 | single | yes | 10.9 | all facts present; expected source cited |
| Q08 | single | yes | 17.0 | all facts present; expected source cited |
| Q09 | single | yes | 10.5 | all facts present; expected source cited |
| Q10 | single | yes | 15.8 | all facts present; expected source cited |
| Q11 | single | yes | 12.6 | all facts present; expected source cited |
| Q12 | single | yes | 10.9 | all facts present; expected source cited |
| Q13 | single | yes | 9.5 | all facts present; expected source cited |
| Q14 | single | yes | 15.6 | all facts present; expected source cited |
| Q15 | single | yes | 12.6 | all facts present; expected source cited |
| Q16 | single | yes | 11.4 | all facts present; expected source cited |
| Q17 | single | yes | 10.6 | all facts present; expected source cited |
| Q18 | single | yes | 12.6 | all facts present; expected source cited |
| Q19 | single | yes | 8.9 | all facts present; expected source cited |
| Q20 | single | yes | 9.2 | all facts present; expected source cited |
| Q21 | multi | yes | 13.8 | all facts present; expected source cited |
| Q22 | multi | no | 27.1 | missing facts ["voluntary", ["NOT applied", "not applied"]] |
| Q23 | multi | no | 4.5 | error from ask.py: exit=2; stderr: ESTION: How early must a weather forecast run be before the cutoff, and how many MOS rows did we download? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. / ERROR: You) |
| Q24 | multi | no | 4.2 | error from ask.py: exit=2; stderr: ESTION: What did I tap on the Step 6 sign-off card, and how did the history features do in the past-flight-only check? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. ) |
| Q25 | multi | no | 4.6 | error from ask.py: exit=2; stderr: ESTION: Which source feeds G3, and what share of F9 flights had empty G3 route values in 2024? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. / ERROR: You’ve hit your) |
| Q26 | unanswerable | no | 5.7 | error from ask.py: exit=2; stderr: ESTION: What ROC-AUC did the baseline model get on the 2025 test set? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. / ERROR: You’ve hit your usage limit. Upgrade to ) |
| Q27 | unanswerable | no | 5.3 | error from ask.py: exit=2; stderr: ESTION: What is the project's total budget in dollars? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://ch) |
| Q28 | unanswerable | no | 4.4 | error from ask.py: exit=2; stderr: ESTION: What was the average airfare on United flights in 2024? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. / ERROR: You’ve hit your usage limit. Upgrade to Pro (h) |
| Q29 | unanswerable | no | 5.3 | error from ask.py: exit=2; stderr: ESTION: How many bird strikes were reported at Denver in 2024? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. / ERROR: You’ve hit your usage limit. Upgrade to Pro (ht) |
| Q30 | unanswerable | no | 4.6 | error from ask.py: exit=2; stderr: ESTION: How much carbon dioxide did Southwest flights emit in 2023? / ERROR: You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:07 PM. / ERROR: You’ve hit your usage limit. Upgrade to Pr) |
