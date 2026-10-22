# Jarvis workflow monitor: independent validation

Validated 2026-10-21 against the implemented metadata event bus, authenticated snapshot/SSE routes, existing mock chat backend, and built React Flow UI.

## Actual results

- `/opt/anaconda3/bin/python3 -m unittest discover -s tests -p test_jarvis_workflow.py -q`: **16 tests passed**.
- `/opt/anaconda3/bin/python3 tracker/render_jarvis_workflow.py`: **16 browser checks passed**, **32 real generated events**, **7 operation nodes**, **zero browser errors**.
- The Chrome test starts a real temporary loopback uvicorn instance with the existing MockProvider and isolated SQLite/token files. It connects the actual frontend through authenticated SSE, then calls the existing chat endpoint to generate plain-chat and real `get_time` tool workflows. The graph is derived from these observed events, not UI fixtures.
- Production model selection, confirmations, memory, permissions, and tokens were not changed. No external provider requests were made; temporary-app OmniRoute log import was explicitly disabled.

## Coverage

The independent Python suite verifies bounded retention and slow-reader gaps; exclusive and limited replay; restart and future-cursor resets; defensive copies; metadata allowlists, credential redaction and nonfinite-number filtering; eight concurrent writers with ordered unique sequences; nested span parent/run relationships; context isolation; safe exception-type reporting; Host and token enforcement for both workflow API routes; page Host protection; original chat response compatibility; real model/tool instrumentation without prompt or tool-argument leakage; confirmation remains necessary before memory writes; SSE order, heartbeats, gap/restart frames, disconnect mid-batch, and prompt cancellation of idle streams.

Actual Chrome checks verify the connected state, React Flow nodes, distinct visible memory nodes with separate IDs from model operations, timeline, operation inspector, generated events, privacy sentinel absent from event metadata, original mock-chat response, real SSE request, browser GET-only behavior, localhost-only browser network requests, no JavaScript errors, and desktop/mobile document overflow. Desktop capture is 1440×1100; mobile capture is an actual emulated 390×1100 viewport. Existing Fit view is used for screenshots after viewport resizing.

## Issues found and resolved

The first real graph run produced Chrome's `ResizeObserver loop completed with undelivered notifications` error. The frontend builder preserved node measurement metadata, deferred controlled node-change batches outside the ResizeObserver delivery cycle, and simplified fit scheduling. The final browser run passed with an empty error list; no error suppression was added.

Initial browser harness startup navigation raced Chrome's first page load; the harness now waits for browser startup and explicitly selects a page target. It also deliberately selects the generated tool run, because the monitor correctly preserves the previously selected run when new runs arrive.

The final memory instrumentation check confirms real context-memory reads have distinct node IDs from their parent model operations and remain visible as memory nodes in the React Flow canvas. This closes the earlier representation gap where model completion overwrote memory stage labels on a shared node.

## Security and operational review

The event journal uses one lock for sequence allocation and snapshot/read access, returns deep copies, and retains a bounded deque. SSE pulls bounded batches rather than accumulating per-client queues, checks disconnects during replay, and cooperates with cancellation. The OmniRoute bridge is read-only, omits request/response bodies, credentials and raw error text, bounds file/state processing, and only reports fallback after an explicitly linked failed combo attempt and observed route change. No independent security blocker was identified in reviewed paths.

This is a per-process, bounded metadata monitor, not a durable audit ledger. A restart or retention gap requires the frontend's explicit history-gap/reset behavior. Mock-provider validation proves instrumentation and transport behavior; it does not claim that a paid provider or every external provider was called.

## Artifacts

- `artifacts/logs/render/jarvis_workflow_validation.json`
- `artifacts/logs/render/jarvis_workflow_desktop.png`
- `artifacts/logs/render/jarvis_workflow_mobile.png`
- `tests/test_jarvis_workflow.py`
- `tracker/render_jarvis_workflow.py`
