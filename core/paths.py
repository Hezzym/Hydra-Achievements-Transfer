"""
Path resolution helpers.

Two distinct concepts live here:

- ``get_app_dir()`` returns the program folder (that of ``main.py`` in source,
  or of the packaged ``.exe``). All writable data (``config.json``, ``cache/``,
  ``gse_backup.zip``) lives relative to this folder, so the program works no
  matter which directory it was launched from.

- ``get_resource_path()`` resolves read-only resources bundled into the
  executable via PyInstaller's ``--add-data`` (icons, images). When frozen with
  ``--onefile``, these are extracted to a temporary folder at runtime
  (``sys._MEIPASS``), which is NOT the same as the folder holding the ``.exe``.
"""
from __future__ import annotations

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """Program folder: that of main.py (source) or of the .exe (packaged).

    Use this for writable/user data: config, cache, backups.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Path to a bundled, read-only resource (icons, images added via --add-data).

    Use this for assets only, never for writable data.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent
    return base_path / relative_path


APP_DIR = get_app_dir()
