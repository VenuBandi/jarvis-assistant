# Jarvis workflow monitor security review

Reviewed the metadata event bus, SSE generator, local OmniRoute completion bridge, FastAPI integration, agent/tool instrumentation, and React reducer/stream client. This is a code review with focused automated checks, not a production deployment approval.

## Findings sent to owners

1. **Lifecycle cleanup:** the lifespan generator currently calls `bridge.stop()` after a bare yield. Wrap yield in try/finally so exceptions propagated during app lifespan cannot skip cleanup. The worker is a daemon with a stop event and bounded join; normal shutdown already stops it.
2. **Validation outcome accuracy:** `/api/model/validate` currently ends its root run as completed when `models.validate()` returns false. Finish the root with error on unsuccessful validation; child validation errors already carry the true failure.
3. **Conservative fallback evidence:** only compare explicit, known route fields. The initially reviewed bridge treats missing provider/model changing to a known value as route change; that is insufficient evidence of fallback. The owner is refining this. A requested/served mismatch alone must never be called fallback.
4. **Client retention:** event/run history is bounded, but the initially reviewed `positions.current` map retains dragged node positions after those nodes expire. Prune it against retained node IDs to bound long-lived browser memory. Sent to frontend owner.

All four findings are corrected for the reviewed scope. Inspected the pure `prunePositions` helper and graph integration; reran the updated Node suite with **12 tests passed**, including expired-position removal and preserving retained runs. Re-inspected root changes: lifespan yield now has finally cleanup; failed model validation explicitly finishes the root with error; fallback comparisons require known values on both sides of the changed route field. Requested/served difference alone remains insufficient. No production files were edited as part of this independent review.

The bridge also now caches file mtime/size versions in a bounded 1,000-entry map to avoid reparsing unchanged log bodies. Initial loading is limited to 24 recent files; subsequent scanning filters older files against that baseline. Completion-log source labels and provider-recorded timestamp metadata distinguish historical observations from live instrumented model calls.

## Security controls verified by inspection

- Both workflow APIs use the existing token and Host guards. The streaming client passes the token in an HTTP header rather than a query string. Workflow HTML checks Host, suppresses caching/referrer exposure, and injects the token using the existing local app model.
- EventBus retains at most its configured capacity, uses a lock for consistent copies, bounds metadata keys/string lengths/numbers, and applies existing secret redaction. Prompt, response, raw error, tool argument/result, and memory body fields are excluded from the allowlist. IDs from OmniRoute records are hashed rather than exposed.
- SSE pulls bounded batches from the journal without a per-client producer queue, checks disconnects, yields cooperative waits, supports retention/restart reset, and sends heartbeats. No browser EventSource query-token workaround is used.
- Span exits reset ContextVar scope in a finally block, record monotonic duration, and capture only exception type. Tool workers copy context so nested model switches retain correct run attribution.
- React renders metadata as escaped text. The reducer deduplicates IDs, caps 500 events and 100 runs, marks history gaps/restarts, and prevents cyclic parent records from crashing layout.
- The monitor is observe-only. It does not add execution controls, new permissions, route selection, or routing fallback policy.
- Confirmation execution rechecks tool existence and permission immediately before validation/execution. A pending approval cannot bypass a subsequently disabled permission. Exactly-once pending decision behavior remains enforced by the database.
- Provider adapters preserve existing API behavior while recording whether a model identifier was actually supplied. Unknown served identifiers remain unknown in events. Local OmniRoute log records are marked completion-log observations, not instrumented in-flight calls.

## Actual checks

Executed `/opt/anaconda3/bin/python3 -m unittest discover -s tests -p 'test_jarvis_workflow*.py' -q`: **23 tests passed**. Coverage includes auth/Host failures, bounded event retention/reset, scope/latency, stream behavior, metadata privacy, confirmation permission recheck, successful versus disabled memory writes, and selected-model retention after failure.

Executed `node --test state.test.mjs` in `src/jarvis_app/workflow_ui`: **9 tests passed**. Coverage includes event/run bounds, replay deduplication, restart/gap state, lifecycle merging, SSE chunk boundaries, incomplete frames, and parent cycles.

The earlier instrumentation regression run also passed all **26 existing Jarvis app core tests**. No live provider credentials or private transcripts were used in this review's test runs. Privacy relies on intentionally limited metadata fields plus redaction; this does not establish that arbitrary caller-provided strings are intrinsically safe, so callers must continue emitting only documented metadata.

Final follow-up: added two focused regression tests in `test_jarvis_workflow_instrumentation.py`: failed validation produces `run.error`, and a synthetic lifespan exception still invokes bridge stop exactly once. Reran the complete workflow Python pattern after root's bridge tests landed: **32 tests passed** (including the two new checks). No unresolved blocking finding remains from this review for the local observe-only workflow monitor. This conclusion is scoped to the reviewed behavior and is not a production security certification.

Final memory visibility refinement: actual memory context reads and memory-tool execution now have dedicated child spans, rather than only stage events merged into their parent node. Read/write counts remain metadata-only and come from successful operations; other tools do not receive synthetic memory nodes. Added a real EventBus hierarchy/privacy test verifying distinct node IDs and model/tool-execution parents. Latest rerun: **33 workflow tests and 26 existing app core tests passed**.
