# itor

**Count your time. When a tool steals it, get it back, even offline.**

itor is a hackathon prototype with two parts:

1. **A time clock.** It counts active time, idle time and time lost because of tools (internet down, PC overloaded, frozen app, "I'm blocked"). The manager sees the same numbers on the company's own server to pay exact hours and rank the team. Nothing goes to Nexthink.
2. **An offline helper.** When the network drops, a local AI (Qwen through Ollama) still guides the employee, proposes safe fixes that run only after Approve, and writes an outage log that is sent when the connection is back. With internet, Gemini (free tier) answers.

See [PLAN.md](PLAN.md) for the plan and status, and [docs/PRIVACY.md](docs/PRIVACY.md) for what is measured.

## Employee app (Windows installer)

Employees use **itor for Windows** (`apps/desktop`, Kotlin + Compose). It is a normal app with a tray icon that starts with Windows and needs no admin rights. It starts its own helper (`itor-helper.exe`, the Python code in `services/agent` packed with PyInstaller).

Build the installer on Windows with JDK 17, WiX 3, and the `.venv` from `./scripts/setup.ps1`.

```powershell
./scripts/build-desktop.ps1
```

Output: `apps/desktop/build/compose/binaries/main/msi/itor-1.0.10.msi`.

Install the chosen MSI per user with `msiexec /i itor-1.0.10.msi /qn` from the folder containing it. Each employee can set a name and an optional Gemini key in **Settings**. Data lives in `%LOCALAPPDATA%\itor-data`, and settings live in `%APPDATA%\itor\config.json`.

**MSI built from this checkout with `build-desktop.ps1`.** Open itor while online to start automatic offline AI setup. On a fresh Windows x64 PC it downloads a verified standalone Ollama runtime and Qwen 3.5 2B, about 4.3 GB combined. Allow about 6 GB of free disk space. Basic checks use simple rules during setup, and you can pause, resume, or retry in the app. Once it says **Offline AI ready**, Qwen can answer without internet access or an API key.

itor manages its own local Ollama process and stores downloads under `%LOCALAPPDATA%\itor-data\offline-ai`. It can reuse an existing local Ollama serving Qwen 3.5 2B or 4B. Set `ITOR_OLLAMA_URL` or `ITOR_OLLAMA_MODEL` to select an existing runtime explicitly. [Standalone Ollama for Windows](https://docs.ollama.com/windows#standalone-cli)

**Published v1.0.10 MSI.** To use offline AI with the release installer, install Ollama separately (`winget install Ollama.Ollama`) and run `ollama pull qwen3.5:4b`. itor uses simple rules until Ollama and the model are available.

The separate **itor demo panel** (`apps/demo-panel`) gives presenters controls for stuck video export, memory leak, sync loop, network outage, and a demo morning. Build it with `./scripts/build-demo-panel.ps1`. With **Settings → Show demo tools** on, itor writes its local address and key to `%LOCALAPPDATA%\itor-data\demo-access.json`. The file is readable by your Windows account only, and itor deletes it on quit. The employee app is distributed separately.

**Develop:** `cd apps/desktop; ./gradlew run` (add `-Pdemo` for the demo menu). In development the app runs the helper from `.venv`.

The web app below is now the **manager / IT console** (Team ranking, tickets).

## Run locally (web console)

Use **Node.js 22.12+**, **npm**, and **Python 3.11+**. Installation downloads the project dependencies. The web app, agent, SQLite database, and bundled assets work on loopback once installed. Ollama is optional.

```bash
./scripts/setup.sh
./scripts/dev.sh
```

Open [itor](http://127.0.0.1:3000). The launcher binds Next.js and the agent to loopback, generates a shared server-side key, and stops both processes on exit. To select a specific Python binary, run `ITOR_PYTHON=/path/to/python3.11 ./scripts/setup.sh`.

On Windows, run `./scripts/setup.ps1` and `./scripts/dev.ps1` from PowerShell. Set `$env:ITOR_PYTHON` to select another Python executable.

For production mode on the same laptop:

```bash
make build
make start
```

On Windows, set `$env:NEXT_TELEMETRY_DISABLED = '1'`, run `npm --prefix apps/web run build`, then run `./scripts/dev.ps1 start`. Copy [.env.example](.env.example) to `.env` to change ports, storage, the model, or the approved connectivity endpoint. An exact web origin is used for request protection, so open the URL printed by the launcher.

## Set up Ollama manually

Use these steps for the published Windows installer, the web console, or a desktop development run. For automatic setup, use a Windows MSI built from this checkout.

Install a current version of [Ollama for your operating system](https://ollama.com/download). Start Ollama and download one local model while online. The model download is several gigabytes. [Qwen model sizes and variants](https://ollama.com/library/qwen3.5).

```bash
OLLAMA_NO_CLOUD=1 ollama serve
```

In a second terminal:

```bash
ollama pull qwen3.5:4b
ollama list
curl -fsS http://127.0.0.1:11434/api/tags
```

If Ollama already runs as a desktop app or service, enable its local-only setting and restart that instance. On Windows PowerShell set `$env:OLLAMA_NO_CLOUD = '1'` before running `ollama serve`. For a smaller model, pull `qwen3.5:2b`, set `ITOR_OLLAMA_MODEL=qwen3.5:2b` in `.env`, and restart itor. Settings and the header report the available model, while each diagnosis identifies its actual provider. [Ollama local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).

## Try the demo

1. Open **My day**. In **Demo controls**, click **Add a demo morning** so the numbers are not empty. Try **I'm blocked**.
2. In the demo controls, **Simulate cloud unavailability**. My day shows the offline helper: ask the local AI, run a quick fix (it needs Approve). Restore the adapter: the outage log is sent.
3. Open **Team** to see the ranking and the time the team lost to tools.
4. Optional: start the CPU workload, then **Fix this for me** and approve. itor checks the process exit and measures again.

Use `make demo-ready` to check the running app, `make demo-reset` to restore the demo state, and `make smoke` to run the critical API flow through Next.js. Add `--cloud-outage` to `.venv/bin/python scripts/smoke-test.py flow` to exercise the simulated cloud outage. The full five-minute walkthrough and recovery steps are in [DEMO.md](docs/DEMO.md).

## Development and documentation

```bash
make test
make lint
make typecheck
make build
```

- [Architecture and provider boundaries](docs/ARCHITECTURE.md)
- [Privacy and data retention](docs/PRIVACY.md)
- [Local security model](docs/SECURITY.md)
- [Nexthink integration plan](docs/NEXTHINK_INTEGRATION.md)
- [Tests and offline verification](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)

If the agent is unavailable, use the printed local address and check the launcher output for a port conflict. If Ollama reports a missing model, verify the exact tag in `ollama list`. Internet reachability starts as unverified unless you configure an approved HTTPS endpoint. Interface data alone cannot prove internet works. Without that endpoint, real offline is detected when the network card is down; the demo outage button always works.
