# Nexthink integration

Spark Ready owns the next-meeting workflow, readiness presentation and approval interaction. The current prototype implements telemetry, diagnosis and remediation locally. Nexthink status is **Not configured** outside the clearly labeled demo outage.

## What tenant access would enable

- **NQL telemetry.** Set up dedicated client credentials with NQL permission. Create predefined queries with approved parameters and map the result to a device snapshot keyed by the verified Collector/device identity. Preserve capture time, query time and source. Respect tenant limits and return unavailable for missing metrics. Historical or sampled NQL measurements can have different granularity from the two-second local series. [Nexthink NQL API](https://docs.nexthink.com/api/nql).
- **Remote Actions.** Use the Remote Actions permission and an API-enabled, reviewed action. Map internal action IDs to configured tenant IDs, verify the current device identity and approval, track resulting execution state, and independently confirm the intended result when measurements permit. [Nexthink Remote Actions API](https://docs.nexthink.com/api/remote-actions).
- **Workflows.** An approved workflow can be an orchestration endpoint for enterprise escalation or follow-up. Configure API access and use a tenant-defined NQL workflow ID. Map outputs explicitly before presenting them in the product. [Nexthink Workflows API](https://docs.nexthink.com/api/workflows).
- **Spark handoff.** Confirm a supported entry point with Nexthink and the customer’s tenant administrator, including employee identity, device identity, consent, scopes, and any approved contextual payload. The public documentation describes employee-initiated support in configured communication channels. A context-prefilled handoff from this app requires vendor and tenant validation. [Nexthink employee experience with Spark](https://docs.nexthink.com/user-guide/spark/working-with-spark/understanding-employee-experience-with-spark).

Nexthink documents OAuth client credentials with per-feature permissions. Establish the correct tenant region, host, API permissions, device identity mapping, test tenant and approved actions before implementing production adapters. Keep client secrets in a company-approved vault. [Nexthink API credentials](https://docs.nexthink.com/api).

## Freshness, outages and authorization

Preserve stale cloud data with its last-updated time. Use separate checks for endpoint reachability and authorization, including explicit handling for 401/403. On recovery, revalidate authentication and refresh context. Keep meetings and local preflight available throughout. A future consented sync adapter must deduplicate local event IDs and suppress automatic replay of actions. The prototype contains no production tenant IDs, credentials, or verified Spark handoff.
