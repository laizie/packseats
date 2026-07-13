"""Send notifications via Telegram and/or Pushover, configured by env vars (see .env.example)."""

import os
import sys
from pathlib import Path

import requests

TIMEOUT = 15


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def send(message: str) -> None:
    """Send to every configured channel; fall back to stdout when none are set up."""
    sent = False

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        _post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": chat_id, "text": message},
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
        if data["priority"] == 2:  # emergency: re-alerts every 60s for an hour until acked
            data.update(retry=60, expire=3600)
        _post("https://api.pushover.net/1/messages.json", data, "pushover")
        sent = True

    if not sent:
        print(f"[notify:stdout] {message}")


def _post(url: str, data: dict, channel: str) -> None:
    try:
        resp = requests.post(url, data=data, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:  # a failed notification must not kill the watcher
        print(f"[notify:{channel}] send failed: {e}", file=sys.stderr)
