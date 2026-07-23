"""Shared JSON state I/O with atomic writes and a cross-process lock.

The bot and the planner both write config/watches.json, and the bot also owns
data/users.json. Two processes touching the same file need (a) atomic writes so a
reader never sees a half-written file, and (b) a lock so a read-modify-write from
one writer isn't clobbered by the other. This module is the single place that does
both; every writer should go through it.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
WATCHES_FILE = ROOT / "config" / "watches.json"
USERS_FILE = ROOT / "data" / "users.json"
SCHEDULES_FILE = ROOT / "data" / "schedules.json"  # per-user: {chat_id: [entries]}
LEGACY_SCHEDULE_FILE = ROOT / "data" / "schedule.json"  # pre-multi-user single schedule
_LOCK_FILE = ROOT / "data" / ".state.lock"


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same dir + os.replace, so readers only ever
    see the old or the new file, never a partial one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text)
    os.replace(tmp, path)  # atomic on POSIX


@contextmanager
def locked():
    """Exclusive advisory lock shared by all state writers (flock on a lockfile).

    Wrap a read-modify-write in this so concurrent bot/planner edits don't lose
    each other's changes.
    """
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_FILE, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# --- watches (config/watches.json) -------------------------------------------

def load_watches() -> list[dict]:
    if WATCHES_FILE.exists():
        return json.loads(WATCHES_FILE.read_text()).get("watches", [])
    return []


def save_watches(watches: list[dict]) -> None:
    _atomic_write(WATCHES_FILE, json.dumps({"watches": watches}, indent=2))


def update_watches(fn: Callable[[list[dict]], list[dict]]) -> list[dict]:
    """Read-modify-write watches under the lock. `fn` takes the current list and
    returns the new one. Returns the saved list."""
    with locked():
        watches = fn(load_watches())
        save_watches(watches)
        return watches


def watches_for(chat_id: int | str) -> list[dict]:
    """Every watch belonging to one user."""
    return [w for w in load_watches() if str(w.get("chat_id")) == str(chat_id)]


def add_watch(record: dict, cap: int | None = None) -> tuple[bool, str]:
    """Add one watch for record['chat_id'] under the lock. Enforces a per-user cap and
    skips duplicates. Returns (added, reason)."""
    def key(w: dict) -> str:
        return f"{w['term']}:{w['subject']}:{w['course_number']}:{w['section']}"

    cid = str(record.get("chat_id"))
    with locked():
        watches = load_watches()
        mine = [w for w in watches if str(w.get("chat_id")) == cid]
        if cap is not None and len(mine) >= cap:
            return False, "cap"
        if any(key(w) == key(record) for w in mine):
            return False, "duplicate"
        watches.append(record)
        save_watches(watches)
        return True, "ok"


def remove_watch(chat_id: int | str, key: str) -> None:
    """Remove the caller's watch whose `term:subject:course_number:section` == key.
    Only ever touches watches owned by this chat_id."""
    remove_watches(chat_id, [key])


def remove_watches(chat_id: int | str, keys: list[str] | None) -> int:
    """Remove several of the caller's watches at once, under one lock. `keys` is a list
    of `term:subject:course_number:section` keys; pass None to remove ALL of the caller's
    watches. Only ever touches watches owned by this chat_id. Returns how many were removed."""
    def wkey(w: dict) -> str:
        return f"{w['term']}:{w['subject']}:{w['course_number']}:{w['section']}"

    cid = str(chat_id)
    wanted = None if keys is None else set(keys)
    removed = 0

    def prune(ws: list[dict]) -> list[dict]:
        nonlocal removed
        kept = []
        for w in ws:
            mine = str(w.get("chat_id")) == cid
            if mine and (wanted is None or wkey(w) in wanted):
                removed += 1
            else:
                kept.append(w)
        return kept

    update_watches(prune)
    return removed


# --- users (data/users.json) -------------------------------------------------

def load_users() -> dict[str, dict]:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text()).get("users", {})
    return {}


def save_users(users: dict[str, dict]) -> None:
    _atomic_write(USERS_FILE, json.dumps({"users": users}, indent=2))


def update_users(fn: Callable[[dict[str, dict]], dict[str, dict]]) -> dict[str, dict]:
    with locked():
        users = fn(load_users())
        save_users(users)
        return users


# --- per-user schedules (data/schedules.json) --------------------------------

def _all_schedules() -> dict[str, list]:
    if SCHEDULES_FILE.exists():
        return json.loads(SCHEDULES_FILE.read_text()).get("schedules", {})
    return {}


def migrate_legacy_schedule(admin_chat_id: str | int | None) -> None:
    """Fold a pre-multi-user data/schedule.json under the admin's chat_id, once. No-op
    if there's nothing to migrate or the admin is unknown."""
    if not admin_chat_id or not LEGACY_SCHEDULE_FILE.exists():
        return
    with locked():
        schedules = _all_schedules()
        if str(admin_chat_id) in schedules:
            return  # already migrated
        entries = json.loads(LEGACY_SCHEDULE_FILE.read_text()).get("entries", [])
        if entries:
            schedules[str(admin_chat_id)] = entries
            _atomic_write(SCHEDULES_FILE, json.dumps({"schedules": schedules}, indent=2))
        LEGACY_SCHEDULE_FILE.rename(LEGACY_SCHEDULE_FILE.with_suffix(".json.migrated"))


def load_schedule(chat_id: int | str) -> list[dict]:
    return _all_schedules().get(str(chat_id), [])


def save_schedule(chat_id: int | str, entries: list[dict]) -> None:
    with locked():
        schedules = _all_schedules()
        schedules[str(chat_id)] = entries
        _atomic_write(SCHEDULES_FILE, json.dumps({"schedules": schedules}, indent=2))
