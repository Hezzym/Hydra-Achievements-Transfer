"""
Shared constants and pure helpers for the UI layer.

Kept free of widget code so the main window and its mixins can import them
without creating import cycles.
"""
from __future__ import annotations

import re

from core.constants import APP_NAME

APP_TITLE = APP_NAME
PAGE_SIZE = 50
SEARCH_DEBOUNCE_MS = 200
DEFAULT_WINDOW_WIDTH = 1150
DEFAULT_WINDOW_HEIGHT = 760


def parse_appids(text: str) -> list[str]:
    """Splits an AppID list typed as '111, 222 333' into unique items."""
    items = re.split(r"[,\s;]+", text.strip())
    appids: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in appids:
            appids.append(item)
    return appids
