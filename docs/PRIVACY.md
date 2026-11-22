# Privacy

## What itor measures
- **Time clock:** only whether the mouse or keyboard was used recently (seconds since the last input). Never which keys, never what is typed.
- **Webcam presence (optional, off by default):** if the employee turns it on in Settings, itor looks at one webcam image every 2 seconds, on the PC, to know if someone is at the desk (MediaPipe face detection, pose as a backup). Images stay in memory and are dropped right away: nothing is saved or sent. Only "present / away" is used, so reading or a call without touching the mouse counts as active. A "cam" indicator is shown while it runs, and the camera light stays on.
- **Frozen apps:** the name of the front app, only when Windows reports it as "not responding".
- **PC readings:** total CPU, memory and disk, network state, and the demo workload itor starts.
- itor never captures screenshots, websites, browser history, documents, network traffic or process command lines.

## Who sees it
- The employee sees everything on **My day**.
- The manager sees **the same numbers** (active, idle, lost, hours to pay, outage logs) on the company server.
- Data goes only to the company server set in `ITOR_COMPANY_URL`, protected by `ITOR_COMPANY_KEY`. **Nothing is sent to Nexthink.**
- While offline, reports wait in a local outbox and are sent when the connection is back.

## AI
- **Gemini (online, free tier):** receives a short summary of the findings and network checks, and the employee's question. No names, device names or identifiers, and never the working time. **On the free tier, Google may use these requests to improve its products.** A real deployment should use a paid tier (not used for training) or only the local AI.
- **Local AI (Qwen via Ollama):** runs on the PC. Receives the same summary, without the question text.
- **Simple rules:** run in the app, no AI.

## Focus reminders (opt-in)
- Off by default. Turned on in Settings > Focus reminders.
- "Looking at your phone" comes from the webcam check above (head tilted down, or face turned away, for about 5 seconds). "Long pause" comes from no mouse/keyboard activity.
- The decision is made on this PC and shown as a Windows notification. It is never saved, never sent, and never changes the time clock. Your manager never sees it.

## Storage
- Local SQLite database (`.itor/`). Activity history is kept 7 days (`ITOR_RETENTION_DAYS`). Daily time totals are kept for pay.
- **Privacy → Clear history** deletes local activity, diagnostics and time totals. Reports already received by the company server are kept there.

## Legal note
In Switzerland (art. 26 OLT 3) and the EU (GDPR), monitoring employee behaviour is restricted. itor stays transparent: the employee sees what the manager sees, measurement is limited to active/idle, and a notice explains it on first launch. A real deployment needs the company's legal and HR approval.
