"""Send notifications via Telegram and/or Pushover, configured by env vars (see .env.example)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

TIMEOUT = 15


def load_dotenv() -> None:
    """Load KEY=value lines from the repo's .env into os.environ (without overriding
    anything already set). Every entry point that needs secrets calls this — the
    planner doesn't import notify, so it calls load_dotenv() itself."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


def send(message: str, url: str | None = None, url_title: str | None = None) -> None:
    """Send to every configured channel; fall back to stdout when none are set up.

    `url` rides along as a tappable link (Pushover shows `url_title`).
    """
    sent = False

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        text = f"{message}\n{url}" if url else message
        _post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": chat_id, "text": text},
            "telegram",
        )
        sent = True

    po_token = os.environ.get("PUSHOVER_TOKEN")
    po_user = os.environ.get("PUSHOVER_USER")
    if po_token and po_user:
        data = {
            "token": po_token,
            "user": po_user,
            "message": message,
            "priority": int(os.environ.get("PUSHOVER_PRIORITY", "1")),
        }
        if url:
            data["url"] = url
            data["url_title"] = url_title or url
        if data["priority"] == 2:  # emergency: re-alerts every 60s for an hour until acked
            data.update(retry=60, expire=3600)
        _post("https://api.pushover.net/1/messages.json", data, "pushover")
        sent = True

    if not sent:
        print(f"[notify:stdout] {message}" + (f" [{url}]" if url else ""))


def send_telegram(message: str, chat_id: str | int, url: str | None = None,
                  url_title: str | None = None) -> bool:
    """Send one message to a specific Telegram chat via the shared bot token.

    Used to alert an individual bot user (fan-out in the watcher). Returns True if
    a token was configured and a send was attempted. `url_title` is unused for
    Telegram (kept for a common signature with the Pushover path) — the link is
    appended to the text instead.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print(f"[notify:telegram] no TELEGRAM_BOT_TOKEN set; would send to {chat_id}: {message}")
        return False
    text = f"{message}\n{url}" if url else message
    _post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat_id, "text": text},
        "telegram",
    )
    return True


def _post(url: str, data: dict, channel: str) -> None:
    try:
        resp = requests.post(url, data=data, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:  # a failed notification must not kill the watcher
        print(f"[notify:{channel}] send failed: {e}", file=sys.stderr)
