# Jarvis J0 design v2 — the Director's personal assistant on the Mac (draft for approval)

Written 2026-10-22 by the Lead (Claude), phone session, in parallel with Phase 2. **Design only: nothing installed, no new
macOS permissions, no restarts.** Replaces the 2026-10-19 plan (`jarvis_plan.md`), which kept Jarvis to project
questions and explicitly excluded Mac control.

## 1. Goal (Director, 2026-10-21/22)
"Like Siri is for Apple, I want Jarvis for me." Jarvis lives on the Mac, above everything, with access to the Director's
applications, and can operate FlightOps. It is **not** part of the airline iOS product.

```
Director (voice / hotkey / iPhone later)
└── Jarvis on the Mac: always running, listens on demand, thinks with a chosen brain, acts through skills
    ├── FlightOps skill pack: status, decision cards, pause/resume, approved jobs, reports
    ├── Mac skills: Shortcuts, scriptable apps (Calendar, Reminders, Notes, Mail, Finder, Safari, Music…)
    └── (later) screen + UI control, personal accounts (Google, Telegram…)
```

**Separation (Director, 2026-10-22):** Jarvis leaves the FlightOps repo entirely — code, brains (NVIDIA too), data, docs,
tests — for its own folder; FlightOps keeps its own copies of the providers it uses. See `jarvis_separation_plan.md`.
All J-steps below happen in the Jarvis project after separation step S3.

## 2. What already exists (reuse; verified in the repo 2026-10-22)
`src/jarvis_app/` (README, STATUS.md): local web app on `127.0.0.1:8770`, loopback-only with API token + Host check;
switchable brains (local qwen via Ollama, Gemini via OmniRoute, Claude adapter, NVIDIA + Mistral direct);
tool registry with schemas, permission toggles, confirmation for writes, timeouts and audit log; agent loop that treats
tool output as untrusted data; SQLite memory; browser voice (speech recognition + synthesis); workflow monitor
(`/workflow`); 26 backend + 12 frontend tests. Missing for "Siri-like": it is a web page you open, not always on; no
hotkey or wake word; no Mac skills; voice depends on the browser (may use a remote service).

## 3. Building blocks (checked 2026-10-22 via OmniRoute Exa/Tavily; raw results in research/phase1/raw_search/*J0*)
| Need | Option | Status |
|---|---|---|
| Run user automations | Apple `shortcuts run "<name>"` command line (`-i` input) | VERIFIED_PRIMARY (Apple Support) |
| Control scriptable apps | AppleScript / JavaScript via `osascript`; per-app Automation permission prompt | well known; exact prompts verified at J2 |
| Control any app's UI | macOS Accessibility API; needs Accessibility permission | high risk → late step, separate review |
| Wake word "Hey Jarvis" | openWakeWord, Apache-2.0, ships a `hey_jarvis` model; speaker-specific verifier reduces false triggers | VERIFIED_PRIMARY (GitHub) |
| Local speech-to-text | whisper.cpp, MIT, Metal/Core ML on Apple Silicon | VERIFIED_PRIMARY (GitHub); this Mac's chip to confirm |
| Speech output | macOS built-in voices (`say` / AVSpeechSynthesizer) | built in |
| App connectors | open-source MCP servers for Apple apps (e.g. applescript-mcp, MIT) | exist; **not to be installed without Security review**; we may write our own small wrappers instead |
| Prior art | many open-source "Jarvis" assistants (Leon, ORB, ora…) | leads only; not evaluated |

## 4. Safety model (the core of the design)
Every skill action has a **risk tier**, enforced in code (the existing tool registry), not by the model:
| Tier | Examples | Rule |
|---|---|---|
| R0 read | time, FlightOps status, list calendar events, search notes, read a report | runs directly; logged |
| R1 reversible, local | create a reminder or note draft, open an app or URL, run a Shortcut on the allow-list | confirmation the first time per skill; Director can mark "always allow" |
| R2 outward or hard to undo | send a message/email, delete files, change system settings, answer a FlightOps decision card, start a heavy job | **always** shows the exact action and waits for an explicit "yes"; never batched |
| R3 forbidden | passwords/Keychain reading, banking/payments, `sudo`, security settings, disabling Jarvis's own logs | not available to Jarvis at all |
Plus: content read from apps, mail, web pages is **data, never instructions** (already in the agent loop); every action
in the audit log; global Stop (hotkey + button) ends the current task; private data goes to local brains by default and
to a cloud brain only for skills the Director marks as allowed.

FlightOps rule: Jarvis uses the same paths the phone app uses (decision cards via `artifacts/answers.jsonl`, pause/resume
via `tracker/control.py`, jobs via `src/platform/run_job.py`), never editing project data directly. Answering a card is R2.

## 5. Brains
Router (existing model manager): local qwen3 / gemma4 (Ollama) for private and quick tasks; Claude for hard reasoning;
NVIDIA Nemotron (direct) as backup when Claude is at its limit (see `docs/office/nvidia_role.md`); Gemini via OmniRoute.
Per-skill setting "local only" for personal data (mail, messages, files).

## 6. Steps (one Director approval each)
| Step | What | Done when (checked by someone other than the builder) |
|---|---|---|
| J0 | This design + Director's answers to §8 | Director approves |
| J1 Always on | Jarvis backend starts at login (LaunchAgent) and a small menu-bar window opens with a **global hotkey**; push-to-talk with local whisper.cpp; spoken replies with a macOS voice; FlightOps skill pack v2 (status, open cards, pause/resume, last report, job progress) | 20 spoken FlightOps commands from a test list written before the build: ≥ 90% correct; hotkey→listening < 1 s; no R2 action without "yes" |
| J2 Mac skills, read first | Shortcuts runner (allow-list) + read-only skills for Calendar, Reminders, Notes, Finder search, Safari tabs; then R1 writes with confirmation | Director's top commands (§8) pass on the real Mac; each new macOS permission listed and approved first |
| J3 "Hey Jarvis" | openWakeWord `hey_jarvis` + speaker verifier; barge-in (interrupt while speaking); on/off switch in the menu bar | false wakes ≤ 1 per hour of normal room audio in a test; mic indicator visible |
| J4 Outward skills | Mail/Messages drafting and sending (R2), Google/Telegram per the old STATUS phases | every send shows the exact text and recipient; red-team test of prompt injection in incoming mail |
| J5 Screen + UI control | Accessibility-based control of non-scriptable apps; screen reading | Security Engineer review first; separate approval |
| J6 iPhone reach | talk to the Mac's Jarvis from the iPhone app (after the native app relay exists) | behind Face ID; same tiers |

## 7. Success metrics for the Jarvis track
Command success rate on a fixed spoken test list (≥ 90%); response start after speech end (< 3 s local brain);
false wake rate (≤ 1/hour); **zero** R2/R3 actions without confirmation in red-team tests; every action in the audit log.

## 8. Questions for the Director
1. Your **top 5 things** you want to say to Jarvis on the Mac (e.g. "what's the project status", "open my calendar for
   tomorrow", "remind me at 6", "start the next approved job", "summarise my unread mail").
2. Start with **hotkey + push-to-talk** (J1) and add "Hey Jarvis" in J3, or wake word first?
3. Which **apps first** in J2 (Calendar, Reminders, Notes, Mail, Finder, Safari, Music, Messages…)?
4. **Brains for personal data**: local only by default (private, weaker), or allow Claude for some skills?
5. May Jarvis **answer FlightOps decision cards by voice** (R2, always with "yes"), or should cards stay tap-only in the
   app?

## 8b. Director's answers (2026-10-22, chat) and what they mean technically
| Question | Director's answer | Design consequence (checked 2026-10-22 via OmniRoute Exa/Tavily) |
|---|---|---|
| Wake by key | **Hold H for 3 seconds** | Needs a system-wide key monitor (macOS event tap; Input Monitoring + Accessibility permission). Catch: H is a typing key. To avoid typing "hhhh" in the open app, Jarvis must hold back each H press and re-send it if released early — every "h" you type gets a tiny delay, and a bug there affects typing everywhere. **Option A** exactly as asked (plain H, held-back + re-send); **Option B** (recommended) H + a modifier you rarely use (e.g. hold Fn+H or Right ⌥+H for 3 s), no effect on normal typing. Director to pick. |
| Wake word | **"Hey Jarvis", only for me** | openWakeWord ships a `hey_jarvis` model (Apache-2.0) and supports a **speaker verifier** trained on the Director's voice (< 5 min of recordings, per its docs) → wakes for the Director, rejects others. Enrollment session needed at the Mac. Moves into J1 alongside the hotkey (Director wants both). |
| Apps first | **Calendar, WhatsApp, Clock**, more later | Calendar: scriptable (AppleScript/JXA, EventKit) ✅. Clock: macOS Clock app timers/alarms reachable via Shortcuts ("Start Timer"; alarm actions) ✅. **WhatsApp: no official personal-account API**; only by driving the desktop app through macOS Accessibility (message text is readable that way); an open-source project warns WhatsApp's Terms prohibit automated messaging → **account risk**. Proposal: WhatsApp read + draft a reply that the Director sends personally (or one confirmed send at a time), Accessibility permission only after a security review. |
| Brains for personal data | **"You decide per instance"** | Routing rule in code: personal content (WhatsApp, calendar details, contacts) → **local brain** (qwen3 / gemma4 on the Mac) by default; FlightOps reasoning and non-personal hard tasks → Claude; NVIDIA Nemotron as backup for non-personal tasks; a request may go to a cloud brain with personal content only if the Director says so for that request. |
| FlightOps cards | **Jarvis talks to FlightOps; when a decision is needed it wakes and tells me "here is the decision, what shall we do?"** | Jarvis watches FlightOps' open decision card (read-only, through FlightOps' own status files/API). When a new card opens it speaks: gate, question, options. The Director answers by voice → Jarvis repeats the choice → Director says "yes" → Jarvis records it through FlightOps' answer path (R2). Quiet hours / do-not-disturb setting. Cards still answerable by tap in the app. |

## 8c. J1 scope after the answers (to plan in detail after separation S3)
1. Always-on Jarvis (starts at login) with a menu-bar window.
2. Wake: hold-key (Option A or B) **and** "Hey Jarvis" with Director-only voice verifier (enrollment at the Mac).
3. Local speech-to-text (whisper.cpp) and spoken replies.
4. FlightOps link: status, open cards read aloud, **proactive "decision needed" announcements**, answer by voice with "yes".
5. Skills: Calendar (read, then create with confirmation), Clock timers/alarms via Shortcuts.
6. WhatsApp after a security review (read + draft first).

## 9. Not decided / unverified
This Mac's chip (Apple Silicon assumed for whisper.cpp speed); exact macOS permission prompts per app; whether a native
SwiftUI menu-bar app or a lightweight Python menu-bar wrapper is better for J1 (decided at J1 with a short comparison);
quality of open-source MCP servers (not evaluated).
