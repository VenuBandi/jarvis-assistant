# Jarvis — personal AI assistant

Local web app on your Mac: text chat, switchable AI models, a central tool registry with permissions,
confirmations and an audit log, SQLite storage, and browser voice conversation. Files, Google, Telegram,
invoices, calls, screen and browser automation come in later phases (see STATUS.md).

## Run
```
cd ~/flightops-ai
/opt/anaconda3/bin/python3 src/jarvis_app/run.py --check --ping   # startup checks + live ping of the active model
/opt/anaconda3/bin/python3 src/jarvis_app/run.py                  # → http://127.0.0.1:8770
```
Open http://127.0.0.1:8770 on the Mac. It listens on loopback only. Remote access needs JARVIS_ALLOW_REMOTE=1,
which is off on purpose.

## Voice conversation
Click 🎤, allow microphone access in the browser (and macOS if prompted), and speak. Interim text appears in
the input; when recognition finishes, the final transcript is submitted through the normal authenticated chat
route. The selected Brain answers, with the same permissions and confirmation buttons as typed chat.
Click the microphone again to cancel recognition. Mute/Unmute controls spoken replies; Stop Speaking cancels
current playback without stopping the backend task. The header Stop button still stops the backend task.
Replies, including replies after confirmation, use browser SpeechSynthesis and prefer a matching local voice.
Refreshing the page does not read old messages aloud. Speech errors remain visible beside the controls.

Recognition uses SpeechRecognition or webkitSpeechRecognition when available. Use a supporting browser
on localhost or HTTPS. Unsupported browsers keep text chat available. Permission denial instructions appear
beside the controls; allow access in browser site settings and macOS microphone settings, then retry.
The app adds no microphone recording, audio upload route, SDK, or third-party audio provider. The browser
owns recognition and may use its own remote speech service; this feature does not guarantee offline STT.

## Models
Configured in `src/jarvis_app/config/providers.yaml` (providers, models, capabilities, spoken aliases).
- **local-qwen**: Ollama qwen3-8b-32k. Default, free, private. Live-tested: tool calls work.
- **gemini-flash**: Gemini 3 Flash through your local OmniRoute (key file ~/.config/flightops/omniroute_key). Live-tested: tool calls work.
- **claude-sonnet / opus / haiku / fable**: Anthropic Messages API. Needs your key (below). Model IDs are
  **unverified** until a key is set and "Check" passes. "Fable 5" is an alias for claude-fable.
Switch from the dashboard's Brain menu, or say/type "switch your brain to Gemini". Jarvis pings the model
first and keeps the current one if the new one does not answer. The choice survives restarts.

### Add your Anthropic key (Keychain, never in files)
```
python3 -m keyring set jarvis anthropic_api_key
```
(paste the key at the hidden prompt). Or for development only: `export ANTHROPIC_API_KEY=...` before starting.

## Workflow monitor

Open **http://127.0.0.1:8770/workflow** alongside the existing chat. The separate React Flow canvas observes
real executions over authenticated SSE: model requests and reported served models, tool validation/permissions,
confirmation waits, distinct memory read/write nodes, measured latency, errors, and recorded routing fallbacks.
Drag nodes, pan/zoom, choose a run in the history, and select nodes or timeline entries for metadata.
The monitor is read-only: moving nodes changes the display, not execution or permissions.

The existing chat frontend remains at `/`. No prompt/response bodies, tool arguments/results, stored memory
text, credentials, account names, or API-key names are forwarded to the monitor. APIs retain the existing
Host check and `X-Jarvis-Token` header; the SSE client uses header-authenticated fetch, never URL tokens.
History is bounded and per-process (1,000 server events; 500 browser events / 100 runs). Reconnects replay
available IDs; history gaps and backend restarts trigger an explicit reset notice. This is not a durable audit log.

OmniRoute integration reads the latest 24 local completion logs and follows new files in
`~/.omniroute/call_logs/` at one-second intervals, without changing OmniRoute settings. It forwards only
allow-listed summary metadata. Gateway requests appear as separate recorded runs; they are not falsely
correlated with Jarvis spans. A fallback is marked observed only when failed, explicitly correlated combo
attempts change a known provider/model. Ordinary alias resolution is not proof of fallback. Hidden/unlogged
gateway attempts are unavailable; the page does not simulate them. Provider timestamps remain separate from
observation timestamps. Set `JARVIS_WORKFLOW_OMNIROUTE=off` to disable this bridge, or
`JARVIS_WORKFLOW_OMNIROUTE_LOG_DIR=/path/to/call_logs` to choose the local log directory.

Production assets are already bundled locally under `frontend/workflow/`; no CDN or Node server is needed
to run Jarvis. To rebuild after editing React source:

```bash
cd ~/flightops-ai/src/jarvis_app/workflow_ui
npm ci
npm run build
npm test
```

React Flow usage follows its [official documentation](https://reactflow.dev/learn).
Additional checks from the repository root:

```bash
/opt/anaconda3/bin/python3 -m unittest discover -s tests -p 'test_jarvis_workflow*.py' -q
/opt/anaconda3/bin/python3 -m unittest discover -s tests -p test_jarvis_app_core.py -q
/opt/anaconda3/bin/python3 tracker/render_jarvis_workflow.py
```

The browser harness uses real Chrome, an isolated temporary Jarvis backend, deterministic mock providers, and
actual SSE traffic. It exercises chat/tool/memory operations without changing production models or approvals.
Screenshots/results: `artifacts/logs/render/jarvis_workflow_*`; review reports:
`reports/office/jarvis_workflow_{validation,security_review}.md`.

## Tools (Phase 1)
| tool | type | notes |
|---|---|---|
| get_time | read | Mac's local time + timezone |
| list_models / switch_model | read / settings | switch validates first |
| flightops_status | read | from artifacts/progress.json |
| search_project_docs | read | keyword search over the existing Jarvis J1 index |
| remember | write | **asks for your confirmation** before storing |
| list_memory | read | |
Every call is validated (pydantic), permission-checked (toggles in the dashboard), time-limited, and written to
the audit log (tool, status, short argument summary; never secrets). Tool output is treated as data: the model is
told never to follow instructions inside it.

## Security
- Loopback only; every /api call needs the per-install token (data/jarvis_app/api_token, mode 600) in
  `X-Jarvis-Token`, and the Host header must be loopback (blocks other websites and DNS rebinding).
- Secrets: macOS Keychain (service "jarvis") → env var → mode-600 file. Never logged, stored or shown; errors are
  redacted.
- Write actions need confirmation; a confirmation runs once; a new message cancels an unanswered one.
- Stop button ends the current agent loop at the next step.

## Tests
```
/opt/anaconda3/bin/python3 -m unittest discover -s tests -p test_jarvis_app_core.py -q
node --test tests/frontend/jarvis_voice.test.cjs
```
26 backend tests and 12 frontend tests pass without network. Frontend tests simulate browser speech APIs
and exercise the chat wiring; physical microphone permission and audible playback need a manual browser check.
The system `python3` currently lacks FastAPI; the Anaconda Python above has the app dependencies.
Live check:
`python3 src/jarvis_app/smoke_live.py` (real models, temp data dir).

## Decisions (reversible)
- Code lives in `src/jarvis_app/` (not `jarvis/`): this Mac's session allow list runs Python only under `src/`.
- Dashboard is plain HTML/JS, not React: `npm install` is not allowed in phone sessions. It can move to React later
  without API changes.
- Anthropic via REST (httpx): the `anthropic` SDK is not installed and pip installs need your approval.
- Data: `data/jarvis_app/jarvis.sqlite` (git-ignored with data/).

## Limits
- No streaming yet (answers appear when complete). Local qwen is slower on long answers (about 20 s).
- Anthropic models untested until a key is added.
