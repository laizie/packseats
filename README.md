# PackSeats

Pings my phone when a seat opens in an NC State class, so I don't have to sit
refreshing the course catalog during registration — plus a planner UI for
finding classes that fit around my current schedule.

It polls the **public** NC State class search
(`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and fires a
notification the moment a watched section flips from full to open. No login, no
MyPack, no SSO — public catalog only.

## Status: running

Live on an Oracle Cloud Always Free VM (cost: $0), polling every ~3 minutes
around the clock. Alerts go to Pushover. Everything in the PRD is built except
optional Phase 5 polish (quiet hours, waitlist-open alerts).

## What it does

**Watcher** — checks each watched section every ~3 min (+ jitter) and notifies
only on a *transition* into open, so a seat that sits open doesn't spam you.
Alerts carry the course title, section, meeting days/time, and class number,
plus a tap-through link to MyPack → Manage Classes:

```
🟢 CSC 316-001 just opened: 3/100 seats (Closed → Open)
CSC 316-001 — Data Structures For Computer Scientists
MW 3:00 PM - 4:15 PM · class #1681
```

**Planner UI** — a single page (Flask) where you:

- enter the sections you're enrolled in; meeting times are fetched from the
  catalog automatically and drawn on a Mon–Fri week grid
- search any course and see which sections **fit** vs. **conflict** with your
  schedule (conflicts are named), with live seat status on each
- use **Replacing** mode to hunt for a swap for one specific class
- **Watch** any section, or **Watch all N that fit**, and manage/remove watches
  in the Watching panel — it writes the same config the cloud watcher reads

## Day-to-day

The VM is aliased as `packseats` in `~/.ssh/config`, and `scripts/vm` wraps
everything (`alias vm='~/Repos/packseats/scripts/vm'` in `~/.zshrc`):

```bash
vm ui        # open the planner in the browser (tunnels to the VM automatically)
vm logs      # follow the watcher logs live
vm status    # are the services up
vm watches   # what's currently being watched
vm update    # pull latest code onto the VM and restart
vm ssh       # shell on the VM (also forwards the planner to localhost:5050)
```

Running it locally instead:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                      # add Pushover/Telegram tokens
.venv/bin/python -m packseats.planner     # planner   → localhost:5050
.venv/bin/python -m packseats.watcher --loop
.venv/bin/python -m packseats.check 2268 CSC 316 --section 001   # one-shot check
```

Term codes: `2` + two-digit year + `1` Spring / `6` Summer 1 / `7` Summer 2 /
`8` Fall. So `2268` = Fall 2026. (The planner's dropdown does this for you.)

## Layout

```
├── README.md                    # this file
├── PRD.md                       # product requirements and build phases
├── NOTES.md                     # reverse-engineered class-search request/response
├── DEPLOY.md                    # Oracle VM setup + day-to-day commands
├── CLAUDE.md                    # working conventions and constraints
├── packseats/
│   ├── catalog.py               # fetch + parse core (seats, meeting times, titles)
│   ├── check.py                 # one-shot CLI seat check
│   ├── watcher.py               # polling loop + transition detection
│   ├── notify.py                # Pushover + Telegram senders (.env-configured)
│   ├── planner.py               # Flask app: schedule, search, watch management
│   └── templates/planner.html   # the single-page UI
├── scripts/vm                   # day-to-day VM helper
├── deploy/                      # systemd units + VM setup script
├── config/watches.json          # what's being watched (gitignored; example provided)
└── data/                        # last-seen seat state + saved schedule (gitignored)
```

## Hard constraints

- **Public catalog only.** Never MyPack Portal, Shibboleth SSO, or Duo. The
  MyPack link in alerts is for *me* to tap — the code never requests it.
- **Polite polling.** Conservative interval, jitter, one request per course even
  when several of its sections are watched.
- **Resilient.** A failed fetch logs and continues; one bad request never
  crashes the watcher.
- **No secrets in the repo.** Tokens live in `.env` (gitignored).
