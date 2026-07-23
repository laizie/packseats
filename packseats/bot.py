"""Shared Telegram bot: let approved friends manage their own seat watches by chat.

Friends never set up hosting or tokens — they message this one bot, join with an
invite code, and add/remove watches. Their watches land in the same
config/watches.json the watcher already polls (tagged with their chat_id), and the
watcher fans out alerts to whoever is watching a section.

Design notes:
  * Long-polling via getUpdates — outbound only, so the bot opens NO inbound port.
  * Access is gated by PACKSEATS_INVITE_CODE; the admin is pinged on every join and
    can /kick anyone. Only chat_id + username + watches are stored — no passwords.
  * A per-user watch cap bounds how much polling load the shared instance takes on.
  * /list is intentionally network-free (no per-request catalog hits) to stay polite
    to NC State; live seat counts come at /watch time and in alerts.

Usage: python -m packseats.bot   (needs TELEGRAM_BOT_TOKEN + PACKSEATS_INVITE_CODE)
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from itsdangerous import URLSafeTimedSerializer

from . import notify, store  # importing notify loads .env
from .catalog import search

POLL_TIMEOUT = 30  # Telegram long-poll seconds
HTTP_TIMEOUT = POLL_TIMEOUT + 10

TERM_RE = re.compile(r"^2\d{3}$")
SUBJECT_RE = re.compile(r"^[A-Za-z]{2,4}$")
NUMBER_RE = re.compile(r"^\d{2,3}[A-Za-z]?$")
SECTION_RE = re.compile(r"^[A-Za-z0-9]{1,4}$")

HELP = (
    "PackSeats bot — I ping you the moment a full NC State section opens up.\n\n"
    "/watch <term> <subject> <number> <section>\n"
    "    e.g. /watch 2268 CSC 316 001\n"
    "    (term = 2 + year + 1 Spring / 6 Su1 / 7 Su2 / 8 Fall, so 2268 = Fall 2026)\n"
    "/list — your current watches\n"
    "/unwatch <n> — stop watching item n from /list\n"
    "/ui — open the web planner (schedule grid + fit-aware search)\n"
    "/help — this message\n\n"
    "Public course catalog only — I never touch MyPack or your login."
)


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] bot: {msg}")


def token() -> str:
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t:
        sys.exit("TELEGRAM_BOT_TOKEN is not set — the bot cannot run without it.")
    return t


def invite_code() -> str | None:
    return os.environ.get("PACKSEATS_INVITE_CODE") or None


def admin_id() -> str | None:
    return os.environ.get("PACKSEATS_ADMIN_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or None


def max_watches() -> int:
    try:
        return int(os.environ.get("PACKSEATS_MAX_WATCHES", "15"))
    except ValueError:
        return 15


def ui_login_url(chat_id) -> str | None:
    """A one-time planner login link for this user, or None if the web UI isn't set up.
    Signed with PACKSEATS_SECRET (shared with the planner) + a matching salt, so the
    planner can verify it. Valid for 10 minutes (enforced on the planner side)."""
    secret = os.environ.get("PACKSEATS_SECRET")
    public_url = os.environ.get("PACKSEATS_PUBLIC_URL")
    if not secret or not public_url:
        return None
    token = URLSafeTimedSerializer(secret, salt="packseats-ui-login").dumps(chat_id)
    return f"{public_url.rstrip('/')}/login?token={token}"


def reply(chat_id: int | str, text: str) -> None:
    notify.send_telegram(text, chat_id)


# --- users -------------------------------------------------------------------

def is_admin(chat_id: int | str) -> bool:
    return admin_id() is not None and str(chat_id) == str(admin_id())


def is_approved(chat_id: int | str, users: dict) -> bool:
    return is_admin(chat_id) or str(chat_id) in users


def user_label(msg_from: dict) -> str:
    return msg_from.get("username") and f"@{msg_from['username']}" or msg_from.get("first_name", "someone")


# --- watch helpers -----------------------------------------------------------

def user_watches(watches: list[dict], chat_id: int | str) -> list[dict]:
    return [w for w in watches if str(w.get("chat_id")) == str(chat_id)]


def same_section(w: dict, term: str, subject: str, number: str, section: str) -> bool:
    return (w["term"] == term and w["subject"] == subject
            and w["course_number"] == number and w["section"] == section)


# --- command handlers --------------------------------------------------------

def cmd_start(chat_id: int, args: list[str], msg_from: dict) -> None:
    users = store.load_users()
    if is_approved(chat_id, users):
        reply(chat_id, "You're already in. " + HELP)
        return
    code = args[0] if args else ""
    if not invite_code():
        reply(chat_id, "This bot isn't accepting new users right now.")
        return
    if code != invite_code():
        reply(chat_id, "That invite code isn't right. Ask the owner for the code, then send:\n/start <code>")
        return
    label = user_label(msg_from)

    def add(u: dict) -> dict:
        u[str(chat_id)] = {
            "username": msg_from.get("username", ""),
            "name": msg_from.get("first_name", ""),
            "joined": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "is_admin": False,
        }
        return u

    store.update_users(add)
    reply(chat_id, "You're in! 🎉\n\n" + HELP)
    if admin_id():
        notify.send_telegram(f"👤 New PackSeats user joined: {label} (chat {chat_id})", admin_id())
    log(f"user joined: {label} ({chat_id})")


def cmd_watch(chat_id: int, args: list[str], users: dict) -> None:
    if len(args) != 4:
        reply(chat_id, "Usage: /watch <term> <subject> <number> <section>\ne.g. /watch 2268 CSC 316 001")
        return
    term, subject, number, section = args
    subject = subject.upper()
    number = number.upper()
    section = section.zfill(3) if section.isdigit() else section.upper()
    if not (TERM_RE.match(term) and SUBJECT_RE.match(subject)
            and NUMBER_RE.match(number) and SECTION_RE.match(section)):
        reply(chat_id, "That doesn't look right. Example: /watch 2268 CSC 316 001")
        return

    mine = user_watches(store.load_watches(), chat_id)
    if len(mine) >= max_watches():
        reply(chat_id, f"You're at the limit of {max_watches()} watches. /unwatch one first.")
        return
    if any(same_section(w, term, subject, number, section) for w in mine):
        reply(chat_id, f"You're already watching {subject} {number}-{section}.")
        return

    try:
        rows = search(term, subject, number)
    except Exception as e:  # noqa: BLE001 — surface a friendly error, keep the bot alive
        log(f"/watch catalog fetch failed for {subject} {number}: {e}")
        reply(chat_id, "Couldn't reach the course catalog just now — try again in a minute.")
        return
    sec = next((s for s in rows if s.section == section), None)
    if sec is None:
        found = ", ".join(sorted(s.section for s in rows)) or "none"
        reply(chat_id, f"No section {section} for {subject} {number} in term {term}.\nSections I see: {found}")
        return

    record = {
        "term": term, "subject": subject, "course_number": number, "section": section,
        "label": f"{subject} {number}-{section}",
        "title": sec.title, "meeting": sec.meeting_text,
        "chat_id": chat_id, "owner": users.get(str(chat_id), {}).get("username", ""),
    }
    store.update_watches(lambda ws: ws + [record])
    state = "open now" if sec.status == "Open" else sec.status.lower()
    reply(chat_id,
          f"✅ Watching {subject} {number}-{section} — {sec.title}\n"
          f"{sec.meeting_text} · {sec.status} ({sec.open_seats}/{sec.total_seats}, {state})\n"
          f"I'll ping you the moment it opens.")
    log(f"watch added: {subject} {number}-{section} for {chat_id}")


def cmd_list(chat_id: int) -> None:
    mine = user_watches(store.load_watches(), chat_id)
    if not mine:
        reply(chat_id, "You're not watching anything yet. Add one with /watch 2268 CSC 316 001")
        return
    lines = [f"{i}. {w['label']} — {w.get('title', '')}".rstrip(" —") for i, w in enumerate(mine, 1)]
    reply(chat_id, "Your watches:\n" + "\n".join(lines) + "\n\nStop one with /unwatch <n>.")


def cmd_unwatch(chat_id: int, args: list[str]) -> None:
    mine = user_watches(store.load_watches(), chat_id)
    if len(args) != 1 or not args[0].isdigit() or not (1 <= int(args[0]) <= len(mine)):
        reply(chat_id, "Usage: /unwatch <n> — use the number from /list.")
        return
    target = mine[int(args[0]) - 1]
    store.update_watches(
        lambda ws: [w for w in ws
                    if not (str(w.get("chat_id")) == str(chat_id)
                            and same_section(w, target["term"], target["subject"],
                                             target["course_number"], target["section"]))]
    )
    reply(chat_id, f"Stopped watching {target['label']}.")
    log(f"watch removed: {target['label']} for {chat_id}")


def cmd_ui(chat_id: int) -> None:
    url = ui_login_url(chat_id)
    if url is None:
        reply(chat_id, "The web planner isn't set up on this instance yet.")
        return
    reply(chat_id, "🗓️ Open your planner (schedule grid + fit-aware search):\n"
                   f"{url}\n\nThis link is just for you and expires in 10 minutes.")


def cmd_users(chat_id: int) -> None:
    users = store.load_users()
    watches = store.load_watches()
    if not users:
        reply(chat_id, "No users have joined yet.")
        return
    lines = []
    for cid, u in users.items():
        n = len(user_watches(watches, cid))
        name = u.get("username") and f"@{u['username']}" or u.get("name", "?")
        lines.append(f"{name} (chat {cid}) — {n} watch{'es' if n != 1 else ''}")
    reply(chat_id, "Users:\n" + "\n".join(lines))


def cmd_kick(chat_id: int, args: list[str]) -> None:
    if len(args) != 1 or not args[0].lstrip("-").isdigit():
        reply(chat_id, "Usage: /kick <chat_id> — get it from /users.")
        return
    target = args[0]
    store.update_users(lambda u: {k: v for k, v in u.items() if k != target})
    store.update_watches(lambda ws: [w for w in ws if str(w.get("chat_id")) != target])
    reply(chat_id, f"Removed user {target} and all their watches.")
    log(f"admin kicked user {target}")


# --- dispatch + loop ---------------------------------------------------------

def handle(update: dict) -> None:
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return
    chat_id = msg["chat"]["id"]
    text = msg["text"].strip()
    if not text.startswith("/"):
        reply(chat_id, "Send /help to see what I can do.")
        return
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()  # strip @botname in group mentions
    args = parts[1:]

    if cmd == "/start":
        cmd_start(chat_id, args, msg.get("from", {}))
        return
    if cmd in ("/help", "/commands"):
        reply(chat_id, HELP)
        return

    users = store.load_users()
    if not is_approved(chat_id, users):
        reply(chat_id, "You need an invite to use this bot. Send:\n/start <code>")
        return

    if cmd == "/watch":
        cmd_watch(chat_id, args, users)
    elif cmd == "/list":
        cmd_list(chat_id)
    elif cmd == "/unwatch":
        cmd_unwatch(chat_id, args)
    elif cmd == "/ui":
        cmd_ui(chat_id)
    elif cmd == "/users" and is_admin(chat_id):
        cmd_users(chat_id)
    elif cmd == "/kick" and is_admin(chat_id):
        cmd_kick(chat_id, args)
    else:
        reply(chat_id, "Not a command I know. Try /help.")


def main() -> None:
    base = f"https://api.telegram.org/bot{token()}"
    if not invite_code():
        log("WARNING: PACKSEATS_INVITE_CODE is not set — nobody can join (admin still works).")
    log("started; long-polling for updates")
    offset: int | None = None
    while True:
        try:
            params = {"timeout": POLL_TIMEOUT}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(f"{base}/getUpdates", params=params, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                try:
                    handle(update)
                except Exception as e:  # noqa: BLE001 — one bad update never kills the bot
                    log(f"error handling update {update.get('update_id')}: {e}")
        except requests.exceptions.RequestException as e:
            log(f"poll error: {e}; retrying shortly")
            time.sleep(5)
        except Exception as e:  # noqa: BLE001
            log(f"unexpected error: {e}; retrying shortly")
            time.sleep(5)


if __name__ == "__main__":
    main()
