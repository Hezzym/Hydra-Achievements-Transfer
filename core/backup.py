"""
Backup and restore of the GSE Saves data folder.

- export_backup(): packs <APPDATA>/GSE Saves into gse_backup.zip, in the
  program folder (same folder as main.py / the .exe).
- import_backup(): validates gse_backup.zip, keeps the current folder as
  "GSE Saves.bak" (deleting a previous .bak, if any) and extracts the zip
  in place of the original folder.

The zip is created with the "GSE Saves" folder itself as its root, so
extracting it under %APPDATA% recreates the expected structure. Import
extracts to a temporary folder first and only swaps the data after
validating the content, so a corrupted zip never loses data.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from core.achievements import get_gse_saves_dir
from core.paths import get_app_dir

logger = logging.getLogger(__name__)

BACKUP_FILENAME = "gse_backup.zip"
BACKUP_SUFFIX = ".bak"


class BackupError(Exception):
    """Error while exporting or importing the GSE Saves folder backup."""


def get_backup_path() -> Path:
    return get_app_dir() / BACKUP_FILENAME


def backup_exists() -> bool:
    return get_backup_path().exists()


def _resolve_gse_dir() -> Path:
    try:
        return get_gse_saves_dir()
    except RuntimeError as exc:
        raise BackupError(str(exc)) from exc


def export_backup() -> Path:
    """
    Packs the current GSE Saves folder into gse_backup.zip (in the program
    folder) and returns the path of the generated file.
    """
    source = _resolve_gse_dir()
    if not source.exists():
        raise BackupError(f"Folder not found: {source}")

    target = get_backup_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(source.rglob("*")):
                if file.is_file():
                    arcname = Path(source.name) / file.relative_to(source)
                    archive.write(file, arcname=str(arcname))
    except OSError as exc:
        logger.exception("Failed to create the backup")
        raise BackupError(f"Failed to create the backup: {exc}") from exc

    logger.info("Backup exported to %s", target)
    return target


def _validate_zip(archive: zipfile.ZipFile) -> None:
    if archive.testzip() is not None:
        raise BackupError("The backup file is corrupted.")

    for name in archive.namelist():
        parts = Path(name).parts
        is_absolute = Path(name).is_absolute() or (len(name) > 1 and name[1] == ":")
        if is_absolute or ".." in parts:
            raise BackupError("The backup file contains invalid paths.")


def import_backup() -> Path:
    """
    Replaces the current GSE Saves folder with the content of gse_backup.zip.

    The current folder is preserved as "GSE Saves.bak" (a previous .bak is
    removed). Returns the path of the restored folder.
    """
    backup_file = get_backup_path()
    if not backup_file.exists():
        raise BackupError(f"Backup file not found: {backup_file}")

    try:
        with zipfile.ZipFile(backup_file) as archive:
            _validate_zip(archive)
            names = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise BackupError("The backup file is not a valid .zip.") from exc

    if not names:
        raise BackupError("The backup file is empty.")

    gse_dir = _resolve_gse_dir()
    parent = gse_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="gse_import_", dir=str(parent)))
    try:
        with zipfile.ZipFile(backup_file) as archive:
            archive.extractall(tmp_dir)

        # The zip may have the "GSE Saves" folder as its root (export
        # format) or contain the files inside it directly.
        candidate = tmp_dir / gse_dir.name
        extracted_root = candidate if candidate.is_dir() else tmp_dir

        bak_dir = gse_dir.with_name(gse_dir.name + BACKUP_SUFFIX)
        if bak_dir.exists():
            shutil.rmtree(bak_dir)
        if gse_dir.exists():
            shutil.move(str(gse_dir), str(bak_dir))

        shutil.copytree(extracted_root, gse_dir)
    except OSError as exc:
        logger.exception("Failed to restore the backup")
        raise BackupError(f"Failed to restore the backup: {exc}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info("Backup restored to %s", gse_dir)
    return gse_dir
