#!/usr/bin/python3
# Author: Stephen J Kennedy
# Version: 1.0
# Script to purge Postfix and remove all related configurations on Ubuntu

import os
import subprocess

LOG_FILE = "/var/log/postfix_purge.log"

def run_command(command, sudo=False):
    """Run shell command securely and log output."""
    try:
        if sudo:
            command.insert(0, 'sudo')
        result = subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        with open(LOG_FILE, "a") as log:
            log.write(f"Command executed successfully: {' '.join(command)}\n")
            log.write(result.stdout.strip() + "\n")
        print(f"Command executed successfully: {' '.join(command)}")
        print(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        with open(LOG_FILE, "a") as log:
            log.write(f"\nERROR: Command failed: {' '.join(command)}\n")
            log.write(f"Exit Code: {e.returncode}\n")
            log.write(f"Error Message: {e.stderr.strip()}\n")
        print(f"\nERROR: Command failed: {' '.join(command)}")
        print(f"Exit Code: {e.returncode}")
        print(f"Error Message: {e.stderr.strip()}")
        exit(1)
    except FileNotFoundError:
        with open(LOG_FILE, "a") as log:
            log.write(f"\nERROR: Command not found: {' '.join(command)}\n")
        print(f"\nERROR: Command not found: {' '.join(command)}")
        exit(1)

def purge_postfix():
    """Purge Postfix and remove all related configuration files."""
    print("Purging Postfix and related configuration files...")
    commands = [
        ["apt-get", "remove", "--purge", "postfix", "-y"],
        ["apt-get", "autoremove", "-y"],
        ["apt-get", "clean"],
        ["rm", "-rf", "/etc/postfix"],
        ["rm", "-f", "/etc/aliases.db"],
        ["rm", "-f", "/etc/postfix.env"],
        ["rm", "-f", "/var/log/mail.*"],
        ["rm", "-f", "/etc/postfix/env_variables.env"]
    ]
    for command in commands:
        run_command(command, sudo=True)
    print("\nPostfix and related configurations have been removed.")

def main():
    print("Postfix Purge Script")
    print("=====================")
    print(f"Logs will be written to {LOG_FILE}")

    purge_postfix()

    print("\nPurge complete. Review the logs for any issues.")

if __name__ == "__main__":
    main()