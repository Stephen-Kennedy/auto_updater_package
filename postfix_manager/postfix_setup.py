#!/usr/bin/python3
# Author: Stephen J Kennedy
# Version: 1.1
# Script to setup Postfix on Ubuntu with Gmail SMTP relay and enhanced environmental variable management.

import os
import subprocess
import getpass
import logging
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
import smtplib

# Define global constants
LOG_FILE = "/var/log/postfix_setup.log"
ENV_FILE = "/etc/postfix/env_variables.env"

# Configure logging
def setup_logger(name, log_file, level=logging.INFO):
    """Set up a logger with rotation."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

logger = setup_logger("postfix_setup", LOG_FILE)

# Utility functions
def run_command(command, sudo=False):
    """Run shell command securely and log output."""
    try:
        if sudo:
            command.insert(0, "sudo")
        result = subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        logger.info(f"Command executed successfully: {' '.join(command)}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(command)} | Error: {e.stderr.strip()}")
        print(f"ERROR: Command failed: {' '.join(command)}")
        raise

def ensure_directory_exists(path):
    """Ensure the directory for the given path exists."""
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        print(f"Created directory: {directory}")

def load_env_variables(env_file):
    """Load environment variables from a file."""
    if not os.path.exists(env_file):
        raise FileNotFoundError(f"Environment file {env_file} not found.")
    env_vars = {}
    with open(env_file) as env:
        for line in env:
            line = line.strip()
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value
            else:
                logger.warning(f"Skipping invalid line in environment file: {line}")
    return env_vars

def create_env_file():
    """Prompt user for environmental variables and create the env file."""
    print("\nCreating environment variables file...")
    from_email = input("Enter the sender's email address (FROM_EMAIL): ").strip()
    to_email = input("Enter the recipient's email address (TO_EMAIL): ").strip()
    smtp_server = input("Enter the SMTP server (default: smtp.gmail.com): ").strip() or "smtp.gmail.com"
    gmail_password = getpass.getpass("Enter your Gmail App Password: ").strip()

    ensure_directory_exists(ENV_FILE)

    try:
        with open(ENV_FILE, "w") as env_file:
            env_file.write(f"FROM_EMAIL={from_email}\n")
            env_file.write(f"TO_EMAIL={to_email}\n")
            env_file.write(f"SMTP_SERVER={smtp_server}\n")
            env_file.write(f"EMAIL_PASSWORD={gmail_password}\n")
        run_command(["chmod", "600", ENV_FILE], sudo=True)
        print(f"Environment file created successfully at {ENV_FILE}")
    except Exception as e:
        print(f"ERROR: Failed to create environment variables file: {e}")
        raise

def preconfigure_postfix():
    """Preconfigure Postfix to avoid interactive prompts."""
    preconfig_data = (
        "postfix postfix/main_mailer_type select Internet Site\n"
        "postfix postfix/mailname string localhost"
    )
    try:
        result = subprocess.run(
            ["sudo", "debconf-set-selections"],
            input=preconfig_data,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info("Postfix preconfiguration completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Preconfiguring Postfix failed: {e.stderr.strip()}")
        print(f"ERROR: Preconfiguring Postfix failed: {e.stderr.strip()}")
        raise

def send_email(subject, body):
    """Send email notification using local Postfix or specified SMTP server."""
    try:
        env_vars = load_env_variables(ENV_FILE)
        FROM_EMAIL = env_vars['FROM_EMAIL']
        TO_EMAIL = env_vars['TO_EMAIL']
        SMTP_SERVER = env_vars['SMTP_SERVER']
        EMAIL_PASSWORD = env_vars['EMAIL_PASSWORD']

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        with smtplib.SMTP(SMTP_SERVER, 587) as server:
            server.starttls()
            server.login(FROM_EMAIL, EMAIL_PASSWORD)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())

        logger.info(f"Email notification sent: {subject}")
        print(f"Email notification sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        print(f"ERROR: Failed to send email: {e}")
        raise

# Main setup function
def main():
    print("Postfix Gmail SMTP Relay Setup")
    print("================================")
    print(f"Logs will be written to {LOG_FILE}")

    # Create or verify environment variables file
    if not os.path.exists(ENV_FILE):
        create_env_file()

    # Preconfigure Postfix to avoid interactive prompts
    print("\nPreconfiguring Postfix...")
    preconfigure_postfix()

    # Install Postfix
    print("\nInstalling Postfix...")
    run_command(["apt-get", "update"], sudo=True)
    run_command(["apt-get", "install", "postfix", "-y"], sudo=True)

    # Configure Postfix main.cf
    print("\nConfiguring Postfix...")
    postfix_config = """relayhost = [smtp.gmail.com]:587
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd
smtp_sasl_security_options = noanonymous
smtp_tls_security_level = encrypt
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt
"""

    try:
        with open("/tmp/main.cf", "w") as f:
            f.write(postfix_config)
        run_command(["mv", "/tmp/main.cf", "/etc/postfix/main.cf"], sudo=True)
        print("Postfix configuration file created successfully.")
    except Exception as e:
        print(f"ERROR: Failed to write Postfix configuration file: {e}")
        raise

    # Create Gmail authentication file
    print("\nCreating Gmail authentication file...")
    try:
        env_vars = load_env_variables(ENV_FILE)
        with open("/tmp/sasl_passwd", "w") as f:
            f.write(f"[{env_vars['SMTP_SERVER']}]:587 {env_vars['FROM_EMAIL']}:{env_vars['EMAIL_PASSWORD']}\n")
        run_command(["mv", "/tmp/sasl_passwd", "/etc/postfix/sasl_passwd"], sudo=True)
        run_command(["chmod", "600", "/etc/postfix/sasl_passwd"], sudo=True)
        run_command(["postmap", "/etc/postfix/sasl_passwd"], sudo=True)
    except Exception as e:
        print(f"ERROR: Failed to write Gmail authentication file: {e}")
        raise

    # Restart Postfix
    print("\nRestarting Postfix...")
    run_command(["systemctl", "restart", "postfix"], sudo=True)

    print("\nPostfix setup is complete. Test by sending an email.")
    send_email("Postfix install status", "Postfix setup is complete and functional.")

if __name__ == "__main__":
    main()

