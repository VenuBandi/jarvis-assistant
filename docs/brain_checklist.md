# Brain checklist: can Jarvis switch to every brain? (2026-10-22)

Two kinds of brain:
- **App models**: what "switch to Sonnet" changes in the Jarvis app. Config: `src/jarvis_app/config/providers.yaml`.
  A switch first pings the model and keeps the current one if the ping fails.
- **Project Q&A brains**: `src/jarvis/ask.py --brain …`. Config: `data/jarvis/brains.json`.

Columns:
- **Offline switch**: `tests/test_jarvis_brain_switch.py`. Fake pings, real config files. Proves the brain is
  configured and switching works by key, label and every spoken alias, the choice survives a restart, and a failed
  ping keeps the current model.
- **Key**: whether Jarvis's own key is in place. Checked by file existence and mode only; nothing was read.
- **Live**: a real ping from `~/jarvis-assistant`. Not run yet; it needs the keys and the Director's OK.

Same brains as before the move: `brains.json` is byte-identical to FlightOps' copy, and `providers.yaml` differs only
in key paths (`~/.config/flightops/` became `~/.config/jarvis/`).

## App models (13; default `local-qwen`)
| # | Model | Spoken names | Provider | Offline switch | Key | Live |
|---|---|---|---|---|---|---|
| 1 | `claude-sonnet` Claude Sonnet 5.5 | sonnet, claude sonnet | anthropic | ✅ | Keychain "jarvis/anthropic_api_key" (not checked) | ☐ |
| 2 | `claude-opus` Claude Opus 5.5 | opus, claude opus | anthropic | ✅ | same | ☐ |
| 3 | `claude-haiku` Claude Haiku 5.5 | haiku, claude haiku | anthropic | ✅ | same | ☐ |
| 4 | `claude-fable` Claude Fable 5.1 | fable, fable 5, claude fable | anthropic | ✅ | same | ☐ |
| 5 | `gemini-flash` Gemini 3 Flash | gemini, gemini flash | omniroute (127.0.0.1:20128) | ✅ | ❌ `~/.config/jarvis/omniroute_key` missing | ☐ |
| 6 | `nv-nemotron-ultra` Nemotron 3 Ultra 550B | nemotron, nemotron ultra | nvidia | ✅ | ❌ `~/.config/jarvis/keys/nvidia` missing | ☐ |
| 7 | `nv-nemotron-lightning` Nemotron 3.5 Lightning 30B | nemotron lightning | nvidia | ✅ | ❌ same | ☐ |
| 8 | `nv-glm` GLM 5.3 | glm | nvidia | ✅ | ❌ same | ☐ |
| 9 | `nv-gpt-oss` gpt-oss 20B | gpt oss | nvidia | ✅ | ❌ same | ☐ |
| 10 | `nv-glimmer` Muse Glimmer 30B | glimmer | nvidia | ✅ | ❌ same | ☐ |
| 11 | `mi-codestral` Codestral | codestral | mistral | ✅ | ❌ `~/.config/jarvis/keys/mistral` missing | ☐ |
| 12 | `mi-ministral` Ministral 8B | ministral | mistral | ✅ | ❌ same | ☐ |
| 13 | `local-qwen` Qwen3 8B | local, qwen, local model | ollama (127.0.0.1:11434) | ✅ | not needed | ☐ (last live check in the copied DB: OK, 0.4 s, 2026-10-21T18:49Z) |

Also checked offline: every provider's adapter builds; a round trip through all 13 and back to `local-qwen` persists.
For each provider, an unreachable model is refused and the current model is kept.

## Project Q&A brains (`ask.py --brain`, auto order codex → opencode → omniroute → local)
| # | Brain | Offline select | Needs | Live |
|---|---|---|---|---|
| 1 | `codex` | ✅ | `codex` CLI (found at /opt/homebrew/bin/codex) | ☐ |
| 2 | `opencode` | ✅ | `opencode` CLI (found at /opt/homebrew/bin/opencode) | ☐ |
| 3 | `omniroute` | ✅ | ❌ `~/.config/jarvis/omniroute_key` missing; gateway on 127.0.0.1 | ☐ |
| 4 | `local` (qwen3-8b-32k) | ✅ | Ollama (found at /usr/local/bin/ollama) | ☐ |
| – | `claude` | disabled in `brains.json` (unchanged) | – | – |
| – | `council` | codex + opencode; falls back to the next brain in the order | – | – |

OmniRoute approved models. The brain uses the one set in `brains.omniroute.model`; changing models means editing that
field.

| Model | Offline (sent as `model`) | Live |
|---|---|---|
| `antigravity/claude-sonnet-4-6` (current) | ✅ | ☐ |
| `antigravity/claude-opus-4-6-thinking` | ✅ | ☐ |
| `antigravity/gemini-3-flash` | ✅ | ☐ |
| `antigravity/gemini-3.5-flash-lite` | ✅ | ☐ |
| `gemini/gemini-3.8-flash` | ✅ | ☐ (FlightOps review 2026-10-21: HTTP 503 after 29.6 s, "not reliable") |
| `ollama-local/qwen3-8b-32k` | ✅ | ☐ |

## How to tick the Live column (after the Director's OK; never against the running Jarvis on 8770 before S4)
1. Director creates `~/.config/jarvis/omniroute_key`, `keys/nvidia`, `keys/mistral` (mode 600).
2. App models: after S4 cut-over, say or type "switch to <name>" for each row. Jarvis pings the model and answers
   "Switched to …" or "not reachable, I kept …". The result is stored as `model_checks` in `data/jarvis_app/jarvis.sqlite`.
3. Q&A brains: `python3 -I src/jarvis/brains.py --probe codex` (then `opencode`, `omniroute`, `local`). This sends one
   fixed "reply {ok: true}" prompt and nothing from the project.
