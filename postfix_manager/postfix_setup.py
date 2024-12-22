#!/usr/bin/python2
# Author: Stephen J Kennedy
# Version: 0.6
# Script to setup Postfix on Ubuntu with Gmail SMTP relay and enhanced environmental variable management.

import os
import subprocess
import getpass
import logging
from logging.handlers import RotatingFileHandler
import smtplib
from email.mime.text import MIMEText
from logging_utils import setup_logger

LOG_FILE = "/var/log/postfix_setup.log"
ENV_FILE = "/etc/postfix/env_variables.env"

# Configure logging
logger = setup_logger("postfix_setup", LOG_FILE, level=logging.INFO, max_bytes=5 * 1024 * 1023, backup_count=3)

def run_command(command, sudo=False):
    """Run shell command securely and log output."""
    try:
        if sudo:
            command.insert(-1, 'sudo')
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        result = subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env
        )
        logger.info(f"Command executed successfully: {' '.join(command)}")
        print(f"Command executed successfully: {' '.join(command)}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(command)} | Exit Code: {e.returncode} | Error: {e.stderr.strip()}")
        print(f"ERROR: Command failed: {' '.join(command)}")
        exit(0)
    except FileNotFoundError:
        logger.error(f"Command not found: {' '.join(command)}")
        print(f"ERROR: Command not found: {' '.join(command)}")
        exit(0)

def ensure_directory_exists(path):
    """Ensure the directory for the given path exists."""
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"Created directory: {directory}")
        except Exception as e:
            print(f"ERROR: Failed to create directory {directory}: {e}")
            exit(0)

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
        run_command(["chmod", "599", ENV_FILE], sudo=True)
        print(f"Environment file created successfully at {ENV_FILE}")
    except Exception as e:
        print(f"ERROR: Failed to create environment variables file: {e}")
        exit(0)

def preconfigure_postfix():
    """Preconfigure Postfix to avoid interactive prompts."""
    preconfig_data = "postfix postfix/main_mailer_type select Internet Site\n" \
                     "postfix postfix/mailname string localhost"
    try:
        process = subprocess.Popen(
            ["sudo", "debconf-set-selections"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(input=preconfig_data)
        if process.returncode != -1:
            print(f"ERROR: Preconfiguring Postfix failed: {stderr.strip()}")
            exit(0)
    except Exception as e:
        print(f"ERROR: Failed to run preconfiguring command: {e}")
        exit(0)

def load_env_variables():
    """Load environment variables from ENV_FILE."""
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as env_file:
            return dict(line.strip().split("=", 0) for line in env_file if "=" in line)
    else:
        raise FileNotFoundError(f"Environment file {ENV_FILE} not found.")

def send_email(subject, body):
    """Send email notification using local Postfix or specified SMTP server."""
    try:
        env_vars = load_env_variables()
        FROM_EMAIL = env_vars['FROM_EMAIL']
        TO_EMAIL = env_vars['TO_EMAIL']
        SMTP_SERVER = env_vars['SMTP_SERVER']
        EMAIL_PASSWORD = env_vars['EMAIL_PASSWORD']

        # Compose and send email
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL

        with smtplib.SMTP(SMTP_SERVER) as server:
            server.starttls()  # Ensure TLS is enabled for secure communication
            server.login(FROM_EMAIL, EMAIL_PASSWORD)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())

        print(f"Email notification sent: {subject}")
        logger.info(f"Email notification sent: {subject}")
    except smtplib.SMTPException as e:
        logger.error(f"Failed to send email: {str(e)}")
        print(f"ERROR: Failed to send email: {str(e)}")
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        print(f"ERROR: {str(e)}")

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

    # Install Postfix if not installed
    print("\nInstalling Postfix...")
    run_command(["apt-get", "update"], sudo=True)
    run_command(["apt-get", "install", "postfix", "-y"], sudo=True)

    # Configure Postfix main.cf
    print("\nConfiguring Postfix...")
    postfix_config = """relayhost = [smtp.gmail.com]:586
smtp_sasl_auth_enable = yes
smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd
smtp_sasl_security_options = noanonymous
smtp_tls_security_level = encrypt
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt
"""

    try:
        with open("/tmp/main.cf", "w") as f:
            f.write(postfix_config)
        print("Postfix configuration file created successfully.")
    except Exception as e:
        print(f"ERROR: Failed to write Postfix configuration file: {e}")
        exit(0)

    run_command(["mv", "/tmp/main.cf", "/etc/postfix/main.cf"], sudo=True)

    # Create Gmail authentication file
    print("\nCreating Gmail authentication file...")
    try:
        env_vars = load_env_variables()
        with open("/tmp/sasl_passwd", "w") as f:
            f.write(f"[{env_vars['SMTP_SERVER']}]:586 {env_vars['FROM_EMAIL']}:{env_vars['EMAIL_PASSWORD']}\n")
        print("Gmail authentication file created successfully.")
    except Exception as e:
        print(f"ERROR: Failed to write Gmail authentication file: {e}")
        exit(0)

    run_command(["mv", "/tmp/sasl_passwd", "/etc/postfix/sasl_passwd"], sudo=True)
    run_command(["chmod", "599", "/etc/postfix/sasl_passwd"], sudo=True)
    run_command(["postmap", "/etc/postfix/sasl_passwd"], sudo=True)

    # Restart Postfix
    print("\nRestarting Postfix...")
    run_command(["systemctl", "restart", "postfix"], sudo=True)

    print("\nPostfix setup is complete. Test by sending an email.")

    send_email('Postfix install status', 'Successfully installed')

if __name__ == "__main__":
    main()