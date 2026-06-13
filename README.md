# sysmaint

Fleet-deployable Linux server maintenance CLI. Drop it on every box you own;
get one weekly email per box summarizing what changed, what failed, what needs
a reboot, and how the disks and services are looking.

Designed for the home lab → small commercial fleet path: standard library
only, isolates into pipx, drives itself from systemd timers, no surprises.

## What it does

| Subcommand | What it does |
|---|---|
| `sysmaint install` | Interactive first-time setup: writes config, installs timers, sends a test email |
| `sysmaint update` | Runs the weekly apt sequence and emails the summary |
| `sysmaint pihole` | Runs `pihole -up` and emails the result (DNS boxes only — timer disabled by default) |
| `sysmaint postfix setup` | Installs Postfix and configures it as an SMTP relay (Gmail by default) |
| `sysmaint postfix purge` | Removes Postfix and its config |
| `sysmaint configure-unattended` | Wires `unattended-upgrades` to email through the same relay |
| `sysmaint vim-config` | Appends a sensible default block to `/etc/vim/vimrc` |
| `sysmaint status` | Local diagnostics: config, next timer fire, disk usage, service health, reboot flag |
| `sysmaint test-email` | Sends a test email using the current config |
| `sysmaint migrate-from-legacy` | One-shot migration from the old `auto_updater_package` layout |
| `sysmaint uninstall` | Removes timers and unit files (preserves `/etc/sysmaint`) |

## Relationship to `unattended-upgrades`

sysmaint does NOT replace `unattended-upgrades`. The two are complementary:

- **`unattended-upgrades` (daily)** — installs security patches in the
  background, emails on change. This is the standard Ubuntu/Debian tool;
  use it for what it's good at.
- **sysmaint (weekly)** — runs the full `dist-upgrade` + `autoremove`
  + `autoclean` sequence and emails a structured summary covering the
  whole box (packages, disks, services, reboot flag).

`sysmaint configure-unattended` sets up `unattended-upgrades` to route its
emails through the same SMTP relay so all maintenance mail looks consistent
in your inbox.

## Install (new box)

```bash
# 1. pipx (system-wide install path works on every pipx version):
sudo apt update && sudo apt install -y pipx

# 2. Install sysmaint pinned to v1.0.1:
sudo PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install \
  git+https://github.com/Stephen-Kennedy/auto_updater_package.git@v1.0.1

# 3. Make those env vars permanent so future `pipx` commands see the install:
echo 'PIPX_HOME=/opt/pipx'         | sudo tee -a /etc/environment
echo 'PIPX_BIN_DIR=/usr/local/bin' | sudo tee -a /etc/environment

# 4. Interactive setup (config + timers + test email):
sudo sysmaint install
```

> **Why the env vars instead of `pipx install --global`?** The `--global` flag
> was added in pipx 1.5.0 (March 2024). Ubuntu 24.04 ships pipx 1.4.3 and
> Debian 12 ships even older — both fail with `unrecognized arguments: --global`.
> The `PIPX_HOME` / `PIPX_BIN_DIR` env-var form has worked since pipx 1.0 and
> achieves the same outcome: app under `/opt/pipx/venvs/sysmaint/`, binary at
> `/usr/local/bin/sysmaint` (where the systemd unit expects it).

The interactive installer asks for:
- The sender Gmail account (use a dedicated noreply account with 2FA + app password, not your personal Gmail).
- The recipient address (where notifications go).
- A Gmail App Password (16 chars, generated at <https://myaccount.google.com/security>).
- Whether you want auto-reboot in a maintenance window.
- The list of services to watch.

It writes config to `/etc/sysmaint/`, installs systemd units, enables the
weekly timer, and sends a test email so you know the wiring works.

## Install on an existing legacy box

If you're upgrading from the old `auto_updater_package` layout (cron jobs
pointing at `main_*.py` scripts, env vars in `/etc/postfix/env_variables.env`):

```bash
sudo apt install -y pipx
sudo PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install \
  git+https://github.com/Stephen-Kennedy/auto_updater_package.git@v1.0.1
sudo sysmaint migrate-from-legacy
```

`migrate-from-legacy` will:
1. Comment out the legacy `main_*.py` cron entries (with `.sysmaint.bak` backups).
2. Carry your existing credentials from `/etc/postfix/env_variables.env` into
   `/etc/sysmaint/sysmaint.conf` (split into config + 0600 password file).
3. Install systemd unit files and enable the weekly timer.

## Fleet deployment — three credential-distribution patterns

Credentials never come from the repo (`.gitignore` excludes `sysmaint.conf`
and `smtp_password`). Pick the pattern that matches your scale:

### A. One box at a time — interactive

```bash
sudo sysmaint install   # prompts for everything, sends test email
```

Good for 1–2 boxes; tedious past that.

### B. Pre-staged config + non-interactive install

Stage two files on the box via your config-management tool (Ansible, scp,
etc.), then install non-interactively:

```bash
# /etc/sysmaint/sysmaint.conf  (mode 0640 root:root) — see config.sample.conf
# /etc/sysmaint/smtp_password  (mode 0600 root:root) — the 16-char app password

sudo install -d -m 755 /etc/sysmaint
sudo install -m 0640 -o root -g root sysmaint.conf /etc/sysmaint/sysmaint.conf
sudo install -m 0600 -o root -g root smtp_password /etc/sysmaint/smtp_password
sudo sysmaint install --non-interactive
```

`--non-interactive` skips prompts, lays down the systemd timers, and sends
a test email. Ideal for Ansible/Chef/Puppet roles.

### C. Copy-paste from a working box

On a working box, print a self-contained install script with your real
config baked in:

```bash
sudo sh -c '
cat <<OUTER
sudo install -d -m 755 /etc/sysmaint
sudo tee /etc/sysmaint/sysmaint.conf > /dev/null <<"CONF"
$(cat /etc/sysmaint/sysmaint.conf)
CONF
sudo chown root:root /etc/sysmaint/sysmaint.conf
sudo chmod 0640 /etc/sysmaint/sysmaint.conf

sudo tee /etc/sysmaint/smtp_password > /dev/null <<"PASS"
$(cat /etc/sysmaint/smtp_password)
PASS
sudo chown root:root /etc/sysmaint/smtp_password
sudo chmod 0600 /etc/sysmaint/smtp_password

sudo sysmaint install --non-interactive
OUTER
'
```

Copy the printed block; paste it on each new box (after pipx-installing
sysmaint). Plaintext credential — paste only into SSH terminals, never
into chat / email / pastebins.

## Pi-hole boxes — enable the extra timer

The Pi-hole timer ships **disabled** by default. On DNS boxes that run
Pi-hole, one command enables monthly updates:

```bash
sudo systemctl enable --now sysmaint-pihole.timer
```

Schedule: first Sunday of each month at 04:00 + up to 1h jitter,
`Persistent=true` for catch-up after downtime. Smoke test without waiting
a month: `sudo systemctl start sysmaint-pihole.service` then
`journalctl -u sysmaint-pihole.service -f`.

To disable later: `sudo systemctl disable --now sysmaint-pihole.timer`.

On a box where Pi-hole isn't installed, the service no-ops cleanly with a
`"Pi-hole not installed at /usr/local/bin/pihole; skipping"` log line — no
spurious failure emails.

## Configuration

`/etc/sysmaint/sysmaint.conf` (INI, 0640 root:root). The SMTP password
lives in a separate `/etc/sysmaint/smtp_password` file (0600 root:root) so
the main config can be grep'd without leaking secrets.

A full annotated sample is at
[`src/sysmaint/data/config.sample.conf`](src/sysmaint/data/config.sample.conf).

Key settings:

```ini
[email]
from = noreply@example.com
to = ops@example.com
smtp_server = smtp.gmail.com    # any STARTTLS relay; not hardcoded to Gmail
smtp_port = 587
password_file = /etc/sysmaint/smtp_password

[update]
auto_reboot = false              # true → reboot during window when needed
reboot_window_start = 03:00
reboot_window_end = 05:00
include_dist_upgrade = true

[notify]
on_success = true                # email on clean upgrade
on_no_changes = false            # email even when nothing was upgraded

[monitor]
disk_threshold_percent = 85
services = sshd,postfix
```

## Schedule

| Timer | Default | Enabled by default? |
|---|---|---|
| `sysmaint-update.timer` | Sunday 03:00 + up to 2h jitter | Yes (via `sysmaint install`) |
| `sysmaint-pihole.timer` | First Sunday of the month 04:00 + 1h jitter | **No** — enable per box on DNS servers only |

Both timers set `Persistent=true`, so a box that was off when the timer
should have fired runs the job as soon as it boots back up — important for
home-lab boxes that aren't 24/7.

## The weekly email

Subject is the at-a-glance signal:

- `[box1.lan] sysmaint weekly: 12 upgraded` — all good
- `[box1.lan] sysmaint weekly: 4 upgraded, REBOOT REQUIRED` — kernel etc.
- `[box1.lan] sysmaint weekly: FAILED` — something failed; check journal
- `[box1.lan] sysmaint weekly: no changes` — quiet week

Body contains:
- Host header (FQDN, distro, kernel, architecture)
- Per-command exit code + duration
- Packages upgraded (counts + names)
- Disk usage per mount, flagged when above threshold
- Configured-service health
- Reboot-required marker with the triggering packages

## Upgrading sysmaint on a box

pipx is version-locked at install time. To move to a new tag (e.g. v1.0.2
when it ships):

```bash
sudo PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install --force \
  git+https://github.com/Stephen-Kennedy/auto_updater_package.git@v1.0.2
```

`--force` reinstalls in place. `/etc/sysmaint/` is preserved — you don't
re-enter credentials. To pick up new systemd-unit content, follow the
re-install with `sudo sysmaint install --non-interactive`.

## Troubleshooting

```bash
sudo sysmaint status                           # high-level: what's the box doing?
sudo systemctl list-timers 'sysmaint-*'        # when does the next run fire?
sudo journalctl -u sysmaint-update.service -e  # what happened last time?
tail -n 200 /var/log/sysmaint.log              # detailed sysmaint logs
sudo sysmaint test-email                       # is the relay working?
```

Common errors:

| Symptom | Diagnosis |
|---|---|
| `pipx: unrecognized arguments: --global` | Pipx < 1.5; use the `PIPX_HOME`/`PIPX_BIN_DIR` env-var form (see Install section) |
| `error: externally-managed-environment` | You used `pip` instead of `pipx`. PEP 668 blocks system-wide `pip` on modern Debian/Ubuntu |
| `sysmaint --version` shows "command not found" | `PIPX_BIN_DIR` not on root's PATH, or didn't persist to `/etc/environment` |
| Config error: "Password file has unsafe permissions" | `sudo chmod 600 /etc/sysmaint/smtp_password` |
| Test email doesn't arrive | `sudo journalctl -u sysmaint-update.service`; look for `SMTP authentication failed` or `SMTP attempt N/3 failed` |

## Security notes

- Run as root (the systemd timer does this for you). The CLI refuses to run
  privileged operations as a non-root user.
- The password file is checked for `0600` permissions on every load —
  sysmaint refuses to start if your credential is world- or group-readable.
- All `apt` commands run with `DEBIAN_FRONTEND=noninteractive` and
  `--force-confold`/`--force-confdef`, so a package never blocks waiting
  for stdin during a scheduled run.
- A file lock at `/run/sysmaint.lock` prevents two timer fires from
  trampling each other (e.g. a `Persistent=true` catch-up firing while
  you're running `sysmaint update` by hand).
- Subprocess and SMTP calls have explicit timeouts — a wedged mirror or
  unreachable SMTP server can't hang the box.
- The Postfix `relayhost` is templated from `/etc/sysmaint/sysmaint.conf`,
  not Gmail-hardcoded. Any STARTTLS-capable relay works.

## Uninstall

```bash
sudo sysmaint uninstall              # removes timers + unit files
sudo rm -rf /etc/sysmaint            # if you also want to nuke the config
sudo PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx uninstall sysmaint
```

## Development

```bash
git clone https://github.com/Stephen-Kennedy/auto_updater_package
cd auto_updater_package
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                  # 85 tests, ~2s
ruff check src tests
mypy src
```

## License

MIT — see [LICENSE](LICENSE).
