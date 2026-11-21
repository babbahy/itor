# Ready Check: Nexthink DEX hackathon (Kotlin desktop app)

## Context
Nexthink challenge: build an AI that removes real work-tech pain **and** that employees open every day even when nothing is broken. Team chose **Ready Check**: a desktop app that, before your next meeting, runs a 10-second device check-up (network, audio, disk, CPU/RAM, battery, pending restart). It shows a brief with a **"Fix now?"** button. A Claude agent explains each issue and runs a fix from a fixed safe list, but **only after the user clicks Approve**. A "time won back" tally makes the daily value visible.
- Daily hook = the next meeting ("your 9:30 call is ready"), not notifications.
- Team: 2 people. Dev on Linux and Windows; **the final demo runs on Windows**.
- **User wants to code in Kotlin.** Decision: the **whole app is Kotlin**, using Compose Multiplatform Desktop instead of Electron. That's the simplest option and uses the fewest tokens: one language, one process, no main/preload/renderer split, no IPC layer.
- Claude: user's own Anthropic API key, `claude-opus-5-5`.
- Repo: GitHub `babbahy/itor`. It will be set up **on the Windows machine** (the user is switching to it before starting).

## Stack
- Kotlin + **Compose Multiplatform Desktop** (Gradle, JetBrains template). Runs on Windows and Linux; `packageMsi` builds the Windows installer.
- **OSHI** (`com.github.oshi:oshi-core`) for cross-platform telemetry: CPU, RAM, disk, battery, network, processes. `ProcessBuilder` for ping and OS commands.
- **Anthropic Java SDK** `com.anthropic:anthropic-java:3.3.0` (works from Kotlin). The key is read from the `ANTHROPIC_API_KEY` environment variable.
- Agent loop: SDK **`BetaToolRunner`** (`client.beta().messages().toolRunner(...)`) with annotated tool classes. The approval gate lives inside each tool's execution: it suspends on a `CompletableDeferred` that the UI's Approve/Decline button completes, and returns "user declined" if the user says no.
- Model `claude-opus-5-5`, adaptive thinking, effort `low` (chat-like, fast), server-side `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`). Handle `stop_reason == refusal`.
- Storage: a JSON file in the user's home app folder (kotlinx.serialization) for check history and the tally.
- Coroutines: checks and the agent run on `Dispatchers.IO`; UI state lives in `StateFlow`s.

## Structure (`composeApp/src/jvmMain/kotlin/readycheck/`)
```
Main.kt              window + tray icon, app state
checks/Checks.kt     one fun per check → CheckResult(id, status: OK|WARN|FAIL, detail, metric)
fixes/
  Registry.kt        allow-list: Fix(id, title, description, commandPreview, linux(), windows())
  WindowsFixes.kt    PowerShell: ipconfig /flushdns, netsh reset, clear %TEMP%, Stop-Process, restart audio service
  LinuxFixes.kt      nmcli, pactl, clear ~/.cache tmp, kill
agent/
  Agent.kt           BetaToolRunner loop, system prompt, streams text to UI state
  Tools.kt           RunCheckup, ListTopProcesses, ProposeFix(fixId, reason) → awaits approval
Store.kt             history + time-won-back tally
Calendar.kt          next meeting: ICS file import, or a demo fixture
ui/
  BriefScreen.kt     "Ready for 9:30 Teams call": check rows ✅/⚠️, a Fix now? button each
  AgentPanel.kt      chat + approval card (exact command, Approve / Decline)
  TallyCard.kt       "This week: 3 bad meeting starts avoided ≈ 25 min won back"
```

## Key design rules
- **The agent can only call fixes in `Registry.kt`.** It never runs arbitrary shell commands. The approval card shows the real command.
- Each check/fix has a Windows and a Linux implementation; one `os.name` switch picks between them.
- **Demo mode** (`DEMO=1`) injects scripted faults (CPU-hog process, low disk, pending restart, bad Wi-Fi), so the Windows demo is reliable. Safe fixes still really run (killing the dummy process, clearing temp).
- Tally: each resolved warning adds a fixed estimate (for example "a meeting audio failure ≈ 8 min"), defined in one constants file.

## 48h split
- **Person A:** Compose UI (Brief, AgentPanel, Tally), tray icon + "open before meeting" trigger, agent + tools.
- **Person B (Windows):** OSHI checks, Windows fixes, demo-mode fault injection.
- Timeline: h0–8 scaffold + checks render; h8–20 agent + approval flow; h20–32 fixes + tally; h32–40 calendar + polish; h40–48 demo script, `packageMsi`, rehearsal on Windows, README/pitch.

## Steps
1. On Windows: install JDK 17+ and IntelliJ IDEA (Kotlin Multiplatform plugin). Generate a Compose Desktop project into the repo folder, add README (`# itor`) and `.gitignore` (`.gradle`, `build`, `.idea`, `.env`). Then `git init`, `main` branch, remote `origin` → `https://github.com/babbahy/itor.git`, first commit (pushing is the user's call).
2. Add OSHI, anthropic-java, kotlinx-serialization, kotlinx-coroutines-swing to `build.gradle.kts`.
3. Checks + Brief UI with no AI first (it works offline).
4. Agent + approval flow.
5. Fix registry: Windows first (demo OS), then Linux.
6. Tally + store, then calendar/next meeting, then demo mode.

## Verification
- `./gradlew run` on Windows: the brief shows real metrics. Start a CPU-hog process → a warning appears → the agent proposes killing it → Approve → the process is gone and the tally increases.
- Decline path: the agent reports the issue as unresolved and runs nothing.
- Same flow on Linux (`./gradlew run`, using `yes > /dev/null` as the CPU hog).
- `./gradlew packageMsi` produces an installer that runs on a clean Windows user account.
- With `ANTHROPIC_API_KEY` unset, the check-up still works and the agent panel shows "add API key".
