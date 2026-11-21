# itor

**Your workday, ready before you are.**

itor is a local hackathon prototype for preparing for a meeting. Open the next meeting, check what the laptop can measure, and run through a short preparation checklist. When a itor demo workload is using CPU, the app can explain the observed problem, ask permission to stop that workload, and verify its exit. The project is designed to complement Nexthink Spark through future provider integrations.

## Run locally

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

## Enable local Qwen

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

1. Open **Today** and prepare the next meeting. The starter schedule is labeled as sample data. Add an HTTPS join link to your own meeting if you plan to click **Join meeting**.
2. In the demo controls, start the CPU workload and run preflight again. The warning uses live CPU activity from the temporary child process.
3. Review the diagnosis and approve the proposed stop action. Inspect the process exit and the before-and-after CPU measurements when verification completes.
4. Simulate cloud unavailability. Local metrics, meetings, diagnosis, and safe actions remain available. Restore the adapter from the same controls.

Use `make demo-ready` to check the running app, `make demo-reset` to restore the sample schedule and demo state, and `make smoke` to run the critical API flow through Next.js. Add `--cloud-outage` to `.venv/bin/python scripts/smoke-test.py flow` to exercise the simulated cloud outage. The full five-minute walkthrough and recovery steps are in [DEMO.md](docs/DEMO.md).

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

If the agent is unavailable, use the printed local address and check the launcher output for a port conflict. If Ollama reports a missing model, verify the exact tag in `ollama list`. Internet reachability starts as unverified unless you configure an approved HTTPS endpoint. Interface data alone cannot establish internet or meeting quality.
