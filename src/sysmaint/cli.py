"""sysmaint command-line entry point.

`sysmaint --help` discovers subcommands. Each subcommand is a thin wrapper
that loads config, sets up logging, and delegates to a tasks/ module.

Exit codes:
  0  success
  1  task-level failure (subprocess returned non-zero, email failed, etc.)
  2  configuration / usage error
  3  another sysmaint instance is already running (lock contention)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sysmaint import __version__
from sysmaint.core.config import (
    DEFAULT_CONFIG_PATH,
    Config,
    ConfigError,
    load_config,
)
from sysmaint.core.lock import AlreadyRunning, acquire_lock
from sysmaint.core.logging_utils import setup_logger

UPDATE_LOG = Path("/var/log/sysmaint.log")
PIHOLE_LOG = Path("/var/log/sysmaint-pihole.log")
POSTFIX_LOG = Path("/var/log/sysmaint-postfix.log")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sysmaint",
        description=(
            "Linux server maintenance toolkit. "
            "Weekly apt updates, email notifications, postfix relay setup."
        ),
    )
    parser.add_argument("--version", action="version", version=f"sysmaint {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config file (default: {DEFAULT_CONFIG_PATH})",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    sub.add_parser(
        "install",
        help="First-time setup: write config, install timers, send test email",
    ).add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip prompts (use existing config; just install timers)",
    )

    upd = sub.add_parser("update", help="Run apt maintenance and send the summary email")
    upd.add_argument(
        "--security-only",
        action="store_true",
        help="Run security upgrades only (instead of full upgrade)",
    )

    sub.add_parser(
        "pihole",
        help="Run `pihole -up` and email the result (DNS boxes only)",
    )

    postfix_parser = sub.add_parser("postfix", help="Postfix management")
    postfix_sub = postfix_parser.add_subparsers(
        dest="postfix_command", metavar="ACTION", required=True
    )
    postfix_sub.add_parser("setup", help="Install + configure Postfix as Gmail relay")
    postfix_sub.add_parser("purge", help="Remove Postfix and its config")

    sub.add_parser("vim-config", help="Append standard vim settings to /etc/vim/vimrc")
    sub.add_parser(
        "configure-unattended",
        help="Install + configure unattended-upgrades to email through the relay",
    )
    sub.add_parser("status", help="Print local diagnostics (config, timers, disks, services)")
    sub.add_parser("test-email", help="Send a test email using the current config")
    sub.add_parser(
        "migrate-from-legacy",
        help="Migrate from the old auto_updater_package layout",
    )
    sub.add_parser(
        "uninstall",
        help="Remove timers and unit files (preserves config under /etc/sysmaint)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse args and dispatch. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # `sysmaint status` is a special case — it must work even when there's no
    # config yet, and it should run as any user.
    if args.command == "status":
        from sysmaint.tasks import status

        return status.execute()

    # Commands that don't need config loaded:
    if args.command == "install":
        from sysmaint.tasks import install

        logger = setup_logger("sysmaint.install", UPDATE_LOG, console=True)
        return install.execute(logger, non_interactive=args.non_interactive)

    if args.command == "migrate-from-legacy":
        from sysmaint.tasks import migrate

        logger = setup_logger("sysmaint.migrate", UPDATE_LOG, console=True)
        return migrate.execute(logger)

    if args.command == "uninstall":
        from sysmaint.tasks import install

        logger = setup_logger("sysmaint.uninstall", UPDATE_LOG, console=True)
        return install.uninstall(logger)

    if args.command == "postfix" and args.postfix_command == "purge":
        from sysmaint.tasks import postfix_purge

        logger = setup_logger("sysmaint.postfix-purge", POSTFIX_LOG, console=True)
        postfix_purge.execute(logger)
        return 0

    # Everything below needs config.
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"sysmaint: config error: {exc}", file=sys.stderr)
        print(
            "  run `sudo sysmaint install` to set up config",
            file=sys.stderr,
        )
        return 2

    return _dispatch_with_config(args, config)


def _dispatch_with_config(args: argparse.Namespace, config: Config) -> int:
    """Handle commands that require a loaded Config."""
    if args.command == "update":
        from sysmaint.tasks import apt_update

        logger = setup_logger("sysmaint.update", UPDATE_LOG, console=True)
        try:
            with acquire_lock():
                outcome = apt_update.execute(
                    config, logger, security_only=args.security_only
                )
        except AlreadyRunning as exc:
            print(f"sysmaint: {exc}", file=sys.stderr)
            return 3
        return 1 if outcome.any_failures else 0

    if args.command == "pihole":
        from sysmaint.tasks import pihole

        logger = setup_logger("sysmaint.pihole", PIHOLE_LOG, console=True)
        try:
            with acquire_lock():
                ok = pihole.execute(config, logger)
        except AlreadyRunning as exc:
            print(f"sysmaint: {exc}", file=sys.stderr)
            return 3
        return 0 if ok else 1

    if args.command == "postfix" and args.postfix_command == "setup":
        from sysmaint.tasks import postfix_setup

        logger = setup_logger("sysmaint.postfix-setup", POSTFIX_LOG, console=True)
        postfix_setup.execute(config, logger)
        return 0

    if args.command == "vim-config":
        from sysmaint.tasks import vim_config

        logger = setup_logger("sysmaint.vim-config", UPDATE_LOG, console=True)
        vim_config.execute(logger)
        return 0

    if args.command == "configure-unattended":
        from sysmaint.tasks import configure_unattended

        logger = setup_logger("sysmaint.configure-unattended", UPDATE_LOG, console=True)
        configure_unattended.execute(config, logger)
        return 0

    if args.command == "test-email":
        from sysmaint.tasks import test_email_cmd

        logger = setup_logger("sysmaint.test-email", UPDATE_LOG, console=True)
        return test_email_cmd.execute(config, logger)

    # Unreachable — argparse already validated the command name.
    print(f"sysmaint: unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
