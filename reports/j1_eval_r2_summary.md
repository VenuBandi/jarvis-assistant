# J1 round 2 (multi-brain): QA summary

Graded 2026-10-19 by `src/validate/qa_j1_grade.py` (QA's own grader; `ask.py --json --brain <id>` used as a black box).
Index `data/jarvis/index.json` was built 2026-10-19T14:09:41Z. Rule (docs/office/jarvis/j1_multibrain.md §4): main ≥ 27/30, each holdout ≥ 9/10,
0 fabricated numbers, 0 secrets, 0 leaks. Per-brain detail: `reports/j1_eval_r2_<brain>[_holdout|_holdout2].md/.json`.

## Scores

| brain | main /30 | holdout /10 | holdout2 /10 | fabricated | removed by guard (main/h1/h2) | mean s/question (main/h1/h2) | meets bar |
|---|---|---|---|---|---|---|---|
| codex | 20 | 8 | 6 | 0 | 3 / 1 / 2 | 5.2 / 5.0 / 4.6 | no |
| opencode | 19 | 8 | 6 | 0 | 7 / 0 / 6 | 6.0 / 7.7 / 5.1 | no |
| council | 21 | 8 | 6 | 0 | 8 / 2 / 2 | 6.3 / 6.4 / 5.5 | no |
| local (re-run) | 20 | 6 | 5 | 0 | 1 / 0 / 0 | 16.5 / 17.5 / 12.7 | no |

- local was re-run on main and holdout because the index (14:09:41Z, 1,566 chunks) and ask.py changed after round 1
  (13:43:48Z, 1,559 chunks). The results are the same as round 1 (20/30, 6/10).
- No brain used a fallback in any answer. Every single-brain answer came from the brain that was asked.

## Council rule (fixed before grading the council output)
An answer starting "Brains disagree." counts as correct only if each side contains every expected fact and an
expected source is cited. A side that is missing a fact contradicts the other side on the asked fact, so the answer
is not correct. For an unanswerable question, a disagreement is not a refusal, so it is not correct.
The sides were labelled by brain id ("codex: … — opencode: …"), not "a:/b:" as the README says. The parser
accepts both forms.
- Council said "Brains disagree." once in 50 answers (Q22). Under the rule above it was not compatible (neither side
  gives the expected "voluntary" cause), so it is not correct.
- Compatible disagreements (both sides had every expected fact): 0. Looser reading: on Q22 both sides agree that the
  fix was not applied. The disagreement was about the cause, which neither side stated.

## Checks
- Secrets in the index: 0 (sb_secret_, service_role, eyJ, BEGIN PRIVATE KEY).
- Leaks: 0 of the 50 question texts (main 30, holdout 10, holdout2 10) are in the index. 0 chunks come from
  reports/j1_eval*, reports/j2_check*, reports/j5_check*, docs/office/jarvis/j1_testset* or data/. The words `expected_facts` and `answerable`
  appear only as format descriptions in work orders and as words in log text, together with file-name mentions.
- ask.py warned on every question that artifacts/progress.json changed after the index build. That is the live log;
  no question depends on it.

## Too-strict expected sources (QA key error, reported separately; the verdict is unchanged)
The brains cited a file that really contains the fact, but my `sources` list missed that file:
Q03 (docs/office/direction_2026-10-19.md "59 features"), Q11 (artifacts/progress.json "mishandled bags"),
Q13 (artifacts/progress.json "43 NASR cycles"), H05 (docs/platform/README.md "4 GB"),
K01 (reports/dc2_qa.json, docs/platform/README.md "65,463"), K04 (artifacts/progress.json "58 PASS").
If these were counted, the best case would be council 22/30, 9/10, 8/10 and codex 22/30, 9/10, 8/10. The main set
would still fail for every brain.
Lesson for QA: grep every allowed file for the fact when writing `sources`, not only the file where I found it.

## Verdict
**No brain meets the pass bar**. Even the best case falls short of 27/30 on the main set.
Common failures, the same across brains: retrieval does not reach the chunk with the full total (Q06, Q20, Q18, K05
refused); multi-file questions miss one half (Q21 WN count, Q22 "voluntary", Q24 tapped choice, Q25 13.0%, H07
Marketing Carrier table, K07 monthly 9E counts); and Q12 names the parquet file instead of the IEM MOS source. Because
all three cloud brains fail on the same questions, the shared retrieval step (top 8 chunks) is the limit, not the model.
