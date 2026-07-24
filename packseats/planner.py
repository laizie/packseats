"""Schedule planner: Flask UI for finding classes that fit around your schedule.

Runs single-user on localhost by default (reach it over an SSH tunnel). When exposed to
friends it is multi-user and authenticated: each person logs in via a one-time link minted
by the Telegram bot's /ui command, and only ever sees their own schedule and watches.

Usage: python -m packseats.planner  →  http://127.0.0.1:5050
"""

from __future__ import annotations

import os
import re
import secrets
import sys
from dataclasses import asdict
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, jsonify, redirect, render_template, request, session
from itsdangerous import BadData, URLSafeTimedSerializer

from . import store
from .catalog import (HEADERS, TIMEOUT, ClassSection, Meeting, list_courses,
                      list_subjects, search, summarize)
from .notify import load_dotenv

# The planner reads secrets (PACKSEATS_SECRET, PUBLIC_URL, admin id) from .env, so load
# it at import — unlike the watcher/bot, the planner doesn't otherwise import notify.
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
FORM_URL = "https://webappprd.acs.ncsu.edu/php/coursecat/"
LOGIN_MAX_AGE = 600  # a /ui login link is valid for 10 minutes

app = Flask(__name__)
_terms_cache: list[dict] = []
_subjects_cache: dict[str, list[dict]] = {}  # term -> subjects
_courses_cache: dict[tuple[str, str], list[dict]] = {}  # (term, subject) -> courses
_serializer: URLSafeTimedSerializer | None = None


# --- auth --------------------------------------------------------------------

def admin_id() -> str | None:
    return os.environ.get("PACKSEATS_ADMIN_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or None


def max_watches() -> int:
    try:
        return int(os.environ.get("PACKSEATS_MAX_WATCHES", "15"))
    except ValueError:
        return 15


def is_approved(chat_id) -> bool:
    return str(chat_id) == str(admin_id()) or str(chat_id) in store.load_users()


def username_for(chat_id) -> str:
    return store.load_users().get(str(chat_id), {}).get("username", "")


def current_chat_id():
    return session.get("chat_id")


def login_gate(msg: str = "") -> str:
    note = msg or "Open the PackSeats bot on Telegram and send <code>/ui</code> to get a fresh link."
    return (
        "<!doctype html><meta charset=utf-8>"
        "<title>PackSeats — sign in</title>"
        "<div style='font:16px/1.5 system-ui;max-width:32rem;margin:15vh auto;padding:0 1rem;color:#222'>"
        "<h1 style='font-size:1.4rem'>PackSeats planner</h1>"
        f"<p>{note}</p></div>"
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        cid = session.get("chat_id")
        if cid is None or not is_approved(cid):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "auth required"}), 401
            return login_gate(), 401
        return view(*args, **kwargs)

    return wrapped


@app.get("/login")
def login():
    token = request.args.get("token", "")
    try:
        chat_id = _serializer.loads(token, max_age=LOGIN_MAX_AGE)
    except BadData:
        return login_gate("That link is invalid or has expired. Send <code>/ui</code> to the bot for a new one."), 400
    if not is_approved(chat_id):
        return login_gate("Your access isn't active. Ask the owner, then send <code>/ui</code> to the bot."), 403
    session["chat_id"] = chat_id
    session.permanent = True
    return redirect("/")


@app.get("/logout")
def logout():
    session.clear()
    return login_gate("Signed out. Send <code>/ui</code> to the bot to sign back in.")


@app.get("/api/me")
@login_required
def api_me():
    cid = current_chat_id()
    return jsonify({"chat_id": cid, "username": username_for(cid),
                    "is_admin": str(cid) == str(admin_id())})


# --- helpers -----------------------------------------------------------------

def entry_key(e: dict) -> str:
    return f"{e['term']}:{e['subject']}:{e['course_number']}:{e['section']}"


def watch_record(w: dict, chat_id, username: str) -> dict:
    """A watch record tagged with its owner. The watcher only needs the routing keys;
    the rest is display detail for the Watching panel."""
    return {
        "term": w["term"], "subject": w["subject"],
        "course_number": w["course_number"], "section": w["section"],
        "label": f"{w['subject']} {w['course_number']}-{w['section']}",
        "title": w.get("title", ""), "meeting": w.get("meeting", ""),
        "chat_id": chat_id, "owner": username,
    }


def as_section(e: dict) -> ClassSection:
    """Rebuild a ClassSection from a stored schedule entry, for conflict checks."""
    if "meetings" in e:
        meetings = [Meeting(**m) for m in e["meetings"]]
    else:  # entry saved before sections could hold multiple meeting patterns
        meetings = [Meeting(days=e.get("days", []), start=e.get("start"),
                            end=e.get("end"), time_text=e.get("time_text", "TBD"))]
        meetings = [m for m in meetings if m.days or m.start is not None]
    return ClassSection(
        course=e["course"], section=e["section"], component=e["component"],
        class_number=e["class_number"], status=e["status"], open_seats=e["open_seats"],
        total_seats=e["total_seats"], waitlist=e["waitlist"], meetings=meetings,
        meeting_text=e.get("meeting_text") or summarize(meetings),
        location=e["location"], instructor=e["instructor"], title=e.get("title", ""),
    )


# --- pages + API (all gated + scoped to the logged-in user) ------------------

@app.get("/")
@login_required
def index():
    return render_template("planner.html")


@app.get("/api/terms")
@login_required
def api_terms():
    """Valid terms with human-readable names, scraped from the search form page."""
    global _terms_cache
    if not _terms_cache:
        try:
            resp = requests.get(FORM_URL, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            _terms_cache = [
                {"code": code, "label": label.strip()}
                for code, label in re.findall(r'<option value="(2\d{3})"[^>]*>([^<]+)</option>', resp.text)
            ]
        except Exception as e:
            return jsonify({"error": f"could not load terms: {e}"}), 502
    return jsonify({"terms": _terms_cache})


@app.get("/api/subjects")
@login_required
def api_subjects():
    """All subjects offered in a term (for the subject pickers). Cached per term."""
    term = request.args.get("term", "").strip()
    if not term:
        return jsonify({"error": "term required"}), 400
    if term not in _subjects_cache:
        try:
            _subjects_cache[term] = list_subjects(term)
        except Exception as e:
            return jsonify({"error": f"could not load subjects: {e}"}), 502
    return jsonify({"subjects": _subjects_cache[term]})


@app.get("/api/courses")
@login_required
def api_courses():
    """All courses in a subject this term (for the course pickers). Cached per subject —
    a subject sweep is a chunky request, so we only ever fetch each one once."""
    term = request.args.get("term", "").strip()
    subject = request.args.get("subject", "").strip().upper()
    if not term or not subject:
        return jsonify({"error": "term and subject required"}), 400
    ck = (term, subject)
    if ck not in _courses_cache:
        try:
            _courses_cache[ck] = list_courses(term, subject)
        except Exception as e:
            return jsonify({"error": f"could not load courses: {e}"}), 502
    return jsonify({"courses": _courses_cache[ck]})


@app.get("/api/watches")
@login_required
def api_watches():
    return jsonify({"watches": store.watches_for(current_chat_id())})


@app.post("/api/watches/remove")
@login_required
def api_watches_remove():
    key = request.get_json()["key"]
    store.remove_watch(current_chat_id(), key)
    return jsonify({"ok": True})


@app.post("/api/watches/remove-bulk")
@login_required
def api_watches_remove_bulk():
    """Remove many of the caller's watches at once. Body: {"keys": [...]} to remove a
    specific set (e.g. one course's sections), or {"all": true} to clear them all."""
    body = request.get_json()
    keys = None if body.get("all") else list(body.get("keys", []))
    removed = store.remove_watches(current_chat_id(), keys)
    return jsonify({"ok": True, "removed": removed})


@app.post("/api/watch")
@login_required
def api_watch():
    cid = current_chat_id()
    watch = watch_record(request.get_json(), cid, username_for(cid))
    added, reason = store.add_watch(watch, cap=max_watches())
    if not added:
        msg = "already watching" if reason == "duplicate" else f"you're at the limit of {max_watches()} watches"
        return jsonify({"error": msg}), 409
    return jsonify({"ok": True})


@app.post("/api/watch/bulk")
@login_required
def api_watch_bulk():
    """Add many watches at once (used by 'watch all that fit')."""
    cid = current_chat_id()
    username = username_for(cid)
    added = 0
    for w in request.get_json()["watches"]:
        ok, _ = store.add_watch(watch_record(w, cid, username), cap=max_watches())
        added += 1 if ok else 0
    return jsonify({"ok": True, "added": added})


@app.get("/api/schedule")
@login_required
def api_schedule():
    return jsonify({"entries": store.load_schedule(current_chat_id())})


@app.post("/api/schedule")
@login_required
def api_schedule_add():
    body = request.get_json()
    term, subject = body["term"].strip(), body["subject"].strip().upper()
    number, section = body["course_number"].strip(), body["section"].strip()
    entries = store.load_schedule(current_chat_id())
    candidate = {"term": term, "subject": subject, "course_number": number, "section": section}
    if any(entry_key(e) == entry_key(candidate) for e in entries):
        return jsonify({"error": "already in schedule"}), 409
    try:
        rows = search(term, subject, number)
    except Exception as e:
        return jsonify({"error": f"catalog fetch failed: {e}"}), 502
    sec = next((s for s in rows if s.section == section), None)
    if sec is None:
        return jsonify({"error": f"{subject} {number}-{section} not found in term {term}"}), 404
    entries.append({**candidate, **asdict(sec)})
    store.save_schedule(current_chat_id(), entries)
    return jsonify({"ok": True})


@app.post("/api/schedule/remove")
@login_required
def api_schedule_remove():
    key = request.get_json()["key"]
    entries = [e for e in store.load_schedule(current_chat_id()) if entry_key(e) != key]
    store.save_schedule(current_chat_id(), entries)
    return jsonify({"ok": True})


@app.post("/api/search")
@login_required
def api_search():
    body = request.get_json()
    term, subject = body["term"].strip(), body["subject"].strip().upper()
    number = body["course_number"].strip()
    exclude = body.get("exclude")  # schedule-entry key ignored in replacement mode
    try:
        rows = search(term, subject, number)
    except Exception as e:
        return jsonify({"error": f"catalog fetch failed: {e}"}), 502
    others = [(e["course"] + "-" + e["section"], as_section(e))
              for e in store.load_schedule(current_chat_id()) if entry_key(e) != exclude]
    results = []
    for s in rows:
        conflicts = [name for name, sched in others if s.conflicts_with(sched)]
        results.append({**asdict(s), "conflicts": conflicts, "fits": not conflicts})
    return jsonify({"sections": results})


def _configure_auth(host: str) -> None:
    """Set up session signing. The bot and planner must share PACKSEATS_SECRET so a
    /ui login link minted by one verifies in the other."""
    global _serializer
    secret = os.environ.get("PACKSEATS_SECRET")
    exposed = host not in ("127.0.0.1", "localhost", "::1")
    if not secret:
        if exposed:
            sys.exit("PACKSEATS_SECRET must be set to expose the planner (it signs login "
                     "links + sessions). Generate one with: openssl rand -hex 32")
        secret = secrets.token_hex(32)  # ephemeral: fine for local single-process use
        print("⚠️  PACKSEATS_SECRET not set — using an ephemeral key. Friend /ui logins "
              "won't work until you set the same PACKSEATS_SECRET for the bot and planner.")
    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Secure cookies only once we're actually served over HTTPS (behind Caddy). A plain
        # http:// PUBLIC_URL (local testing) keeps them non-Secure so the cookie still sends.
        SESSION_COOKIE_SECURE=os.environ.get("PACKSEATS_PUBLIC_URL", "").startswith("https://"),
    )
    _serializer = URLSafeTimedSerializer(secret, salt="packseats-ui-login")


def main() -> None:
    host = os.environ.get("PACKSEATS_PLANNER_HOST", "127.0.0.1")
    port = int(os.environ.get("PACKSEATS_PLANNER_PORT", "5050"))
    _configure_auth(host)
    store.migrate_legacy_schedule(admin_id())
    if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("PACKSEATS_PUBLIC_URL"):
        print(f"⚠️  Binding to {host} without PACKSEATS_PUBLIC_URL: serve this behind an "
              "HTTPS reverse proxy (Caddy), don't expose plain HTTP. See the README.")
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
