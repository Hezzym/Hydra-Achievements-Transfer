"""
Runs a batch of games (fetch + transfer) without blocking the UI.

Encapsulates the worker and the modal progress dialog, so the main window
only has to start the batch and react to its signals.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from core.constants import APP_NAME
from ui.progress_dialog import ProgressDialog
from ui.workers import BatchFetchAndSaveAchievementsWorker

PREVIEW_LIMIT = 15  # max games listed in the preview dialog


class BatchRunner(QObject):
    progress = Signal(int, int, str, str)  # current, total, label, phase
    no_achievements = Signal(str)  # appid without achievements
    pending = Signal(list)  # appids that failed/skipped (for a resume)
    completed = Signal(int, int, list, bool)  # saved, failed, failures, canceled

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: BatchFetchAndSaveAchievementsWorker | None = None
        self._dialog: ProgressDialog | None = None

    def start(
        self,
        items: list[tuple[str, str]],
        api_key: str,
        steam_id: str,
        create_name_file: bool,
        owner,
        cache_ttl_seconds: int = 0,
    ) -> None:
        self._dialog = ProgressDialog(parent=owner)
        self._worker = BatchFetchAndSaveAchievementsWorker(
            items,
            api_key,
            steam_id,
            create_name_file,
            cache_ttl_seconds=cache_ttl_seconds,
            parent=owner,
        )

        # The modal dialog blocks the UI and asks the worker to cancel.
        self._dialog.canceled.connect(self._worker.cancel)
        self._worker.progress.connect(self._dialog.set_progress)
        self._worker.progress.connect(self.progress)
        self._worker.no_achievements.connect(self.no_achievements)
        self._worker.pending.connect(self.pending)
        self._worker.preview_ready.connect(self._on_preview_ready)
        self._worker.completed.connect(self._on_completed)
        self._worker.finished.connect(self._on_worker_finished)

        self._dialog.show()
        self._worker.start()

    def _on_preview_ready(self, diffs: list) -> None:
        """Shows the change summary and lets the user confirm or cancel."""
        worker = self._worker
        if worker is None:
            return
        proceed = True
        if any(gained or lost or is_new for _label, gained, lost, is_new in diffs):
            proceed = self._confirm_changes(diffs)
        worker.resolve_preview(proceed)

    def _confirm_changes(self, diffs: list) -> bool:
        lines = []
        for label, gained, lost, is_new in diffs[:PREVIEW_LIMIT]:
            if is_new:
                lines.append(f"- {label}: new file ({gained} unlocked)")
            elif gained or lost:
                lines.append(f"- {label}: +{gained} unlocked / -{lost} relocked")
            else:
                lines.append(f"- {label}: no changes")
        hidden = len(diffs) - len(lines)
        if hidden > 0:
            lines.append(f"... and {hidden} more.")

        total_gained = sum(item[1] for item in diffs)
        total_lost = sum(item[2] for item in diffs)
        message = (
            f"This will write achievements for {len(diffs)} game(s):\n\n"
            + "\n".join(lines)
            + f"\n\nTotal: +{total_gained} unlocked, -{total_lost} relocked.\n\n"
            "Do you want to continue?"
        )

        parent = self._dialog if self._dialog is not None else self.parent()
        answer = QMessageBox.question(
            parent,
            APP_NAME,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return answer == QMessageBox.Yes

    def _on_worker_finished(self) -> None:
        # Drop the reference first (the C++ object is about to be deleted),
        # so cancel()/wait() never touch a deleted object.
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def _on_completed(self, saved: int, failed: int, failures: list, canceled: bool) -> None:
        self._close_dialog()
        self.completed.emit(saved, failed, failures, canceled)

    def _close_dialog(self) -> None:
        if self._dialog is not None:
            self._dialog.finish()
            self._dialog = None

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def close(self) -> None:
        self._close_dialog()
        self.cancel()

    def wait(self, timeout_ms: int) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(timeout_ms)
