# env_utils module 
import os


def load_env_variables(env_file, required_vars=None, logger=None):
    """Load environment variables from a file."""
    if not os.path.exists(env_file):
        raise FileNotFoundError(f"Environment file {env_file} not found.")

    env_vars = {}
    with open(env_file) as env:
        for line in env:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                env_vars[key] = value
            else:
                if logger:
                    logger.warning(f"Skipping invalid line in env file: {line.strip()}")

    if required_vars:
        for var in required_vars:
            if var not in env_vars or not env_vars[var]:
                raise ValueError(f"Missing required environment variable: {var}")

    if logger:
        logger.info(f"Environment variables loaded successfully from {env_file}")
    return env_vars

