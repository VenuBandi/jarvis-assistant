# J1 round 3 · retrieval recall diagnosis (QA)

Checked 2026-10-19T14:51:10Z with `src/validate/qa_j1_recall.py --recall`: for each question, the 8 chunks `ask.py --search` marks as selected (`*`) were looked up in `data/jarvis/index.json` (path + section) and every expected fact was searched in their text (case-insensitive, commas ignored, word boundaries). Correctness = round-2 codex grade (`reports/j1_eval_r2_codex*.json`, original source lists).

| Item | Result |
|---|---|
| Answerable questions with every expected fact in the top 8 | 36/41 |
| Expected facts found in the top 8 | 54/59 |
| Round-2 codex failures (answerable) | 16 |
| … of which a fact was missing from the top 8 (retrieval) | 5: Q06, Q12, Q20, Q21, Q25 |
| … of which every fact was in the top 8 (model / answer / source list) | 11: Q03, Q13, Q18, Q22, Q24, H05, H07, K01, K04, K05, K07 |
| Correct although a fact was not in the top 8 | 0: — |
| Facts not in any index chunk | 0  |
| Selected sections that could not be resolved in the index | 0 |

## Diagnosis (QA, written by hand)

- **Retrieval is the bottleneck for 5 of the 16 round-2 codex failures** (Q06, Q12, Q20, Q21, Q25): at least one
  expected fact is not in the 8 chunks the model sees. Every fact does exist somewhere in the index (0 missing).
- **For the other 11, every fact was already in the top 8:**
  - 5 were QA source-list errors: right answer, file not in my list (Q03, Q13, H05, K01, K04). They are fixed in §2.2.
  - 6 were model/answer failures although the chunk was there: refusals (Q18, K05; Q24 and H07 for some brains),
    and missing half of a multi-file answer (Q22 "voluntary", Q24 tapped choice, H07 table name, K07 2023 counts).
- So the hypothesis "retrieval is the bottleneck" is **partly rejected**. Retrieval explains about a third of the
  failures. The rest are answer behaviour (over-refusal, dropping one half of a two-part question) and QA key errors.
- No question was answered correctly while its fact was missing from the top 8. Recall for answerable questions is
  36/41 questions (54/59 facts).
- Method notes: the `*` rows of `ask.py --search` are the 8 selected chunks (after diversification). The shown
  section names are cut off, so they were matched by path + section prefix (0 unresolved). For generic facts, a chunk
  counts only if it also holds the question's context term (same rule as the source audit).

## Per question

| set | id | type | facts in top 8 | r2 codex | r2 reason |
|---|---|---|---|---|---|
| j1_testset | Q01 | single | ✓ ["7,121,934", "7121934"] | yes | all facts present; expected source cited |
| j1_testset | Q02 | single | ✓ "ACCEPT WITH NOTES" | yes | all facts present; expected source cited |
| j1_testset | Q03 | single | ✓ "59" | no | no expected source cited (cited: docs/office/direction_2026-10-19.md) |
| j1_testset | Q04 | single | ✓ ["79,288", "79288"] | yes | all facts present; expected source cited |
| j1_testset | Q05 | single | ✓ ["16,614", "16614"] | yes | all facts present; expected source cited |
| j1_testset | Q06 | single | ✗ ["1,526,473", "1526473"] | no | refused an answerable question |
| j1_testset | Q07 | single | ✓ ["24 hours", "24 h", "24h", "T−24h", "T-24h"], ✓ "scheduled departure" | yes | all facts present; expected source cited |
| j1_testset | Q08 | single | ✓ "actual delay", ✓ "taxi times", ✓ "delay causes" | yes | all facts present; expected source cited |
| j1_testset | Q09 | single | ✓ ["15 days", "15"] | yes | all facts present; expected source cited |
| j1_testset | Q10 | single | ✓ ["PARTIAL", "Partial", "partial"] | yes | all facts present; expected source cited |
| j1_testset | Q11 | single | ✓ ["Mishandled bags", "mishandled bags"] | yes | all facts present; expected source cited |
| j1_testset | Q12 | single | ✓ "MOS", ✗ ["Iowa Environmental Mesonet", "IEM"] | no | missing facts [["Iowa Environmental Mesonet", "IEM"]]; no expected source cited (cited: artifacts/progress.json) |
| j1_testset | Q13 | single | ✓ "43" | no | no expected source cited (cited: artifacts/progress.json) |
| j1_testset | Q14 | single | ✓ ["0.2173", "21.73%"] | yes | all facts present; expected source cited |
| j1_testset | Q15 | single | ✓ "G10_sched_dep_hour_local", ✓ ["0.6478", "0.65"] | yes | all facts present; expected source cited |
| j1_testset | Q16 | single | ✓ ["89,074", "89074"] | yes | all facts present; expected source cited |
| j1_testset | Q17 | single | ✓ "362" | yes | all facts present; expected source cited |
| j1_testset | Q18 | single | ✓ "I installed it" | no | refused an answerable question |
| j1_testset | Q19 | single | ✓ "ACCEPT WITH NOTES", ✓ "19" | yes | all facts present; expected source cited |
| j1_testset | Q20 | single | ✗ ["4,249,769", "4249769"] | no | refused an answerable question |
| j1_testset | Q21 | multi | ✓ ["7,121,934", "7121934"], ✗ ["4,249,769", "4249769"] | no | missing facts [["4,249,769", "4249769"]] |
| j1_testset | Q22 | multi | ✓ "voluntary", ✓ ["NOT applied", "not applied"] | no | missing facts ["voluntary"] |
| j1_testset | Q23 | multi | ✓ ["6 h", "6 hours"], ✓ ["14,580,247", "14580247"] | yes | all facts present; expected source cited |
| j1_testset | Q24 | multi | ✓ "Sign off Step 6", ✓ "126/126" | no | missing facts ["Sign off Step 6"] |
| j1_testset | Q25 | multi | ✓ "T-100", ✗ "13.0%" | no | missing facts ["13.0%"]; no expected source cited (cited: docs/registry/data_dictionary.csv, reports/m5_leakage_audit.json) |
| j1_testset | Q26 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset | Q27 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset | Q28 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset | Q29 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset | Q30 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset_holdout | H01 | single | ✓ ["2,388,494", "2388494"] | yes | all facts present; expected source cited |
| j1_testset_holdout | H02 | single | ✓ ["317,600", "317600"] | yes | all facts present; expected source cited |
| j1_testset_holdout | H03 | single | ✓ ["538,837", "538837"] | yes | all facts present; expected source cited |
| j1_testset_holdout | H04 | single | ✓ "16.1" | yes | all facts present; expected source cited |
| j1_testset_holdout | H05 | single | ✓ ["4 GB", "4GB"] | no | no expected source cited (cited: docs/platform/README.md) |
| j1_testset_holdout | H06 | single | ✓ ["57,845", "57845"] | yes | all facts present; expected source cited |
| j1_testset_holdout | H07 | multi | ✓ "Marketing Carrier On-Time Performance", ✓ "S02" | no | refused an answerable question |
| j1_testset_holdout | H08 | multi | ✓ ["455,857", "455857"], ✓ ["4 months", "M-4", "M−4"] | yes | all facts present; expected source cited |
| j1_testset_holdout | H09 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset_holdout | H10 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset_holdout2 | K01 | single | ✓ ["65,463", "65463"] | no | no expected source cited (cited: reports/dc2_qa.json) |
| j1_testset_holdout2 | K02 | single | ✓ ["40,181", "40181"] | yes | all facts present; expected source cited |
| j1_testset_holdout2 | K03 | single | ✓ "529" | yes | all facts present; expected source cited |
| j1_testset_holdout2 | K04 | single | ✓ "58" | no | no expected source cited (cited: artifacts/progress.json) |
| j1_testset_holdout2 | K05 | single | ✓ "129" | no | refused an answerable question |
| j1_testset_holdout2 | K06 | multi | ✓ "358", ✓ "362" | yes | all facts present; expected source cited |
| j1_testset_holdout2 | K07 | multi | ✓ ["14,633", "14633"], ✓ ["18,121", "18121"], ✓ "all-carrier counts" | no | missing facts [["14,633", "14633"], ["18,121", "18121"]] |
| j1_testset_holdout2 | K08 | multi | ✓ "S12", ✓ "G11", ✓ "Validated Proxy" | yes | all facts present; expected source cited |
| j1_testset_holdout2 | K09 | unanswerable | n/a (unanswerable) | yes | refused as expected |
| j1_testset_holdout2 | K10 | unanswerable | n/a (unanswerable) | yes | refused as expected |
