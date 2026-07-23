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

# config/ and data/ hold BOTH tracked files (config/watches.example.json, data/.gitkeep)
# and runtime state the service writes (watches.json, state.json, users.json, ...). Keep
# them owned by whoever cloned the repo so `git pull` (as that user) keeps working, but
# give the packseats group write access — setgid so new state files inherit the group.
# (Handing the whole dirs to the service user broke the next `git pull` on tracked files.)
CODE_OWNER=$(stat -c '%U' "$REPO_DIR")
mkdir -p data
chown -R "$CODE_OWNER:packseats" "$REPO_DIR/config" "$REPO_DIR/data"
chmod -R g+w "$REPO_DIR/config" "$REPO_DIR/data"
chmod g+s "$REPO_DIR/config" "$REPO_DIR/data"
# .env is gitignored (git never touches it), so keep it owned by and readable only to the service user.
chown packseats:packseats "$REPO_DIR/.env"
chmod 600 "$REPO_DIR/.env"

cp deploy/packseats-watcher.service deploy/packseats-planner.service \
   deploy/packseats-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now packseats-watcher packseats-planner
systemctl --no-pager --lines=0 status packseats-watcher packseats-planner

# The shared Telegram bot (let friends manage their own watches) is OPT-IN — it only
# runs if you want it. Set TELEGRAM_BOT_TOKEN + PACKSEATS_INVITE_CODE in .env, then:
#   systemctl enable --now packseats-bot
echo "To enable the optional shared friends bot: set the bot env vars in .env, then"
echo "  sudo systemctl enable --now packseats-bot   (see SECURITY.md)"
echo "To expose the web planner to friends (Caddy + free HTTPS domain), see the"
echo "  'web planner for friends' section of SECURITY.md (opens ports 80/443)."
