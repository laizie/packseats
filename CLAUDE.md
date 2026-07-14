# CLAUDE.md

## What this is

PackSeats is a personal watcher that notifies me when a seat opens in an NC State class section, plus a local schedule-planner UI for finding classes that fit around my current schedule or replace a specific class. It polls the public NC State class search (`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and pings me when a watched section frees up. See PRD.md for full scope and NOTES.md for the verified request/response format.

## Current status

**Shipped and running.** All PRD phases done except optional Phase 5 polish.

- Deployed on an Oracle Cloud Always Free VM (Ubuntu 20.04, `150.136.139.176`), two systemd services: `packseats-watcher` (polling loop) and `packseats-planner` (UI on the VM's localhost, reached via SSH tunnel). See DEPLOY.md.
- Pushover is configured and verified end-to-end from the VM. Telegram is coded but has no tokens set (blank channels are skipped).
- Access from the Mac: `packseats` host alias in `~/.ssh/config` (with `LocalForward 5050`), `vm` alias in `~/.zshrc` → `scripts/vm ui|logs|status|watches|update|ssh`.

**Gotcha:** the VM runs **Python 3.8**, so every module needs `from __future__ import annotations` for modern type syntax (`int | None`). Keep it that way, or recreate the VM on Ubuntu 24.04 (planned, not urgent).

## Tech stack

- Language / runtime: Python 3 (3.8-compatible — see gotcha above)
- HTTP + parsing: requests + BeautifulSoup (response is JSON-wrapped HTML — see NOTES.md)
- Notification: Pushover (live, running at emergency priority — re-alerts every 60s for an hour until acknowledged) + Telegram (coded, unconfigured — the multi-user-ready option if friends join)
- UI: Flask, single-page app (weekly schedule grid + conflict-aware search + watch management)
- Scheduling / host: Oracle Cloud Always Free VM, systemd services — see DEPLOY.md
- State storage: JSON files, no server — `config/watches.json` (watches), `data/state.json` (last-seen seats), `data/schedule.json` (my enrolled sections)

## Hard constraints

- **Public catalog only.** Never touch MyPack Portal, Shibboleth SSO, or Duo. No authenticated requests anywhere in this project.
- **Be polite to the server.** Conservative poll interval, small random jitter, no hammering. This matters most during peak registration.
- **Resilient loop.** A single failed fetch logs and continues. One bad request never crashes the watcher.
- **No secrets in the repo.** Keep any notification tokens out of source control (env vars or an ignored config file).

The MyPack link attached to alerts is the one place MyPack is named. It's a link for a human to tap — the code must never request it.

## Conventions

- Keep it small and readable. This is a personal tool, not a framework. Resist over-engineering.
- Watched sections live in a config file, not hardcoded.
- Notify only on a transition into availability (full to open), not on every poll while a seat sits open.
- The planner writes the same `config/watches.json` the watcher reads — that's the integration point between UI and daemon; keep it that way rather than adding a database.
- One catalog request per *course* per pass, even when several of its sections are watched (there is no section-level query parameter — see NOTES.md).

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

# the deployed VM (from the Mac)
vm ui | vm logs | vm status | vm watches | vm update | vm ssh

# run tests — none yet
```
