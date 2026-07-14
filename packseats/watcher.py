"""Watcher: poll watched sections, notify on a transition into availability.

Usage:
  python -m packseats.watcher            # one pass over all watches
  python -m packseats.watcher --loop     # poll forever (interval + jitter)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from .catalog import search
from .notify import send

ROOT = Path(__file__).resolve().parent.parent
WATCHES_FILE = ROOT / "config" / "watches.json"
STATE_FILE = ROOT / "data" / "state.json"

# Included in alerts so enrolling is one tap away. The watcher itself NEVER
# requests this URL — the no-auth constraint stands; the human logs in.
MYPACK_ENROLL_URL = (
    "https://portalsp.acs.ncsu.edu/psc/CS92PRD_8/EMPLOYEE/NCSIS/c/SSR_STUDENT_FL.SSR_MD_SP_FL.GBL"
    "?Action=U&MD=Y&GMenu=SSR_STUDENT_FL&GComp=SSR_START_PAGE_FL&GPage=SSR_START_PAGE_FL"
    "&scname=CS_SSR_MANAGE_CLASSES_NAV&"
)


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


def label(w: dict) -> str:
    return w.get("label") or f"{w['subject']} {w['course_number']}-{w['section']}"


def watch_key(w: dict) -> str:
    return f"{w['term']}:{w['subject']}:{w['course_number']}:{w['section']}"


def load_watches() -> list[dict]:
    if not WATCHES_FILE.exists():
        sys.exit(f"no watch config at {WATCHES_FILE} — copy config/watches.example.json there")
    return json.loads(WATCHES_FILE.read_text())["watches"]


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def became_available(prev: dict, now: dict) -> bool:
    return now["status"] == "Open" and prev["status"] != "Open"


def run_once() -> None:
    watches = load_watches()
    state = load_state()

    # one request per distinct course, even when several of its sections are watched
    courses: dict[tuple, list[dict]] = {}
    for w in watches:
        courses.setdefault((w["term"], w["subject"], w["course_number"]), []).append(w)

    for (term, subject, number), course_watches in courses.items():
        try:
            rows = {s.section: s for s in search(term, subject, number)}
        except Exception as e:  # one bad fetch never crashes the pass
            log(f"fetch failed for {subject} {number} (term {term}): {e}")
            continue
        for w in course_watches:
            sec = rows.get(w["section"])
            if sec is None:
                log(f"watched section not in results: {label(w)}")
                continue
            now = {"status": sec.status, "open_seats": sec.open_seats, "waitlist": sec.waitlist}
            log(f"{label(w)}: {sec.status} {sec.open_seats}/{sec.total_seats}")
            prev = state.get(watch_key(w))
            if prev is not None and became_available(prev, now):
                send(
                    f"🟢 {label(w)} just opened: {sec.open_seats}/{sec.total_seats} seats "
                    f"({prev['status']} → {sec.status}, class #{sec.class_number}, term {term})",
                    url=MYPACK_ENROLL_URL,
                    url_title="Enroll now: MyPack → Manage Classes",
                )
            state[watch_key(w)] = now

    save_state(state)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loop", action="store_true", help="keep polling instead of one pass")
    ap.add_argument("--interval", type=int, default=180, help="seconds between passes in loop mode")
    args = ap.parse_args()

    if not args.loop:
        run_once()
        return
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"pass failed: {e}")
        time.sleep(args.interval + random.uniform(0, 30))


if __name__ == "__main__":
    main()
