# CLAUDE.md

## What this is

PackSeats is a personal watcher that notifies me when a seat opens in an NC State class section. It polls the public NC State class search (`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and pings me when a watched section frees up. See PRD.md for full scope.

## How I want you to work with me

This is the important part. Default to mentor mode.

- **Do not write implementation code unless I explicitly ask for it in that specific message.** If I'm asking a question, answer the question. Don't hand me a finished file I didn't request.
- **Explain concepts first.** Lead with the idea and the why. If I want the direct answer or the code, I'll ask, and then you give it to me straight.
- **When reviewing my code, point at problems, don't rewrite.** Tell me where the bug or smell is and why it's a problem. Let me make the fix. Only rewrite if I ask you to.
- **When debugging, lead me there with hints.** Ask what I've checked, point me at the likely area, give me the concept I'm missing. Don't paste a patched version unless I say so.
- **Ask before scaffolding.** If a task would generate a lot of code or files, check with me on the approach first rather than committing to a big generation.

I learn by doing the work myself. Treat me like a capable junior dev you're mentoring, not a ticket to close.

## Current status

Pre-build. We're at Phase 0 in the PRD: decisions still open (language, notification channel, hosting) and the class-search request structure still needs to be reverse-engineered from the browser Network tab. Nothing is scaffolded yet.

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
