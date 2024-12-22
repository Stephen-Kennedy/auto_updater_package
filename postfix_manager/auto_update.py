# auto_update module
from .email_utils import send_email
from .env_utils import load_env_variables
from .logging_utils import setup_logger
from .command_utils import run_command

LOG_FILE = "/var/log/pyupdate.log"
ENV_FILE = "/etc/postfix/env_variables.env"

def auto_update():
    """Perform system updates and clean-up."""
    logger = setup_logger("update_script", LOG_FILE)

    logger.info("Starting system update...")
    env_vars = load_env_variables(ENV_FILE, required_vars=["FROM_EMAIL", "TO_EMAIL", "SMTP_SERVER", "EMAIL_PASSWORD"])

    commands = [
        ['apt-get', '-y', 'update'],
        ['apt-get', '-y', 'upgrade'],
        ['apt-get', '-y', 'autoremove'],
        ['apt-get', '-y', 'autoclean']
    ]

    updates_performed = []
    for command in commands:
        try:
            result = run_command(command, logger, sudo=True)
            if result:
                updates_performed.append(' '.join(command))
        except Exception as e:
            logger.error(f"Failed to run {' '.join(command)}: {str(e)}")

    if updates_performed:
        send_email(
            env_vars["FROM_EMAIL"],
            env_vars["TO_EMAIL"],
            env_vars["SMTP_SERVER"],
            env_vars["EMAIL_PASSWORD"],
            "System Update Completed",
            f"The following updates were performed:\n\n" + '\n'.join(updates_performed),
            logger
        )
    else:
        logger.info("No updates were performed.")

def main():
    """Main function to execute the auto-update logic."""
    try:
        auto_update()
    except Exception as e:
        logger = setup_logger("update_script", LOG_FILE)
        logger.critical(f"Unhandled exception: {str(e)}", exc_info=True)
        env_vars = load_env_variables(ENV_FILE, required_vars=["FROM_EMAIL", "TO_EMAIL", "SMTP_SERVER", "EMAIL_PASSWORD"])
        send_email(
            env_vars["FROM_EMAIL"],
            env_vars["TO_EMAIL"],
            env_vars["SMTP_SERVER"],
            env_vars["EMAIL_PASSWORD"],
            "System Update Error",
            f"An error occurred during the update process:\n\n{str(e)}",
            logger
        )
