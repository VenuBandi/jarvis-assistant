# J1 plan: Jarvis on the Mac, like Siri (draft for the Director's approval, 2026-10-22)

Based on `docs/office/jarvis/j0_design_v2.md` (sections 6, 8b and 8c, Director's answers) and the separation plan
(hotkey: hold Right-Option+H for 3 s; WhatsApp read + draft first). The old `j1_*` files in `docs/office/jarvis/` belong
to the 2026-10-19 project-Q&A track and are history.

**Plan only: nothing installed, no new macOS permission, no restart.** J1 is split into small steps (J1a to J1g). Each
one needs the Director's approval before it starts and is checked before the next one begins.

## 1. Where we start (checked 2026-10-22)
| | Today |
|---|---|
| Jarvis | runs from `~/jarvis-assistant` on 127.0.0.1:8770 (after S4), started by hand: **does not survive a restart or logout** |
| Using it | a web page in the browser; browser voice (may use a remote speech service); no hotkey, no wake word |
| Tools | time, models, FlightOps status, project-doc search, web search, memory. No Mac apps yet |
| Brains | local Qwen3 8B works (default); NVIDIA 5/5 work; Claude key in place but **no API credits**; Mistral not set |
| This Mac | Apple M4, 16 GB, macOS 26.7.1; Swift 6.4 + Xcode, `shortcuts`, `osascript`, `say`, ffmpeg, Homebrew. **Not installed:** whisper.cpp (local speech-to-text), openWakeWord ("Hey Jarvis") |
| FlightOps link | Jarvis reads `<FLIGHTOPS_ROOT>/artifacts/progress.json`. FlightOps' own answer path is its tracker server on 127.0.0.1:8765 (`POST /api/answer` for decision cards, `POST /api/control` for pause/resume) |

## 2. What "like Siri" means here (end of J1)
1. Jarvis starts by itself when you log in and stays running; an icon in the menu bar shows what it is doing.
2. Hold **Right-Option+H for 3 s** (or say **"Hey Jarvis"**, your voice only), speak, and it answers out loud.
3. Speech is turned into text **on the Mac** (whisper.cpp); audio is never stored or sent anywhere.
4. It knows FlightOps: status, open decisions, pause/resume, last report. When a decision is waiting it tells you, and
   it records your answer only after you say "yes".
5. Calendar and Clock work by voice. WhatsApp comes after a security review (read + draft only).
6. Personal things (calendar, messages, contacts) go to the **local brain** unless you say otherwise for that request.

## 3. Steps
### J1a: Always on
**Status 2026-10-22: installed** (`scripts/launch_agent.py`, `6edd2f5`). Checked: Jarvis started by launchd from
`~/jarvis-assistant`, 127.0.0.1:8770 only; pages 200, API 401 without token; Keychain + key files found; workflow
monitor live. Crash test (kill -9): back in 1 s with a new pid. **Still to check:** logout/login (Director).
- **What:** a LaunchAgent (`~/Library/LaunchAgents/com.jarvis.assistant.plist`) starts `src/jarvis_app/run.py` from
  `~/jarvis-assistant` at login and restarts it if it crashes. Log in `data/jarvis_app/jarvis.log`. A short script
  installs, checks and removes it (dry run first).
- **Needs:** the Director's OK to replace the hand-started Jarvis (pid 28966) with the LaunchAgent one (one restart).
- **Done when:** after logout/login Jarvis answers on 8770; after a forced crash it is back within 10 s; still
  loopback-only; FlightOps' own LaunchAgent (`com.flightops.doorbell`) untouched.

### J1b: Menu-bar app + hotkey + Stop
**Status 2026-10-22: built** (`mac/JarvisBar/`, `scripts/build_jarvis_bar.sh`). Both hotkeys registered with **no
permission**; Director's tries: right Option recognised (`option=right`), Stop worked. 3-s hold not completed yet (held
2.45–2.6 s; chime added at 3 s). **Still to check:** full hold with chime, no stray character in TextEdit, 20-try
timing. **Update 2026-10-22:** Jarvis Bar starts at login (`com.jarvis.bar`, crash → back in 1 s). Director asked for
a HUD circle in the middle of the screen instead of a panel/tab: built (`Orb.swift`); the hotkey shows only the circle.
- **What:** a small native Mac app ("Jarvis Bar", Swift) in the menu bar. Icon shows idle / listening / thinking /
  speaking. Click: a small panel with the conversation, a text box, **Stop** and **Mute**. It talks only to
  127.0.0.1:8770 with Jarvis's token. Starts at login.
- **Hotkey (Director decided 2026-10-22):** hold **Right-Option+H for 3 s**. The H must never reach the app you are
  typing in. Permissions, in order of preference (which one works on macOS 26 is **unverified** until built):
  1. **No permission:** macOS's standard hotkey service for Option+H (it swallows the key), plus a check of which
     Option key is down; ignore it if it was the left one.
  2. If 1 does not work: a system-wide key monitor. Seeing keys needs **Input Monitoring**; stopping a key from
     reaching the front app most likely also needs **Accessibility** (to confirm when built).
  The Director turns a permission on in System Settings → Privacy & Security, only after being told which one and why.
- **Stop (Director decided 2026-10-22):** **Right-Option+V** stops the current task and speech at once (same key
  mechanism as the hotkey; the V must not reach the front app either).
- **Done when:** 20 tries hotkey → "listening" in under 1 s; no stray character typed into the front app; Stop ends a
  running task every time; the panel works in light and dark mode.

### J1c: Local ears and voice
**Status 2026-10-22: works end to end** (whisper-cpp 1.9.5, model `ggml-large-v3-turbo-q5_0.bin`, sha256 checked).
Director's first try: 4.7 s of speech → text in 1.4 s → reply spoken. **Open:** (1) voice: Director dislikes the
default; wants a male, British, Jarvis-*style* voice (no clone of a real actor). Candidates: Apple Jamie (Premium),
Daniel (Enhanced), Oliver; Kokoro-82M (Apache-2.0) `bm_george`, `bm_fable`. Director researching tonight. (2) speed:
reply came 18.7 s after speech end (local brain 17.2 s), target < 3 s. (3) 20-phrase accuracy test not run yet.
**Speed work 2026-10-22** (measured, throwaway DB): the cost was answer length (260 tokens at ~18 tokens/s).
Spoken requests now get ≤ 2 sentences (live: 18.3 s → 6–9 s) and the answer is streamed, Jarvis Bar speaking each
sentence when complete (first sentence 5.8 s FlightOps status, 3.5 s time; **live after a Jarvis restart**, pending
Director's OK). Not done: trimming the status tool output (~0.5 s, not worth the lost detail); NVIDIA models have no
tool support in Jarvis, so they cannot read FlightOps; Claude Haiku needs API credits.
- **What:** push-to-talk. After the hotkey, Jarvis Bar records from the mic until you stop talking, turns it into text
  with **whisper.cpp** (Homebrew `whisper-cpp`, MIT licence; runs on the M4's GPU), and sends the text to Jarvis.
  The reply is spoken with a built-in macOS voice (Director 2026-10-22: explore the voice options together at this step). Audio stays in memory and is deleted
  after transcription; only the text goes into the conversation and audit log.
- **Needs:** install `whisper-cpp` + one speech model (download; size depends on the model chosen, measured at install
  time); **Microphone** permission for Jarvis Bar.
- **Done when:** a list of 20 spoken phrases (written before the build) is transcribed correctly ≥ 18 / 20; reply starts
  speaking < 3 s after you stop talking with the local brain (measured, not estimated); mic indicator visible while
  listening; nothing audio-related on disk afterwards.

### J1d: FlightOps skill pack v2
- **What:** new tools in Jarvis's tool registry:
  | Tool | Tier | How |
  |---|---|---|
  | status (exists), open decision card, last report, job progress | R0 read | read FlightOps files (read-only) |
  | pause / resume FlightOps | R2 (asks "yes") | FlightOps server `POST /api/control` |
  | answer a decision card | R2: Jarvis repeats the choice, waits for "yes" | FlightOps server `POST /api/answer` |
  | start an approved job | R2 | only through FlightOps' own path; exact path agreed with the FlightOps session first |
- **"Decision needed" announcements:** Jarvis watches FlightOps' open decision (read-only). When a new one opens it
  shows a notification and says: "FlightOps needs a decision: <question>. Options: … What shall we do?" No quiet hours for now
  (Director 2026-10-22); **when J1d is built, remind the Director** that quiet hours can be set.
- **Needs:** check with the FlightOps session how it wants Jarvis's answers labelled (its server records a "device" for
  each answer).
- **Done when:** 20 spoken FlightOps commands (written before the build) ≥ 18 / 20 correct; red-team test: **0** R2 actions
  without "yes" (incl. instructions hidden in FlightOps text); every answer appears in FlightOps' `answers.jsonl` via
  its server, never written by Jarvis directly.

### J1e: Calendar and Clock
- **What:** Calendar: "what's on today / tomorrow", "when is my next meeting" (R0); "add lunch with … at 1 pm" (R1:
  shows the event, asks once). Clock: timers and alarms through two Shortcuts the Director creates once ("Jarvis Timer",
  "Jarvis Alarm"), run with `shortcuts run` (R1). Calendar content goes to the local brain only.
- **Needs:** **Calendar** permission; the Director creates the two Shortcuts (a guide will be provided).
- **Done when:** the Director's 10 everyday phrases work on the real Mac ≥ 9 / 10; no calendar text sent to a cloud brain
  (checked in the audit log).

### J1f: "Hey Jarvis", your voice only
- **What:** **openWakeWord** (Apache-2.0, ships a `hey_jarvis` model) listens locally, plus a speaker check trained on
  the Director's voice (enrollment: a few minutes of recordings at the Mac). On/off switch in the menu bar; mic
  indicator always visible when it is listening.
- **Needs:** install `openwakeword` (Python package + model files); enrollment session with the Director.
- **Done when:** wakes for the Director ≥ 9 / 10 at normal distance; ≤ 1 false wake per hour of normal room audio
  (TV/talking); another person saying "Hey Jarvis" rejected ≥ 8 / 10. How well the speaker check works is
  **unverified** until tested; if it misses these numbers we report it and decide together.

### J1g: WhatsApp, read + draft (only after a security review)
- **What:** read recent chats and draft a reply that **you send yourself**. WhatsApp has no official API for personal
  accounts; this works by reading the WhatsApp desktop app through macOS **Accessibility**, which is a powerful
  permission. Automated messaging may break WhatsApp's terms (account risk), so Jarvis never sends.
- **Needs:** a written security review first (what Accessibility allows, how to limit it to WhatsApp, prompt-injection
  in incoming messages); then the Director's separate approval.
- **Done when:** decided in the review.

## 4. Safety (unchanged rules, plus what J1 adds)
- Tiers enforced in code: R0 direct, R1 asks once, **R2 always an explicit "yes"**, R3 never (passwords, Keychain reading,
  banking, sudo, security settings, disabling logs).
- Text from apps, FlightOps, mail, web = data, never instructions.
- New: audio never stored or sent; mic indicator whenever listening; a hotkey Stop; every new macOS permission listed
  and approved **before** it is requested.

## 5. Brains in J1
| Request | Brain |
|---|---|
| Personal (calendar, WhatsApp, contacts) | local (Qwen3 8B) only, unless you say otherwise for that request |
| Quick everyday commands | local |
| FlightOps reasoning, hard non-personal tasks | Claude (**needs API credits**); until then NVIDIA Nemotron, then local |

## 6. Decisions for the Director
Already decided (2026-10-22): hotkey **hold Right-Option+H for 3 s**; Stop **Right-Option+V**; wake word **"Hey Jarvis",
Director's voice only**; no quiet hours for now (remind after J1d).

| # | Question | Proposal |
|---|---|---|
| D1 | Jarvis's voice | explore the options together at J1c |
| D2 | Order | J1a → J1b → J1c → J1d → J1e → J1f → J1g (wake word after push-to-talk works) |

## 7. Not decided / unverified
- Right-Option+H hold on macOS 26, whisper.cpp speed on this M4, speaker-check accuracy: measured in the
  step that builds them.
- How FlightOps labels answers from Jarvis, and the exact path for starting a job: to agree with the FlightOps session.
- Claude needs API credits for the "hard tasks" brain.
