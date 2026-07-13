# CLAUDE.md

## What this is

PackSeats is a personal watcher that notifies me when a seat opens in an NC State class section. It polls the public NC State class search (`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and pings me when a watched section frees up. See PRD.md for full scope.

## Current status

Pre-build, Phase 0. The class-search request has been fully reverse-engineered and verified — endpoint, minimal params, term-code scheme, and response format are documented in NOTES.md. Remaining Phase 0 decisions: language, notification channel, hosting. Nothing is scaffolded yet.

## Tech stack

To be locked in Phase 0. Leaning Python for the scrape-and-poll core, but not decided. Fill this in once chosen:

- Language / runtime: TBD
- HTTP + parsing: TBD (e.g. requests + BeautifulSoup, or fetch + a parser)
- Notification: TBD (Telegram bot / ntfy / Pushover / Twilio / email)
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

To be filled in once the stack is set. Placeholder:

```
# run once against a single section
# run the full watcher loop
# run tests
```
