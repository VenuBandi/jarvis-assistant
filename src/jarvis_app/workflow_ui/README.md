# Jarvis workflow monitor frontend

Separate read-only React Flow page at `/workflow`, observing real events from the existing authenticated backend. It never submits chats, executes tools, approves requests, or changes model selection.

Committed local bundles need no Node installation to run the Python application. Rebuild after source edits:

```sh
cd src/jarvis_app/workflow_ui
npm ci --no-audit --no-fund
npm test
npm run build
```

Source: `app.jsx`, `styles.css`, independently testable `state.mjs`. Build output: `../frontend/workflow/app.js` and `app.css`. HTML shell: `../frontend/workflow.html`. No CDN resources.

Server substitutes `__JARVIS_TOKEN__` in the HTML meta element. Snapshot and SSE requests use the `X-Jarvis-Token` header. Tokens never enter URLs. Fetch streaming supports this header, unlike native EventSource.

Endpoints: `GET /api/workflow/snapshot`, `GET /api/workflow/events?after=<cursor>&instance_id=<id>`. SSE kinds: `workflow`, `reset`, `heartbeat`. Reconnect resumes from the cursor; replay is deduplicated. Instance changes and expired history are explicitly marked. Client retains at most 500 events and 100 distinct runs. Only backend metadata is shown; browser fabricates no execution events.

Drag nodes, pan canvas, use minimap/zoom controls. Edges and execution remain read-only. Node/timeline selection opens metadata. Empty backend displays an explicit waiting canvas. Mobile places run selector above canvas and operation details below.

## FlightOps assignment records

The source selector separates Jarvis, OmniRoute, and FlightOps assignment records. FlightOps nodes represent recorded task, provider allocation, output references, and review metadata; they do not execute agents or prove that a provider served a model request. Recorded running states never animate edges or count as live running operations. Missing and stale records remain explicit. Provider allocations are labeled separately from observed provider/model calls.
