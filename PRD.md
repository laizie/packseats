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

**Status (2026-07-13): 3 of 4 resolved.**
1. Class-search request — **done**, fully verified and documented in NOTES.md.
2. Language — **Python** (requests + BeautifulSoup for fetch/parse).
3. Notifications — **Telegram bot** as the primary channel (free, multi-user-ready), plus **Pushover** for my own account (emergency priority repeats until acknowledged and bypasses DND).
4. Hosting — **still open.**

1. **Nail down the class-search request.** Open the class search in a browser, run a real section lookup, and watch the Network tab. Figure out: is it GET or POST, what parameters does it take (term, subject, course number, section), and does the response come back as HTML I have to parse or as something more structured. Everything downstream depends on knowing this exactly. This is task one.

2. **Language.** Python is the natural fit for a scrape-and-poll tool (clean HTTP + parsing story, and I already know it from the ML work). Node/TypeScript is also fine and I've been living in TS lately. Recommendation: Python unless I have a reason to want this in the TS world. Decide and lock it.

3. **Notification channel.** Options, roughly cheapest and simplest first:
   - Telegram bot: free, instant, trivial API. Strong default.
   - ntfy.sh: free push to phone, near-zero setup.
   - Pushover: a few dollars once, very reliable.
   - Twilio SMS: real text message, pennies each, slight setup.
   - Plain email via SMTP app password: fine if inbox is enough.
   Recommendation: Telegram or ntfy for v1.

4. **Where it runs.** It has to keep polling while my laptop is closed.
   - GitHub Actions cron: zero cost, but ~5 min minimum interval and the timing drifts, which hurts during peak registration.
   - Always-on host (Raspberry Pi, cheap VPS, Fly.io, Cloudflare Worker cron): tighter intervals, more control, slight cost or setup.
   Recommendation: pick based on how fast I need alerts. If seconds matter during add/drop, go always-on. If a few minutes is fine, Actions is the lazy win.

## Data model

Minimal. Two things to track.

- **Watches**: the list of sections I care about. Each is roughly `{ term, subject, course_number, section, label }`. Lives in a config file (JSON, YAML, or a `.env`-plus-list, whatever's cleanest).
- **My schedule**: the sections I'm currently enrolled in, same shape as a watch minus the label. Meeting days/times get fetched from the catalog on demand, not stored by hand.
- **Last-seen state**: per watch, the last observed open-seat count (and waitlist count). Needed so I only notify on a transition into availability, not on every poll while a seat sits open. A tiny JSON file or SQLite table is plenty. No database server.

## Build phases

- **Phase 1**: One-shot script. Given one hardcoded section, fetch and print its current seat count. Proves the request and parsing work.
- **Phase 2**: Add the compare-to-last-state logic and a single notification channel. Run it manually a few times, drop and re-add a test section if possible to confirm the transition fires.
- **Phase 3**: Multiple watches from a config file. Loop over all of them per run.
- **Phase 4**: Put it on a schedule in the chosen host. Confirm it survives a laptop-closed run.
- **Phase 5 (optional)**: Nicer config, quiet hours, waitlist-open detection, basic logging.

Planner track (can start after Phase 1, since it shares the fetch/parse core):

- **Phase P1**: Parse meeting days/times from section rows; conflict detection between two sections.
- **Phase P2**: Flask app with the week-grid view of my entered schedule.
- **Phase P3**: Search-around-schedule and replacement mode in the UI.

## Constraints and etiquette

- Public catalog only. Never the authenticated MyPack side.
- Poll on a sane interval. Don't hammer the server, especially during peak registration when everyone else is hitting it too. Space requests out and add small jitter.
- Fail quietly and keep going. A single failed fetch (timeout, transient 500) should not crash the whole watcher. Log it and retry next cycle.
- No credentials in the repo, ever. There shouldn't be any to begin with, but keep any notification tokens out of source control.

## Risks and open questions

- The class-search response format could change or be harder to parse than hoped. Phase 1 flushes this out early.
- If the catalog rate-limits or blocks aggressive polling, I'll need to back off. Design the interval to be conservative from the start.
- Reserved-seat logic is subtle. A section can show open seats that are actually reserved for a major I'm not in. Decide whether to notify on any open seat or try to distinguish reserved vs unreserved. Probably start simple (notify on any change) and refine if it's noisy.
