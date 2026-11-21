# Architecture

Spark Ready runs as two loopback services on the employee’s machine. Next.js serves the UI and bundled assets and passes approved API routes to FastAPI. FastAPI samples the host through psutil, owns the bounded child workload, and stores meetings and compact events in SQLite. Ollama runs separately on loopback and receives a limited diagnosis payload.

```mermaid
flowchart LR
    User["Employee"] --> Web["Next.js meeting launchpad"]
    Web --> Proxy["Same-origin API proxy"]
    Proxy --> Agent["FastAPI device agent"]
    Agent --> Telemetry["Local telemetry and readiness rules"]
    Agent --> Store[("Local SQLite")]
    Agent --> Diagnose["Diagnosis provider"]
    Diagnose --> Ollama["Local Ollama"]
    Diagnose --> Rules["Rules-based explanation"]
    Agent --> Actions["Approved action and verification"]
    Actions --> Child["Spark Ready child workload"]
    Agent --> Connectivity["Connectivity manager"]
    Connectivity -. "Optional approved HTTPS probe" .-> Endpoint["Configured endpoint"]
```

## Meeting preparation

The local meeting provider reads time-zone-aware records. The demo provider seeds a schedule relative to startup or reset. A preflight associates a readiness report with a meeting and returns deterministic checks without waiting for inference. The UI requests a diagnosis separately when relevant. The diagnosis service receives summarized findings and connection states. The executable action and fresh verification always come from the agent.

## Provider boundaries

| Concern | Local implementation | Future integration |
| --- | --- | --- |
| Meetings | SQLite and labeled fixtures | Optional calendar import or enterprise calendar provider |
| Telemetry | psutil snapshots and bounded in-memory history | Predefined tenant NQL queries with measurement timestamps |
| Diagnosis | Deterministic rules and optional loopback Ollama | Supported authenticated Spark handoff |
| Remediation | One allowlisted, agent-owned stop action | Configured Remote Actions or permitted workflows |
| Connectivity | Passive OS checks, independent status objects, optional HTTPS probe | Tenant-specific reachability and authentication adapter |

System CPU is a normalized all-core percentage. Child CPU is measured relative to one logical core. Sustained CPU rules use a configurable observation window and hysteresis. Audio and camera checks are manual. Default-route and resolver configuration checks use Linux and Unix system files where available and report their limits on other platforms. An approved HTTPS probe measures reachability to that endpoint.

## Offline operation

Next.js can render and serve static files with loopback alone. Browser-to-agent errors are reported separately from Internet, local Ollama, and Nexthink status. A failed HTTPS probe, a present interface, and an authentication failure have distinct meanings. The demo outage switch affects an adapter state only. An adapter can recover after stable successful checks without changing the local action history or regenerating approvals.

Nexthink remains unconfigured in the prototype. The optional synchronization boundary accepts minimal consented records and has no default cloud destination. See [NEXTHINK_INTEGRATION.md](NEXTHINK_INTEGRATION.md).

## Bundled artwork

The local meeting illustration is [hero-art.webp](../apps/web/public/hero-art.webp). It was created with the built-in image generation tool and compressed to WebP for offline delivery. The tool received this generation prompt.

> Create a wide landscape 3D decorative hero art background for the right half of the Spark Ready meeting dashboard. In a near-black ink navy studio, a single large angled continuous orbital ring made of smoked dark violet glass and brushed chrome, with a fine electric-lavender edge reflection and two subtly luminous pinpoints on the orbit. Premium restrained industrial design render, sculptural and believable materials, crisp rim, subtle depth. Concentrate the object and all bright details in the rightmost two-thirds, letting the left third and exterior edges fade smoothly into uniform near-black navy, so a meeting title on the left stays readable. Wide crop with generous breathing space. No letters, text, logo, interface, instrument overlay, extra props or people.
