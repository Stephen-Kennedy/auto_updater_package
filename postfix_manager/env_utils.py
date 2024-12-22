import os


def load_env_variables(env_file, required_vars=None):
    """Load environment variables from a file."""
    if not os.path.exists(env_file):
        raise FileNotFoundError(f"Environment file {env_file} not found.")
    with open(env_file) as env:
        env_vars = dict(line.strip().split("=", 1) for line in env if "=" in line)
    
    if required_vars:
        for var in required_vars:
            if var not in env_vars or not env_vars[var]:
                raise ValueError(f"Missing required environment variable: {var}")
    
    return env_vars
