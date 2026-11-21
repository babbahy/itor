# Five-minute demo

## Before you go on stage
1. Open PowerShell **as administrator**, run `./scripts/dev.ps1`, open the printed address.
2. Start Ollama with `qwen3.5:4b` (see README). Ask one question once so the model is warm.
3. Set `ANTHROPIC_API_KEY` in `.env` if you want to show Claude online.
4. **Demo controls** → **Reset demo session**, then **Add a demo morning** (so the numbers are not empty).

## Script

| Time | On screen | What to say |
| --- | --- | --- |
| 0:00–0:40 | **My day**: active, lost to tools, idle, hours to pay. | Every company pays hours. itor counts real working time, and also the time **tools** made you lose. That's why people open it every day, even when nothing is broken. |
| 0:40–1:10 | Point to **What your manager sees**. | The manager sees exactly these numbers, nothing more. No keystrokes, no screenshots, no websites. And it stays inside the company, never at Nexthink. |
| 1:10–1:40 | Click **I'm blocked**, then stop it. | When a tool blocks me, I say so in one click. It counts as lost time because of IT, not as idle. |
| 1:40–2:30 | **Demo controls** → **Simulate cloud unavailability**. Close. Show **You're offline. itor keeps helping.** → **Ask the local helper**. | The network is down: remote IT is blind. itor's local AI runs on this laptop and still guides me. It writes an outage log. |
| 2:30–3:10 | Click **Fix it** on "Clear the DNS cache". Show the exact command, **Approve and run**. | The AI can only propose fixes from a safe list. Nothing runs until I approve. Then itor measures again. |
| 3:10–3:40 | **Demo controls** → **Restore cloud adapter**. | Connection is back. The outage log and my day are sent to the company automatically. |
| 3:40–4:30 | Open **Team**. | The manager sees the ranking for exact pay, and the time the team lost to tools: this is what IT should fix first. |
| 4:30–5:00 | Back to **My day**. Optional: Demo controls → Start safe CPU workload → **Fix this for me**. | One tool: count your time, and when a tool steals it, get it back, even offline. |

## If something goes wrong
- **Local AI missing or slow:** itor answers with simple rules (labeled). Keep going.
- **No Claude key / no internet:** answers come from the local AI. That is the point of the demo.
- **Wi-Fi fix fails:** itor is not running as administrator. Use the DNS fix instead.
- **Team page empty for you:** click **Send my day now**.
- **Agent disconnected:** check the launcher output and reopen the printed address.
