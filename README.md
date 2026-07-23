# PackSeats

Get a phone notification the moment a seat opens in a full NC State class — so you don't
have to sit refreshing the course catalog during registration. Comes with a local
schedule-planner UI for finding sections that fit around your existing classes.

PackSeats polls the **public** NC State class search
(`webappprd.acs.ncsu.edu/php/coursecat/`), parses seat availability, and fires a
notification the instant a watched section flips from full to open. No login, no MyPack,
no SSO — public catalog only.

> **Unofficial.** Not affiliated with, endorsed by, or supported by NC State University.
> It reads only the public catalog, stores no credentials, and is shared as-is under the
> [MIT license](LICENSE). Please run it responsibly — see [SECURITY.md](SECURITY.md).

<!-- Add a screenshot of the planner here once you have one: ![Planner](docs/planner.png) -->

## What it does

**Watcher** — checks each watched section every ~3 min (+ jitter) and notifies only on a
*transition* into open, so a seat that sits open doesn't spam you. Alerts carry the course
title, section, meeting days/time, and class number, plus a tap-through link to
MyPack → Manage Classes:

```
🟢 CSC 316-001 just opened: 3/100 seats (Closed → Open)
CSC 316-001 — Data Structures For Computer Scientists
MW 3:00 PM - 4:15 PM · class #1681
```

**Planner UI** — a single Flask page (localhost) where you:

- enter the sections you're enrolled in; meeting times are fetched from the catalog
  automatically and drawn on a Mon–Fri week grid
- search any course and see which sections **fit** vs. **conflict** with your schedule
  (conflicts are named), with live seat status on each
- use **Replacing** mode to hunt for a swap for one specific class
- **Watch** any section, or **Watch all N that fit**, and manage/remove watches in the
  Watching panel — it writes the same config the watcher reads

The watcher and planner share one fetch/parse core (`packseats/catalog.py`) and talk to
each other only through `config/watches.json` — no server, no database.

## Quickstart (local)

Requires Python 3.8+.

```bash
git clone https://github.com/laizie/packseats.git
cd packseats

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # then add a notification token — see below

# one-shot check: all sections of a course, or a single section
.venv/bin/python -m packseats.check 2268 CSC 316 --section 001

# the planner UI  →  http://127.0.0.1:5050
.venv/bin/python -m packseats.planner

# the watcher: poll config/watches.json forever
.venv/bin/python -m packseats.watcher --loop
```

Add the sections you care about through the planner UI (it writes `config/watches.json`),
then leave the watcher running.

Term codes: `2` + two-digit year + `1` Spring / `6` Summer 1 / `7` Summer 2 / `8` Fall.
So `2268` = Fall 2026. (The planner's dropdown does this for you.)

## Notifications

You only need one channel. If none is configured, alerts print to stdout.

- **Telegram (recommended)** — free, ~2 minutes: message [@BotFather](https://t.me/BotFather),
  `/newbot`, copy the token; message your bot once, then read your chat id from
  `https://api.telegram.org/bot<TOKEN>/getUpdates`. Put both in `.env`.
- **Pushover (optional)** — a one-time paid license, but supports *emergency priority*
  that re-alerts until acknowledged and bypasses Do Not Disturb.

All of this is spelled out in [`.env.example`](.env.example). Blank channels are skipped.

## Always-on hosting (optional, still $0)

To keep watching with your laptop closed, run it on a free always-on VM. The `deploy/`
directory has a one-shot `setup.sh` and the two systemd units for an **Oracle Cloud Always
Free** VM (free forever); [SECURITY.md](SECURITY.md) covers safe hosting end to end.

Two safety rules if you host it (full detail in [SECURITY.md](SECURITY.md)):

1. **Never expose the planner** — it has no login; keep it on localhost and reach it over
   an SSH tunnel.
2. **Set an Oracle budget alert** — so a charge can never surprise you.

The included `scripts/vm` helper (`vm ui | logs | status | watches | update | ssh`) is the
author's convenience wrapper for driving the VM over SSH; adapt it to your own host alias.

## Share it with friends (optional shared bot)

If you host PackSeats, you can let friends use it **without any setup on their end** — no
VM, no tokens, no install. They just message your Telegram bot:

```
Friend →  /start <your-invite-code>
Bot    →  You're in! 🎉  (try /watch)
Friend →  /watch 2268 CSC 316 001
Bot    →  ✅ Watching CSC 316-001 — Data Structures (Closed 0/100). I'll ping you.
You    ←  👤 New PackSeats user joined: @friend (chat 123456789)
```

Their watches go into the same `config/watches.json` the watcher already polls, and alerts
fan out to everyone watching a section. Commands: `/watch`, `/list`, `/unwatch <n>`,
`/help`; admin (you) also gets `/users` and `/kick <chat_id>`.

It's **opt-in and invite-gated** — set `TELEGRAM_BOT_TOKEN`, `PACKSEATS_INVITE_CODE`, and
`PACKSEATS_ADMIN_CHAT_ID` in `.env`, then `systemctl enable --now packseats-bot`. The bot
talks to Telegram outbound-only (no new open ports), stores only chat-ids + watches (no
passwords or personal data), and caps watches per user. Full safety model in
[SECURITY.md](SECURITY.md).

### The web planner, for friends too

Friends can also use the full **web planner** (week-grid + fit-aware search) — they send
`/ui` to the bot and tap a one-time login link:

```
Friend →  /ui
Bot    →  🗓️ Open your planner: https://you.duckdns.org/login?token=…  (just for you, 10 min)
```

Each person logs in as themselves (no password — the link carries a signed, expiring
token), gets their **own** schedule + watches, and everything they watch flows to the same
watcher. It's authenticated on every route and `/kick` revokes web access instantly. The
Flask app stays bound to localhost; a **Caddy** reverse proxy fronts it with automatic
HTTPS on a free **DuckDNS** domain, so the only new open ports are 80/443 — still $0. Setup
steps and the full threat model are in [SECURITY.md](SECURITY.md).

## Project layout

```
├── README.md                    # this file
├── SECURITY.md                  # safe self-hosting: no exposure, no charges, no leaks
├── LICENSE                      # MIT
├── packseats/
│   ├── catalog.py               # fetch + parse core (seats, meeting times, titles)
│   ├── check.py                 # one-shot CLI seat check
│   ├── watcher.py               # polling loop + transition detection + alert fan-out
│   ├── notify.py                # Telegram + Pushover senders (.env-configured)
│   ├── bot.py                   # optional shared Telegram bot (friends manage watches)
│   ├── store.py                 # atomic, lock-guarded JSON state (bot + planner write it)
│   ├── planner.py               # Flask app: schedule, search, watch management
│   └── templates/planner.html   # the single-page UI
├── scripts/vm                   # day-to-day VM helper (author's convenience wrapper)
├── deploy/                      # systemd units + VM setup script
├── config/watches.json          # what's being watched (gitignored; example provided)
└── data/                        # last-seen seat state + saved schedule (gitignored)
```

## Design constraints

- **Public catalog only.** Never MyPack Portal, Shibboleth SSO, or Duo. The MyPack link in
  alerts is for a human to tap — the code never requests it.
- **Polite polling.** Conservative interval, jitter, one request per course even when
  several of its sections are watched, and an identifying `User-Agent`.
- **Resilient.** A failed fetch logs and continues; one bad request never crashes the
  watcher.
- **No secrets in the repo.** Tokens live in `.env` (gitignored).

## License

[MIT](LICENSE) — use it, fork it, adapt it. Just keep it public-catalog-only and be kind
to the servers.
