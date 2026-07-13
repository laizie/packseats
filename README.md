# PackSeats

A personal watcher that pings me when a seat opens up in an NC State class section, so I don't have to sit refreshing the course catalog during registration.

It polls the **public** NC State class search (`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and fires a notification when a watched section flips from full to open. No login, no MyPack, no SSO — public catalog only.

## Status

**Phase 0 — pre-build.** Core decisions (language, notification channel, hosting) are still open, and the class-search request structure still needs to be reverse-engineered from the browser Network tab. See [PRD.md](PRD.md) for the full plan and [CLAUDE.md](CLAUDE.md) for working conventions.

## Layout

```
├── CLAUDE.md                    # working conventions and constraints
├── PRD.md                       # product requirements and build phases
├── config/
│   └── watches.example.json     # example watched-sections config (copy to watches.json)
└── data/                        # runtime state (last-seen seat counts) — gitignored
```

## Hard constraints

- Public catalog only. Never MyPack Portal, Shibboleth SSO, or Duo.
- Polite polling: conservative interval, jitter, no hammering.
- One bad fetch never crashes the watcher.
- No secrets in the repo — notification tokens live in env vars or ignored config.
