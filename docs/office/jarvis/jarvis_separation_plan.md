# Jarvis ↔ FlightOps separation plan (draft for approval)

Director 2026-10-22: pull Jarvis — including all its brains, NVIDIA too — completely out of FlightOps. Anything FlightOps
itself uses must stay working with FlightOps' own copy, and every place where FlightOps uses something *through* Jarvis
must be fixed. Plan only: nothing moved, nothing restarted. Inventory checked in the repo on 2026-10-22.

## 1. Target
```
~/flightops-ai          FlightOps only: data, models, recovery engine, tracker app, iOS app, its own AI-provider config
~/jarvis-assistant      Jarvis only (new folder, own git repo): assistant code, brains, voice, memory, Mac skills, tests
Shared infrastructure   OmniRoute gateway and Ollama stay system services; each project has its own config for them
Jarvis → FlightOps      only through FlightOps' own scripts / small local API (status, cards, control, run_job)
```

## 2. Inventory (what is where today)

### A. Jarvis-owned → moves to ~/jarvis-assistant
| Item | Notes |
|---|---|
| `src/jarvis_app/` (whole app: brains config `providers.yaml`, voice, tools, workflow monitor, frontend) | running on 127.0.0.1:8770 (last known PID 77622, from the Codex checkpoint) |
| `src/jarvis/` assistant parts: `ask.py`, `agentic.py`, `build_index.py`, `corpus_build.py`, `briefing.py`, `galaxy_build.py`, probes (`nvidia_probe`, `omniroute_*`, `tavily_search`) | see B for the shared parts |
| `data/jarvis/`, `data/jarvis_app/` | index, Q&A runs, SQLite, API token |
| `docs/office/jarvis/`, `tests/test_jarvis_*.py` (11), `tests/frontend/jarvis_voice.test.cjs` | |
| `src/validate/qa_j1_*`, `qa_j2_check`, `qa_j5_check`; `reports/j1_*`, `reports/j2_check.json`; `reports/office/jarvis_*` | Jarvis evaluation history |
| `tracker/render_jarvis*.py`, `tracker/env_probe_jarvis.py` | |
| Keychain service "jarvis" (Anthropic key) | already Jarvis's |

### B. Shared code FlightOps uses → FlightOps keeps its OWN copy (then Jarvis takes the original)
| Jarvis module | Used by FlightOps in | FlightOps copy |
|---|---|---|
| `src/jarvis/brains.py` (Brain classes, OmniRoute/CLI brains, engine) | `src/office/role_runner.py` (Floor 2 roles), `tracker/ops_runner.py`, `src/ops/request_card.py`, `tracker/or_messages_probe.py`, `src/validate/qa_ops_desk_probe.py` | `src/common/ai/brains.py` |
| `src/jarvis/jarvis_core.py` helpers (`norm_text`, `extract_json`, `numbers_in`, `is_excluded`, …) | `role_runner.py`, `src/validate/secret_scan_docs.py` | `src/common/text_tools.py` (only the functions used) |
| `src/jarvis/omniroute_search.py` | `src/research/or_multi_search.py` (Phase 1 research) | `src/common/ai/omniroute_search.py` |

### C. Config and data FlightOps uses through Jarvis → FlightOps' own config
| Today | Used by | FlightOps own |
|---|---|---|
| NVIDIA + Mistral entries in `src/jarvis_app/config/providers.yaml` | `src/office/direct_ping.py`, `src/office/tool_status.py` (Tools & feeds card) | `config/ai_providers.yaml` (NVIDIA, Mistral, OmniRoute, Ollama) |
| `data/jarvis/brains.json` approved model list | `tracker/fallback.py` | `config/approved_models.json` |
| `data/office/role_brains.json` | `role_runner.py` | already FlightOps (stays) |
| Keys `~/.config/flightops/keys/nvidia`, `…/mistral`, `~/.config/flightops/omniroute_key` | both | stay FlightOps'. Jarvis gets its own `~/.config/jarvis/…` keys (the Director creates them; separate keys so revoking one never breaks the other) |

### D. Jarvis features inside the FlightOps tracker app
| Feature | Built by | Decision needed |
|---|---|---|
| Jarvis screen (orb, "Ask Jarvis", mic) in `tracker/index.html` | Jarvis | remove from FlightOps |
| "FlightOps Galaxy" 3D project map (Home + Factors) | `src/jarvis/galaxy_build.py` | **Q1** keep as a FlightOps project map (move the builder into FlightOps) or remove |
| Home "Jarvis briefing" card | `src/jarvis/briefing.py` | **Q1** same question |
| Chat tab "Front Desk" auto-drafts with local qwen (`tracker/agent_brain.py`, started by `tracker/server.py`) | FlightOps tracker, but it is an assistant brain | **Q2** keep as FlightOps project chat, or move to Jarvis and keep only Director ↔ Claude chat |
| Office roster: Front Desk "Jarvis auto: Codex → Claude → local qwen" | office JSON | rename / reassign after Q2 |

### E. History (decision cards, old reports mentioning Jarvis)
Kept in FlightOps as governance history (not runtime). Jarvis-only evaluation reports move with Jarvis (A).

## 3. Steps (each verified, Director approves each)
| Step | What | Verified by |
|---|---|---|
| S1 **done 2026-10-22** | Create FlightOps-owned `src/common/ai/` (brains, omniroute_search), `src/common/text_tools.py`, `config/ai_providers.yaml`, `config/approved_models.json`; re-point the 9 FlightOps files in B/C; no behaviour change | FlightOps tests (`test_role_runner`, QA scripts) pass; a check script proves **no FlightOps file imports `src/jarvis*` or reads Jarvis config/data**; NVIDIA/Mistral ping still OK from the new config |
| S2 **done 2026-10-22** | Tracker app: remove the Jarvis screen; Galaxy / briefing / Front Desk per Q1–Q2 | render check (all tabs, light + dark, no errors) |
| S3 | Build `~/jarvis-assistant` as a copy (code, data, docs, tests) with its own config + key paths; Jarvis tests pass there | Jarvis's 26 + 12 tests + workflow tests in the new folder |
| S4 | Cut-over: stop Jarvis on 8770 from the old folder, start it from the new folder (**restart needs your approval**, at a time Jarvis is idle) | Jarvis answers on 8770 from the new folder; workflow monitor live |
| S5 | Remove the Jarvis copies from FlightOps (listed in A), update docs (README, roadmap, CLAUDE.md note), office roster, Tools card | full FlightOps checks + render check; grep shows Jarvis only in history |
| S6 | Jarvis J1+ continues in its own project | — |

**Permission note:** this Claude session may only work inside `~/flightops-ai`. S3–S5 need either a separate Claude session
opened in `~/jarvis-assistant`, or the Director adding that folder to the allow list. Moving/deleting files is done with a
reviewed script, never by hand; nothing is deleted until S3 + S4 are verified.

## 3b. Director decisions (2026-10-22) and S1 result
- Q1 delegated → Lead: Galaxy map + Home briefing **stay in FlightOps** (they describe FlightOps files/progress only);
  their builders move from `src/jarvis/` into FlightOps in S2; renamed "FlightOps Galaxy" / "Project briefing".
- Q2: Chat-tab Front Desk brain (`tracker/agent_brain.py`) **stays in FlightOps** (project chat).
- Q3: `~/jarvis-assistant` approved. Jarvis hotkey: hold Right-Option+H 3 s; WhatsApp read + draft first.

**S1 done 2026-10-22 (verified):**
- New FlightOps-owned: `src/common/ai/ai_brains.py` (OmniRouteBrain, BrainError, load_config, strip_tokens),
  `src/common/ai/ai_text.py` (secret patterns, text/number helpers, extract_json, is_excluded),
  `src/common/ai/omniroute_search.py`, `config/ai/providers.yaml` (NVIDIA, Mistral, OmniRoute, Ollama),
  `config/ai/brains.json` (OmniRoute settings + approved models for office roles).
- Re-pointed 10 files: `src/office/role_runner.py`, `src/validate/qa_role_runner.py`, `src/validate/secret_scan_docs.py`,
  `tracker/or_messages_probe.py`, `src/ops/request_card.py`, `tracker/ops_runner.py`, `src/validate/qa_ops_desk_probe.py`,
  `src/research/or_multi_search.py`, `src/office/direct_ping.py`, `src/office/tool_status.py` (+ comment in `tracker/fallback.py`).
- `src/validate/check_no_jarvis_dependency.py`: **0 runtime dependencies** on Jarvis in FlightOps code; control run that
  includes Jarvis's own files finds 64 (the check works). 15 tracker-app items remain for S2.
- `src/validate/s1_equivalence_check.py`: FlightOps copies vs Jarvis originals — **0 differences** on 634 text samples
  (incl. attack strings) and 5,557 repo paths; OmniRoute settings identical.
- Tests: 62 / 62 pass (same as the baseline before the change). NVIDIA ping from FlightOps' own config: Lightning 1.3 s,
  gpt-oss 0.6 s OK. Search via FlightOps' own client OK. Tools card rebuilt; app render check OK.
- **Pre-existing issues found (not caused by S1; identical behaviour proven):**
  1. `src/validate/qa_role_runner.py` crashes at its secret check because the role runner was fixed after that QA script
     was written (it now refuses secret-like tasks); the QA script needs updating.
  2. Ops-desk probe P7a–c: `strip_tokens` misses keys split by colour codes, multi-line private-key bodies, and
     Groq / **NVIDIA** / 64-hex key formats. Now that FlightOps owns this code and calls NVIDIA, worth fixing (small task,
     needs approval). P10 is informational.

**Scrubber fix + S2 done 2026-10-22 (Director: "start S2 and fix the scrubber"; verified):**
- Scrubber (`src/common/ai/ai_brains.py`, `ai_text.py`, `tracker/ops_runner.py`): multi-line private keys, PEM without
  END line, Groq `gsk_`, NVIDIA `nvapi-`, 64-hex keys; colour codes removed before known-key replacement. Ops-desk probe
  4 → 1 finding (P7a–c fixed; P10 informational). New `tests/test_ai_scrubber.py` (6 tests incl. "ordinary text unchanged").
  Note: 64-hex redaction also hides SHA-256 values in scrubbed output (manifests are not scrubbed).
- Tracker app: Jarvis screen removed (`src/office/s2_strip_jarvis_ui.py`: CSS 48 + button 1 + dialog 34 + JS 122 lines,
  plus one call in render(); backup `tracker/index_before_s2.html`); "Jarvis briefing" → "Project briefing"; all builder
  paths now FlightOps'. `tracker/index.html` contains 0 "jarvis" mentions.
- Builders moved (`src/office/s2_move_builders.py`): `src/office/project_briefing.py`, `src/office/galaxy_build.py` +
  `tests/test_project_briefing.py`, `tests/test_galaxy_build.py` (26 tests OK); briefing and Galaxy rebuilt with them.
- Front Desk stays (Q2): roster model text corrected to what `tracker/agent_brain.py` really runs (local qwen3 drafts,
  Claude reviews).
- Checks: dependency check FAIL 0 / S2 0 (control 70); 94 / 94 tests; render check OK on all tabs, light + dark.

## 4. Questions for the Director (answered 2026-10-22, see 3b)
- **Q1** FlightOps Galaxy map and Home briefing: keep them as FlightOps features (built by FlightOps code), or remove?
- **Q2** Chat tab Front Desk auto-drafting brain: keep in FlightOps (project chat), or move to Jarvis?
- **Q3** Folder name for Jarvis: `~/jarvis-assistant` OK?
