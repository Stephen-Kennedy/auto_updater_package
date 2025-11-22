import subprocess
import os
from .email_utils import send_email
from .env_utils import load_env_variables
from .logging_utils import setup_logger

LOG_FILE = "/var/log/pyupdate.log"
ENV_FILE = "/etc/postfix/env_variables.env"

def run_command(command, logger, sudo=False, env=None):
    """Run a shell command and log its output."""
    if sudo:
        command.insert(0, "sudo")
    try:
        logger.info(f"Executing command: {' '.join(command)}")
        # Merge environment variables if provided
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)
        
        result = subprocess.run(
            command, 
            check=True, 
            text=True, 
            capture_output=True,
            env=cmd_env
        )
        logger.info(f"Command succeeded: {' '.join(command)}\nOutput:\n{result.stdout}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(command)}\nError:\n{e.stderr}")
        raise

def check_reboot_required():
    """Check if system reboot is required after updates."""
    reboot_required_file = '/var/run/reboot-required'
    return os.path.exists(reboot_required_file)

def get_reboot_reason():
    """Get list of packages that require reboot."""
    reboot_pkgs_file = '/var/run/reboot-required.pkgs'
    if os.path.exists(reboot_pkgs_file):
        try:
            with open(reboot_pkgs_file, 'r') as f:
                return f.read().strip()
        except Exception:
            return "Unable to determine specific packages"
    return "Reboot required (reason unknown)"

def execute_reboot(logger):
    """Execute system reboot."""
    try:
        logger.warning("Initiating system reboot...")
        subprocess.run(['sudo', 'reboot'], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to execute reboot: {e}")
        raise

def auto_update():
    """Perform system updates and clean-up."""
    logger = setup_logger("update_script", LOG_FILE)
    print("Starting system update...")
    logger.info("Starting system update...")

    # Load environment variables for email notifications
    env_vars = load_env_variables(ENV_FILE, required_vars=["FROM_EMAIL", "TO_EMAIL", "SMTP_SERVER", "EMAIL_PASSWORD"])

    # Set non-interactive environment for apt commands
    apt_env = {
        'DEBIAN_FRONTEND': 'noninteractive'
    }

    # Commands to run with Dpkg options to avoid interactive prompts
    commands = [
        ['apt-get', '-y', 'update'],
        ['apt-get', '-y', 'upgrade'],
        ['apt-get', '-y', 'dist-upgrade', 
         '-o', 'Dpkg::Options::=--force-confdef',
         '-o', 'Dpkg::Options::=--force-confold'],
        ['apt-get', '-y', 'autoremove'],
        ['apt-get', '-y', 'autoclean']
    ]

    updates_performed = []
    errors_encountered = []
    
    for command in commands:
        try:
            print(f"Running: {' '.join(command)}")
            result = run_command(command, logger, sudo=True, env=apt_env)
            if result:
                logger.debug(f"Command output:\n{result}")
                updates_performed.append(' '.join(command))
            else:
                logger.debug(f"No output for command: {' '.join(command)}")
        except Exception as e:
            error_msg = f"Failed to run {' '.join(command)}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            print(error_msg)
            errors_encountered.append(error_msg)

    # Check if reboot is required
    reboot_required = check_reboot_required()
    reboot_message = ""
    
    if reboot_required:
        reboot_reason = get_reboot_reason()
        reboot_message = f"\n\n⚠️  REBOOT REQUIRED ⚠️\n\nPackages requiring reboot:\n{reboot_reason}\n\nSystem will reboot automatically."
        logger.warning(f"Reboot required. Packages: {reboot_reason}")
        print(reboot_message)

    # Summarize results
    if updates_performed and not errors_encountered:
        subject = "System Update Completed Successfully"
        body = "The following updates were performed:\n\n" + '\n'.join(updates_performed) + reboot_message
    elif updates_performed and errors_encountered:
        subject = "System Update Completed with Errors"
        body = (
            "The following updates were performed:\n\n" + 
            '\n'.join(updates_performed) + 
            "\n\nHowever, the following errors were encountered:\n\n" + 
            '\n'.join(errors_encountered) +
            reboot_message
        )
    elif not updates_performed and errors_encountered:
        subject = "System Update Failed"
        body = "The update process failed with the following errors:\n\n" + '\n'.join(errors_encountered)
    else:
        subject = "System Update - No Changes"
        body = "No updates were performed, and no errors were encountered."

    print(body)
    logger.info("Update summary:\n" + body)

    # Send email summary
    try:
        send_email(
            env_vars["FROM_EMAIL"],
            env_vars["TO_EMAIL"],
            env_vars["SMTP_SERVER"],
            env_vars["EMAIL_PASSWORD"],
            subject,
            body,
            logger
        )
        logger.info("Email notification sent successfully.")
    except Exception as email_error:
        logger.error(f"Failed to send email notification: {str(email_error)}")

    # Execute reboot if required
    if reboot_required:
        logger.info("Waiting 30 seconds before reboot to allow email delivery...")
        print("Waiting 30 seconds before reboot...")
        import time
        time.sleep(30)  # Give email time to send
        execute_reboot(logger)

def main():
    """Main function to execute the auto-update logic."""
    try:
        auto_update()
    except Exception as e:
        error_msg = f"An unexpected error occurred during the update process:\n\n{str(e)}"
        logger = setup_logger("update_script", LOG_FILE)
        logger.critical(error_msg, exc_info=True)
        print(error_msg)

        # Attempt to send an email notification about the failure
        try:
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
        except Exception as email_error:
            logger.error(f"Failed to send critical error email notification: {str(email_error)}")

if __name__ == "__main__":
    main()
