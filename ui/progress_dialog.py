"""
Modal progress dialog shown while a batch of achievements is being fetched
and saved.

It is application-modal, so the interface stays locked while the batch
runs, but it offers a "Cancel" button (and Esc) to stop the process early.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

from ui.theme import DARK_STYLESHEET

WINDOW_TITLE = "Fetching achievements"


class ProgressDialog(QDialog):
    canceled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._finished = False
        self._canceled = False

        self.setWindowTitle(WINDOW_TITLE)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setWindowModality(Qt.ApplicationModal)
        self.setModal(True)
        self.setFixedWidth(420)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.label = QLabel("Preparing...")
        self.label.setWordWrap(True)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(True)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setProperty("role", "hint")

        self.button_cancel = QPushButton("Cancel")
        self.button_cancel.setProperty("role", "secondary")
        self.button_cancel.clicked.connect(self.request_cancel)

        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addWidget(self.detail)
        layout.addWidget(self.button_cancel)

    def set_progress(self, current: int, total: int, label: str, phase: str = "fetch") -> None:
        self.bar.setRange(0, total)
        self.bar.setValue(current)
        verb = "Saving" if phase == "save" else "Fetching"
        self.label.setText(f"{verb} {current} of {total}...")
        self.detail.setText(label)

    def request_cancel(self) -> None:
        if self._canceled:
            return
        self._canceled = True
        self.button_cancel.setEnabled(False)
        self.button_cancel.setText("Canceling...")
        self.canceled.emit()

    def finish(self) -> None:
        self._finished = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._finished:
            super().closeEvent(event)
        else:
            # Fechar pelo X (ou Alt+F4) cancela o processo em vez de fechar.
            self.request_cancel()
            event.ignore()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.key() == Qt.Key_Escape:
            self.request_cancel()
            return
        super().keyPressEvent(event)
