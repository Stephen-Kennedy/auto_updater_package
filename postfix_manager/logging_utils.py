import logging
from logging.handlers import RotatingFileHandler


def setup_logger(name, log_file, level=logging.INFO, max_bytes=5 * 1024 * 1024, backup_count=3):
    """Set up a logger with rotation."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
