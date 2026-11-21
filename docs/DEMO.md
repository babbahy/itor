# Five-minute demo

## Rehearse

1. Start the local launcher and open the printed URL. Run `make demo-ready`.
2. Open **Demo controls**, select **Reset demo session**, and click **Confirm reset**. Confirm that the workload is idle and the next meeting is labeled as a sample.
3. For a live AI demo, start Ollama with the configured model installed. In Settings, check the Local AI status. A rehearsal through the full issue flow warms model files and confirms the explanation provider. Reset afterward.
4. If you plan to join a real call, add a near-future manual meeting with an HTTPS URL you control. Sample meetings have no real join links. An approved reachability endpoint is optional and can be configured before startup if you want to show measured internet status.

| Time | On screen | What to say |
| --- | --- | --- |
| 0:00–0:40 | Open **Today** and show the next meeting and time remaining. | Most employees only think about IT support after something goes wrong. Preparing for a meeting gives them a reason to use proactive support every day. |
| 0:40–1:20 | Click **Prepare my meeting**. Show the latest preflight and checklist. | The laptop checks supported signals in seconds. The employee can use the checklist and launch shortcut on a healthy day. |
| 1:20–2:00 | Click **Demo controls** → **Start safe CPU workload**. Close the dialog, wait for a sampled reading, and click **Run preflight again**. | This temporary workload is consuming a measured fraction of one CPU core. The reading comes from the local child process. |
| 2:00–2:40 | Read the diagnosis and point to its provider label and measured evidence. | Qwen can explain the issue on this laptop. When the model is unavailable, the app gives a deterministic local explanation. |
| 2:40–3:30 | Click **Fix this for me**, read the scope, then click **Approve and stop workload**. Wait for the verification panel. | The employee approves just this workload. We recheck process exit and show the actual CPU samples. |
| 3:30–4:15 | Return to the meeting. Show the checklist and **Join meeting** if a configured link is available. | The employee can go back to their original goal. Audio and camera can be checked in the meeting app. |
| 4:15–4:40 | Open **Settings** to show providers, then **Demo controls** → **Simulate cloud unavailability**. Close the dialog to show the banner, then reopen controls and click **Restore cloud adapter**. | Spark Ready can keep preparing meetings and checking the device during cloud loss. The simulated outage changes only the demo adapter. |
| 4:40–5:00 | Return to **Today**. | With tenant access, NQL and governed Remote Actions can sit behind the same provider boundaries. Spark Ready gives employees a daily reason to benefit from proactive IT. |

## If the demonstration goes off-script

- **Sample meeting advanced.** Reset the demo schedule from the demo controls or run `make demo-reset`.
- **Model is loading, missing or unavailable.** Show the ready device checks immediately and use the labeled local explanation. Verify the tag in `ollama list` after the session.
- **Workload timed out.** Start a new demo run and prepare the meeting again. Existing approvals are scoped to the prior run.
- **Verification shows a smaller drop or higher overall CPU.** Show the measured before/after readings and confirmed child-process exit. Other work on the laptop can change total CPU during verification.
- **No usable network or join link.** Show the last cached meeting and the **Investigate connection** panel. Show any published join action only when a usable link is present and local checks do not indicate an outage.
- **Agent disconnected.** Check the launcher's output and reopen the printed loopback URL after restarting both services.
