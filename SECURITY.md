# Security & safe self-hosting

PackSeats is meant to be run by one person, for themselves, at $0. If you self-host it,
these are the practices that keep it that way — no surprise charges, nothing exposed, no
secrets leaked. None of this is exotic; it's mostly "don't undo the safe defaults."

## Two golden rules

1. **Never expose the planner.** The planner UI (`packseats.planner`, port 5050) has
   **no authentication** — by design. Anyone who can reach it can read and rewrite your
   watch list. It binds to `127.0.0.1` only. Reach it remotely with an **SSH tunnel**, not
   by opening a port. Concretely, do **not**:
   - open port 5050 in your cloud provider's security list / firewall,
   - put the planner behind a public reverse proxy,
   - set `PACKSEATS_PLANNER_HOST` to `0.0.0.0` or any non-loopback address (the app prints
     a warning if you do).

   The watcher (`packseats.watcher`) makes only outbound requests and listens on nothing,
   so it has no network exposure.

2. **Never commit secrets.** Notification tokens live in `.env`, which is gitignored (as
   are `config/watches.json` and `data/`). Confirm before your first push:

   ```bash
   git check-ignore .env config/watches.json   # should print both paths
   git grep -nI -iE 'pushover_token|telegram_bot_token'  # should show only .env.example
   ```

   Keep `.env` at mode `600` (the deploy `setup.sh` does this on the VM).

## The shared friends bot (if you enable it)

The optional Telegram bot (`packseats.bot`) lets friends manage their own watches without
any setup on their end. It's built to add as little risk as possible:

- **Invite-gated.** Only someone with your `PACKSEATS_INVITE_CODE` can join. Treat the code
  like a password — hand it out only to people you want using your instance. You're pinged
  on every join and can `/kick <chat_id>` anyone (which also drops their watches).
- **No new attack surface.** The bot polls Telegram **outbound** (`getUpdates`) — it opens
  no inbound port and needs no webhook. On its own it adds no ingress; SSH stays your only
  open port. (The web planner below is a separate opt-in that does open 80/443.)
- **Almost nothing to steal.** The only data stored is `data/users.json` (chat-id +
  Telegram username) and each person's watched sections in `config/watches.json` — no
  passwords, no emails, no catalog credentials. The single secret is your bot token, which
  stays in `.env`. Both files are gitignored.
- **Bounded load / stays $0.** A per-user cap (`PACKSEATS_MAX_WATCHES`, default 15) and the
  watcher's one-request-per-course dedup keep polling polite no matter how many friends
  join. More users doesn't cost more on Always Free (see below); your budget alert still
  covers you.
- **Input is validated** before it ever reaches the catalog, and one malformed message can
  never crash the bot (it logs and keeps going, like the watcher).

If you'd rather not run it, just don't `enable` the `packseats-bot` service — the watcher
and planner work exactly as before.

## The web planner for friends (if you expose it)

This is the one feature that opens an inbound port, so it's built to be safe by
construction. Off by default; it only turns on when you set `PACKSEATS_SECRET` +
`PACKSEATS_PUBLIC_URL` and put a reverse proxy in front.

- **Login without passwords.** A friend sends `/ui` to the bot and gets a one-time link
  carrying a short-lived (10-minute) token signed with `PACKSEATS_SECRET`. The planner
  verifies the signature, confirms the chat-id is still an approved bot user, and issues a
  signed session cookie (HttpOnly, Secure, SameSite=Lax). No account, no password, nothing
  to phish or leak.
- **Every route is gated.** There is no unauthenticated endpoint — each request re-checks
  that the session's chat-id is still approved, so `/kick` cuts off web access immediately.
- **Flask never faces the internet.** It stays bound to `127.0.0.1`; **Caddy** is the only
  public listener and it terminates HTTPS. If `PACKSEATS_SECRET` is missing the app refuses
  to bind a public interface at all.
- **Per-user isolation.** Each person only reads/writes their own schedule
  (`data/schedules.json`) and their own watches; the same per-user cap applies.

### Standing it up (≈10 min, still $0)

1. **Free domain:** grab a subdomain at <https://www.duckdns.org> and point it at your VM's
   public IP.
2. **Open 80 + 443** in the Oracle security list — and *only* those plus 22. **Never open
   5050** (that's the unproxied Flask app).
3. **Install Caddy** (it isn't in Ubuntu's default repos — add Caddy's first):
   ```bash
   sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
     | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
     | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt update && sudo apt install -y caddy
   ```
   Then copy `deploy/Caddyfile`, replace the domain, put it at `/etc/caddy/Caddyfile`, and
   `sudo systemctl restart caddy`. Caddy fetches a Let's Encrypt cert automatically once the
   domain resolves and ports 80/443 are open.
4. **Configure PackSeats:** in `/opt/packseats/.env` set
   `PACKSEATS_SECRET=$(openssl rand -hex 32)` (the **same** value is read by the bot and the
   planner) and `PACKSEATS_PUBLIC_URL=https://your.duckdns.org`, then
   `sudo systemctl restart packseats-planner packseats-bot`.
5. Test: send `/ui` to the bot, open the link, confirm `https://` shows a valid padlock and
   that `http://<vm-ip>:5050` is **not** reachable from outside.

Keep the URL low-profile (share it with friends, don't post it publicly) and your budget
alert on. To turn the web UI back off, blank `PACKSEATS_SECRET`/`PACKSEATS_PUBLIC_URL`,
close 80/443, and the planner returns to localhost-only.

## Staying on the free tier (never get charged)

PackSeats is tiny and runs comfortably in Oracle Cloud's **Always Free** tier. To be
certain a bill never appears:

- Launch **only** an "Always Free-eligible" shape (e.g. `VM.Standard.E2.1.Micro`). The
  console badges the free ones.
- **Set a budget alert:** Console → Billing → Budgets → a small budget (e.g. $1) with an
  alert threshold near 0%. If a single cent ever accrues, you get an email that day.
- Don't attach paid extras (extra block storage beyond the free allotment, load
  balancers, a second non-free instance).
- Leave the account as **Free Tier** — it will not auto-upgrade to Pay As You Go without
  you explicitly converting it.

The card Oracle asks for at signup is for identity verification; Always Free resources do
not draw on it.

### Deploying, briefly

1. Create an Always-Free-eligible Ubuntu VM (see the shape/budget notes above) and add
   your SSH public key. Keep port 22 as the only open ingress.
2. On the VM, clone this repo to `/opt/packseats` (a **read-only** GitHub deploy key is
   ideal) and run `sudo bash /opt/packseats/deploy/setup.sh` — it installs deps, creates
   the non-login `packseats` service user, and starts the `packseats-watcher` and
   `packseats-planner` systemd services.
3. Copy your `.env` (notification tokens) to `/opt/packseats/.env`, `chmod 600` it, and
   `sudo systemctl restart packseats-watcher`.
4. Reach the planner over an SSH tunnel — e.g. `ssh -L 5050:localhost:5050 <vm>` then open
   `http://localhost:5050`. **Never** publish port 5050.

## VM hardening

- **SSH key-only.** Disable password authentication (`PasswordAuthentication no` in
  `/etc/ssh/sshd_config`) and use a key. Keep port 22 as the **only** open ingress.
- **Least privilege.** The services run as a dedicated non-login `packseats` user, and the
  code is deployed with a **read-only** GitHub deploy key — a compromised VM can't push to
  your repo.
- **Keep it patched.** `sudo apt update && sudo apt upgrade` periodically; prefer Ubuntu
  24.04 for a supported OS.

## Ethics & scope (please keep it this way)

- **Public catalog only.** PackSeats reads only NC State's public class search. It never
  touches MyPack Portal, Shibboleth SSO, or Duo, and stores no credentials. The MyPack link
  in an alert is a convenience link for a human to tap — the code never requests it. Don't
  add authenticated scraping.
- **Be polite to the server.** Keep the poll interval conservative with jitter (the
  defaults are), and one request per course per pass. Don't tighten it into hammering,
  especially during peak registration.
- **Unofficial.** This project is not affiliated with, endorsed by, or supported by NC
  State University. It's a personal tool shared as-is.

## Reporting a vulnerability

If you find a security issue in this code, please open a GitHub issue (for non-sensitive
reports) or contact the repository owner privately for anything that shouldn't be public.
This is a small personal project with no SLA, but genuine reports are appreciated.
