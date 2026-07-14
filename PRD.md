# PackSeats: PRD

A personal watcher that pings me when a seat opens up in an NC State class, so I don't have to sit refreshing the course catalog during registration — plus a local schedule-planner UI for finding classes that fit around my current schedule.

## Problem

NC State registration is a race. When a section is full, the only way to catch a seat is to keep manually checking the class search and hope you're looking at the right moment. Seats can open and vanish in seconds when someone drops. I want a background process that watches the sections I care about and notifies me the instant one frees up.

## Who this is for

Just me for v1. Single user, single machine or single hosted process. No accounts, no multi-tenant anything. Keeping it personal keeps it simple.

That said, I may open it up to friends later, so v1 choices shouldn't foreclose that: notifications go through a Telegram bot (one bot serves unlimited users — each person just messages it once), and the UI is a Flask web app (runs on localhost now, hostable with logins later). If a shared instance ever happens, it must dedupe polling — five people watching sections of the same course is still one request per cycle.

## Goals

- Watch one or more specific class sections for open seats.
- Notify me quickly (ideally within a minute or two of a seat opening) through a channel that actually reaches my phone.
- Be reliable enough to run unattended for the whole registration window without me babysitting it.
- Be polite to NC State's servers.

## Non-goals / out of scope

- Actually enrolling me in the class. This only watches and alerts. I do the enrollment myself. Auto-enrollment would mean touching the authenticated MyPack side, which I'm deliberately avoiding.
- Any interaction with MyPack Portal, Shibboleth SSO, or Duo. Everything reads from the public catalog only.
- A hosted/public web app or a mobile app for v1. (A *local* schedule-planner web UI **is** in scope — see "Schedule-aware planning" below. Multi-user hosting is a maybe-later, not v1.)
- Historical analytics or seat-trend graphs. Maybe a "nice someday" but not v1.

## How it works

The whole thing is a polling loop. On a schedule, it fetches seat data for each watched section from NC State's public class search, parses out the open-seat count, and compares against the last known state. When a section flips from full to having open seats (or its waitlist opens), it fires a notification. That's the entire core.

The important architectural fact: NC State exposes two separate layers.

- The **registration** layer (where you actually enroll) lives behind SSO plus Duo two-factor. Off limits. Scraping it is a terms and 2FA nightmare.
- The **public class search** at `webappprd.acs.ncsu.edu/php/coursecat/` shows open seats, reserved seats, and waitlist counts with no login at all. This is the data source.

So the design leans entirely on the public catalog. No credentials anywhere in this project.

## Schedule-aware planning (added 2026-07-13)

Beyond watching for seats, I want to plan around my existing schedule. A small local web UI (Flask, single page, opens at localhost) that supports:

- **Enter my current schedule** as a list of enrolled sections (`term, subject, course_number, section`). The app fetches each section's meeting days/times from the catalog itself — no manual time entry.
- **Week-grid view**: my schedule laid out on a Mon–Fri time grid.
- **Search around my schedule**: search the catalog and show only sections that don't conflict with the grid, with open/closed/waitlist status visible.
- **Replacement mode**: pick one enrolled class; find alternative sections of that course (or other candidate courses) that fit around everything else.

Conflict detection runs on the day/time data parsed from search responses (see NOTES.md for the markup). The planner and the watcher share the same fetch/parse core.

## Phase 0: decisions to make before building

These are the real forks. Resolve them first, in Claude Code, before scaffolding anything.

**All four resolved (2026-07-13).**

1. **Class-search request** — reverse-engineered and verified. A four-field POST to
   `search.php`, no auth or cookies, returning JSON-wrapped HTML. Full detail in NOTES.md.
2. **Language** — **Python** (requests + BeautifulSoup). The response body being HTML
   inside JSON settled it.
3. **Notifications** — **Pushover** (live and verified; supports emergency priority that
   repeats until acknowledged and bypasses DND). **Telegram** is also implemented but
   unconfigured — it's the free, unlimited-user option if this ever gets shared with
   friends, since one bot token serves everyone.
4. **Hosting** — **Oracle Cloud Always Free VM** ($0 forever, no expiry), systemd
   services, planner reached over an SSH tunnel. Chosen over GitHub Actions cron, whose
   ~5-minute floor and peak-hour drift are worst exactly when registration is hottest.
   See DEPLOY.md.

## Data model

Minimal. Three JSON files, no database. The planner writes what the watcher reads.

- **Watches** (`config/watches.json`): the sections I care about — `{ term, subject, course_number, section, label }`, plus `title` and `meeting` as display detail for the UI. The watcher only needs the first five.
- **My schedule** (`data/schedule.json`): the sections I'm enrolled in. Meeting days/times are fetched from the catalog when added, not typed by hand.
- **Last-seen state** (`data/state.json`): per watch, the last observed status and open-seat/waitlist counts. This is what makes notifications fire only on a *transition* into availability, rather than every poll while a seat sits open.

## Build phases

All shipped as of 2026-07-13.

- ~~**Phase 1**: One-shot script — fetch and print a section's current seat count.~~ `packseats/check.py`
- ~~**Phase 2**: Compare-to-last-state logic and a notification channel.~~ Verified by forcing a Closed→Open transition against a live section.
- ~~**Phase 3**: Multiple watches from a config file.~~ Folded into Phase 2 — one request per *course* serves all its watched sections.
- ~~**Phase 4**: Put it on a schedule in the chosen host.~~ Oracle VM, systemd, running unattended.
- **Phase 5 (optional, not started)**: quiet hours, waitlist-open detection, structured logging.

Planner track (shares the fetch/parse core):

- ~~**Phase P1**: Parse meeting days/times; conflict detection between sections.~~ `ClassSection.conflicts_with()`; online/TBD sections never conflict.
- ~~**Phase P2**: Flask app with the week-grid view.~~
- ~~**Phase P3**: Search-around-schedule and replacement mode.~~

Added beyond the original plan:

- Term dropdown populated from the catalog's own term list (real names, not codes).
- **Watch all N that fit** — bulk-watch every conflict-free section of a course.
- Watching panel: see and remove active watches, with watch state reflected on search results.
- Alerts carry course title, section, meeting days/time, class number, and a tap-through link to MyPack → Manage Classes. (A link for me to tap — the code never requests it.)

## Constraints and etiquette

- Public catalog only. Never the authenticated MyPack side.
- Poll on a sane interval. Don't hammer the server, especially during peak registration when everyone else is hitting it too. Space requests out and add small jitter.
- Fail quietly and keep going. A single failed fetch (timeout, transient 500) should not crash the whole watcher. Log it and retry next cycle.
- No credentials in the repo, ever. There shouldn't be any to begin with, but keep any notification tokens out of source control.

## Risks and open questions

- The class-search response format could change or be harder to parse than hoped. Phase 1 flushes this out early.
- If the catalog rate-limits or blocks aggressive polling, I'll need to back off. Design the interval to be conservative from the start.
- Reserved-seat logic is subtle. A section can show open seats that are actually reserved for a major I'm not in. Decide whether to notify on any open seat or try to distinguish reserved vs unreserved. Probably start simple (notify on any change) and refine if it's noisy.
