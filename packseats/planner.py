"""Schedule planner: local Flask UI for finding classes that fit around my schedule.

Usage: python -m packseats.planner  →  http://127.0.0.1:5050
"""

import json
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .catalog import ClassSection, search

ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = ROOT / "data" / "schedule.json"
WATCHES_FILE = ROOT / "config" / "watches.json"

app = Flask(__name__)


def entry_key(e: dict) -> str:
    return f"{e['term']}:{e['subject']}:{e['course_number']}:{e['section']}"


def load_schedule() -> list[dict]:
    if SCHEDULE_FILE.exists():
        return json.loads(SCHEDULE_FILE.read_text())["entries"]
    return []


def save_schedule(entries: list[dict]) -> None:
    SCHEDULE_FILE.parent.mkdir(exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps({"entries": entries}, indent=2))


def as_section(e: dict) -> ClassSection:
    """Rebuild a ClassSection from a stored schedule entry, for conflict checks."""
    return ClassSection(
        course=e["course"], section=e["section"], component=e["component"],
        class_number=e["class_number"], status=e["status"], open_seats=e["open_seats"],
        total_seats=e["total_seats"], waitlist=e["waitlist"], days=e["days"],
        start=e["start"], end=e["end"], time_text=e["time_text"],
        location=e["location"], instructor=e["instructor"],
    )


@app.get("/")
def index():
    return render_template("planner.html")


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
    body = request.get_json()
    watch = {
        "term": body["term"], "subject": body["subject"],
        "course_number": body["course_number"], "section": body["section"],
        "label": f"{body['subject']} {body['course_number']}-{body['section']}",
    }
    data = {"watches": []}
    if WATCHES_FILE.exists():
        data = json.loads(WATCHES_FILE.read_text())
    if any(entry_key(w) == entry_key(watch) for w in data["watches"]):
        return jsonify({"error": "already watching"}), 409
    data["watches"].append(watch)
    WATCHES_FILE.parent.mkdir(exist_ok=True)
    WATCHES_FILE.write_text(json.dumps(data, indent=2))
    return jsonify({"ok": True})


def main() -> None:
    app.run(host="127.0.0.1", port=5050)


if __name__ == "__main__":
    main()
