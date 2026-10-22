# FlightOps Jarvis: plan (draft for the Director's approval)

Written: 2026-10-19 by the Lead (Claude), phone session. Status: **PLAN ONLY, nothing built.**
Idea source: Director, from a YouTube video by Zubair (AI Workshop, skool.com/aiworkshop). Its description
lists: voice, a 3D "second brain" from notes with sources, web research by voice, morning briefings (Gmail +
Calendar), Mac control by voice, wake word + barge-in, personas, swapping models (Claude / Grok / GPT).
Those features are the creator's claims; I haven't watched the video or checked them.

## 1. Goal
One assistant ("Jarvis") the Director can ask about the project in plain words, typed or spoken, on the iPhone,
and that answers only from project facts, names its source, and never takes an action without a tap.

## 2. Rules (same as the rest of the project)
- Answers only from project files; every answer cites the file it came from; unknown → "I don't know / unverified".
- Actions (answer a card, Start/Pause/Stop) go through the existing paths (cards, control.py), never directly.
- Behind the app lock (Face ID → passcode). No flight data leaves the Mac.
- No third-party installers or add-ons without a Security Engineer review.
- Builder ≠ checker (virtual-office rule). Each step: plan → approval → build → independent check → Director.

## 3. What we already have (reuse, don't rebuild)
- tracker/agent_brain.py: local model (Ollama qwen3-8b-32k) drafts chat answers from gathered facts, Claude
  reviews them → "Reviewed by Claude". This is Jarvis's brain v0, text-only.
- Phone app (web page now, native app in A3): chat, decision cards, Pause/Stop, watcher wakes Claude.
- Isometric office page: the visual base for a later "galaxy" view.

## 4. Steps (one approval each)
| Step | What | Done when (checked by someone other than the builder) |
|---|---|---|
| J0 | This plan + Director's top 3 voice commands | Director approves the plan |
| J1 Project brain | Index of project knowledge (docs/, factor sheets, source registry, progress.json, decision cards, logs) with file + section for every chunk; agent_brain answers from that index and cites sources | 30-question test set written by QA *before* the build: ≥ 90% correct with the right source; 0 made-up numbers or URLs; "don't know" when the answer isn't in the files |
| J2 Briefing | "Morning briefing": overnight jobs, open cards, blocked items, next step, from progress.json + logs only | every line traced to a file; read aloud as text in the app |
| J3 Voice on iPhone | Mic button + spoken answers in the native app, using Apple's on-device speech recognition + voice (no audio leaves the phone; exact iOS 26 APIs **unverified**, checked at J3) | works behind the lock; SE review; Director tests on the real iPhone |
| J4 Wake word + barge-in | "Jarvis…" while the app is open, interrupt while it's speaking | only while the app is open and unlocked (no always-listening in the background) |
| J5 Galaxy view | 3D map of factors G1–G12, sources, agents, decisions; lights up the source of each answer | renders at iPhone width, light + dark |
| J6 Web research by voice | "Jarvis, research …" → web search; every URL goes into the source registry; results marked unverified until checked | registry rows written; nothing used as data without the normal checks |

### J5 detail: "FlightOps Galaxy" (from the Director's screenshot, 2026-10-19)
Reference: screenshot of "AI WORKSHOP OS" (localhost page, 531 notes / 1,940 connections, 3D force graph).
Elements to copy, built from real project files only (node and link counts come from disk, never typed in):
- **Nodes by type, colour + filter legend:** Factors G1–G12, Features (59), Sources (source registry URLs),
  Data files (raw + parquet), Scripts (src/), Docs, Decisions (cards), Agents (office workers), Steps (M0–M6).
- **Links:** feature → factor, factor → source, data file → script that made it, decision → evidence files,
  agent → its deliveries.
- **Left panel:** search; inspector (click = focus a node and its links + show its file; shift-click a second node =
  trace the path, e.g. "G8 weather → MOS source → download script → parquet"); top hubs with counts; force sliders.
- **Jarvis dial:** listening / thinking / speaking states + which model answered (local qwen3 or Claude).
- **Bottom bar:** live captions, ask box with shortcuts ("status", "good morning", "what's blocked"),
  hands-free "say 'Jarvis…'" (J4).
- **The answer flies to its source:** when Jarvis answers, the camera moves to the node of the cited file (J1 citations).
Where: first as a Mac/browser page served by tracker/server.py (fast to build + check with render_check.py),
then inside the native iPhone app. Library likely a three.js force-graph package (exact package + version
**unverified**, chosen at J5 under the "exact version from an allowed CDN" rule, or vendored).

Not planned (each would need its own decision + security review): full Mac control by voice, Gmail/Calendar,
buying or installing the AI Workshop JARVIS, cloud voice services.

## 5. Order with the iPhone app
- J1 + J2 don't depend on the app; they can start right after approval (Mac web page + chat).
- J3 + J4 need the native app: after C1 build passes (card D-app-a3-c1-build) and the screens task (C3).
- J5 + J6 last. Option: J5 galaxy as a Mac web page can move up to right after J1 (it needs J1's index + citations,
  not the native app).

## 6. Team
- Lead (Claude): design, index rules, reviews, cards.
- Engineer (Claude subagent or Codex in its sandbox): builds J1/J2 in src/ or tracker/.
- QA (Claude subagent, separate from the builder): writes the J1 test questions first, then grades.
- iOS App Engineer (Codex) + Security Engineer: J3/J4.

## 7. Open questions for the Director
1. Your top 3 things to say to Jarvis (e.g. "status?", "approve that", "what's blocked?").
2. Name/personality: "Jarvis", calm and short? Humor on or off?
3. Start J1 now in parallel with the app, or after C1–C3?
4. Local model only (free, private, weaker) or allow Claude for answers too (stronger; project text goes to
   Anthropic, which already happens in these sessions)?

## 8. Unverified
- Video features (creator's description only). iOS 26 speech APIs and on-device voice quality.
- Whether qwen3-8b handles cited answers well enough to hit 90%: J1's test set decides.
