import os
from .logging_utils import setup_logger
from .command_utils import run_command
from .email_utils import send_email
from .env_utils import load_env_variables

LOG_FILE = "/var/log/pihole_update.log"
ENV_FILE = "/etc/postfix/env_variables.env"

def update_pihole():
    """Update Pi-hole to the latest version."""
    logger = setup_logger("pihole_update", LOG_FILE)
    logger.info("Starting Pi-hole update...")
    env_vars = load_env_variables(ENV_FILE, required_vars=["FROM_EMAIL", "TO_EMAIL", "SMTP_SERVER", "EMAIL_PASSWORD"])

    pihole_path = "/usr/local/bin/pihole"  # Default installation path
    try:
        if os.path.exists(pihole_path):
            result = run_command([pihole_path, "-up"], logger, sudo=True)
            logger.info("Pi-hole updated successfully.")
            send_email(
                env_vars["FROM_EMAIL"],
                env_vars["TO_EMAIL"],
                env_vars["SMTP_SERVER"],
                env_vars["EMAIL_PASSWORD"],
                "Pi-hole Update Successful",
                f"Pi-hole was updated successfully.\n\n{result}",
                logger
            )
        else:
            logger.warning("Pi-hole is not installed. Skipping update.")
    except Exception as e:
        logger.error(f"Pi-hole update failed: {e}")
        send_email(
            env_vars["FROM_EMAIL"],
            env_vars["TO_EMAIL"],
            env_vars["SMTP_SERVER"],
            env_vars["EMAIL_PASSWORD"],
            "Pi-hole Update Failed",
            f"An error occurred while updating Pi-hole.\n\nError: {e}",
            logger
        )
def main():
    update_pihole()
