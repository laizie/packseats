# Deploying PackSeats to a DigitalOcean droplet

Always-on hosting so the watcher keeps polling with the laptop closed. One-time
setup, ~20 minutes of clicking.

## 1. Get the free credit (student)

1. Apply for the [GitHub Student Developer Pack](https://education.github.com/pack)
   with your NC State email. Approval ranges from minutes to a couple of days.
2. In the pack's offers, redeem the **DigitalOcean credit** — it applies to a new
   DO account's billing page.

## 2. Create the droplet

- Ubuntu 24.04 LTS, **Basic** shared CPU, the cheapest size ($4/mo, 512 MB —
  plenty; the watcher is tiny).
- Region: NYC (closest to NC).
- Authentication: add your Mac's SSH key
  (`cat ~/.ssh/id_ed25519.pub`, create one with `ssh-keygen` if missing).

## 3. Put the code on it

SSH in as root (`ssh root@<droplet-ip>`), then give the droplet read access to
this private repo with a deploy key:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519   # on the droplet
cat ~/.ssh/id_ed25519.pub
```

Paste that public key at GitHub → repo **Settings → Deploy keys → Add deploy
key** (read-only is fine). Then:

```bash
git clone git@github.com:laizie/packseats.git /opt/packseats
bash /opt/packseats/deploy/setup.sh
```

The script installs Python deps, creates a service user, and starts two
systemd services: `packseats-watcher` (polling loop) and `packseats-planner`
(UI on localhost:5050).

## 4. Configure

From your Mac, copy your notification tokens and watch list up:

```bash
scp .env config/watches.json root@<droplet-ip>:/opt/packseats/
ssh root@<droplet-ip> 'mv /opt/packseats/watches.json /opt/packseats/config/ 2>/dev/null;
  chown packseats:packseats /opt/packseats/.env /opt/packseats/config/watches.json;
  systemctl restart packseats-watcher'
```

## 5. Day-to-day

```bash
# watch the logs
ssh root@<droplet-ip> journalctl -u packseats-watcher -f

# use the planner UI from your Mac (it is deliberately NOT exposed publicly —
# it has no login, so it only listens on the droplet's localhost)
ssh -L 5050:localhost:5050 root@<droplet-ip>
# then open http://localhost:5050 in your browser; watches you add there
# take effect on the droplet's watcher directly

# deploy an update
ssh root@<droplet-ip> 'cd /opt/packseats && git pull && systemctl restart packseats-watcher packseats-planner'
```

## Notes

- The watcher polls every ~3 minutes (+jitter). During peak add/drop you can
  tighten it by editing `ExecStart` in the service file to add `--interval 90`,
  but stay polite.
- `.env`, `config/watches.json`, and `data/` live only on the droplet (all
  gitignored) — `git pull` never touches them.
