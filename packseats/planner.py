"""Schedule planner: local Flask UI for finding classes that fit around my schedule.

Usage: python -m packseats.planner  →  http://127.0.0.1:5050
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

from .catalog import TIMEOUT, ClassSection, search

ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = ROOT / "data" / "schedule.json"
WATCHES_FILE = ROOT / "config" / "watches.json"
FORM_URL = "https://webappprd.acs.ncsu.edu/php/coursecat/"

app = Flask(__name__)

_terms_cache: list[dict] = []


def entry_key(e: dict) -> str:
    return f"{e['term']}:{e['subject']}:{e['course_number']}:{e['section']}"


def load_schedule() -> list[dict]:
    if SCHEDULE_FILE.exists():
        return json.loads(SCHEDULE_FILE.read_text())["entries"]
    return []


def save_schedule(entries: list[dict]) -> None:
    SCHEDULE_FILE.parent.mkdir(exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps({"entries": entries}, indent=2))


def load_watches() -> list[dict]:
    if WATCHES_FILE.exists():
        return json.loads(WATCHES_FILE.read_text())["watches"]
    return []


def save_watches(watches: list[dict]) -> None:
    WATCHES_FILE.parent.mkdir(exist_ok=True)
    WATCHES_FILE.write_text(json.dumps({"watches": watches}, indent=2))


def as_section(e: dict) -> ClassSection:
    """Rebuild a ClassSection from a stored schedule entry, for conflict checks."""
    return ClassSection(
        course=e["course"], section=e["section"], component=e["component"],
        class_number=e["class_number"], status=e["status"], open_seats=e["open_seats"],
        total_seats=e["total_seats"], waitlist=e["waitlist"], days=e["days"],
        start=e["start"], end=e["end"], time_text=e["time_text"],
        location=e["location"], instructor=e["instructor"], title=e.get("title", ""),
    )


@app.get("/")
def index():
    return render_template("planner.html")


@app.get("/api/terms")
def api_terms():
    """Valid terms with human-readable names, scraped from the search form page."""
    global _terms_cache
    if not _terms_cache:
        try:
            resp = requests.get(FORM_URL, timeout=TIMEOUT)
            resp.raise_for_status()
            _terms_cache = [
                {"code": code, "label": label.strip()}
                for code, label in re.findall(r'<option value="(2\d{3})"[^>]*>([^<]+)</option>', resp.text)
            ]
        except Exception as e:
            return jsonify({"error": f"could not load terms: {e}"}), 502
    return jsonify({"terms": _terms_cache})


@app.get("/api/watches")
def api_watches():
    return jsonify({"watches": load_watches()})


@app.post("/api/watches/remove")
def api_watches_remove():
    key = request.get_json()["key"]
    save_watches([w for w in load_watches() if entry_key(w) != key])
    return jsonify({"ok": True})


def as_watch(w: dict) -> dict:
    """A watch record. The watcher only needs the first five keys; the rest are
    display detail for the UI's Watching panel."""
    return {
        "term": w["term"], "subject": w["subject"],
        "course_number": w["course_number"], "section": w["section"],
        "label": f"{w['subject']} {w['course_number']}-{w['section']}",
        "title": w.get("title", ""),
        "meeting": w.get("meeting", ""),
    }


@app.post("/api/watch/bulk")
def api_watch_bulk():
    """Add many watches at once (used by 'watch all that fit')."""
    wanted = request.get_json()["watches"]
    watches = load_watches()
    existing = {entry_key(w) for w in watches}
    added = 0
    for w in wanted:
        watch = as_watch(w)
        if entry_key(watch) in existing:
            continue
        watches.append(watch)
        existing.add(entry_key(watch))
        added += 1
    save_watches(watches)
    return jsonify({"ok": True, "added": added})


@app.get("/api/schedule")
def api_schedule():
    return jsonify({"entries": load_schedule()})


@app.post("/api/schedule")
def api_schedule_add():
    body = request.get_json()
    term, subject = body["term"].strip(), body["subject"].strip().upper()
    number, section = body["course_number"].strip(), body["section"].strip()
    entries = load_schedule()
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
    save_schedule(entries)
    return jsonify({"ok": True})


@app.post("/api/schedule/remove")
def api_schedule_remove():
    key = request.get_json()["key"]
    entries = [e for e in load_schedule() if entry_key(e) != key]
    save_schedule(entries)
    return jsonify({"ok": True})


@app.post("/api/search")
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
              for e in load_schedule() if entry_key(e) != exclude]
    results = []
    for s in rows:
        conflicts = [name for name, sched in others if s.conflicts_with(sched)]
        results.append({**asdict(s), "conflicts": conflicts, "fits": not conflicts})
    return jsonify({"sections": results})


@app.post("/api/watch")
def api_watch():
    watch = as_watch(request.get_json())
    watches = load_watches()
    if any(entry_key(w) == entry_key(watch) for w in watches):
        return jsonify({"error": "already watching"}), 409
    watches.append(watch)
    save_watches(watches)
    return jsonify({"ok": True})


def main() -> None:
    app.run(host="127.0.0.1", port=5050)


if __name__ == "__main__":
    main()
