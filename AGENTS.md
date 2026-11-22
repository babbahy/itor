# Notes for AI coding agents (Claude, Codex, Copilot, ...)

Read this before you work on this repo.

## The project name is **itor**
- The app is called **itor** (lowercase). Use this name everywhere: UI text, docs, code, commit messages.
- Do **not** use the old name "Spark Ready" (or SparkReady, spark-ready). It was renamed.
- Environment variables start with `ITOR_` (for example `ITOR_AGENT_KEY`), the local data folder is `.itor/`, and the web package is `itor-web`.
- "Nexthink Spark" is a real Nexthink product. Keep that name when you talk about Nexthink's product. It is not our app.

## Talk simply
- The team is two people at a hackathon. Explain things in plain, everyday words.
- Avoid jargon. If you must use a technical word, explain it in a few words the first time.
- Keep answers short: what you did, what works, what is left. No long lists of options.
- Don't add complexity "for later". It is a 48-hour hackathon: the simplest working version wins.

## How we work
- Read [PLAN.md](PLAN.md) first: it is the shared plan.
- Pull before you start, and commit small changes often, so the two of us don't overwrite each other.
- Run the tests before you push (`make test`).

## Project layout
- `services/agent/` — Python helper (measures the PC, time clock, AI, fixes, IT tickets). Tested with pytest.
- `apps/desktop/` — **the employee app, Kotlin (Compose Desktop)**. Installed with an MSI on every PC. Talks to the helper on 127.0.0.1.
- `apps/demo-panel/` — **itor demo panel**, a separate presenter app (Kotlin) with buttons that simulate problems. Reuses `apps/desktop` code. Build: `./scripts/build-demo-panel.ps1`.
- `apps/web/` — manager / IT console (Team ranking, tickets). Employees don't use it.

## Design rules (no "AI slop" UI)
- Look: crisp Swiss / enterprise utility software (Linear, Stripe, Raycast, Vercel). Not a generic AI SaaS landing page.
- Colors: monochrome base (`#FAFAFA` / `#0A0A0A`) with `1px solid` borders (`#E5E7EB` / `#262626`). At most ONE functional accent: emerald for OK/active, amber for offline/warning. Accents only for status.
- Banned: purple/blue/pink gradients, glow, glassmorphism, floating blobs, gratuitous animations.
- Type: Inter (or Geist) for text; JetBrains Mono with tabular numbers for every time, duration, log, status code and command.
- Layout: compact, 12–16 px padding, 4–6 px corner radius, flat cards, no shadows.
- Copy & icons: Lucide line icons at 1.5 px stroke. No emojis, no marketing words, no "AI-powered" badges.

## Install the employee app (Windows)
The installer is published as a GitHub Release, not in the code (it is ~100 MB). To install the latest version:

```powershell
gh release download -R babbahy/itor -p "itor-*.msi" --clobber
msiexec /i (Get-ChildItem itor-*.msi | Select-Object -Last 1).FullName /qn
```

No admin rights needed (per-user install, in `%LOCALAPPDATA%\itor`). Start **itor** from the Start menu.
To publish a new version: raise `packageVersion` in `apps/desktop/build.gradle.kts` (Windows refuses the same version twice), run `./scripts/build-desktop.ps1`, then `gh release create vX.Y.Z apps/desktop/build/compose/binaries/main/msi/itor-X.Y.Z.msi -R babbahy/itor`.
