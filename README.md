<img src="apps/desktop/icons/itor-256.png" width="56" alt="itor app icon">

# itor

**A Windows worktime tracker with offline IT help.**

A slow PC, frozen app, or lost connection can cost an employee part of their workday. itor records that lost time and gives the employee a place to get help. They can check their device, approve a supported fix, or send IT a ticket with the details. The manager view brings time summaries, outages, and tickets together so recurring problems are visible.

[Download itor for Windows x64](https://github.com/babbahy/itor/releases/download/v1.0.19/itor-1.0.19.msi) · [Download the presenter panel](https://github.com/babbahy/itor/releases/download/v1.0.10/itor-demo-panel-1.0.0.msi) · [See the five-minute demo](#see-itor-in-five-minutes)

## Try it on Windows

1. Run the MSI and open **itor** from the Start menu. The app starts its own helper and stays available in the Windows tray.
2. Keep itor online on first launch. On a fresh setup it automatically downloads Ollama and Qwen 3.5 2B, about **4.3 GB** combined. Allow about **6 GB** of free disk space. Basic checks work during setup, and you can pause and resume the download.
3. Open **Settings** and wait for **Offline AI ready**. Qwen then runs on the PC, including during an outage, without an API key. itor can also reuse an existing local Ollama running Qwen 3.5 2B or 4B.

## See itor in five minutes

Install the separate **itor demo panel** using the link above. In itor, enable **Show demo tools** and **Show manager view** in **Settings**, click **Save and restart helper**, then open **itor demo panel** from Start. Leave the company settings blank to use the laptop as the demo receiver.

| On screen | What to show |
| --- | --- |
| **My day** | Click **Add a demo morning** in the panel to seed sample hours. Show active, idle, and time lost to tool problems. |
| **Fix my problem** | Start **Stuck video export** in the panel. Once itor detects the workload, run the device check and click **Run** next to **Stop VideoExport**. Show the approval prompt, then click **Approve and run** and point to the verified result. |
| **Offline help** | Click **Simulate outage**. Ask **“Why is my Wi-Fi offline?”** in **Fix my problem**. The completed answer’s `source: local-ai` label shows that Qwen answered on the laptop. |
| **Ask IT → Team** | Send a sample ticket from the diagnosis, end the simulated outage, and find the message under **Team → Tickets for IT**. |

The panel simulates the outage and seeds sample hours. **Stuck video export** starts a real, bounded test process. itor measures the workload and checks that it exited after the approved fix. Team can also show example coworkers alongside the local report. [Full presenter script](docs/DEMO.md#script)

## How it works

- **Employee app.** The Kotlin and Compose Desktop interface talks to a packaged Python helper on the same PC. The FastAPI helper reads CPU, memory, disk, and connection status, keeps the time clock, and stores records in SQLite.
- **Diagnosis and fixes.** The helper uses measured findings to explain problems. Qwen runs locally through Ollama. Rules provide basic answers when the model is unavailable. Employees approve built-in fixes before the helper runs them, and the helper checks the result.
- **Reporting.** itor saves daily summaries, outage logs, and tickets in a local queue. It sends them to the configured company receiver when reachable. The Next.js browser console reads the team and ticket data from that receiver.

[Architecture](docs/ARCHITECTURE.md) · [Tests and offline verification](docs/TESTING.md)

## Privacy and Nexthink

The time clock uses recent mouse and keyboard activity to estimate worktime. Windows supplies input timing, and employees can review their daily totals in **My day**. Webcam presence and posture feedback are optional. MediaPipe runs on the PC, and camera frames are discarded after processing. The posture rules were adapted from Birdy. [Posture implementation](services/agent/posture.py)

Company reporting shares time summaries, outage logs, and submitted tickets. The optional Gemini setting uses your own API key and sends the question and a limited diagnostic summary to Google for an online answer. [Privacy details](docs/PRIVACY.md)

The hackathon build uses local device readings and itor’s own reporting. The provider interfaces give us a place to connect tenant-approved Nexthink NQL queries and Remote Actions. A Spark handoff would require a supported entry point and validation in an authorized tenant. [Nexthink integration notes](docs/NEXTHINK_INTEGRATION.md)

## Build and run from source

### Windows installers

Use Windows x64, JDK 17, WiX 3, Python 3.11+, and Node.js 22.12+ with npm. Set `JAVA_HOME` to your JDK 17 folder if it is installed somewhere other than the build script’s default.

```powershell
.\scripts\setup.ps1
.\scripts\build-desktop.ps1
.\scripts\build-demo-panel.ps1
```

Look for `itor-1.0.19.msi` in `apps/desktop/build/compose/binaries/main/msi` and the presenter MSI in `apps/demo-panel/build/compose/binaries/main/msi`. Local app data is in `%LOCALAPPDATA%\itor-data`. Settings are stored in `%APPDATA%\itor\config.json`.

For Windows desktop development, run `.\gradlew.bat run -Pdemo` from `apps/desktop` after setup. The developer run uses the Python helper from `.venv`.

### Browser console

Use Node.js 22.12+ with npm and Python 3.11+. From the repository root:

```bash
./scripts/setup.sh
./scripts/dev.sh
```

On Windows PowerShell, use `.\scripts\setup.ps1` and `.\scripts\dev.ps1`. Open the address printed by the launcher, normally [http://127.0.0.1:3000](http://127.0.0.1:3000). The launcher runs the browser app and its helper on the local machine. To test the installed app sending to this separate console, set `ITOR_COMPANY_KEY` in the console’s `.env`, then set the same key and the receiver URL, normally `http://127.0.0.1:8765`, in itor’s company settings. [Example configuration](.env.example)

For a local production build, use `make build` and `make start`. On Windows, run `npm.cmd --prefix apps/web run build` and `.\scripts\dev.ps1 start`.

### Set up Ollama manually

For the browser console, desktop development, or an older employee MSI, start Ollama and download the default model while online.

```bash
OLLAMA_NO_CLOUD=1 ollama serve
```

In a second terminal:

```bash
ollama pull qwen3.5:4b
ollama list
```

On Windows PowerShell, set `$env:OLLAMA_NO_CLOUD = '1'` before running `ollama serve`. You can select a smaller downloaded model with `ITOR_OLLAMA_MODEL=qwen3.5:2b` and select the local server with `ITOR_OLLAMA_URL`. Restart itor after changing the configuration. [Ollama local-only setup](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)

### Development checks

```bash
make test
make lint
make typecheck
make build
```

Use `make demo-ready` to check the running browser demo and `make smoke` to exercise diagnosis and approval through the local API. [Testing guide](docs/TESTING.md) · [Project plan](PLAN.md) · [Roadmap](docs/ROADMAP.md) · [Security model](docs/SECURITY.md)
