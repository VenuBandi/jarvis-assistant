# Jarvis

Always-on personal AI assistant for macOS. Push a hotkey, speak — Jarvis thinks and responds.

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen)]()
[![Privacy](https://img.shields.io/badge/Privacy-Local%20Brain%20First-purple)]()

---

- Listens via a global hotkey (hold key → push-to-talk) using **local whisper.cpp STT**
- Routes to the right brain: **Qwen3/Gemma4 locally** for personal data, **Claude** for hard reasoning, **Gemini Flash** for speed
- Speaks back with **macOS native voices** and streaming replies
- Reads **FlightOps project status**, announces open decision cards
- Logs every tool call in a tamper-evident audit trail — R3 actions are unavailable, period

## Safety

Every action is classified by risk tier, enforced in code — the model cannot override it.

| Tier | Examples | Rule |
|---|---|---|
| **R0** Read | Calendar read, search, status | Runs directly — logged |
| **R1** Reversible | Create reminder, open app | Confirm once; "always allow" option |
| **R2** Outward | Send message, delete file, answer a card | Always shows exact action — waits for explicit "yes" |
| **R3** Forbidden | Passwords, Keychain, banking, `sudo` | Not available — ever |

Content from apps, mail, and web pages is treated as **data, never instructions**.

## Quick Start

```bash
python3 src/jarvis_app/run.py --check --ping   # startup check
python3 src/jarvis_app/run.py                  # → 127.0.0.1:8770
open http://127.0.0.1:8770
```

Jarvis Bar (menu-bar app) starts at login via LaunchAgent. Keys live in macOS Keychain, never in files.

## Build Status

| Phase | What | Status |
|---|---|---|
| Phase 1 | Core app, tool registry, agent loop, SQLite memory | ✅ Done |
| Phase 2 | Browser voice, React Flow workflow monitor | ✅ Done |
| J1a | Menu-bar app + LaunchAgent | ✅ Done |
| J1b | Hotkey push-to-talk, whisper.cpp STT, streaming voice | ✅ Done |
| J1c | FlightOps skill pack | ✅ Done |
| J2 | Mac skills: Calendar, Reminders, Finder, Safari | 🔄 In progress |
| J3 | "Hey Jarvis" wake word (openWakeWord + speaker verifier) | ⏳ Planned |
| J4 | Outward skills: Mail, Messages, WhatsApp | ⏳ Planned |
| J5 | Screen + UI control via Accessibility API | ⏳ Planned |
| J6 | iPhone reach | ⏳ Planned |

## Stack

| Layer | Tools |
|---|---|
| Core | Python 3.10+, FastAPI, SQLite |
| Brains | Ollama (Qwen3/Gemma4), Claude API, Gemini via OmniRoute, NVIDIA Nemotron, Mistral |
| Speech | whisper.cpp (STT), macOS AVSpeechSynthesizer (TTS) |
| Mac Skills | Apple Shortcuts CLI, AppleScript/JXA |
| Menu Bar | JarvisBar (Python), LaunchAgent |
| UI | React Flow (live execution graph) |
| Security | Loopback-only, API token, macOS Keychain, risk-tier enforcement |

## License

MIT
