# J1 round 3 — brains search the files themselves (work order)

Approved: Director in chat, 2026-10-19 ("yes start round 3"). Round-2 finding (reports/j1_eval_r2_summary.md): all
brains fail the same questions → the top-8 retrieval is the bottleneck, not the model.

## 1. Engineer
1. **Corpus snapshot** `src/jarvis/corpus_build.py` → `data/jarvis/corpus/` (data/ is never indexed): copies ONLY the
   J1 allowlist files (same rules/exclusions as build_index: no eval material, no config/, supabase/, ios/, tracker/,
   data/, chat/answers files), progress.json pruned the same way as the index, and any line matching the secret
   patterns replaced by "[removed: secret pattern]". Manifest with sha256 of every source file + copy.
2. **Agentic mode** `ask.py --brain codex|opencode --search agentic`: the brain runs with the corpus folder as its
   working dir and may list/grep/open files there to find the answer itself. Prompt: use only files in the current
   folder; return JSON `{"quotes":[{"path","quote"}],"answer"}` with `[n]` = quote number; refusal rules as before.
   Codex: `-s read-only -C data/jarvis/corpus ... --json` (event stream) so every command/file it touched is logged;
   OpenCode: `--dir data/jarvis/corpus --format json`, same logging.
3. **Guards (code, not trust):**
   - Every quote must appear verbatim (case/space/dash-normalised) in that corpus file, and the corpus file's sha must
     match the manifest. Quotes that fail are dropped; answer numbers must be in kept quotes (else removed + "(unverified)").
   - **Access audit:** parse the event log; any command or path outside `data/jarvis/corpus/` (absolute paths, `..`,
     `~`, other dirs), any network tool, or any write → answer REJECTED (`rejected_reason: "access outside corpus"`),
     fall back to the next brain / normal retrieval mode, and record it. Log kept per answer in `data/jarvis/audit/`.
   - Refusal handling as before. Timeouts ~180 s.
4. Keep `--search bm25` (current behaviour) as default until QA passes a mode. `auto`/`council` accept `--search`.
5. Tests with fake event logs (inside/outside access, bad quotes, sha mismatch). Do NOT read test sets / eval reports /
   QA code. Write only src/jarvis/, tests/test_jarvis_*.py, data/jarvis/{corpus,audit,brains.json}, README J1 section.

## 2. QA (independent)
1. **Retrieval recall (diagnosis):** for each of the 50 questions, with the current BM25 mode, was each expected fact
   present in any of the top-8 chunks (`ask.py --search` scores / `--debug`)? Report recall vs. correctness.
2. **Fix source lists properly:** for every expected fact, grep ALL allowed files; add every file that really holds it
   (log in change_log). Expected facts themselves unchanged.
3. Grade agentic codex, agentic opencode, agentic council on main + holdout + holdout2. Count answers rejected by the
   access audit (and check 3 audit logs by hand). Also re-grade bm25 codex with the fixed source lists for comparison.
## 3. Pass
Same bar: main ≥ 27/30, each holdout ≥ 9/10, 0 fabricated, 0 secrets, 0 leaks, and 0 accepted answers whose audit
shows access outside the corpus.
