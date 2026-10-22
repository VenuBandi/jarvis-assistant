# Jarvis workflow monitor delivery

Separate page: http://127.0.0.1:8770/workflow. Original chat frontend preserved at `/`.
Actual React Flow (@xyflow/react), locally bundled React assets; read-only interaction with live header-auth SSE.

## Implemented

- Per-app bounded metadata journal, ContextVar run/parent hierarchy and monotonic latency spans.
- Model requested/reported-served routing; unknown served identity retained explicitly when provider omits it.
- Actual tool validation/permission/confirmation/execution events; permissions rechecked before confirmed execution.
- Distinct memory read/write nodes around real operations, counts only; no memory text in telemetry.
- Failed model switch reports retained selection without adding a new automatic fallback policy.
- Read-only local OmniRoute completion-log metadata bridge; observed combo fallbacks require failed correlated
  attempt plus known route change. Separate gateway runs, not guessed cross-system correlations.
- Authenticated snapshot/SSE with replay, reset on retention gap/restart, heartbeats, disconnect/cancel handling.
- Interactive node canvas, pan/zoom/minimap, run selection, timeline, metadata inspector, error/stale/gap states,
  bounded client history and dragged-position storage. Existing permissions and confirmation callbacks remain.

## Actual verification

- 33 workflow Python tests passed (journal/API/SSE/concurrency/privacy/bridge/instrumentation).
- 26 existing Jarvis core tests passed.
- 13 React reducer/parser/layout-state tests passed.
- 12 existing voice/frontend integration tests passed.
- 16 real Chrome/SSE checks passed: isolated temporary backend, 32 actual mock-backend events, 7 graph nodes,
  distinct memory nodes, zero browser errors, desktop/mobile captures.
- React production bundle build passed.
- Launched updated live backend with existing database/token/model preserved (local-qwen); workflow page and
  authenticated snapshot HTTP200. Live production SSE time-tool check result saved separately in
  artifacts/handoff/FO-WORKFLOW/live_sse_check.json. Only a separate test conversation was used; no existing
  conversation, approval, provider choice, permission, or memory entry was changed by the smoke test.
- Monitor URL opened using macOS open. Backend process metadata: artifacts/handoff/FO-WORKFLOW/server.json.

Browser testing found a real ResizeObserver feedback issue; builder fixed deferred measurement updates and
fit behavior without suppressing warnings. Final review also added distinct memory spans instead of conflating
memory stages with model nodes. Independent review corrections have regression coverage.

## Limits

Telemetry is per-process and bounded, not a durable audit ledger. OmniRoute logs expose completed requests,
not all internal in-flight attempts. No fallback is fabricated when gateway correlation/route metadata is absent.
Gateway logs are local and metadata-only; no credentials or prompt bodies are sent to the browser. The launched
server uses the current configured model; switching models continues through the existing validated settings path.

Documentation: src/jarvis_app/README.md, workflow_ui/README.md. Independent evidence:
reports/office/jarvis_workflow_validation.md and jarvis_workflow_security_review.md;
artifacts/logs/render/jarvis_workflow_validation.json and jarvis_workflow_{desktop,mobile}.png.
