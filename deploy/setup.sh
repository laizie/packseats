#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu droplet. See DEPLOY.md for the full walkthrough.
# Expects the repo already cloned to /opt/packseats. Run as root:
#   bash /opt/packseats/deploy/setup.sh
set -euo pipefail

REPO_DIR=/opt/packseats

if [ ! -d "$REPO_DIR" ]; then
  echo "clone the repo to $REPO_DIR first (see DEPLOY.md), then re-run" >&2
  exit 1
fi

apt-get update -qq
apt-get install -y -qq git python3-venv

id -u packseats &>/dev/null || useradd --system --home "$REPO_DIR" --shell /usr/sbin/nologin packseats

cd "$REPO_DIR"
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "!! fill in $REPO_DIR/.env with your notification tokens, then: systemctl restart packseats-watcher"
fi
[ -f config/watches.json ] || cp config/watches.example.json config/watches.json

# only the mutable bits belong to the service user; the code stays owned by
# whoever cloned it, so `git pull` updates keep working without sudo gymnastics
mkdir -p data
chown -R packseats:packseats "$REPO_DIR/data" "$REPO_DIR/config" "$REPO_DIR/.env"

cp deploy/packseats-watcher.service deploy/packseats-planner.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now packseats-watcher packseats-planner
systemctl --no-pager --lines=0 status packseats-watcher packseats-planner
