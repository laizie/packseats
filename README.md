# PackSeats

A personal watcher that pings me when a seat opens up in an NC State class section, so I don't have to sit refreshing the course catalog during registration.

It polls the **public** NC State class search (`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and fires a notification when a watched section flips from full to open. No login, no MyPack, no SSO — public catalog only.

Alongside the watcher, a local Flask UI lets me lay my current schedule on a week grid, search for classes that fit around it, and find replacements for a specific class.

## Status

**End of Phase 0 — pre-build.** The class-search request is reverse-engineered and verified (see [NOTES.md](NOTES.md)). Stack: Python + requests/BeautifulSoup, Telegram (+ personal Pushover) for alerts, Flask for the planner UI. Hosting is the last open decision. See [PRD.md](PRD.md) for the full plan and [CLAUDE.md](CLAUDE.md) for working conventions.

## Layout

```
├── CLAUDE.md                    # working conventions and constraints
├── PRD.md                       # product requirements and build phases
├── NOTES.md                     # verified class-search request/response format
├── packseats/
│   ├── catalog.py               # fetch + parse core (shared by watcher and planner)
│   ├── check.py                 # one-shot CLI: python -m packseats.check 2268 HESF 101
│   ├── watcher.py               # polling loop: python -m packseats.watcher [--loop]
│   └── notify.py                # Telegram + Pushover senders (.env-configured)
├── config/
│   └── watches.example.json     # example watched-sections config (copy to watches.json)
└── data/                        # runtime state (last-seen seat counts) — gitignored
```

## Hard constraints

- Public catalog only. Never MyPack Portal, Shibboleth SSO, or Duo.
- Polite polling: conservative interval, jitter, no hammering.
- One bad fetch never crashes the watcher.
- No secrets in the repo — notification tokens live in env vars or ignored config.
