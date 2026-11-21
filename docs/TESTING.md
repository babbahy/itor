# Development checks

Run the suite from the repository root after setup.

```bash
make test-agent
make test-web
make lint
make typecheck
make build
```

The Python suite covers telemetry and readiness, the time clock, outage logs, the company outbox and ranking, Gemini fallback, action consent, owned-process checks, measured verification, expiration and duplicate prevention. Connectivity tests cover internet, DNS, Ollama and Nexthink as separate services, plus recovery stability and simulation. Sync tests use a test sender to exercise event eligibility, deduplication, retry limits and jitter. Ollama contract tests use a local transport double for structured responses, invalid output, and the rules fallback.

For a running app, check the real API path and action through the Next.js proxy.

```bash
make demo-ready
make demo-reset
make smoke
.venv/bin/python scripts/smoke-test.py flow --cloud-outage
```

With Ollama running and the configured model installed, use `.venv/bin/python scripts/smoke-test.py flow --expect-ollama` to require a validated local model explanation. Add `--expect-offline` to require observed network loss in the same run.

The live flow starts a bounded itor workload, observes CPU activity, runs preflight and diagnosis, verifies approval before execution, confirms process exit, and verifies repeated approval does not rerun it.

## Offline smoke

After setup, use a laptop with Internet access disconnected or an isolated network namespace with loopback enabled. Leave both itor services running locally. Start the app and run `make smoke-offline` to require a measured connection loss and exercise the local flow. In the browser, check live CPU and memory, check My day, investigate the connection, and verify the approved workload stop. If Ollama and the model are installed, keep Ollama running in the same network environment and verify the diagnosis provider. Restore the connection and check that the UI updates and that completed actions stay completed. With no authorized HTTPS probe configured, internet status can remain unknown while passive interface observations are available.

The **Simulate cloud unavailability** control exercises provider failure and recovery. It leaves the laptop’s network settings intact. Test it separately from a real network isolation check.

On Linux with unprivileged user namespaces enabled, the following starts the already-built app with only loopback available and a fresh database. It exercises the network-loss path without changing the host connection.

```bash
make build
unshare -Urn bash
ip link set lo up
ITOR_DB_PATH="$(mktemp -d)/local.sqlite3" ./scripts/dev.sh start &
itor_launcher=$!
# After both servers start
make smoke-offline
kill "$itor_launcher"
exit
```

## Browser cases

The browser suite uses controlled API responses to check UI loading, readiness, approval, verification, and connectivity. Playwright may need its Chromium binary installed once during setup.

```bash
cd apps/web
npx playwright install chromium
npm run test:e2e
```
