# itor: Nexthink DEX hackathon plan

## The idea
Nexthink challenge: build an AI that removes real work-tech pain **and** that employees open every day even when nothing is broken.

**itor** gets your laptop ready before your next meeting. It runs a quick check-up (internet, CPU, memory, disk, battery, sound, pending restart) and shows a short brief: "Your 9:30 call is ready" or "2 things need attention". For each problem, the AI explains it in plain words and proposes a fix from a fixed safe list. **Nothing runs until the user clicks Approve.** After the fix, itor measures again to show it worked. A "time won back" counter shows the daily value.

- Daily hook = the next meeting, not notifications.
- Team: 2 people, 48 hours. **The final demo runs on Windows, on our own laptop.**
- Name: **itor** everywhere (not "Spark Ready"). See [AGENTS.md](AGENTS.md).

## What we merged
We had two versions: a Kotlin desktop plan, and a working web app built by a teammate. **We keep the web app** (it already works and has tests) and add the best ideas from the Kotlin plan. The Kotlin app is dropped.

**Already built (web app):**
- A web page (Next.js) that talks to a small Python helper running on the laptop (FastAPI).
- Meeting list with a demo schedule.
- Checks: CPU, memory, disk, network, plus a demo "CPU hog" workload.
- AI explanation: simple built-in rules, or a local AI model (Qwen through Ollama) that works offline.
- One fix: stop the demo CPU hog, only after Approve, then measure again to prove it worked.
- Works offline, keeps history on the laptop, has tests and a demo script ([docs/DEMO.md](docs/DEMO.md)).

**Added from the Kotlin plan (to do):**
1. **Claude as the AI** when an API key is set (`claude-opus-5-5`, effort `low`). If there is no key or no internet, itor falls back to the local model, then to the built-in rules. So the demo never breaks.
2. **More quick fixes (Windows first)**, each one shown with its exact command and needing Approve:
   - flush DNS (fixes "website won't load" after a network change)
   - turn Wi-Fi off and on
   - clear temporary files
   - restart the Windows sound service
   - stop a heavy app the user picked from the "top apps" list (never a system app)
   Only fixes that work right away. No fix that needs a restart.
3. **More checks:** battery level, pending Windows restart, Wi-Fi signal strength, speaker and microphone present.
4. **"Time won back" counter:** each problem fixed before a meeting adds a fixed estimate (for example "sound problem ≈ 8 min"). Shown as "This week: 3 bad meeting starts avoided ≈ 25 min won back".

## Simple rules
- **The AI can only pick fixes from the safe list.** It never runs its own commands.
- **Approve before anything runs**, and the card shows the real command.
- **The Python helper runs as admin** on the demo laptop (open PowerShell as administrator, then start itor). Some fixes need it.
- **Stopping an app is limited:** only apps from the "top apps" list, owned by the user, never system apps.
- **No installer.** We run itor with the start script. Keep everything as simple as possible.
- **Demo mode** keeps the demo reliable: it creates fake problems (CPU hog, low disk, pending restart, weak Wi-Fi). Real fixes still run where possible; fake problems are marked fixed after Approve.

## Who does what
- **Person A:** Claude in the AI step (with fallback), "time won back" counter, UI for the new fixes and checks.
- **Person B (Windows):** new Windows checks and fixes in the Python helper, demo mode for the new fake problems.
- Timeline: h0–12 Claude + counter + first new fix; h12–28 the other fixes and checks; h28–40 polish and demo mode; h40–48 demo rehearsal on Windows, README, pitch.

## How to run
See [README.md](README.md). On Windows: `./scripts/setup.ps1` once, then `./scripts/dev.ps1`, then open the address it prints.

## How we check it works
- `make test` passes.
- On Windows: start the demo CPU hog → a warning appears → the AI explains it → Approve → the hog stops, itor shows before/after CPU, the counter goes up.
- Decline: nothing runs, the problem stays marked as not fixed.
- Each new Windows fix runs once and works without a restart.
- With no Claude key, or with the internet off, the check-up and the explanation still work (local model or rules).
- Demo mode: every fake problem shows up and can be fixed during the rehearsal.
