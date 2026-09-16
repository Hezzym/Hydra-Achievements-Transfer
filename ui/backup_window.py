"""
Backup/restore window for the GSE Saves folder.

Opened by the "Backup" item in the menu bar. It follows the same dark
theme and the same feedback pattern (status + sound + popup) as the rest
of the application.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

from core import backup
from ui import sounds
from ui.theme import DARK_STYLESHEET

WINDOW_TITLE = "Backup Manager"


class BackupWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(WINDOW_TITLE)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setMinimumWidth(440)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        description = QLabel(
            "Export a backup of your GSE Saves folder as a .zip in the program "
            "folder, or restore a backup exported previously."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.button_export = QPushButton("Export Backup")
        self.button_export.clicked.connect(self._on_export_clicked)
        layout.addWidget(self.button_export)

        self.button_import = QPushButton("Import Backup")
        self.button_import.setProperty("role", "secondary")
        self.button_import.clicked.connect(self._on_import_clicked)
        layout.addWidget(self.button_import)

        self.status_label = QLabel("Ready.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    # ---------------------------------------------------------------- actions

    def _on_export_clicked(self) -> None:
        try:
            path = backup.export_backup()
        except backup.BackupError as exc:
            self._notify_error(str(exc))
            return

        message = f"Backup exported to: {path}"
        self._set_status(message)
        sounds.play_success()
        QMessageBox.information(self, WINDOW_TITLE, message)

    def _on_import_clicked(self) -> None:
        backup_path = backup.get_backup_path()
        if not backup.backup_exists():
            self._notify_error(f"No backup file found at: {backup_path}. Export one first.")
            return

        confirm = QMessageBox.question(
            self,
            WINDOW_TITLE,
            "This will replace your current GSE Saves folder. A copy of it "
            "will be saved as 'GSE Saves.bak'. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            path = backup.import_backup()
        except backup.BackupError as exc:
            self._notify_error(str(exc))
            return

        message = f"Backup restored to: {path}"
        self._set_status(message)
        sounds.play_success()
        QMessageBox.information(self, WINDOW_TITLE, message)

    # -------------------------------------------------------------- helpers

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("role", "status_error" if error else "status_success")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _notify_error(self, message: str) -> None:
        self._set_status(message, error=True)
        sounds.play_error()
        QMessageBox.warning(self, WINDOW_TITLE, message)

