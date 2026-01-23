"""Logging configuration for Acme Dental AI Agent."""

import logging
import os
import sys


def setup_logging(level: str | None = None) -> logging.Logger:
    """Set up logging configuration for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO,
               or uses LOG_LEVEL environment variable.

    Returns:
        The root logger for the application.
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Configure root logger for our app
    logger = logging.getLogger("acme_dental")
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.addHandler(console_handler)

    # Prevent duplicate logs
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: The module name (e.g., "calendly", "agent")

    Returns:
        A configured logger instance.
    """
    return logging.getLogger(f"acme_dental.{name}")
