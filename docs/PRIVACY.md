# Privacy

itor measures aggregate system CPU, memory and storage, passive network state, and the workload that it starts. The network panel reports check outcomes. It does not capture traffic, screen contents, browser history, employee documents, process command lines, or process environment variables.

Manual meeting entries and sample meetings reside in the local SQLite database. The database also contains compact preflight, finding, diagnosis, connectivity and action history. Rolling device samples stay in a bounded memory buffer. The default history retention is seven days, configurable with `ITOR_RETENTION_DAYS`. Clearing local history from Privacy preserves meeting records.

The agent sends a structured subset of findings and network check states to a configured local Ollama model. Meeting titles, notes, URLs, device identifiers and raw network details are omitted from diagnostic context. The model can describe a permitted action. The agent makes approval and execution decisions.

By default, the app contacts the loopback device agent and configured local Ollama. Configuring `ITOR_INTERNET_PROBE_URL` permits rate-limited DNS and HTTPS checks for that endpoint. Requests carry no meeting, device telemetry, or authentication payload. DNS queries and HTTPS connections expose ordinary network connection metadata to their respective operators.

A manual **Join meeting** click opens the saved HTTPS URL in the browser. The external meeting service then handles the connection according to its own settings. Downloading NPM/Python dependencies, Ollama and model weights requires prior access to their distribution services. For strict local inference, disable Ollama cloud features. [Ollama local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).

Nexthink telemetry and synchronization are inactive by default. Reconnection does not auto-upload local history. A future upload path must have an explicit, policy-approved destination and event-level authorization.
