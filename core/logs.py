"""
File logging setup (hydra.log in the program folder).

Network/cover failures and unexpected errors are recorded for diagnostics
without cluttering the interface.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from core.paths import APP_DIR

LOG_FILE = APP_DIR / "hydra.log"
_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return

    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    _configured = True
