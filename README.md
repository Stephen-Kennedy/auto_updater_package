# AutoUpdater with Email Notifications

A Python package designed to manage automatic updates for different programs and ensure email functionality through streamlined utilities.

## Features
- Automated updates for Debian/Ubuntu systems, including Pi-hole updates.
- Secure email notifications for update statuses or errors using Gmail SMTP relay.
- Modular design with shared utilities for commands, logging, and environment variable management.

## Installation
1. Clone or download this repository.
2. Install the package:
   ```bash
   sudo apt-intall pip
   pip install .
   ```

## Usage
- Run the Postfix setup script with elevated permissions:
   ```bash
   python3 main_postfix_setup.py
   ```
- Run the Postfix purge script to clear out Postfix configuration:
   ```bash
   python3 main_postfix_purge.py
   ```
- Run the auto-update script:
   ```bash
   python3 main_apt_update.py
   ```

## Author
Stephen J Kennedy


### Pi-hole Update Script
- Run the Pi-hole update script:
  ```bash
  python main_pihole_update.py
  ```
