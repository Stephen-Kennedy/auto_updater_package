from .email_utils import send_email
from .env_utils import load_env_variables
from .logging_utils import setup_logger
from .command_utils import run_command

LOG_FILE = "/var/log/pyupdate.log"
ENV_FILE = "/etc/postfix/env_variables.env"

def auto_update():
    """Perform system updates and clean-up."""
    logger = setup_logger("update_script", LOG_FILE)
    print("Starting system update...")  # CLI feedback

    logger.info("Starting system update...")
    env_vars = load_env_variables(ENV_FILE, required_vars=["FROM_EMAIL", "TO_EMAIL", "SMTP_SERVER", "EMAIL_PASSWORD"])

    commands = [
        ['apt-get', '-y', 'update'],
        ['apt-get', '-y', 'upgrade'],
        ['apt-get', '-y', 'autoremove'],
        ['apt-get', '-y', 'autoclean']
    ]

    updates_performed = []
    errors_encountered = []
    
    for command in commands:
        try:
            print(f"Running: {' '.join(command)}")  # CLI feedback
            result = run_command(command, logger, sudo=True)
            if result:
                updates_performed.append(' '.join(command))
        except Exception as e:
            error_msg = f"Failed to run {' '.join(command)}: {str(e)}"
            logger.error(error_msg)
            print(error_msg)  # CLI feedback
            errors_encountered.append(error_msg)

    if updates_performed and not errors_encountered:
        subject = "System Update Completed Successfully"
        body = "The following updates were performed:\n\n" + '\n'.join(updates_performed)
    elif updates_performed and errors_encountered:
        subject = "System Update Completed with Errors"
        body = (
            "The following updates were performed:\n\n" + 
            '\n'.join(updates_performed) + 
            "\n\nHowever, the following errors were encountered:\n\n" + 
            '\n'.join(errors_encountered)
        )
    elif not updates_performed and errors_encountered:
        subject = "System Update Failed"
        body = "The update process failed with the following errors:\n\n" + '\n'.join(errors_encountered)
    else:
        subject = "System Update No Changes"
        body = "No updates were performed, and no errors were encountered."

    print(body)  # CLI feedback
    logger.info("Update summary:\n" + body)

    # Send email summary
    send_email(
        env_vars["FROM_EMAIL"],
        env_vars["TO_EMAIL"],
        env_vars["SMTP_SERVER"],
        env_vars["EMAIL_PASSWORD"],
        subject,
        body,
        logger
    )

def main():
    """Main function to execute the auto-update logic."""
    try:
        auto_update()
    except Exception as e:
        error_msg = f"An unexpected error occurred during the update process:\n\n{str(e)}"
        logger = setup_logger("update_script", LOG_FILE)
        logger.critical(error_msg, exc_info=True)
        print(error_msg)  # CLI feedback
        
        env_vars = load_env_variables(ENV_FILE, required_vars=["FROM_EMAIL", "TO_EMAIL", "SMTP_SERVER", "EMAIL_PASSWORD"])
        send_email(
            env_vars["FROM_EMAIL"],
            env_vars["TO_EMAIL"],
            env_vars["SMTP_SERVER"],
            env_vars["EMAIL_PASSWORD"],
            "System Update Critical Error",
            error_msg,
            logger
        )

if __name__ == "__main__":
    main()

