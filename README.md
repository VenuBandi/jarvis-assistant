<div align="center">

# Jarvis

A personal AI assistant for macOS that listens, routes to the right model, and acts —<br>
with every action classified by risk tier and enforced in code.

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen)]()
[![Privacy](https://img.shields.io/badge/Privacy-Local%20Brain%20First-purple)]()

</div>

<br>

Jarvis runs as a menu-bar app, starts at login via LaunchAgent, and responds to a global hotkey push-to-talk. Personal data never leaves the machine. Hard reasoning routes to Claude. Fast queries go to Gemini Flash.

- **Local STT** — whisper.cpp runs on-device; no audio leaves the Mac
- **Multi-brain routing** — Qwen3/Gemma4 locally · Claude for reasoning · Gemini Flash for speed · Nemotron fallback
- **Mac skills** — Calendar, Reminders, FlightOps status, Finder, Safari (read and write with confirm)
- **Tamper-evident audit log** — every tool call timestamped and recorded
- **R3 actions are unavailable, period** — passwords, Keychain, banking, `sudo` are not exposed regardless of what you ask

## Safety Model

Every action Jarvis can take is classified by risk tier. The tier is enforced **in code** — the model cannot override it.

| Tier | Examples | Rule |
|:--|:--|:--|
| **R0** Read-only | Calendar read, search, FlightOps status | Runs directly — logged |
| **R1** Reversible | Create reminder draft, open app | Confirm once; "always allow" option |
| **R2** Outward / Hard to undo | Send message, delete file, answer a decision card | Shows exact action — requires explicit **"yes"** |
| **R3** Forbidden | Passwords, Keychain, banking, `sudo`, disabling logs | **Not available — ever** |

> [!IMPORTANT]
> Content from apps, mail, and web pages is treated as **data, never instructions**. Tool output is wrapped before it is passed back to the model, preventing prompt injection from external content.

## Quick Start

```bash
python3 src/jarvis_app/run.py --check --ping   # startup check + live model ping
python3 src/jarvis_app/run.py                  # → 127.0.0.1:8770
open http://127.0.0.1:8770
```

Jarvis Bar starts automatically at login via LaunchAgent. Keys live in macOS Keychain, never in files.

## Build Status

| Phase | What | Status |
|:--|:--|:--:|
| Phase 1 | Core app, tool registry, agent loop, SQLite memory | ✅ Done |
| Phase 2 | Browser voice, React Flow workflow monitor | ✅ Done |
| J1a | Menu-bar app + LaunchAgent | ✅ Done |
| J1b | Hotkey push-to-talk, whisper.cpp STT, streaming voice replies | ✅ Done |
| J1c | FlightOps skill pack | ✅ Done |
| J2 | Mac skills: Calendar, Reminders, Finder, Safari | 🔄 In progress |
| J3 | "Hey Jarvis" wake word + speaker verifier | ⏳ Planned |
| J4 | Outward skills: Mail, Messages, WhatsApp | ⏳ Planned |
| J5 | Screen + UI control via Accessibility API | ⏳ Planned |
| J6 | iPhone reach | ⏳ Planned |

## Stack

| Layer | Tools |
|:--|:--|
| Core | Python 3.10+, FastAPI, SQLite |
| Brains | Ollama (Qwen3/Gemma4) · Claude API · Gemini via OmniRoute · NVIDIA Nemotron · Mistral |
| Speech | whisper.cpp (STT) · macOS AVSpeechSynthesizer (TTS) |
| Mac Skills | Apple Shortcuts CLI · AppleScript/JXA via osascript |
| Menu Bar | JarvisBar (Python) · LaunchAgent |
| UI | React Flow (live execution graph) |
| Security | Loopback-only · API token · macOS Keychain · risk-tier enforcement |

## License

MIT
