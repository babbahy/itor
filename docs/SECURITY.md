# Security

## Local trust boundary

The supported launcher binds both servers to loopback and shares a randomly generated key between Next.js and FastAPI. The proxy allowlists methods and paths, validates the configured authority, checks browser request origin and Fetch Metadata, requires JSON for POST, and bounds the body size. The key is server-side. Python verifies the service key before returning agent data or accepting mutations. The documented defaults intentionally target a single-user developer laptop.

A process running as the same OS user may access that user's files, environment or browser session. This prototype relies on OS account isolation and is unsuitable for exposure through a tunnel or public listener. The database uses normal OS filesystem protections. The project has no additional application-level encryption for history.

## Supported operation

The only remediation is `stop_demo_workload`. The agent owns the child-process handle and captures its identity before planning. On approval, it checks the action ID, scope, expiration, token and active workload identity before executing. The backend tracks action state and prevents repeated calls from starting a second execution. On Linux it rechecks the parent PID and the kernel's process start ticks, which remain stable across wall-clock corrections. It signals a process descriptor where available and can use the original owned child handle on other systems. Verification requires confirmed process exit.

The workload uses one duty-cycled child with a fixed upper runtime bound. The agent stops its child on graceful shutdown, and the hard runtime bound covers forced exits. The demonstration stop/reset controls explicitly identify the temporary workload in scope. End-user applications and operating-system network/security configuration are outside this action policy.

Ollama receives structured observations without tools. A diagnosis can reference an action already approved for presentation by backend rules. It cannot authorize the action, select a PID, or provide executable code to the remediation service. Treat model text as assistance alongside the displayed evidence.

## Connectivity and future integrations

Active probes are optional, use a configured HTTPS endpoint and report bounded outcomes. The demo switch never changes a network interface. Nexthink tenant operations would require credentials, device resolution, reviewed mappings, tenant authorization, and fresh user approval for changes. Expired approvals are ineligible after recovery.

Future deployment work includes a signed distribution, tamper-resistant audit, reviewed tenant policies and credential storage, OS-level isolation review, and vulnerability assessment for dependencies and local interfaces.
