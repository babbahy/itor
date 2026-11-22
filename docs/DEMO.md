# Five-minute demo (live)

## Before you go on stage
1. itor 1.0.5 installed and open (Start menu → itor). **Settings → Show manager view (demo)** ticked.
2. Ollama running with `qwen3.5:4b`. Do **Fix my problem** once before going on stage: the first local-AI answer is the slowest (it loads the model).
3. Close heavy apps: the local AI runs on the processor.
4. Know where to turn Wi-Fi off and on (taskbar network icon, or airplane mode).

## Script

| Time | On screen | What to say |
| --- | --- | --- |
| 0:00–0:40 | **Home**: calm pixel landscape (night), "Everything looks fine". | Every company pays hours, and every employee loses time to tools. itor sits on the PC, quiet when all is fine. |
| 0:40–1:20 | **My day**: active / lost / idle / to pay, "What your manager sees". | It counts real working time, and the time **tools** made you lose. The manager sees exactly these numbers, nothing more: no keystrokes, no screenshots, no websites. |
| 1:20–1:50 | **Turn Wi-Fi off.** Back to **Home**: the horizon turns amber and the water ripples faster, "You are offline". | The network is down: remote IT is blind. itor isn't. |
| 1:50–3:00 | **Fix my problem** → "websites do not load" → **Check and fix**. The steps tick live: snapshot, network, explain (local-ai), propose. | No internet, so the AI runs on this laptop. It explains in plain words and only proposes fixes from a safe list. Nothing runs without my approval. |
| 3:00–3:30 | **Ask IT** → "websites do not load since this morning" → **Send to IT**: "Saved. It will be sent when you are back online." | IT gets my words plus what itor measured and tried, even if I'm offline. |
| 3:30–4:00 | **Turn Wi-Fi on.** Home goes back to calm. | Connection back: the ticket and the outage log leave by themselves. |
| 4:00–4:40 | **Team** tab: the ranking bars grow, time lost to tools, the ticket is there. | The manager sees exact hours, and what tools cost the team. This is what IT should fix first. |
| 4:40–5:00 | Back to **Home**. | One app: count your time, and when a tool steals it, get it back, even offline. |

## If something goes wrong
- **Local AI slow:** the step list shows the seconds ticking; keep talking. If it fails, itor answers with simple rules (labeled `source: rules`).
- **Wi-Fi off but Home still "fine":** wait ~5 s (itor checks every few seconds), or use Settings → Demo → Simulate outage (needs `--demo`).
- **Ticket not in Team:** wait a few seconds after Wi-Fi is back, then reopen the Team tab.
- **Window gone:** it's in the tray (bottom right, black square with an "i").
