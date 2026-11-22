# itor: hackathon plan

## The idea
Nexthink challenge: build an AI that removes real work-tech pain **and** that employees open every day even when nothing is broken.

**itor** does two things, linked by one idea: *itor counts your time, and when a tool makes you lose time, it helps you get it back, even offline.*

1. **During the day, a time clock.** itor counts active time (mouse or keyboard used in the last 2 minutes), idle time, and **time lost because of tools** (internet down, PC overloaded, frozen app, or "I'm blocked"). The manager gets these numbers to pay exact hours and to rank the team. Data goes **only to the company's own server**, never to Nexthink.
2. **When the network drops, a local helper.** The local AI (Qwen through Ollama) guides the employee step by step without internet. itor keeps an outage log and sends it to the company when the connection is back. With internet, Gemini (free tier) answers.

- Team: 2 people, 48 hours. **The final demo runs on Windows.**
- Name: **itor** everywhere. See [AGENTS.md](AGENTS.md).

> ⚠️ For the pitch: in Switzerland (art. 26 OLT 3) and the EU (GDPR), a tool made *mainly* to monitor behaviour can be illegal. So: the employee sees **exactly** what the manager sees, we only measure active/idle (no keystrokes, no screenshots, no websites), and a notice explains it on first launch. Pitch it as "pay exact hours + see time lost because of tools".

## Status

**Done**
- Meetings removed.
- Time clock: `services/agent/worktime.py`. Routes `/api/worktime/today`, `/week`, `/blocked`, `/api/demo/worktime`.
- AI chain: Gemini free tier when online (`gemini-3.5-flash-lite`) → local Qwen → simple rules. Shown on screen.
- Outage log: `services/agent/incidents.py`. Opens when internet or the cloud drops, closes when it comes back.
- Two quick fixes with Approve: clear DNS cache, restart Wi-Fi (`services/agent/network_fixes.py`).
- Company server + ranking: `services/agent/company.py`. Reports wait in an outbox while offline, then are sent. With no company server set, the PC plays the server for the demo. 4 example colleagues.
- Web pages: **My day** (time, "I'm blocked", "What your manager sees", offline help), **My PC**, **Log**, **Team** (ranking), Privacy, Settings. First-launch notice.
- Python tests: 55 pass. Web type-check and lint pass.

- **Employee app for Windows** (`apps/desktop`, Kotlin Compose): Home (status, Fix my problem, Ask IT), My day, Settings, tray, starts with Windows. MSI installer (`scripts/build-desktop.ps1`), per-user, no admin. Monochrome design rules in AGENTS.md.
- Helper packed as `itor-helper.exe`. The Wi-Fi fix asks Windows for admin itself, so itor never runs as admin.

**To do**
- Update Node.js to 22.12+ on the demo PC, then run the web app and `make test` (web tests need Node 22).
- Install Ollama + `qwen3.5:4b` on the demo PC.
- Get a free Gemini key (aistudio.google.com/apikey) and set `GEMINI_API_KEY` in `.env`.
- Optional: set `ITOR_INTERNET_PROBE_URL` so itor can test real internet (without it, real offline is detected when the Wi-Fi/network card is down; the demo outage button always works).
- Polish the UI (h32–40), rehearse the demo ([docs/DEMO.md](docs/DEMO.md)), pitch.

## Simple rules
- **The AI only picks fixes from the safe list.** It never runs its own commands.
- **Approve before anything runs**, and the card shows the exact command.
- **Run itor as administrator** on the demo PC (the Wi-Fi fix needs it).
- No installer. Keep it simple.

## How we check it works
- `make test` passes.
- Leave the mouse 3 minutes → idle goes up. Click "I'm blocked" → lost time goes up. Start the CPU hog → lost time goes up with cause "PC overloaded".
- Demo controls → simulate cloud outage → "You're offline. itor keeps helping.", local AI answers, outage log opens. Restore → the log is sent and shows on **Team**.
- With a Gemini key and internet → answers say "Gemini · online". Without → "Local AI" or "Simple rules", no crash.
- **Team** shows this PC ranked with the 4 example colleagues, and My day numbers match "What your manager sees".
