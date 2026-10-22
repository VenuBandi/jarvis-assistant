# FlightOps assignment workflow: independent validation

Validated 2026-10-21 against the read-only AssignmentBridge and actual built workflow page.

## Actual results

- `/opt/anaconda3/bin/python3 -m unittest discover -s tests -p test_jarvis_workflow_assignments.py -v`: **14 tests passed**.
- `/opt/anaconda3/bin/python3 tracker/render_jarvis_assignments.py`: **17 Chrome checks passed**, **9 observed events**, **4 assignment graph nodes**, **zero browser errors**.

The browser test runs an isolated real FastAPI/uvicorn application with a temporary project root, token, database and mock-provider configuration. It writes a task plan and status file, waits for the real background assignment watcher and authenticated SSE, then changes the status from recorded `running` to `done`, creates an output reference, and records an explicit accepted review. The frontend updates from those real file observations without manual bridge scans, UI fixture injection, or backend chat calls. Source filtering and record-only qualifiers are verified.

Production task artifacts, model settings, permissions, approvals and output files were not changed. The test browser made only GET requests to its temporary localhost app. No external providers were called, and OmniRoute import was disabled for isolation.

## Coverage and review

Independent tests cover recorded-running normalization to unknown; completion without inferred acceptance; explicit structured review with canonical aliases; stale recorded activity; deduplication and stable node/run IDs across updates; output existence without reading output contents; omission of task messages and argument bodies; private, absolute, traversal and data path rejection; source/output symlinks; malformed/oversized sources; source deletion invalidating prior graph nodes; output deletion updating availability without source edits; byte-identical source preservation; and task-ID traversal rejection.

The actual Chrome test verifies SSE connection and update delivery, source filtering, no running assignment animation, clear record-only notice, initially unverified review, explicit accepted review, output availability, privacy sentinel exclusion, desktop/mobile document overflow, local-only requests, GET-only browser behavior, and zero browser errors. Screenshots are actual 1440×1100 desktop and 390×1100 mobile captures. Both were independently viewed; assignment/provider/output/review nodes, record qualifiers, filter controls and inspector are visible.

Source review confirms descriptor-based traversal with `O_NOFOLLOW` for source and output paths, regular-file and single-link checks, bounded reads, restricted output-reference locations, and metadata-only event generation. Outputs are represented by path and availability; output bodies are never read. Deleted sources and removed outputs produce unavailable updates on stable node IDs. Allocation records do not claim a model call or live execution, and recorded completion does not imply accepted review.

One timestamp edge case was flagged to the implementation owner: an active record lacking an activity timestamp currently falls back to file modification time. The fallback reason is explicit, but fresh file modification alone should not establish fresh task activity. Final disposition is tracked with the owner.

## Artifacts

- `artifacts/logs/render/jarvis_assignments_validation.json`
- `artifacts/logs/render/jarvis_assignments_desktop.png`
- `artifacts/logs/render/jarvis_assignments_mobile.png`
- `tests/test_jarvis_workflow_assignments.py`
- `tracker/render_jarvis_assignments.py`
