"""Shared logger setup for the Sports Prediction Bot.

All modules import `logger` from this module for consistent logging.

Log files:
- logs/app.log       — main rotating log (INFO and above, keeps 14 days)
- logs/errors.log    — error-only log (ERROR and above)
"""

import logging
import logging.handlers
import os
from pathlib import Path

BASE_DIR = Path(r"C:/Users/DELL/Documents/SportsPredictionBot")
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "app.log"
ERROR_LOG_PATH = LOG_DIR / "errors.log"

os.makedirs(LOG_DIR, exist_ok=True)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(module)s.%(funcName)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# Main rotating file handler -- auto-deletes logs older than 14 days
rotating_handler = logging.handlers.TimedRotatingFileHandler(
    filename=str(LOG_PATH),
    when="D",
    interval=1,
    backupCount=14,
    encoding="utf-8",
)
rotating_handler.setLevel(logging.INFO)
rotating_handler.setFormatter(formatter)

# Error-only file handler
error_handler = logging.FileHandler(str(ERROR_LOG_PATH), encoding="utf-8")
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

# Console output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Root logger
logger = logging.getLogger("SportsBotLogger")
logger.setLevel(logging.INFO)
logger.addHandler(rotating_handler)
logger.addHandler(error_handler)
logger.addHandler(console_handler)


def log_exception(func):
    """Decorator that logs any exception raised within the decorated function."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            raise

    return wrapper
