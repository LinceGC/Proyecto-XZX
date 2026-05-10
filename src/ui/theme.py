# -*- coding: utf-8 -*-
"""
src/ui/theme.py  —  Spryta Design System (PySide6)

Unico archivo de diseno. Todo el color, espaciado, tipografia y
stylesheet global viven aqui. Para cambiar colores, edita theme_dark.py.

El resto del proyecto usa simplemente:
    from ui import theme
    theme.BG_BASE
    theme.get_stylesheet()
    app.setPalette(theme.get_palette())
"""

from PySide6.QtGui  import QFont, QColor, QPalette
from PySide6.QtCore import Qt

from ui import theme_dark as _dark



# ============================================================
# SECCION 1: CONSTANTES DE COLOR
# Para cambiar colores, edita theme_dark.py.
# ============================================================

BG_BASE    = _dark.BG_BASE
BG_SURFACE = _dark.BG_SURFACE
BG_RAISED  = _dark.BG_RAISED
BG_HOVER   = _dark.BG_HOVER

BORDER_DIM = _dark.BORDER_DIM
BORDER_MID = _dark.BORDER_MID
BORDER_HI  = _dark.BORDER_HI

ACCENT       = _dark.ACCENT
ACCENT_HOVER = _dark.ACCENT_HOVER
ACCENT_DIM   = _dark.ACCENT_DIM

TEXT_BRIGHT = _dark.TEXT_BRIGHT
TEXT_NORMAL = _dark.TEXT_NORMAL
TEXT_MUTED  = _dark.TEXT_MUTED

COLOR_SUCCESS = _dark.COLOR_SUCCESS
COLOR_WARNING = _dark.COLOR_WARNING
COLOR_DANGER  = _dark.COLOR_DANGER

SELECT_BG = _dark.SELECT_BG
SELECT_FG = _dark.SELECT_FG

# Aliases de acento para compatibilidad con codigo existente
ACCENT_BLUE   = _dark.ACCENT
ACCENT_GREEN  = _dark.ACCENT
ACCENT_YELLOW = _dark.COLOR_WARNING
ACCENT_RED    = _dark.COLOR_DANGER

DARK_BG        = _dark.BG_SURFACE
DARK_BG_LIGHT  = _dark.BG_RAISED
DARK_FG        = _dark.TEXT_BRIGHT
DARK_FG_DIM    = _dark.TEXT_MUTED
DARK_SELECT_BG = _dark.ACCENT_DIM
DARK_SELECT_FG = _dark.TEXT_BRIGHT




# ============================================================
# SECCION 3: ESPACIADO (grilla de 8px) — no cambia entre modos
# ============================================================

SP1 =  8
SP2 = 16
SP3 = 24
SP4 = 32
SP5 = 40

PADDING_SMALL  = SP1
PADDING_NORMAL = SP2
PADDING_LARGE  = SP3
PADDING_MAIN   = SP2
PADDING_PANEL  = SP2
PADDING_CARD   = SP2


# ============================================================
# SECCION 4: FORMA — no cambia entre modos
# ============================================================

RADIUS        =  8
RADIUS_SMALL  =  4
RADIUS_LARGE  = 12

# Estilo completo para botones con texto blanco y hover azul.
# Usar en lugar de setStyleSheet("color:#ffffff") para que
# el hover no quede bloqueado por el stylesheet del widget.
BTN_STYLE = (
    "QPushButton { color: #ffffff; }"
    f"QPushButton:hover {{ background-color: {ACCENT}; color: #ffffff; }}"
    f"QPushButton:pressed {{ background-color: {ACCENT_HOVER}; color: #ffffff; }}"
)

# Stylesheet directo para botones de peligro (Delete, etc.)
# Se aplica via setStyleSheet() para garantizar que el hover
# funcione sin depender del cascading del stylesheet global.
DANGER_STYLE = (
    f"QPushButton {{ color: {COLOR_DANGER}; background-color: transparent;"
    f" border: 1px solid {COLOR_DANGER}; border-radius: {RADIUS}px;"
    f" padding: 7px 16px; font-size: 10pt; min-height: 32px; }}"
    f"QPushButton:hover {{ background-color: #2a0a0e; color: {COLOR_DANGER}; }}"
    f"QPushButton:pressed {{ background-color: {COLOR_DANGER}; color: #ffffff; }}"
)


# ============================================================
# SECCION 5: DIMENSIONES DE VENTANA — no cambia entre modos
# ============================================================

MAIN_WINDOW_WIDTH  = 1080
MAIN_WINDOW_HEIGHT =  860
SIDEBAR_WIDTH      =  220
PANEL_SIDE_WIDTH   =  320
GALLERY_HEIGHT     =  598
CONTENT_MIN_WIDTH  =  600


# ============================================================
# SECCION 6: TIPOGRAFIA — no cambia entre modos
# ============================================================

_FONT_FAMILY      = "Segoe UI"
_FONT_FAMILY_MONO = "Consolas"

_FONT_SIZES = {
    "title"    : 15,
    "subtitle" : 12,
    "section"  : 10,
    "normal"   : 10,
    "small"    :  9,
    "tiny"     :  8,
}

def font(size_name: str = "normal", bold: bool = False, mono: bool = False) -> QFont:
    """Devuelve un QFont listo para usar en cualquier widget."""
    family = _FONT_FAMILY_MONO if mono else _FONT_FAMILY
    size   = _FONT_SIZES.get(size_name, 10)
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    f = QFont(family, size)
    f.setWeight(weight)
    return f

FONT_TITLE      = font("title",    bold=True)
FONT_SUBTITLE   = font("subtitle", bold=True)
FONT_SECTION    = font("section",  bold=True)
FONT_NORMAL     = font("normal")
FONT_SMALL      = font("small")
FONT_TINY       = font("tiny")
FONT_MONO       = font("normal",   mono=True)
FONT_MONO_LARGE = font("subtitle", bold=True, mono=True)


# ============================================================
# SECCION 7: get_stylesheet()
# Genera el QSS completo con los colores del tema oscuro.
# ============================================================

def get_stylesheet() -> str:
    """
    Devuelve el stylesheet QSS completo de Spryta (modo oscuro).
    Uso:
        app.setStyleSheet(theme.get_stylesheet())
    """
    bg        = BG_BASE
    surface   = BG_SURFACE
    raised    = BG_RAISED
    hover     = BG_HOVER
    border    = BORDER_MID
    border_hi = BORDER_HI
    fg        = TEXT_BRIGHT
    fg_dim    = TEXT_MUTED
    sel_bg    = ACCENT_DIM
    sel_fg    = SELECT_FG
    accent    = ACCENT
    accent_hv = ACCENT_HOVER
    danger    = COLOR_DANGER
    r         = RADIUS
    r_sm      = RADIUS_SMALL
    r_lg      = RADIUS_LARGE
    sp1       = SP1
    sp2       = SP2
    danger_hover_bg = "#2a0a0e"

    return f"""

/* BASE ───────────────────────────────────────────────────── */

QMainWindow, QWidget {{
    background-color: {bg};
    color: {fg};
    font-family: "Segoe UI";
    font-size: 10pt;
    border: none;
    outline: none;
}}

/* SIDEBAR ────────────────────────────────────────────────── */

QWidget#Sidebar {{
    background-color: {surface};
    border-right: 1px solid {border};
}}

/* HEADER ─────────────────────────────────────────────────── */

QWidget#Header {{
    background-color: {surface};
    border-bottom: 1px solid {border};
}}

/* LABELS ─────────────────────────────────────────────────── */

QLabel {{
    background-color: transparent;
    color: {fg};
    font-size: 10pt;
}}

QLabel[role="title"]    {{ color: {fg};     font-size: 15pt; font-weight: bold; }}
QLabel[role="subtitle"] {{ color: {fg};     font-size: 12pt; font-weight: bold; }}
QLabel[role="section"]  {{ color: {accent}; font-size: 10pt; font-weight: bold; }}
QLabel[role="muted"]    {{ color: {fg_dim}; font-size: 9pt;  }}
QLabel[role="accent"]   {{ color: {accent}; font-size: 10pt; }}
QLabel[role="danger"]   {{ color: {danger}; font-size: 10pt; }}

/* BOTONES ────────────────────────────────────────────────── */

QPushButton {{
    background-color: transparent;
    color: {accent};
    border: 1px solid {accent};
    border-radius: {r}px;
    padding: 7px 16px;
    font-size: 10pt;
    font-family: "Segoe UI";
    min-height: 32px;
}}
QPushButton:hover    {{ background-color: {accent}; color: #ffffff; }}
QPushButton:pressed  {{ background-color: {accent_hv}; border-color: {accent_hv}; }}
QPushButton:checked  {{ background-color: {accent}; color: #ffffff; border-color: {accent}; font-weight: bold; }}
QPushButton:disabled {{ color: {fg_dim}; border-color: {border}; }}

QPushButton[role="primary"] {{
    background-color: {accent};
    color: #ffffff;
    border: 1px solid {accent};
    border-radius: {r}px;
    padding: 7px 16px;
    font-size: 10pt;
    font-weight: bold;
    min-height: 32px;
}}
QPushButton[role="primary"]:hover    {{ background-color: {accent_hv}; border-color: {accent_hv}; }}
QPushButton[role="primary"]:pressed  {{ background-color: {accent}; }}
QPushButton[role="primary"]:disabled {{ background-color: {border}; border-color: {border}; color: {fg_dim}; }}
QPushButton[role="primary"][active="true"]  {{ background-color: {accent_hv}; border-color: {accent_hv}; font-weight: bold; }}
QPushButton[role="primary"][active="false"] {{ background-color: {accent}; border-color: {accent}; font-weight: normal; opacity: 0.75; }}

QPushButton[role="danger"] {{
    background-color: transparent;
    color: {danger};
    border: 1px solid {danger};
    border-radius: {r}px;
    padding: 7px 16px;
    font-size: 10pt;
    min-height: 32px;
}}
QPushButton[role="danger"]:hover   {{ background-color: {danger_hover_bg}; }}
QPushButton[role="danger"]:pressed {{ background-color: {danger}; color: #ffffff; }}

QPushButton[role="icon"] {{
    background-color: transparent;
    border: none;
    border-radius: {r}px;
    padding: {sp1}px;
    min-width: 32px; min-height: 32px;
    max-width: 32px; max-height: 32px;
}}
QPushButton[role="icon"]:hover {{ background-color: {hover}; }}

QPushButton[role="sidebar"] {{
    background-color: transparent;
    color: {fg_dim};
    border: none;
    border-radius: {r}px;
    padding: 10px {sp2}px;
    text-align: left;
    font-size: 10pt;
    min-height: 40px;
}}
QPushButton[role="sidebar"]:hover              {{ background-color: {hover}; color: {fg}; }}
QPushButton[role="sidebar"][active="true"]     {{ background-color: {sel_bg}; color: {accent}; font-weight: bold; }}

/* INPUTS ─────────────────────────────────────────────────── */

QLineEdit {{
    background-color: {raised};
    color: {fg};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 6px {sp1}px;
    font-size: 10pt;
    selection-background-color: {sel_bg};
    selection-color: {sel_fg};
    min-height: 32px;
}}
QLineEdit:focus    {{ border-color: {accent}; }}
QLineEdit:disabled {{ color: {fg_dim}; background-color: {surface}; }}

/* COMBOBOX ───────────────────────────────────────────────── */

QComboBox {{
    background-color: {raised};
    color: {fg};
    border: 1px solid {border};
    border-radius: {r}px;
    padding: 6px {sp1}px;
    font-size: 10pt;
    min-height: 32px;
}}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {fg_dim};
    width: 0; height: 0; margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {surface};
    color: {fg};
    border: 1px solid {border};
    border-radius: {r_sm}px;
    selection-background-color: {sel_bg};
    selection-color: {sel_fg};
    outline: none;
    padding: 4px;
}}

/* LISTAS ─────────────────────────────────────────────────── */

QListWidget, QListView {{
    background-color: {raised};
    color: {fg};
    border: 1px solid {border};
    border-radius: {r}px;
    outline: none;
    font-size: 10pt;
}}
QListWidget::item, QListView::item {{
    padding: 8px {sp1}px;
    border-radius: {r_sm}px;
    margin: 1px 4px;
}}
QListWidget::item:hover, QListView::item:hover {{ background-color: {hover}; }}
QListWidget::item:selected, QListView::item:selected {{
    background-color: {sel_bg};
    color: {fg};
}}

/* SCROLLBAR ──────────────────────────────────────────────── */

QScrollBar:vertical {{
    background: {surface}; width: 6px; margin: 0;
    border: none; border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {border_hi}; border-radius: 3px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: none; }}

QScrollBar:horizontal {{
    background: {surface}; height: 6px; margin: 0;
    border: none; border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {border_hi}; border-radius: 3px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; background: none; }}

/* CHECKBOX ───────────────────────────────────────────────── */

QCheckBox {{
    color: {fg}; font-size: 10pt; spacing: 8px;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {border_hi};
    border-radius: {r_sm}px;
    background-color: {raised};
}}
QCheckBox::indicator:hover   {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background-color: {accent}; border-color: {accent}; }}

/* RADIOBUTTON ────────────────────────────────────────────── */

QRadioButton {{
    color: {fg}; font-size: 10pt; spacing: 8px;
    background-color: transparent;
}}
QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {border_hi};
    border-radius: 8px;
    background-color: {raised};
}}
QRadioButton::indicator:hover   {{ border-color: {accent}; }}
QRadioButton::indicator:checked {{ background-color: {accent}; border-color: {accent}; }}

/* PROGRESSBAR ────────────────────────────────────────────── */

QProgressBar {{
    background-color: {raised}; border: none;
    border-radius: 3px; height: 4px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background-color: {accent}; border-radius: 3px; }}

/* SLIDER ─────────────────────────────────────────────────── */

QSlider::groove:horizontal {{
    background: {raised}; height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {accent}; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {accent_hv}; }}
QSlider::sub-page:horizontal     {{ background: {accent}; border-radius: 2px; }}

/* SEPARADORES ────────────────────────────────────────────── */

QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {border};
    background-color: {border};
    border: none;
    max-height: 1px;
}}

/* TOOLTIP ────────────────────────────────────────────────── */

QToolTip {{
    background-color: {surface};
    color: {fg};
    border: 1px solid {border_hi};
    border-radius: {r_sm}px;
    padding: 6px {sp1}px;
    font-size: 9pt;
}}

/* DIALOG ─────────────────────────────────────────────────── */

QDialog {{
    background-color: {bg};
    color: {fg};
}}

/* STATUSBAR ──────────────────────────────────────────────── */

QStatusBar {{
    background-color: {surface};
    color: {fg_dim};
    border-top: 1px solid {border};
    font-size: 9pt;
    padding: 2px {sp1}px;
}}

"""


# ============================================================
# SECCION 8: get_colors() — dict de colores del tema oscuro
# ============================================================

def get_colors() -> dict:
    """Devuelve un diccionario con los colores del tema oscuro."""
    return {
        "bg":        BG_BASE,
        "bg_light":  BG_RAISED,
        "fg":        TEXT_BRIGHT,
        "fg_dim":    TEXT_MUTED,
        "select_bg": SELECT_BG,
        "select_fg": SELECT_FG,
        "border":    BORDER_MID,
    }


# ============================================================
# SECCION 9: get_palette() — QPalette del tema oscuro
# ============================================================

def get_palette() -> QPalette:
    """Devuelve un QPalette con los colores del tema oscuro."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(BG_BASE))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_BRIGHT))
    palette.setColor(QPalette.ColorRole.Base,            QColor(BG_RAISED))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.Text,            QColor(TEXT_BRIGHT))
    palette.setColor(QPalette.ColorRole.BrightText,      QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_BRIGHT))
    palette.setColor(QPalette.ColorRole.Button,          QColor(BG_RAISED))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link,            QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.Mid,             QColor(BORDER_MID))
    palette.setColor(QPalette.ColorRole.Dark,            QColor(BG_BASE))
    palette.setColor(QPalette.ColorRole.Shadow,          QColor("#000000"))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT_BRIGHT))
    return palette


# ============================================================
# SECCION 10: HELPERS de widgets
# ============================================================

def set_role(widget, role: str) -> None:
    """
    Asigna un rol visual a un widget.

    Roles para botones: "primary" | "danger" | "icon" | "sidebar"
    Roles para labels:  "title" | "subtitle" | "section" | "muted" | "accent" | "danger"
    """
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_active(widget, active: bool) -> None:
    """Marca un boton de sidebar como activo o inactivo."""
    widget.setProperty("active", "true" if active else "false")
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def qcolor(name: str) -> QColor:
    """Devuelve un QColor por nombre semantico."""
    table = {
        "bg_base"    : BG_BASE,
        "bg_surface" : BG_SURFACE,
        "bg_raised"  : BG_RAISED,
        "bg_hover"   : BG_HOVER,
        "border"     : BORDER_MID,
        "border_hi"  : BORDER_HI,
        "accent"     : ACCENT,
        "accent_dim" : ACCENT_DIM,
        "text"       : TEXT_BRIGHT,
        "text_dim"   : TEXT_MUTED,
        "danger"     : COLOR_DANGER,
        "warning"    : COLOR_WARNING,
    }
    return QColor(table.get(name, "#ff00ff"))
