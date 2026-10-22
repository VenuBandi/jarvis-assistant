# Work order J5 — FlightOps Galaxy (3D project map)

> **Moved to FlightOps (S2, 2026-10-22):** FlightOps Galaxy is now built by `~/flightops-ai/src/office/galaxy_build.py`.
> Kept here as Jarvis history only.

Approved: Director in chat, 2026-10-19 ("start J5 galaxy now"). Design: jarvis_plan.md §J5 detail (from the
Director's screenshot of "AI WORKSHOP OS"). Team: Engineer (Claude subagent) builds; QA (separate subagent) checks
the graph data against the files; Lead render-checks and promotes the page.

## 1. Graph data — `src/jarvis/galaxy_build.py [--out]` (Python stdlib only)
Every node and every link comes from a file; each carries `src` = "<path>#<field/row/line>" proving it.
Node types (colour + filter legend):
| type | from |
|---|---|
| step | progress.json `milestones` (M0–M6) + `agent.plan` |
| factor | progress.json `factors` (G1–G12) |
| feature | docs/registry/data_dictionary.csv rows (`feature_id`) |
| source | docs/registry/source_registry.csv rows (`source_id`) |
| data | data/features/*.parquet, data/processed/*.parquet (file names only; never open or copy data rows) |
| script | src/**/*.py (not tests) |
| doc | docs/**/*.md, reports/*.md |
| decision | artifacts/decisions/*.json |
| agent | progress.json `agent.office` workers |
Links (only when the file says so): feature→factor (`g_category`); factor→source (coverage `primary_sources` /
source `factors`); feature→source (`raw_source` when it names a source id); decision→evidence path; agent→output path;
step→task evidence path; script→data file (only if the script's text contains that file name, by grep-style match);
doc→file it names (backticked or plain relative paths that exist). Unresolvable reference → skipped and counted.
Layout: deterministic 3D force layout in Python (fixed seed) → x,y,z per node, so the phone only draws.
Output `artifacts/galaxy/galaxy.json`: `{"built_at","counts":{by type, links, skipped_refs},"nodes":[{"id","type","label","path","src","x","y","z","deg"}],"links":[[i,j,"kind"]]}`;
keep it compact (target < 80 KB). `--out` also stores it for the app via
`python3 tracker/agent_update.py galaxy artifacts/galaxy/galaxy.json` (Lead adds this command; Engineer must not edit tracker/).

## 2. Page — in `tracker/index_stage_galaxy.html` only (Lead stages it; never edit tracker/index.html)
A "Galaxy" button on the Home tab (and Data tab) opens a full-screen overlay (Esc/close button returns).
Canvas 2D drawing of the 3D points (own small projection code; **no external libraries, no CDN**):
- drag = rotate, pinch / wheel = zoom, tap = select; light live force sim in JS starting from the given positions
  with **Repel** and **Link length** sliders (pause the sim when the overlay is closed or the tab is hidden).
- Left/top panel (collapsible on phone): search box; **inspector** (selected node: type, label, path, src, neighbours;
  only it + its links light up); **Trace path** button: pick a second node → shortest path highlighted;
  **Top hubs** (highest degree, with counts); filter legend by type with counts.
- **Jarvis dial** (corner): state text from progress.json `agent.state` + "brain: none (J1 not connected)" — truthful.
- **Fly to source:** each briefing line's source path (Home briefing card) gets a small "show in galaxy" link that
  opens the overlay and flies the camera to that file's node (if it exists).
- Works at 390 px width, light + dark (use the page's CSS variables). Smooth on a phone: ≤ ~400 nodes, draw labels only
  for hubs + selection.

## 3. Tests + checks
- `tests/test_jarvis_galaxy.py` (unittest, fake project in temp folder): node/link extraction, skipped refs counted,
  determinism (same input → same output), no data rows read (only file names).
- QA `src/validate/qa_j5_check.py` (own code): recount nodes per type from the files; for every link, open its `src`
  and confirm the reference; 0 dangling links; 0 secrets in galaxy.json (sb_secret_/service_role/eyJ/BEGIN PRIVATE KEY);
  size. Report `reports/j5_check.md|json`; PASS = counts match, 100% links proven, 0 secrets.
- Lead: render_check of the staged page (all tabs × themes, 0 JS errors, no sideways scroll) + overlay screenshots,
  then `stage_page.py promote galaxy`.

## 4. Rules
Phone-session tool rules (python3 -I src/..., unittest discover, no inline python, no tracker/ edits except the
staged page file named above). Never invent nodes, links or counts.
