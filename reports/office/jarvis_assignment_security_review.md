# FlightOps assignment monitor security review

Independent read-only review of `workflow/assignments.py`, expanded EventBus fields, and assignment/source-filter frontend semantics. No task source, task execution, Ops activation, provider configuration, or production code was changed during this review.

## Findings and resolution

1. When a handoff status source is missing/unreadable but the plan still supplies an accepted review, `_task(..., available=False)` now downgrades the record review to `unverified` and the review child to `unknown`. Output-file physical availability remains separately qualified.
2. The root directory descriptor is now opened with `O_NOFOLLOW`, matching child traversal and rejecting a root path swapped to a symlink after constructor resolution.

Both findings were corrected in the source after the initial review and revalidated by the targeted test suite and isolated browser fixture.

## Verified properties

- Source access is read-only and restricted to fixed plan/resume/allocation metadata paths plus ID-validated per-task status files. Reads cap at 1 MiB and accept JSON objects only. Task counts cap at 200 handoff, 100 resume, and 100 allocation records; output references cap at 30 per task.
- The bridge never reads output/report bodies. Output references are allowlisted relative `.md`/`.json`/`.csv` paths under reports, office docs, and handoff artifacts; absolute/traversal/backslash/control-character paths and sensitive directory/file names are excluded. Reference existence uses open/fstat only.
- Descriptor traversal rejects linked child directories/files, nonregular leaves, and hardlinked leaves. File reads use a bounded descriptor handle, so later pathname replacement cannot redirect an already-open read.
- Only selected metadata fields enter events. Prompt/task notes/stdout/stderr/report content/acceptance prose are not forwarded. Expanded metadata fields retain existing length bounds, redaction, and scalar-only handling. React displays paths as escaped text, without adding filesystem download/open endpoints.
- Recorded `running` does not emit a live started/running execution signal. UI source filters, record banners, node labels, inspector wording, and unanimated assignment edges explicitly distinguish records from actual model/tool execution.
- Task `done` does not imply review accepted. Review verdicts require explicit recognized review metadata; unknown values remain unverified.
- Changed records are compared against prior rows. Removed task/output nodes receive unknown/unavailable events. Stable scans deduplicate; stale transitions can emit new observations. State is bounded by fixed collection limits and the existing event journal/UI retention limits.
- The assignment bridge adds no execution, approval, tool-permission, provider-selection, or model-routing behavior. Existing API token/Host controls remain in place; monitor sources remain observations only.

## Actual validation

Ran `/opt/anaconda3/bin/python3 -m unittest discover -s tests -p 'test_jarvis_workflow*.py' -q`: **47 tests passed**. Ran `node --test state.test.mjs` in workflow_ui: **17 tests passed**, including source separation, no live animation for recorded running, unknown review replacing completed state, and retained task titles while children update.

The isolated browser fixture additionally passed 17 checks: actual file-change observation through SSE, source filtering, no live animation for recorded running state, private-body exclusion, responsive desktop/mobile layout, no POST requests, local-only network requests, and no browser errors. This review is scoped to the local observe-only assignment integration and is not a production security certification.
