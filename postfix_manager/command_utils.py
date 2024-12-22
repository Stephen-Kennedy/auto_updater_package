# command_utils
import subprocess


def run_command(command, logger=None, sudo=False, timeout=600):
    """Run shell command securely and log output."""
    try:
        if sudo:
            command.insert(0, "sudo")
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        if logger:
            logger.info(f"Command executed successfully: {' '.join(command)}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        if logger:
            logger.error(f"Command timed out: {' '.join(command)}")
        raise
    except subprocess.CalledProcessError as e:
        if logger:
            logger.error(f"Command failed: {' '.join(command)} | Error: {e.stderr.strip()}")
        raise
