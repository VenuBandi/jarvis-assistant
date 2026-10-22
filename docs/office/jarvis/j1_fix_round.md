# J1 fix round 1 — work order

Approved: Director in chat, 2026-10-19 ("yes start J1 fix round"). Base: j1_work_order.md; round-0 result
reports/j1_eval.md (FAIL 18/30). Model stays local (qwen3-8b-32k); switching to Claude is NOT approved.

## 1. Engineer (must NOT read docs/office/jarvis/j1_testset*.json, reports/j1_eval*, src/validate/qa_j1_*)
Failure types from round 0 (categories only, no questions):
- A. Retrieval missed the chunk that holds the answer (answer was in a QA report / registry, Jarvis refused).
- B. Noise: large progress.json sections crowd out reports and registries; citations point at broad packed sections.
- C. Model picked the wrong fact among retrieved chunks (e.g. a pilot/sample number instead of the full total,
  wrong item when comparing values, wrong source named).
- D. Answers that contain the refusal sentence plus other text were not marked refused.
- E. Numbers not in cited chunks (all caught by the guard; still counted as failures).
Required generic fixes (no question-specific rules, no hard-coded answers):
1. Index hygiene: exclude evaluation material — reports/j1_eval*, reports/j2_check*, reports/j5_check*,
   docs/office/jarvis/j1_testset*, data/jarvis/** — and the bulky machine sections of progress.json
   (agent.galaxy, agent.briefing, agent.log older entries beyond the last 30, agent.datacenter raw lists). Smaller,
   precise JSON chunks (one record per chunk with a readable section name, e.g. "milestones › M5 › M5.3").
2. Retrieval: BM25 field boost (title/section/heading tokens), number-aware tokens ("7,121,934" = "7121934"),
   simple synonym/alias table built from the project's own registries (carrier codes ↔ names, factor ids ↔ titles,
   "late" ↔ "ArrDel15"/"15 or more minutes"), larger candidate pool (e.g. top 20) then re-rank/diversify to top 8
   so one file can't take every slot. Optional: Ollama embeddings only if an embedding model is already installed
   locally (check /api/tags; do not pull models) — report which.
3. Answering in two steps with the local model: (a) extract verbatim quotes with chunk ids that answer the question,
   (b) answer only from those quotes, citing them. Instruct: prefer totals over samples/pilots unless asked, state the
   scope (period, carrier) of each number.
4. Refusal: if the answer contains the refusal sentence, return exactly the refusal (refused=true, no citations).
5. Guard stays; numbers not in a cited quote → removed from the answer and listed, answer marked "(unverified)".
6. Tests for every change (fake LLM), whole suite green. Rebuild index, report stats + 3 own smoke questions.

## 2. QA (independent, before seeing round-1 outputs)
1. Fix only the source lists already found too narrow in round 0 (Q01, Q05, Q13, Q23 — documented in
   reports/j1_eval.md review notes); no other changes to j1_testset.json; log the change in the file's notes.
2. Write a NEW hidden set docs/office/jarvis/j1_testset_holdout.json: 10 questions (6 single, 2 multi,
   2 unanswerable), same format, verified against files, written now and never shown to the Engineer.
3. Grade round 1 with the existing grader on both sets → reports/j1_eval_r1.json/.md.
## 3. Pass (J1 done)
Original set ≥ 27/30 AND holdout ≥ 9/10 AND 0 fabricated numbers left in answers AND 0 secrets AND no eval
material in the index. Otherwise: report, and the Director decides (another round, or Claude as the brain).
