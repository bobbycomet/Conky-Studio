"""
Griffin Dark -- the only theme Conky Studio has, by design (a Steam-like
creative tool, not a productivity suite that needs to match every OS
light/dark preference). One considered palette beats a toggle nobody
asked for.

Two accents rather than the generic "near-black + one neon colour" look:
a cool teal for primary interaction (it's also nodes.registry's default
visual-node fill colour, so the same teal you see on a slider or a
selected tab is the teal a freshly-dropped Arc Gauge node draws with),
and a warm heraldic gold for secondary emphasis and the Store/brand
accent -- a nod to what a griffin actually looks like on a coat of arms.

QSS has no real equivalent of CSS custom properties, so PALETTE is the
single source of truth in Python instead; build_qss() formats it into
one stylesheet string applied once at app startup.
"""
from __future__ import annotations

PALETTE = {
    "void": "#0b0d10",
    "bg": "#14171c",
    "raised": "#1b1f26",
    "raised_hover": "#20242c",
    "inset": "#0f1216",
    "border": "#2a2f38",
    "border_strong": "#3a4048",
    "text": "#e9ebee",
    "text_secondary": "#9aa2ad",
    "text_muted": "#5c636d",
    "teal": "#4fd1c5",
    "teal_dim": "#2d7d74",
    "teal_soft": "#1c3a37",
    "gold": "#c9a227",
    "gold_dim": "#8a701f",
    "danger": "#e0655f",
    "danger_dim": "#7a2f2c",
    "success": "#4caf7d",
}

FONT_UI = '"Inter", "Segoe UI", "Cantarell", "Ubuntu", sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", monospace'


def build_qss() -> str:
    p = PALETTE
    return f'''
QWidget {{
    background-color: {p["bg"]};
    color: {p["text"]};
    font-family: {FONT_UI};
    font-size: 13px;
    selection-background-color: {p["teal_soft"]};
    selection-color: {p["text"]};
}}

QMainWindow, QDialog {{
    background-color: {p["void"]};
}}

/* ---- Tabs (Manager / Studio / Store) ------------------------------- */
QTabWidget::pane {{
    border: 1px solid {p["border"]};
    background: {p["bg"]};
    top: -1px;
}}
QTabBar::tab {{
    background: {p["void"]};
    color: {p["text_secondary"]};
    padding: 9px 22px;
    border: 1px solid {p["border"]};
    border-bottom: none;
    margin-right: 2px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
QTabBar::tab:selected {{
    background: {p["bg"]};
    color: {p["text"]};
    border-top: 2px solid {p["teal"]};
    padding-top: 8px;
}}
QTabBar::tab:hover:!selected {{
    color: {p["text"]};
    background: {p["raised"]};
}}

/* ---- Panels / group boxes ------------------------------------------- */
QGroupBox {{
    border: 1px solid {p["border"]};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
    color: {p["text_secondary"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {p["text_secondary"]};
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.6px;
}}

/* ---- Buttons ---------------------------------------------------------*/
QPushButton {{
    background: {p["raised"]};
    border: 1px solid {p["border"]};
    border-radius: 5px;
    padding: 7px 16px;
    color: {p["text"]};
    font-weight: 600;
}}
QPushButton:hover {{
    background: {p["raised_hover"]};
    border-color: {p["border_strong"]};
}}
QPushButton:pressed {{
    background: {p["void"]};
}}
QPushButton:disabled {{
    color: {p["text_muted"]};
    border-color: {p["border"]};
}}
QPushButton#primary {{
    background: {p["teal_dim"]};
    border-color: {p["teal"]};
    color: {p["text"]};
}}
QPushButton#primary:hover {{
    background: {p["teal"]};
    color: {p["void"]};
}}
QPushButton#danger {{
    border-color: {p["danger_dim"]};
    color: {p["danger"]};
}}
QPushButton#danger:hover {{
    background: {p["danger_dim"]};
    color: {p["text"]};
}}

/* ---- Inputs ----------------------------------------------------------*/
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background: {p["inset"]};
    border: 1px solid {p["border"]};
    border-radius: 4px;
    padding: 5px 8px;
    color: {p["text"]};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {p["teal"]};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p["raised"]};
    border: 1px solid {p["border_strong"]};
    selection-background-color: {p["teal_soft"]};
    color: {p["text"]};
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: {p["border"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {p["teal"]};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {p["teal_dim"]};
    border-radius: 2px;
}}

QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {p["border_strong"]};
    border-radius: 3px;
    background: {p["inset"]};
}}
QCheckBox::indicator:checked {{
    background: {p["teal"]};
    border-color: {p["teal"]};
}}

/* ---- Lists / trees -----------------------------------------------------*/
QListWidget, QTreeWidget, QListView {{
    background: {p["inset"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 7px 8px;
    border-radius: 4px;
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {p["teal_soft"]};
    color: {p["text"]};
}}
QListWidget::item:hover:!selected {{
    background: {p["raised_hover"]};
}}

/* ---- Scrollbars ----------------------------------------------------- */
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p["border_strong"]};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {p["text_muted"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p["border_strong"]};
    border-radius: 4px;
    min-width: 24px;
}}

/* ---- Menus / toolbars ------------------------------------------------ */
QMenuBar {{ background: {p["void"]}; border-bottom: 1px solid {p["border"]}; }}
QMenuBar::item:selected {{ background: {p["raised"]}; }}
QMenu {{ background: {p["raised"]}; border: 1px solid {p["border_strong"]}; }}
QMenu::item:selected {{ background: {p["teal_soft"]}; }}
QToolBar {{ background: {p["void"]}; border: none; spacing: 6px; padding: 4px; }}
QStatusBar {{ background: {p["void"]}; color: {p["text_secondary"]}; border-top: 1px solid {p["border"]}; }}

QSplitter::handle {{ background: {p["border"]}; }}
QSplitter::handle:hover {{ background: {p["teal_dim"]}; }}

QLabel[role="heading"] {{
    font-size: 16px;
    font-weight: 700;
    color: {p["text"]};
}}
QLabel[role="caption"] {{
    color: {p["text_muted"]};
    font-size: 11px;
}}
QLabel[role="mono"] {{
    font-family: {FONT_MONO};
    color: {p["text_secondary"]};
}}

QToolTip {{
    background: {p["raised"]};
    color: {p["text"]};
    border: 1px solid {p["border_strong"]};
    padding: 5px 8px;
}}
'''
