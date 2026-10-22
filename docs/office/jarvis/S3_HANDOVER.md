# S3 hand-over: create the Jarvis project in ~/jarvis-assistant

From: the FlightOps Lead session (Claude), 2026-10-22. For: a NEW Claude Code session opened in `~/jarvis-assistant`.
Director approved option A (card D-jarvis-s3).

## 0. Context in five lines
- Jarvis = the Director's personal Mac assistant (like Siri). It is being separated from FlightOps.
- S1 + S2 are done in FlightOps: FlightOps has its own AI config and no longer depends on Jarvis (checked: 0 dependencies).
- S3 (this session) = copy Jarvis into `~/jarvis-assistant`, make it run from there **as a copy**, prove its tests pass.
- S4 (later, needs the Director) = switch the running Jarvis (port 8770) to the new folder. S5 = remove the old copy from FlightOps.
- Read first: `~/flightops-ai/docs/office/jarvis/jarvis_separation_plan.md` and `j0_design_v2.md` (section 8b).

## 1. Rules for this session
- Do not edit, move or delete anything in `~/flightops-ai`. Only write `~/flightops-ai/docs/office/jarvis/s3_result.md` at the end.
- Do not stop, restart or start Jarvis on port 8770 (the running one serves the Director). For checks, use tests only, or a
  different port only if the Director agrees.
- Do not copy, read or print any key. Jarvis's new keys go in `~/.config/jarvis/`, created by the Director.
- Before running any script, check what files it writes. Commit to git before each change.

## 2. Steps
1. `cd ~/jarvis-assistant && git init` (local only).
2. Dry run, then copy (589 files, 4.9 MB, 1 secret = the API token, copied byte-for-byte with mode 600; never printed):
   ```
   python3 -I ~/flightops-ai/src/office/s3_copy_jarvis.py ~/jarvis-assistant --dry-run
   python3 -I ~/flightops-ai/src/office/s3_copy_jarvis.py ~/jarvis-assistant
   ```
   Expect `errors: 0`. Output: `S3_COPY_REPORT.json`, `CLAUDE.md`, `.gitignore` in the new folder. Commit ("S3 copy as-is").
3. Rewire the NEW copy only (each change its own commit):
   - `FLIGHTOPS_ROOT` setting (default `~/flightops-ai`) used instead of the repo root for FlightOps reads:
     `src/jarvis_app/tools/builtin.py` (flightops_status reads `artifacts/progress.json`),
     `src/jarvis_app/workflow/assignments.py` (reads `artifacts/handoff/...`),
     `src/jarvis/jarvis_core.py` / `build_index.py` (project Q&A index over FlightOps docs/reports/decisions).
   - Key paths → `~/.config/jarvis/...` with the same mode-600 rules: `src/jarvis/brains.py` (OmniRoute key),
     `omniroute_*.py`, `nvidia_probe.py`, `tavily_search.py`, `src/jarvis_app/config/providers.yaml`
     (omniroute / nvidia / mistral `secret_file`). Until the Director creates those keys, live pings will say "key missing";
     that is expected.
   - `src/jarvis/README.md` and docs: briefing / Galaxy now belong to FlightOps (`~/flightops-ai/src/office/`); remove
     them from Jarvis's docs.
4. Tests in the new folder (they must not touch port 8770 or the network):
   ```
   python3 -m unittest discover -s tests -p "test_jarvis*.py"
   node --test tests/frontend/jarvis_voice.test.cjs
   ```
   Known pre-existing failure (not caused by the move): `test_jarvis_brains.Adapters.test_repo_brains_json` expects only
   `ollama-local/` or `antigravity/` models, but `data/jarvis/brains.json` also approves `gemini/gemini-3.8-flash`.
   Report it; ask the Director whether the test or the config is right. `workflow_ui` needs `npm ci` before its frontend
   tests (needs the Director's OK to install).
5. Write `~/flightops-ai/docs/office/jarvis/s3_result.md`: copy report summary, rewiring commits, test results (counts,
   failures with reasons), anything unverified, and what S4 needs (stop old Jarvis, start new one, re-copy
   `data/jarvis_app/jarvis.sqlite` at cut-over because the running app keeps writing to the old one).

## 3. What the Director types at the Mac
```
mkdir -p ~/jarvis-assistant
cd ~/jarvis-assistant
claude
```
Then say: **"Read ~/flightops-ai/docs/office/jarvis/S3_HANDOVER.md and do step S3. Stop and ask me before anything not in it."**
