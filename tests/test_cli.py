"""Smoke tests for the CLI parser. These don't run subcommands — just verify
that argparse is wired up correctly and that --help renders without errors."""

from __future__ import annotations

import pytest

from sysmaint.cli import _build_parser


def test_parser_builds() -> None:
    parser = _build_parser()
    assert parser.prog == "sysmaint"


def test_parser_requires_subcommand() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


@pytest.mark.parametrize(
    "args",
    [
        ["status"],
        ["update"],
        ["update", "--security-only"],
        ["pihole"],
        ["postfix", "setup"],
        ["postfix", "purge"],
        ["vim-config"],
        ["configure-unattended"],
        ["test-email"],
        ["install"],
        ["install", "--non-interactive"],
        ["migrate-from-legacy"],
        ["uninstall"],
    ],
)
def test_all_subcommands_parse(args: list[str]) -> None:
    parser = _build_parser()
    ns = parser.parse_args(args)
    assert ns.command == args[0]


def test_postfix_requires_action() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["postfix"])


def test_version_flag() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
