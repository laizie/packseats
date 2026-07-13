# CLAUDE.md

## What this is

PackSeats is a personal watcher that notifies me when a seat opens in an NC State class section, plus a local schedule-planner UI for finding classes that fit around my current schedule or replace a specific class. It polls the public NC State class search (`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and pings me when a watched section frees up. See PRD.md for full scope and NOTES.md for the verified request/response format.

## Current status

Watcher phases 1–3 and planner track P1–P3 done: `catalog.py` (fetch/parse core incl. meeting days/times), `check.py` (one-shot CLI), `watcher.py` (multi-watch config, per-course request dedupe, transition-only notifications, resilient loop mode), `notify.py` (Telegram + Pushover via `.env`; Pushover is configured and verified on my phone), `planner.py` + `templates/planner.html` (local Flask UI: week grid, schedule entry with auto-fetched meeting times, conflict-aware search, replacement mode, watch-from-UI). Phase 4 decided: Oracle Cloud Always Free VM (chosen over paid options to stay completely free); deploy artifacts in `deploy/` + DEPLOY.md, VM not yet created. Remaining: create the VM, then Phase 5 polish.

## Tech stack

- Language / runtime: Python 3
- HTTP + parsing: requests + BeautifulSoup (response is JSON-wrapped HTML — see NOTES.md)
- Notification: Telegram bot (primary, multi-user-ready) + Pushover (my account only, emergency priority for DND-busting)
- UI: Flask, single-page local web app (weekly schedule grid + search)
- Scheduling / host: Oracle Cloud Always Free VM (completely free), systemd services — see DEPLOY.md
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

# watcher: one pass over config/watches.json
.venv/bin/python -m packseats.watcher
# watcher: poll forever (default 180s + jitter)
.venv/bin/python -m packseats.watcher --loop

# schedule-planner UI → http://127.0.0.1:5050
.venv/bin/python -m packseats.planner

# run tests — none yet
```
