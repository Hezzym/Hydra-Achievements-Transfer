"""
File logging setup (``logs/_hydra-at.log`` in the program folder).

Network/cover failures and unexpected errors are recorded for diagnostics
without cluttering the interface.

On every startup the logs left by the previous session are moved to
``<name>.bak`` (dropping the leading ``_`` and replacing an older backup) and
the originals are removed, so each run starts with a clean pair of logs.
"""
from __future__ import annotations

import logging
import os

from core import appid_log
from core.paths import LOGS_DIR

LOG_FILE = LOGS_DIR / "_hydra-at.log"
BACKUP_SUFFIX = ".bak"
_configured = False


def _backup_name(name: str) -> str:
    """``_hydra-at.log`` -> ``hydra-at.log.bak`` (only the active logs keep ``_``)."""
    return name.removeprefix("_") + BACKUP_SUFFIX


def backup_previous_logs() -> None:
    """Move the previous session's logs to ``<name>.bak`` (originals removed).

    A backup that fails must never prevent the program from starting.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    for path in (LOG_FILE, appid_log.LOG_FILE):
        if not path.exists():
            continue
        try:
            os.replace(path, path.with_name(_backup_name(path.name)))
        except OSError:
            pass


def setup_logging() -> None:
    global _configured
    if _configured:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    _configured = True
