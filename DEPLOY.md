# Deploying PackSeats to an Oracle Cloud Always Free VM

Always-on hosting at $0 forever, so the watcher keeps polling with the laptop
closed. One-time setup, ~30 minutes, most of it Oracle's signup.

## 1. Oracle account

Sign up at https://www.oracle.com/cloud/free/. Notes:

- The card is for identity verification only — Always Free resources never
  charge, and the account can't silently upgrade to paid without explicit consent.
- **Home region matters**: Always Free VMs live in your home region and it
  can't be changed later. Pick **US East (Ashburn)** — closest to NC.

## 2. Create the VM

Console → Compute → Instances → **Create instance**:

- **Image**: Ubuntu 24.04 (Canonical).
- **Shape**: `VM.Standard.E2.1.Micro` (the AMD "Always Free-eligible" badge;
  1 GB RAM is plenty — the watcher is tiny). The bigger Ampere A1 shape is also
  free but often capacity-constrained; don't fight for it.
- **SSH key**: paste your Mac's public key (`cat ~/.ssh/id_ed25519.pub`;
  create one with `ssh-keygen` if missing).

SSH is open by default and nothing else needs to be — the planner UI stays on
localhost by design. Log in as the `ubuntu` user:

```bash
ssh ubuntu@<vm-ip>
```

## 3. Put the code on it

Give the VM read access to this private repo with a deploy key:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519   # on the VM
cat ~/.ssh/id_ed25519.pub
```

Paste that public key at GitHub → repo **Settings → Deploy keys → Add deploy
key** (read-only). Then:

```bash
git clone git@github.com:laizie/packseats.git
sudo mv packseats /opt/
sudo bash /opt/packseats/deploy/setup.sh
```

The script installs Python deps, creates a service user, and starts two
systemd services: `packseats-watcher` (polling loop) and `packseats-planner`
(UI on localhost:5050).

## 4. Configure

From your Mac, copy your notification tokens and watch list up:

```bash
cd ~/Repos/packseats
scp .env config/watches.json ubuntu@<vm-ip>:~
ssh ubuntu@<vm-ip> 'sudo mv ~/.env /opt/packseats/.env && sudo mv ~/watches.json /opt/packseats/config/ \
  && sudo chown packseats:packseats /opt/packseats/.env /opt/packseats/config/watches.json \
  && sudo chmod 600 /opt/packseats/.env && sudo systemctl restart packseats-watcher'
```

## 5. Day-to-day

```bash
# watch the logs
ssh ubuntu@<vm-ip> sudo journalctl -u packseats-watcher -f

# use the planner UI from your Mac (it is deliberately NOT exposed publicly —
# it has no login, so it only listens on the VM's localhost)
ssh -L 5050:localhost:5050 ubuntu@<vm-ip>
# then open http://localhost:5050 in your browser; watches you add there
# take effect on the VM's watcher directly

# deploy an update
ssh ubuntu@<vm-ip> 'cd /opt/packseats && git pull && sudo systemctl restart packseats-watcher packseats-planner'
```

## Notes

- The watcher polls every ~3 minutes (+jitter). During peak add/drop you can
  tighten it by editing `ExecStart` in the service file to add `--interval 90`,
  but stay polite.
- `.env`, `config/watches.json`, and `data/` live only on the VM (all
  gitignored) — `git pull` never touches them.
- If Ubuntu 24.04 isn't offered on the Micro shape in your region, Ubuntu 22.04
  works identically.
