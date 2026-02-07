"""
SwiftShot Logging Module
Provides a rotating file logger writing to %APPDATA%/SwiftShot/swiftshot.log.
All modules should import `log` and use log.info(), log.warning(), log.error().
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler


def _get_log_dir():
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    log_dir = os.path.join(base, "SwiftShot")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def setup_logger():
    """Create and return the app-wide logger."""
    logger = logging.getLogger("swiftshot")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # File handler: rotating, 2 MB max, keep 3 backups
    log_path = os.path.join(_get_log_dir(), "swiftshot.log")
    try:
        fh = RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=3,
            encoding='utf-8'
        )
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-7s] %(name)s.%(funcName)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass

    # Console handler (only in dev mode, not frozen)
    if not getattr(sys, 'frozen', False):
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter(
            "[%(levelname)-7s] %(funcName)s: %(message)s"
        ))
        logger.addHandler(ch)

    return logger


# Module-level logger instance - import this everywhere
log = setup_logger()
