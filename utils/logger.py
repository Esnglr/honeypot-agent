import logging
import logging.config
import os
import sys
from pathlib import Path
from config.settings import LOGGING_CONFIG_FILE

def setup_logging():
    if os.path.exists(LOGGING_CONFIG_FILE):
        logging.config.fileConfig(LOGGING_CONFIG_FILE)
    else:
        # fallback to basic config with console and optional file logging
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        logging.getLogger(__name__).warning(
            f"Logging config file {LOGGING_CONFIG_FILE} not found. Using basicConfig."
        )

# Call setup on import
setup_logging()

def get_logger(name: str, level=logging.DEBUG, log_to_file=False, log_dir="logs"):
    """
    Returns a logger instance.
    If log_to_file=True, adds a FileHandler dynamically to the logger.

    Note: File handlers added dynamically are *in addition* to config file handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if log_to_file:
        # Check if file handler already exists
        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(Path(log_dir) / f"{name}.log")
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger