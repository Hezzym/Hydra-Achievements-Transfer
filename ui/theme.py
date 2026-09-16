"""
Dark theme (QSS) used across the whole application.
Palette inspired by modern launchers (blue-gray tones + purple/blue accent).
"""

COLOR_BG = "#141414"
COLOR_BG_ELEVATED = "#1e1e1e"
COLOR_BG_INPUT = "#262626"
COLOR_BORDER = "#333333"
COLOR_TEXT = "#e6e6e6"
COLOR_TEXT_MUTED = "#9a9a9a"
COLOR_ACCENT = "#7c5cff"
COLOR_ACCENT_HOVER = "#8f72ff"
COLOR_SUCCESS = "#3ddc84"
COLOR_ERROR = "#ff5c5c"

DARK_STYLESHEET = f"""
QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {COLOR_BG};
}}

QLabel {{
    background: transparent;
}}

QLabel[role="link"] {{
    color: {COLOR_ACCENT};
    text-decoration: underline;
}}

QLabel[role="link"]:hover {{
    color: {COLOR_ACCENT_HOVER};
}}

QLabel[role="help"] {{
    color: {COLOR_ACCENT};
    font-weight: 700;
    font-size: 14px;
}}

QLabel[role="help"]:hover {{
    color: {COLOR_ACCENT_HOVER};
}}

QLabel[role="status_success"] {{
    color: {COLOR_SUCCESS};
}}

QLabel[role="status_error"] {{
    color: {COLOR_ERROR};
}}

QLabel[role="section_title"] {{
    font-weight: 600;
}}

QLabel[role="separator"] {{
    color: {COLOR_BORDER};
    font-weight: 700;
}}

#SelectedPanel {{
    background-color: {COLOR_BG_ELEVATED};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}

#SelectedScroll,
#SelectedScroll > QWidget,
#SelectedChips {{
    background: transparent;
}}

#SelectedChip {{
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
}}

QLabel[role="chip"] {{
    color: {COLOR_TEXT};
}}

QToolButton#ChipRemove {{
    background: transparent;
    border: none;
    color: {COLOR_TEXT_MUTED};
    font-weight: 700;
    padding: 0px 4px;
}}

QToolButton#ChipRemove:hover {{
    color: {COLOR_ERROR};
}}

QLabel[role="about_title"] {{
    font-size: 17px;
    font-weight: 700;
}}

QLabel[role="hint"] {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
}}

QProgressBar {{
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    text-align: center;
    color: {COLOR_TEXT};
    min-height: 18px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_ACCENT};
    border-radius: 5px;
}}

QLineEdit, QComboBox {{
    background-color: {COLOR_BG_INPUT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    color: {COLOR_TEXT};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {COLOR_ACCENT};
}}

QPushButton {{
    background-color: {COLOR_ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {COLOR_ACCENT_HOVER};
}}

QPushButton:disabled {{
    background-color: {COLOR_BORDER};
    color: {COLOR_TEXT_MUTED};
}}

QPushButton[role="secondary"] {{
    background-color: {COLOR_BG_ELEVATED};
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT};
}}

QPushButton[role="secondary"]:hover {{
    border: 1px solid {COLOR_ACCENT};
}}

QScrollArea {{
    border: none;
}}

QCheckBox {{
    spacing: 6px;
}}

QMenuBar {{
    background-color: {COLOR_BG_ELEVATED};
}}

QMenuBar::item:selected {{
    background-color: {COLOR_ACCENT};
}}

QMenu {{
    background-color: {COLOR_BG_ELEVATED};
    border: 1px solid {COLOR_BORDER};
}}

QMenu::item:selected {{
    background-color: {COLOR_ACCENT};
}}

QScrollBar:vertical {{
    background: {COLOR_BG};
    width: 10px;
}}

QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 5px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLOR_ACCENT};
}}

QScrollBar:horizontal {{
    background: {COLOR_BG};
    height: 10px;
}}

QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER};
    border-radius: 5px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLOR_ACCENT};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
"""
