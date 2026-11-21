# Notes for AI coding agents (Claude, Codex, Copilot, ...)

Read this before you work on this repo.

## The project name is **itor**
- The app is called **itor** (lowercase). Use this name everywhere: UI text, docs, code, commit messages.
- Do **not** use the old name "Spark Ready" (or SparkReady, spark-ready). It was renamed.
- Environment variables start with `ITOR_` (for example `ITOR_AGENT_KEY`), the local data folder is `.itor/`, and the web package is `itor-web`.
- "Nexthink Spark" is a real Nexthink product. Keep that name when you talk about Nexthink's product. It is not our app.

## Talk simply
- The team is two people at a hackathon. Explain things in plain, everyday words.
- Avoid jargon. If you must use a technical word, explain it in a few words the first time.
- Keep answers short: what you did, what works, what is left. No long lists of options.
- Don't add complexity "for later". It is a 48-hour hackathon: the simplest working version wins.

## How we work
- Read [PLAN.md](PLAN.md) first: it is the shared plan.
- Pull before you start, and commit small changes often, so the two of us don't overwrite each other.
- Run the tests before you push (`make test`).
