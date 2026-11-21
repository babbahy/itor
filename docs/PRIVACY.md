# Privacy

## What itor measures
- **Time clock:** only whether the mouse or keyboard was used recently (seconds since the last input). Never which keys, never what is typed.
- **Frozen apps:** the name of the front app, only when Windows reports it as "not responding".
- **PC readings:** total CPU, memory and disk, network state, and the demo workload itor starts.
- itor never captures screenshots, websites, browser history, documents, network traffic or process command lines.

## Who sees it
- The employee sees everything on **My day**.
- The manager sees **the same numbers** (active, idle, lost, hours to pay, outage logs) on the company server.
- Data goes only to the company server set in `ITOR_COMPANY_URL`, protected by `ITOR_COMPANY_KEY`. **Nothing is sent to Nexthink.**
- While offline, reports wait in a local outbox and are sent when the connection is back.

## AI
- **Claude (online):** receives a short summary of the findings and network checks, and the employee's question. No device names or identifiers.
- **Local AI (Qwen via Ollama):** runs on the PC. Receives the same summary, without the question text.
- **Simple rules:** run in the app, no AI.

## Storage
- Local SQLite database (`.itor/`). Activity history is kept 7 days (`ITOR_RETENTION_DAYS`). Daily time totals are kept for pay.
- **Privacy → Clear history** deletes local activity, diagnostics and time totals. Reports already received by the company server are kept there.

## Legal note
In Switzerland (art. 26 OLT 3) and the EU (GDPR), monitoring employee behaviour is restricted. itor stays transparent: the employee sees what the manager sees, measurement is limited to active/idle, and a notice explains it on first launch. A real deployment needs the company's legal and HR approval.
