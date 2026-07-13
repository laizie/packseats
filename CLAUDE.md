# CLAUDE.md

## What this is

PackSeats is a personal watcher that notifies me when a seat opens in an NC State class section, plus a local schedule-planner UI for finding classes that fit around my current schedule or replace a specific class. It polls the public NC State class search (`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and pings me when a watched section frees up. See PRD.md for full scope and NOTES.md for the verified request/response format.

## Current status

Phase 1 done: `packseats/catalog.py` is the shared fetch/parse core (verified live), `packseats/check.py` is the one-shot CLI. Next: Phase 2 (state tracking + notifications) and planner track P1 (meeting-time parsing + conflict detection). Hosting is the last open Phase 0 decision.

## Tech stack

- Language / runtime: Python 3
- HTTP + parsing: requests + BeautifulSoup (response is JSON-wrapped HTML — see NOTES.md)
- Notification: Telegram bot (primary, multi-user-ready) + Pushover (my account only, emergency priority for DND-busting)
- UI: Flask, single-page local web app (weekly schedule grid + search)
- Scheduling / host: TBD (GitHub Actions cron / always-on host)
- State storage: small JSON file or SQLite, no server

## Hard constraints

- **Public catalog only.** Never touch MyPack Portal, Shibboleth SSO, or Duo. No authenticated requests anywhere in this project.
- **Be polite to the server.** Conservative poll interval, small random jitter, no hammering. This matters most during peak registration.
- **Resilient loop.** A single failed fetch logs and continues. One bad request never crashes the watcher.
- **No secrets in the repo.** Keep any notification tokens out of source control (env vars or an ignored config file).

## Conventions

- Keep it small and readable. This is a personal tool, not a framework. Resist over-engineering.
- Watched sections live in a config file, not hardcoded past Phase 1.
- Notify only on a transition into availability (full to open), not on every poll while a seat sits open.

## Commands

```bash
# setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# one-shot seat check for a course, optionally narrowed to one section
.venv/bin/python -m packseats.check 2268 HESF 101 --section 001

# run the full watcher loop — not built yet (Phase 2+)
# run tests — none yet
```
