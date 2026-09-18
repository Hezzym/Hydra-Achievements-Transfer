"""
Hydra Achievement Transfer
--------------------------
Application entry point.

Usage:
    python main.py

To build the executable (.exe):
    python -m PyInstaller --onefile --windowed --name HydraAchievementTransfer ^
        --add-data "assets;assets" --icon assets/icon.ico main.py
"""
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.constants import APP_NAME
from core.logs import backup_previous_logs, setup_logging
from core.paths import get_resource_path
from ui.main_window import MainWindow

ICON_PATH = get_resource_path("assets/icon.png")


def main() -> None:
    backup_previous_logs()
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
