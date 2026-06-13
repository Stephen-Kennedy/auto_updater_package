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
| `sysmaint postfix setup` | Installs Postfix and configures it as a Gmail SMTP relay |
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
emails through the same Gmail relay so all maintenance mail looks consistent
in your inbox.

## Install (new box, three commands)

```bash
sudo apt install -y pipx
sudo pipx install --global git+https://github.com/Stephen-Kennedy/sysmaint.git
sudo sysmaint install
```

The interactive installer asks for:
- The sender Gmail account (you should use a dedicated noreply account with 2FA + app password, not your personal Gmail).
- The recipient address (where notifications go).
- A Gmail App Password (16 chars, generated at <https://myaccount.google.com/security>).
- Whether you want auto-reboot in a maintenance window.
- The list of services to watch.

It then writes config to `/etc/sysmaint/`, installs systemd units, enables
the weekly timer, and sends a test email so you know the wiring works.

## Install (existing legacy box)

If you're upgrading from the old `auto_updater_package` layout (cron jobs
pointing at `main_*.py` scripts, env vars in `/etc/postfix/env_variables.env`):

```bash
cd ~/auto_updater_package && git pull
sudo pipx install --global .
sudo sysmaint migrate-from-legacy
```

`migrate-from-legacy` will:
1. Comment out the legacy `main_*.py` cron entries (with `.sysmaint.bak` backups).
2. Carry your existing credentials from `/etc/postfix/env_variables.env` into
   `/etc/sysmaint/sysmaint.conf` (split into config + 0600 password file).
3. Install systemd unit files and enable the weekly timer.

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
smtp_server = smtp.gmail.com
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

| Timer | Default | Configurable via |
|---|---|---|
| `sysmaint-update.timer` | Every Sunday 03:00 + up to 2h jitter | Edit `/etc/systemd/system/sysmaint-update.timer` |
| `sysmaint-pihole.timer` | First Sunday of the month 04:00 + 1h jitter | DISABLED by default; `systemctl enable --now sysmaint-pihole.timer` to opt in |

`Persistent=true` is set on both timers, so a box that was off when the timer
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

## Troubleshooting

```bash
sudo sysmaint status                           # high-level: what's the box doing?
sudo systemctl list-timers sysmaint*           # when does the next run fire?
sudo journalctl -u sysmaint-update.service -e  # what happened last time?
tail -n 200 /var/log/sysmaint.log              # detailed sysmaint logs
sudo sysmaint test-email                       # is the relay working?
```

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

## Uninstall

```bash
sudo sysmaint uninstall              # removes timers + unit files
sudo rm -rf /etc/sysmaint            # if you also want to nuke the config
sudo pipx uninstall --global sysmaint
```

## Development

```bash
git clone https://github.com/Stephen-Kennedy/sysmaint
cd sysmaint
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                  # 81 tests, ~2s
ruff check src tests
mypy src
```

## License

MIT — see [LICENSE](LICENSE).
