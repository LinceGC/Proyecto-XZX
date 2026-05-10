# -*- coding: utf-8 -*-
"""
setting.pyw  —  Spryta Settings (PySide6)

Ventana principal de configuracion de Spryta.
Toda la logica de interfaz esta organizada en:

    ui/theme.py    -- colores, fuentes, stylesheet global
    ui/widgets.py  -- SpriteGalleryWidget, AudioListWidget
    ui/panels.py   -- LeftToolPanel, RightProcessPanel
    ui/help.py     -- HelpWindow
    ui/dialog.py   -- show_info, show_warning, show_error, ask_yes_no

Las herramientas de negocio estan en:

    tools/ambient_audio.py   -- AmbientAudioManager
    tools/frame_extractor.py -- FrameExtractor
    tools/process_manager.py -- ProcessManager

Layout principal:
    +------------+------------------------------------------+
    | SIDEBAR    | HEADER: titulo + acciones                |
    | [Sprites]  |------------------------------------------|
    | [Scenes]   | CONTENT AREA (cambia segun sidebar)      |
    | [Playlists]|  - Galeria / Config / Scenes / Playlists |
    | [Tools]    |                                          |
    |            | STATUS BAR: sprite activo, coordenadas   |
    +------------+------------------------------------------+
"""

import os
import sys
import configparser
import threading
import subprocess
import tempfile
import zipfile

from PySide6.QtCore    import Qt, QTimer, Signal, QObject, QPropertyAnimation, QEasingCurve, QMimeData, QByteArray
from PySide6.QtGui     import QIcon, QFont, QIntValidator, QDrag
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit,
    QComboBox, QRadioButton, QCheckBox,
    QButtonGroup, QListWidget, QListWidgetItem,
    QScrollArea, QSizePolicy, QFileDialog,
    QAbstractItemView, QStatusBar, QSplitter,
    QSystemTrayIcon,
)

# ============================================================
# Directorio base
# ============================================================

def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
os.chdir(BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

def resolve_runtime_executable(base_dir: str, runtime_dir: str, exe_name: str, script_name: str):
    """
    Busca primero el ejecutable aislado en runtime_dir (PyInstaller --onedir)
    y luego cae a rutas legacy en la raiz del proyecto o script .pyw.
    Devuelve (ruta_absoluta, usar_pythonw) o (None, None).
    """
    runtime_exe = os.path.join(base_dir, runtime_dir, exe_name)
    root_exe = os.path.join(base_dir, exe_name)
    root_script = os.path.join(base_dir, script_name)

    if os.path.exists(runtime_exe):
        return runtime_exe, False
    if os.path.exists(root_exe):
        return root_exe, False
    if os.path.exists(root_script):
        return root_script, True
    return None, None

# ============================================================
# Importar modulos propios
# ============================================================

from tools.ambient_audio   import AmbientAudioManager
from tools.frame_extractor import FrameExtractor
from tools.process_manager import ProcessManager
from tools.lasso_manager   import LassoManager

from ui.panels  import LeftToolPanel, RightProcessPanel
from ui.widgets import SpriteGalleryWidget, SceneListWidget
from ui.help    import HelpWindow
from ui         import theme
from ui.dialog  import show_info, show_warning, show_error, ask_yes_no, ask_string
from ui.tray_icon import SpryTrayIcon

# ============================================================
# Constantes de archivos
# ============================================================

def _get_user_docs():
    try:
        import ctypes
        from ctypes import wintypes
        CSIDL_LOCAL_APPDATA = 28
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(0, CSIDL_LOCAL_APPDATA, 0, 0, buf)
        return os.path.join(buf.value, "Spryta")
    except Exception:
        return os.path.join(os.path.expanduser("~"), "AppData", "Local", "Spryta")

_USER_DOCS = _get_user_docs()
DATA_DIR    = os.path.join(_USER_DOCS, "data")
SPRITES_DIR = os.path.join(_USER_DOCS, "sprites")

# Crear carpetas del usuario si no existen
for _d in [_USER_DOCS, DATA_DIR, SPRITES_DIR, os.path.join(_USER_DOCS, "Audio")]:
    os.makedirs(_d, exist_ok=True)

SHOW_FLAG           = os.path.join(DATA_DIR, "show_settings.flag")
CONFIG_FILE         = os.path.join(DATA_DIR, "config.ini")
POSITIONS_FILE      = os.path.join(DATA_DIR, "positions.ini")
SCENES_FILE         = os.path.join(DATA_DIR, "scenes.ini")
REEL_FILE           = os.path.join(DATA_DIR, "reel.ini")
REEL_POSITIONS_FILE = os.path.join(DATA_DIR, "reel_positions.ini")
REEL_CONFIG_FILE    = os.path.join(DATA_DIR, "reel_config.ini")
SESSION_FILE        = os.path.join(DATA_DIR, "session.ini")


# ============================================================
# HELPERS INTERNOS DE WIDGET
# ============================================================

def _hsep() -> QFrame:
    """Separador horizontal de 1px."""
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{theme.BORDER_MID}; border:none;")
    return f

def _lbl(text: str, role: str = "normal") -> QLabel:
    """Crea un QLabel con el rol visual indicado."""
    l = QLabel(text)
    l.setFont(theme.FONT_SMALL)
    theme.set_role(l, role)
    return l

def _card() -> QFrame:
    """Card con fondo BG_SURFACE y borde redondeado."""
    f = QFrame()
    f.setObjectName("Card")
    f.setStyleSheet(f"""
        QFrame#Card {{
            background:{theme.BG_SURFACE};
            border:1px solid {theme.BORDER_MID};
            border-radius:{theme.RADIUS}px;
        }}
    """)
    return f


def _show_launch_toast(parent: QWidget, title: str, subtitle: str) -> None:
    """Muestra una notificacion con formato Spryta y texto contextual al launch."""
    toast = QWidget(None)
    toast.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    toast.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    toast.setFixedSize(300, 80)

    screen = QApplication.primaryScreen().availableGeometry()
    x = screen.right() - toast.width() - 18
    y = screen.bottom() - toast.height() - 18
    toast.move(x, y)

    outer = QFrame(toast)
    outer.setGeometry(0, 0, toast.width(), toast.height())
    outer.setStyleSheet(f"""
        QFrame {{
            background-color: {theme.BG_SURFACE};
            border: 1px solid {theme.BORDER_MID};
            border-radius: 8px;
        }}
    """)

    lay = QHBoxLayout(outer)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(14)

    icon_lbl = QLabel()
    icon_lbl.setFixedSize(36, 36)
    icon_lbl.setStyleSheet("background: transparent; border: none;")
    icon_path = os.path.join(BASE_DIR, "assets", "icons", "icon.png")
    if os.path.exists(icon_path):
        icon_lbl.setPixmap(QIcon(icon_path).pixmap(36, 36))
    else:
        icon_lbl.setText("●")
        icon_lbl.setStyleSheet(
            f"background: transparent; border: none; color: {theme.ACCENT}; font-size: 18px;"
        )
    lay.addWidget(icon_lbl)

    text_col = QVBoxLayout()
    text_col.setContentsMargins(0, 0, 0, 0)
    text_col.setSpacing(4)
    lbl_title = QLabel(title)
    lbl_title.setStyleSheet(
        f"color: {theme.TEXT_BRIGHT}; font-family: 'Segoe UI'; "
        "font-size: 10pt; font-weight: bold; background: transparent; border: none;"
    )
    lbl_sub = QLabel(subtitle)
    lbl_sub.setStyleSheet(
        f"color: {theme.TEXT_NORMAL}; font-family: 'Segoe UI'; "
        "font-size: 8pt; background: transparent; border: none;"
    )
    text_col.addWidget(lbl_title)
    text_col.addWidget(lbl_sub)
    lay.addLayout(text_col, 1)

    if not hasattr(parent, "_launch_toasts"):
        parent._launch_toasts = []
    parent._launch_toasts.append(toast)

    anim = QPropertyAnimation(toast, b"windowOpacity")
    anim.setDuration(350)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InQuad)

    def _cleanup():
        try:
            parent._launch_toasts.remove(toast)
        except Exception:
            pass
        toast.close()
        toast.deleteLater()

    anim.finished.connect(_cleanup)
    toast._fade_anim = anim
    toast.show()
    QTimer.singleShot(2000, anim.start)



# ============================================================
# WIDGET: SpeedPicker
# ============================================================

class _SpeedPicker(QWidget):
    """
    Boton de 140x40 (igual que Save Config).
    Al clicarlo se expande hacia la derecha mostrando 5 opciones.
    Elegir una opcion colapsa el panel y actualiza el boton.

    Ancho cerrado : 140 px
    Ancho expandido: 140 * 5 + 4 * 4 = 716 px  (5 botones + 4 gaps de 4px)
    """

    SPEEDS        = ["30", "60", "90", "120"]
    BTN_W         = 140
    BTN_H         = 40
    GAP           = 8
    EXPANDED_W    = BTN_W * 3 + GAP * 3   # 3 opciones (excluye la activa)

    def __init__(self, default: str = "60", parent=None):
        super().__init__(parent)
        self._value = default if default in self.SPEEDS else "60"
        self._open  = False
        self.setStyleSheet("background:transparent;")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Boton principal ───────────────────────────────────
        self._main_btn = QPushButton(self._value)
        self._main_btn.setFont(theme.FONT_SMALL)
        self._main_btn.setFixedSize(self.BTN_W, self.BTN_H)
        self._main_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._main_btn.setStyleSheet(theme.BTN_STYLE)
        self._main_btn.clicked.connect(self._toggle)
        root.addWidget(self._main_btn, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # ── Panel de opciones (se expande a la derecha) ───────
        self._panel = QWidget()
        self._panel.setFixedHeight(self.BTN_H + 8)
        self._panel.setStyleSheet("background:transparent;")
        self._panel.setVisible(False)

        panel_lay = QHBoxLayout(self._panel)
        panel_lay.setContentsMargins(self.GAP, 0, 0, 8)
        panel_lay.setSpacing(self.GAP)

        self._opt_btns = []
        for val in self.SPEEDS:
            btn = QPushButton(val)
            btn.setFont(theme.FONT_SMALL)
            btn.setFixedSize(self.BTN_W, self.BTN_H)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("_val", val)
            self._style_opt(btn)
            btn.clicked.connect(lambda _checked, v=val: self._select(v))
            panel_lay.addWidget(btn)
            self._opt_btns.append(btn)

        root.addWidget(self._panel, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        root.addStretch()

        # Animacion horizontal sobre maximumWidth del panel
        self._anim = QPropertyAnimation(self._panel, b"maximumWidth")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

    # ── Estilo de cada opcion ─────────────────────────────────
    def _style_opt(self, btn):
        val    = btn.property("_val")
        active = (val == self._value)
        if active:
            btn.setStyleSheet(
                f"QPushButton {{"
                f" background:{theme.ACCENT_DIM}; color:{theme.ACCENT};"
                f" border:1px solid {theme.ACCENT}; border-radius:{theme.RADIUS}px;"
                f" font-size:10pt; font-weight:bold;"
                f"}}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{"
                f" background:transparent; color:{theme.TEXT_MUTED};"
                f" border:1px solid {theme.BORDER_MID}; border-radius:{theme.RADIUS}px;"
                f" font-size:10pt;"
                f"}} "
                f"QPushButton:hover {{"
                f" background:{theme.BG_HOVER}; color:{theme.TEXT_BRIGHT};"
                f"}}"
            )

    # ── Toggle ────────────────────────────────────────────────
    def _toggle(self):
        if self._open:
            self._collapse()
        else:
            self._expand()

    def _expand(self):
        self._open = True
        # Mostrar solo las opciones que no son el valor activo
        visible_count = 0
        for btn in self._opt_btns:
            is_active = btn.property("_val") == self._value
            btn.setVisible(not is_active)
            if not is_active:
                visible_count += 1
        expanded = self.BTN_W * visible_count + self.GAP * visible_count
        self._panel.setMaximumWidth(0)
        self._panel.setVisible(True)
        self._anim.stop()
        self._anim.setStartValue(0)
        self._anim.setEndValue(expanded)
        self._anim.start()

    def _collapse(self):
        self._open = False
        self._anim.stop()
        self._anim.setStartValue(self._panel.width())
        self._anim.setEndValue(0)
        self._anim.start()

    def _on_anim_finished(self):
        if not self._open:
            self._panel.setVisible(False)

    # ── Seleccion ─────────────────────────────────────────────
    def _select(self, val: str):
        self._value = val
        self._main_btn.setText(val)
        for btn in self._opt_btns:
            self._style_opt(btn)
            btn.setVisible(True)  # restaurar antes de colapsar
        self._collapse()

    # ── API publica ───────────────────────────────────────────
    def get_value(self) -> str:
        return self._value

    def set_value(self, val: str):
        if val not in self.SPEEDS:
            val = "60"
        self._value = val
        self._main_btn.setText(val)
        for btn in self._opt_btns:
            self._style_opt(btn)
            btn.setVisible(True)
        if self._open:
            self._collapse()

# ============================================================
# CLASE PRINCIPAL
# ============================================================

class SettingsApp(QMainWindow):
    """
    Ventana principal de configuracion de Spryta.

    Hereda de QMainWindow para poder usar QStatusBar.
    En tkinter heredia de nada (era una clase plana que recibia master).
    Aqui la ventana ES la clase.
    """

    def __init__(self):
        super().__init__()

        # ── Variables de estado de la UI ──────────────────────
        # En tkinter eran tk.IntVar / tk.StringVar / tk.BooleanVar.
        # En Qt guardamos los valores directamente y leemos/escribimos
        # los widgets con .text(), .currentText(), .isChecked(), etc.
        self._selected_solo        = ""
        self._aspect_ratio_locked  = True
        self._aspect_ratio         = 1.0
        self._lock_anim            = None
        self._coord_x_label        = None
        self._coord_y_label        = None
        self._pl_coord_x_label     = None
        self._pl_coord_y_label     = None
        self._updating_size        = False
        self._real_img_width       = 0
        self._real_img_height      = 0
        self.selected_reel_name = None
        self.scenes_list           = []
        self.reel_list        = []

        # ── Gestores de logica ────────────────────────────────
        self.audio_manager   = AmbientAudioManager()
        self.frame_extractor = FrameExtractor()
        self.process_manager = ProcessManager()
        self.lasso_manager    = LassoManager()     # motor de vinculos cancion-sprite
        # Conectar el callback para abrir el panel Running automaticamente
        # cuando lasso lanza sprites, igual que con solo/scene/reel.
        self.lasso_manager.on_lasso_launched = self._on_lasso_sprites_launched

        # ── Paneles flotantes ─────────────────────────────────
        self.left_panel = LeftToolPanel(
            self,
            self.audio_manager,
            self.frame_extractor,
            on_close_callback=self._on_left_panel_closed,
            on_solo_created_callback=self._on_solo_created,
            lasso_manager=self.lasso_manager,
        )
        self.right_panel = RightProcessPanel(
            self,
            self.process_manager,
            on_close_callback=self._on_right_panel_closed,
            on_process_closed_callback=self.save_session,
            lasso_manager=self.lasso_manager,
            audio_manager=self.audio_manager,
        )

        # ── Estado general ────────────────────────────────────
        self.solo_gallery   = None
        self.help_window  = HelpWindow(self)

        # ── Archivos de configuracion ─────────────────────────
        self.config                    = configparser.ConfigParser()
        self.positions_config          = configparser.ConfigParser()
        self.reel_config          = configparser.ConfigParser()
        self.reel_positions_config = configparser.ConfigParser()
        self.reel_params_config           = configparser.ConfigParser()

        # ── Iniciar ───────────────────────────────────────────
        self._setup_window()
        self._load_or_create_config()
        self._load_or_create_positions()
        self._load_or_create_reel()
        self._create_ui()

        # Seleccionar solo activo al arrancar
        active = self.config.get("General", "active_sprite", fallback="")
        if active and active in self._get_solo_list():
            self._selected_solo = active
            self._load_sprite_config()

        self._start_coord_timer()
        self._start_show_flag_timer()

        # ── Tray unificado ────────────────────────────────────
        # Se crea aqui, despues de que todos los gestores existen.
        # Solo se activa si el sistema operativo soporta tray icons.
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = SpryTrayIcon(
                self,
                self.audio_manager,
                self.process_manager,
            )
            self.tray.show()
        else:
            self.tray = None

    # =========================================================
    # Show flag — IPC con main.pyw
    # =========================================================

    def _start_show_flag_timer(self):
        """Revisa cada 500ms si main.pyw solicito traer la ventana al frente."""
        self._show_flag_timer = QTimer(self)
        self._show_flag_timer.setInterval(500)
        self._show_flag_timer.timeout.connect(self._check_show_flag)
        self._show_flag_timer.start()

    def _check_show_flag(self):
        """Si existe el archivo flag, restaurar ventana y eliminarlo."""
        if os.path.exists(SHOW_FLAG):
            try:
                os.remove(SHOW_FLAG)
            except Exception:
                pass
            self._restore_main_window()

    # =========================================================
    # Configuracion de ventana
    # =========================================================

    def _setup_window(self):
        """Configura titulo, icono, tamano y stylesheet."""
        self.setWindowTitle("Spryta — Settings")
        self.setFixedSize(theme.MAIN_WINDOW_WIDTH, theme.MAIN_WINDOW_HEIGHT)

        icon_path = os.path.join("assets", "icons", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Aplicar stylesheet global del tema oscuro
        self.setStyleSheet(theme.get_stylesheet())

        # StatusBar inferior
        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    # =========================================================
    # Construccion del layout principal
    # =========================================================

    def _create_ui(self):
        """
        Construye el layout sidebar + content.

        +------------+--------------------------------------+
        | SIDEBAR    | HEADER                               |
        | 220px      |--------------------------------------|
        |            | CONTENT (paginas intercambiables)    |
        |            |                                      |
        +------------+--------------------------------------+
        """
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────
        self._sidebar = self._build_sidebar()
        root.addWidget(self._sidebar)

        # Separador vertical
        self._main_vsep = QFrame()
        self._main_vsep.setFrameShape(QFrame.Shape.VLine)
        self._main_vsep.setFixedWidth(1)
        self._main_vsep.setStyleSheet(f"background:{theme.BORDER_MID}; border:none;")
        root.addWidget(self._main_vsep)

        # ── Zona derecha: header + contenido ─────────────────
        right_zone = QWidget()
        right_zone.setStyleSheet(f"background:{theme.BG_BASE};")
        right_layout = QVBoxLayout(right_zone)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_layout.addWidget(self._build_header())
        right_layout.addWidget(_hsep())

        # Stack de paginas (solo se muestra una a la vez)
        self._page_solo       = self._build_page_solo()
        self._page_scenes     = self._build_page_scenes()
        self._page_reel  = self._build_page_reel()

        # Contenedor que mantiene todas las paginas apiladas
        self._pages_container = QWidget()
        pages_layout = QVBoxLayout(self._pages_container)
        pages_layout.setContentsMargins(0, 0, 0, 0)
        pages_layout.setSpacing(0)
        pages_layout.addWidget(self._page_solo)
        pages_layout.addWidget(self._page_scenes)
        pages_layout.addWidget(self._page_reel)

        right_layout.addWidget(self._pages_container, 1)

        root.addWidget(right_zone, 1)

        # Mostrar pagina solo por defecto
        self._show_page("solo")

        # Cargar datos iniciales
        self._load_solo_gallery()
        self._refresh_scenes_list()
        self._refresh_reel_list()

    # ----------------------------------------------------------
    # Sidebar
    # ----------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        """
        Panel lateral izquierdo con navegacion y acciones.

        Botones de navegacion:
            Solo / Scenes / Reel

        Botones de herramientas:
            Create Frame / Ambient Audio

        Botones de sistema:
            Dark Mode / Exit
        """
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(theme.SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"QWidget#Sidebar {{ background:{theme.BG_SURFACE}; }}")

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(theme.SP1, theme.SP2, theme.SP1, theme.SP2)
        lay.setSpacing(2)

        # Logo / nombre
        logo_row = QWidget()
        logo_row.setStyleSheet("background:transparent;")
        logo_row_lay = QHBoxLayout(logo_row)
        logo_row_lay.setContentsMargins(8, 0, 8, 0)
        logo_row_lay.setSpacing(8)

        # Icono
        lbl_icon = QLabel()
        lbl_icon.setFixedSize(28, 28)
        lbl_icon.setStyleSheet("background:transparent;")
        _icon_loaded = False
        for _icon_name in ("icon.png", "icon.ico"):
            _icon_path = os.path.join("assets", "icons", _icon_name)
            if os.path.exists(_icon_path):
                _pix = QIcon(_icon_path).pixmap(28, 28)
                lbl_icon.setPixmap(_pix)
                _icon_loaded = True
                break

        # Texto
        lbl_logo = QLabel("Spryta")
        lbl_logo.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lbl_logo.setStyleSheet(f"color:{theme.ACCENT}; background:transparent;")

        if _icon_loaded:
            logo_row_lay.addWidget(lbl_icon)
        logo_row_lay.addWidget(lbl_logo)
        logo_row_lay.addStretch()

        logo_row.setFixedHeight(36)
        lay.addWidget(logo_row)
        lay.addSpacing(theme.SP2)

        # ── Seccion: Navegacion ───────────────────────────────
        lbl_nav = QLabel("NAVIGATION")
        lbl_nav.setFont(theme.FONT_TINY)
        lbl_nav.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; background:transparent;"
            f"padding-left:8px; letter-spacing:1px;"
        )
        lay.addWidget(lbl_nav)
        lay.addSpacing(4)

        self._nav_btns = {}
        for name, label in [
            ("solo",      "Solo"),
            ("scenes",    "Scenes"),
            ("playlists", "Reel"),
        ]:
            btn = QPushButton(label)
            btn.setFont(theme.FONT_SMALL)
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            theme.set_role(btn, "sidebar")
            btn.clicked.connect(lambda checked=False, n=name: self._show_page(n))
            lay.addWidget(btn)
            self._nav_btns[name] = btn

        lay.addSpacing(theme.SP2)
        lay.addWidget(_hsep())
        lay.addSpacing(theme.SP2)

        # ── Seccion: Herramientas ─────────────────────────────
        lbl_tools = QLabel("TOOLS")
        lbl_tools.setFont(theme.FONT_TINY)
        lbl_tools.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; background:transparent;"
            f"padding-left:8px; letter-spacing:1px;"
        )
        lay.addWidget(lbl_tools)
        lay.addSpacing(4)

        self._btn_cf = QPushButton("Create Frame")
        self._btn_cf.setFont(theme.FONT_SMALL)
        self._btn_cf.setFixedHeight(38)
        self._btn_cf.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.set_role(self._btn_cf, "sidebar")
        theme.set_active(self._btn_cf, False)
        self._btn_cf.clicked.connect(self._show_create_frame)
        lay.addWidget(self._btn_cf)

        self._btn_aa = QPushButton("Ambient Audio")
        self._btn_aa.setFont(theme.FONT_SMALL)
        self._btn_aa.setFixedHeight(38)
        self._btn_aa.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.set_role(self._btn_aa, "sidebar")
        theme.set_active(self._btn_aa, False)
        self._btn_aa.clicked.connect(self._show_ambient_audio)
        lay.addWidget(self._btn_aa)

        self._btn_proc = QPushButton("Processes")
        self._btn_proc.setFont(theme.FONT_SMALL)
        self._btn_proc.setFixedHeight(38)
        self._btn_proc.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.set_role(self._btn_proc, "sidebar")
        theme.set_active(self._btn_proc, False)
        self._btn_proc.clicked.connect(self._toggle_process_panel)
        lay.addWidget(self._btn_proc)

        # Empujar controles de sistema hacia abajo
        lay.addStretch()
        lay.addWidget(_hsep())
        lay.addSpacing(theme.SP1)

        # ── Seccion: Support ──────────────────────────────────
        lbl_support = QLabel("SUPPORT")
        lbl_support.setFont(theme.FONT_TINY)
        lbl_support.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding-left: 8px; background: transparent;")
        lay.addWidget(lbl_support)

        btn_help = QPushButton("Help")
        btn_help.setFont(theme.FONT_SMALL)
        btn_help.setFixedHeight(38)
        btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.set_role(btn_help, "sidebar")
        btn_help.clicked.connect(self.help_window.show)
        lay.addWidget(btn_help)

        support_row = QHBoxLayout()
        support_row.setSpacing(8)

        btn_patreon = QPushButton("Patreon")
        btn_patreon.setFont(theme.FONT_SMALL)
        btn_patreon.setFixedHeight(38)
        btn_patreon.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_patreon.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.set_role(btn_patreon, "sidebar")
        btn_patreon.clicked.connect(
            lambda: __import__("webbrowser").open("https://www.patreon.com/Spryta")
        )
        support_row.addWidget(btn_patreon)

        btn_discord = QPushButton("Discord")
        btn_discord.setFont(theme.FONT_SMALL)
        btn_discord.setFixedHeight(38)
        btn_discord.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_discord.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.set_role(btn_discord, "sidebar")
        btn_discord.clicked.connect(
            lambda: __import__("webbrowser").open("https://discord.gg")
        )
        support_row.addWidget(btn_discord)
        lay.addLayout(support_row)

        btn_minimize = QPushButton("Hide Window")
        btn_minimize.setFont(theme.FONT_SMALL)
        btn_minimize.setFixedHeight(38)
        btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.set_role(btn_minimize, "sidebar")
        btn_minimize.clicked.connect(self._to_background)
        lay.addWidget(btn_minimize)

        lay.addSpacing(17)

        btn_exit = QPushButton("Exit")
        btn_exit.setFont(theme.FONT_SMALL)
        btn_exit.setFixedHeight(34)
        btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exit.setStyleSheet(theme.DANGER_STYLE)
        btn_exit.clicked.connect(self._finalize_and_exit)
        lay.addWidget(btn_exit)
        lay.addSpacing(3)

        return sidebar

    # ----------------------------------------------------------
    # Header
    # ----------------------------------------------------------

    def _build_header(self) -> QWidget:
        """Barra superior con titulo dinamico y boton de ayuda."""
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(56)
        header.setStyleSheet(f"QWidget#Header {{ background:{theme.BG_SURFACE}; }}")

        lay = QHBoxLayout(header)
        lay.setContentsMargins(theme.SP2, 0, theme.SP2, 0)

        self._header_title = QLabel("Solo")
        self._header_title.setFont(theme.FONT_SUBTITLE)
        self._header_title.setStyleSheet(
            f"color:{theme.ACCENT}; background:transparent;"
        )

        # Autostart checkbox en el header
        self._autostart_chk = QCheckBox("Start with Windows")
        self._autostart_chk.setFont(theme.FONT_SMALL)
        self._autostart_chk.setStyleSheet("background:transparent;")
        self._autostart_chk.setChecked(self._is_autostart_enabled())
        self._autostart_chk.toggled.connect(self._toggle_autostart)

        lay.addWidget(self._header_title)
        lay.addStretch()
        lay.addWidget(self._autostart_chk)

        return header

    # ----------------------------------------------------------
    # Navegacion entre paginas
    # ----------------------------------------------------------

    def _show_page(self, name: str):
        """
        Muestra la pagina indicada y oculta las demas.
        Actualiza el estado visual de los botones del sidebar.

        Parametros:
            name -- "solo" | "scenes" | "reel"
        """
        pages = {
            "solo"      : self._page_solo,
            "scenes"    : self._page_scenes,
            "playlists" : self._page_reel,
        }
        titles = {
            "solo"      : "Solo",
            "scenes"    : "Scenes",
            "playlists" : "Reel",
        }

        for n, page in pages.items():
            page.setVisible(n == name)

        for n, btn in self._nav_btns.items():
            theme.set_active(btn, n == name)

        self._header_title.setText(titles.get(name, "Settings"))

    # =========================================================
    # PAGINA: SOLO
    # =========================================================

    def _build_page_solo(self) -> QWidget:
        """
        Pagina Solo con galeria y configuracion individual.

        Layout interno:
            +------------------+----------------------------+
            | Galeria (scroll) | Config del solo            |
            | Buscador         | Frame Size                 |
            | [Add Solo]       | Position                   |
            |                  | Dynamic Mode               |
            |                  | Speed / Delay              |
            |                  | [Save] [Run]               |
            +------------------+----------------------------+
        """
        page = QWidget()
        page.setStyleSheet(f"background:{theme.BG_BASE};")

        root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Columna izquierda: galeria ────────────────────────
        left_col = QWidget()
        left_col.setFixedWidth(226)
        left_col.setStyleSheet(
            f"background:{theme.BG_BASE};"
        )
        left_lay = QVBoxLayout(left_col)
        left_lay.setContentsMargins(theme.SP2, theme.SP2, theme.SP2, theme.SP2)
        left_lay.setSpacing(theme.SP1)

        # Titulo galeria
        lbl_gal = QLabel("Sprite Gallery")
        lbl_gal.setFont(theme.font("small", bold=True))
        lbl_gal.setStyleSheet(f"color:{theme.ACCENT}; background:transparent;")
        left_lay.addWidget(lbl_gal)
        left_lay.addSpacing(6)

        # Buscador
        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText("Search sprites...")
        self._search_entry.setFixedHeight(46)
        self._search_entry.setStyleSheet(
            f"QLineEdit {{ min-height: 46px; max-height: 46px; }}"
        )
        self._search_entry.textChanged.connect(self._filter_solo)
        left_lay.addWidget(self._search_entry)
        left_lay.addSpacing(-6)

        # Galeria
        self.solo_gallery = SpriteGalleryWidget(
            left_col,
            SPRITES_DIR,
            on_select_callback=self._on_solo_selected,
            fixed_height=theme.GALLERY_HEIGHT,
        )
        left_lay.addWidget(self.solo_gallery)

        # Boton agregar sprite
        btn_add = QPushButton("Add Sprite")
        btn_add.setFont(theme.FONT_SMALL)
        btn_add.setFixedHeight(34)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(theme.BTN_STYLE)
        btn_add.clicked.connect(self._select_solo_folder)
        left_lay.addWidget(btn_add)

        left_lay.addStretch()
        root.addWidget(left_col)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{theme.BORDER_DIM}; border:none;")
        root.addWidget(sep)

        # ── Columna derecha: configuracion ────────────────────
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.BG_BASE}; border:none; }}"
            f"QScrollArea > QWidget > QWidget {{ background:{theme.BG_BASE}; }}"
        )
        self._right_scroll = right_scroll

        right_inner = QWidget()
        right_inner.setStyleSheet(f"background:{theme.BG_BASE};")
        self._right_inner = right_inner
        right_lay = QVBoxLayout(right_inner)
        right_lay.setContentsMargins(theme.SP3, theme.SP2, theme.SP3, theme.SP2)
        right_lay.setSpacing(theme.SP2)

        self._build_config_panel(right_lay)

        right_scroll.setWidget(right_inner)

        # ── Contenedor derecho: scroll arriba + botones fijos abajo ──
        right_col = QWidget()
        right_col.setStyleSheet(f"background:{theme.BG_BASE};")
        right_col_lay = QVBoxLayout(right_col)
        right_col_lay.setContentsMargins(0, 0, 0, 0)
        right_col_lay.setSpacing(0)
        right_col_lay.addWidget(right_scroll, 1)

        # Fila de botones fijos
        btn_bar = QWidget()
        btn_bar.setStyleSheet(f"background:{theme.BG_BASE};")
        btn_bar_lay = QHBoxLayout(btn_bar)
        btn_bar_lay.setContentsMargins(theme.SP3, theme.SP2, theme.SP3, theme.SP2)
        btn_bar_lay.setSpacing(theme.SP1)

        btn_save = QPushButton("Save Config")
        btn_save.setFont(theme.FONT_SMALL)
        btn_save.setFixedSize(140, 40)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(theme.BTN_STYLE)
        btn_save.clicked.connect(self._save_solo_config)

        btn_run = QPushButton("Run Solo")
        btn_run.setFont(theme.FONT_SMALL)
        btn_run.setFixedSize(140, 40)
        btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_run.setStyleSheet(theme.BTN_STYLE)
        btn_run.clicked.connect(self._run_main)

        btn_bar_lay.addWidget(btn_run)
        btn_bar_lay.addWidget(btn_save)
        btn_bar_lay.addStretch()
        right_col_lay.addWidget(btn_bar)

        root.addWidget(right_col, 1)

        return page


    def _make_speed_bar(self, default="60"):
        """
        Crea un SpeedPicker — boton unico que despliega panel deslizante.
        Devuelve (picker_widget, picker_widget) — segundo valor por compatibilidad
        con _set_speed_bar / _get_speed_bar.
        """
        picker = _SpeedPicker(default, parent=self)
        return picker, picker

    def _set_speed_bar(self, picker, val):
        """Activa el valor en el picker."""
        picker.set_value(val)

    def _get_speed_bar(self, picker):
        """Devuelve el valor actual del picker."""
        return picker.get_value()

    def _build_config_panel(self, lay: QVBoxLayout):
        """Construye todos los controles de configuracion del solo."""

        # ── Frame Size ────────────────────────────────────────
        lbl_size = QLabel("Frame Size (px)")
        lbl_size.setFont(theme.font("small", bold=True))
        # color heredado del stylesheet global
        lay.addWidget(lbl_size)
        lay.addSpacing(-2)

        size_card = _card()
        size_card.setFixedHeight(60)
        self._cards = []
        self._cards.append(size_card)
        size_lay = QHBoxLayout(size_card)
        size_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        size_lay.setContentsMargins(theme.SP2, 0, theme.SP2, 0)
        size_lay.setSpacing(theme.SP1)

        self._width_entry = QLineEdit("150")
        self._width_entry.setValidator(QIntValidator(1, 9999))
        self._width_entry.setFixedSize(140, 40)
        self._width_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._width_entry.textChanged.connect(self._on_width_changed)

        lbl_x = QLabel("x")
        lbl_x.setFont(theme.FONT_NORMAL)
        lbl_x.setStyleSheet("background:transparent;")

        self._height_entry = QLineEdit("150")
        self._height_entry.setValidator(QIntValidator(1, 9999))
        self._height_entry.setFixedSize(140, 40)
        self._height_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._height_entry.textChanged.connect(self._on_height_changed)

        self._lock_btn = QPushButton("locked")
        self._lock_btn.setFont(theme.FONT_TINY)
        self._lock_btn.setFixedSize(140, 40)
        self._lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lock_btn.setStyleSheet(theme.BTN_STYLE)
        self._lock_btn.clicked.connect(self._toggle_aspect_lock)

        size_lay.addWidget(self._width_entry, 0, Qt.AlignmentFlag.AlignVCenter)
        size_lay.addWidget(lbl_x,              0, Qt.AlignmentFlag.AlignVCenter)
        size_lay.addWidget(self._height_entry, 0, Qt.AlignmentFlag.AlignVCenter)
        size_lay.addSpacing(14)
        size_lay.addWidget(self._lock_btn,     0, Qt.AlignmentFlag.AlignVCenter)
        size_lay.addStretch()
        QTimer.singleShot(0, self._start_lock_pulse)
        lay.addWidget(size_card)

        # ── Position ──────────────────────────────────────────
        pos_card = _card()
        self._cards.append(pos_card)
        pos_lay = QHBoxLayout(pos_card)
        pos_lay.setContentsMargins(theme.SP3, theme.SP2, theme.SP3, theme.SP2)
        pos_lay.setSpacing(theme.SP3)

        for axis, attr in [("X", "_coord_x_label"), ("Y", "_coord_y_label")]:
            block = QWidget()
            block.setStyleSheet("background:transparent;")
            block_lay = QVBoxLayout(block)
            block_lay.setContentsMargins(0, 0, 0, 0)
            block_lay.setSpacing(2)

            lbl_axis = QLabel(axis)
            lbl_axis.setFont(theme.FONT_TINY)
            lbl_axis.setStyleSheet(f"color:{theme.TEXT_MUTED}; background:transparent;")

            lbl_val = QLabel("--")
            lbl_val.setFont(theme.FONT_MONO_LARGE)
            lbl_val.setStyleSheet(f"color:{theme.ACCENT}; background:transparent;")
            lbl_val.setFixedWidth(52)

            block_lay.addWidget(lbl_axis)
            block_lay.addWidget(lbl_val)
            pos_lay.addWidget(block)
            setattr(self, attr, lbl_val)

        pos_lay.addStretch()
        lay.addWidget(pos_card)

        # ── Dynamic Mode ──────────────────────────────────────
        lbl_dyn = QLabel("Dynamic Mode")
        lbl_dyn.setFont(theme.font("small", bold=True))
        # color heredado del stylesheet global
        lay.addWidget(lbl_dyn)

        dyn_card = _card()
        self._cards.append(dyn_card)
        dyn_lay  = QHBoxLayout(dyn_card)
        dyn_lay.setContentsMargins(theme.SP2, theme.SP1, theme.SP2, theme.SP1)
        dyn_lay.setSpacing(theme.SP2)

        self._dyn_group = QButtonGroup(dyn_card)
        for i, (label, val) in enumerate([
            ("Stitched", "clavado"),
            ("Walk",     "paseo"),
            ("Wandering","errante"),
        ]):
            rb = QRadioButton(label)
            rb.setFont(theme.FONT_SMALL)
            rb.setStyleSheet("background:transparent;")
            rb.setProperty("_val", val)
            self._dyn_group.addButton(rb, i)
            dyn_lay.addWidget(rb)
            if val == "errante":
                rb.setChecked(True)

        dyn_lay.addStretch()
        lay.addWidget(dyn_card)

        # ── Movement Speed ────────────────────────────────────
        lbl_spd = QLabel("Movement Speed")
        lbl_spd.setFont(theme.font("small", bold=True))
        # color heredado del stylesheet global
        lay.addWidget(lbl_spd)

        _spd_w, self._speed_btns = self._make_speed_bar("60")
        lay.addWidget(_spd_w)

        # ── Delay Mode ────────────────────────────────────────
        lbl_delay = QLabel("Delay Mode")
        lbl_delay.setFont(theme.font("small", bold=True))
        # color heredado del stylesheet global
        lay.addWidget(lbl_delay)

        delay_card = _card()
        self._cards.append(delay_card)
        delay_lay  = QHBoxLayout(delay_card)
        delay_lay.setContentsMargins(theme.SP2, theme.SP1, theme.SP2, theme.SP1)
        delay_lay.setSpacing(theme.SP2)

        self._delay_group = QButtonGroup(delay_card)
        for i, (label, val) in enumerate([
            ("Fixed", "fixed"),
            ("CPU",   "cpu"),
            ("Presentation", "presentacion"),
        ]):
            rb = QRadioButton(label)
            rb.setFont(theme.FONT_SMALL)
            rb.setStyleSheet("background:transparent;")
            rb.setProperty("_val", val)
            self._delay_group.addButton(rb, i)
            delay_lay.addWidget(rb)
            if val == "cpu":
                rb.setChecked(True)

        delay_lay.addStretch()
        lay.addWidget(delay_card)
        self._delay_group.idClicked.connect(self._update_delay_ui)

        # ── Sub-paneles de delay (uno visible a la vez) ───────

        # Fixed
        self._fixed_delay_card = _card()
        fdl = QHBoxLayout(self._fixed_delay_card)
        fdl.setContentsMargins(theme.SP2, theme.SP1, theme.SP2, theme.SP1)
        lbl_fd = QLabel("Fixed Delay (ms):")
        lbl_fd.setFont(theme.FONT_SMALL)
        lbl_fd.setStyleSheet("background:transparent;")
        self._fixed_delay_entry = QLineEdit("30")
        self._fixed_delay_entry.setValidator(QIntValidator(1, 9999))
        self._fixed_delay_entry.setFixedSize(80, 30)
        self._fixed_delay_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fdl.addWidget(lbl_fd,                    0, Qt.AlignmentFlag.AlignVCenter)
        fdl.addWidget(self._fixed_delay_entry,   0, Qt.AlignmentFlag.AlignVCenter)
        fdl.addStretch()
        lay.addWidget(self._fixed_delay_card)

        # CPU — 5 columnas horizontales: label arriba, input abajo
        self._cpu_card = _card()
        cpu_outer = QVBoxLayout(self._cpu_card)
        cpu_outer.setContentsMargins(theme.SP2, theme.SP2, theme.SP2, theme.SP2)
        cpu_outer.setSpacing(6)

        lbl_cpu = QLabel("CPU Delays (ms per level):")
        lbl_cpu.setFont(theme.FONT_SMALL)
        lbl_cpu.setStyleSheet("background:transparent;")
        cpu_outer.addWidget(lbl_cpu)

        cols_row = QHBoxLayout()
        cols_row.setSpacing(theme.SP1)
        cols_row.setContentsMargins(0, 0, 0, 0)

        self._cpu_entries = []
        defaults = [(0,20,200),(21,40,150),(41,60,120),(61,80,90),(81,100,60)]
        for a, b, ms in defaults:
            col_w = QWidget()
            col_w.setStyleSheet("background:transparent;")
            col_l = QVBoxLayout(col_w)
            col_l.setContentsMargins(0, 0, 0, 8)
            col_l.setSpacing(3)

            lbl_r = QLabel(f"{a}-{b}%")
            lbl_r.setFont(theme.FONT_TINY)
            lbl_r.setStyleSheet(f"color:{theme.TEXT_MUTED}; background:transparent;")
            lbl_r.setAlignment(Qt.AlignmentFlag.AlignCenter)

            ent = QLineEdit(str(ms))
            ent.setValidator(QIntValidator(1, 9999))
            ent.setFixedHeight(32)
            ent.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._cpu_entries.append(ent)

            col_l.addWidget(lbl_r)
            col_l.addWidget(ent)
            cols_row.addWidget(col_w, 1)

        cpu_outer.addLayout(cols_row)
        lay.addWidget(self._cpu_card)

        # Presentacion
        self._pres_card = _card()
        prl = QHBoxLayout(self._pres_card)
        prl.setContentsMargins(theme.SP2, theme.SP1, theme.SP2, theme.SP1)
        lbl_pr = QLabel("Presentation Delay (sec):")
        lbl_pr.setFont(theme.FONT_SMALL)
        lbl_pr.setStyleSheet("background:transparent;")
        self._pres_delay_entry = QLineEdit("2")
        self._pres_delay_entry.setValidator(QIntValidator(1, 999))
        self._pres_delay_entry.setFixedSize(80, 30)
        self._pres_delay_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prl.addWidget(lbl_pr,                  0, Qt.AlignmentFlag.AlignVCenter)
        prl.addWidget(self._pres_delay_entry,  0, Qt.AlignmentFlag.AlignVCenter)
        prl.addStretch()
        lay.addWidget(self._pres_card)

        self._update_delay_ui()
        lay.addStretch()

    # =========================================================
    # PAGINA: SCENES
    # =========================================================

    def _build_page_scenes(self) -> QWidget:
        """Pagina de gestion de escenas."""
        page = QWidget()
        page.setStyleSheet(f"background:{theme.BG_BASE};")

        lay = QVBoxLayout(page)
        lay.setContentsMargins(theme.SP3, theme.SP2, theme.SP3, theme.SP2)
        lay.setSpacing(theme.SP2)

        lay.addWidget(_hsep())

        # Lista de escenas
        self._scenes_list_widget = SceneListWidget(
            page, SPRITES_DIR,
            on_select_callback=self._on_scene_selected,
            fixed_height=220,
        )
        lay.addWidget(self._scenes_list_widget)

        # Botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(theme.SP1)
        for label, slot in [
            ("Run Scene", self._run_scene),
            ("Create",    self._create_scene_window),
            ("Delete",    self._delete_scene),
        ]:
            b = QPushButton(label)
            b.setFont(theme.FONT_SMALL)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if label == "Delete":
                b.setFixedSize(140, 40)
                b.setStyleSheet(theme.DANGER_STYLE)
            else:
                b.setFixedSize(140, 40)
                b.setStyleSheet(theme.BTN_STYLE)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addStretch()

        return page

    # =========================================================
    # PAGINA: REEL
    # =========================================================

    def _build_page_reel(self) -> QWidget:
        """Pagina de gestion del Reel."""
        from PySide6.QtWidgets import QScrollArea

        page = QWidget()
        page.setStyleSheet(f"background:{theme.BG_BASE};")

        lay = QVBoxLayout(page)
        lay.setContentsMargins(theme.SP3, theme.SP2, theme.SP3, theme.SP2)
        lay.setSpacing(theme.SP2)

        lay.addWidget(_hsep())

        # Lista de Reels
        self._reel_list_widget = SceneListWidget(
            page, SPRITES_DIR,
            on_select_callback=self._on_reel_selected_name,
            fixed_height=160,
        )
        lay.addWidget(self._reel_list_widget)

        # Configuracion del Reel
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.BG_BASE}; border:none; }}"
            f"QScrollArea > QWidget > QWidget {{ background:{theme.BG_BASE}; }}"
        )
        inner = QWidget()
        inner.setStyleSheet(f"background:{theme.BG_BASE};")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, theme.SP1, 0, theme.SP1)
        inner_lay.setSpacing(theme.SP2)

        self._build_reel_config_panel(inner_lay)

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        return page

    def _build_reel_config_panel(self, lay: QVBoxLayout):
        """Controles de configuracion del Reel: Position, Dynamic Mode, Speed."""

        # ── Current Position ─────────────────────────────────
        pos_card = _card()
        pos_lay = QHBoxLayout(pos_card)
        pos_lay.setContentsMargins(theme.SP3, theme.SP2, theme.SP3, theme.SP2)
        pos_lay.setSpacing(theme.SP3)

        for axis, attr in [("X", "_pl_coord_x_label"), ("Y", "_pl_coord_y_label")]:
            block = QWidget()
            block.setStyleSheet("background:transparent;")
            block_lay = QVBoxLayout(block)
            block_lay.setContentsMargins(0, 0, 0, 0)
            block_lay.setSpacing(2)

            lbl_axis = QLabel(axis)
            lbl_axis.setFont(theme.FONT_TINY)
            lbl_axis.setStyleSheet(f"color:{theme.TEXT_MUTED}; background:transparent;")

            lbl_val = QLabel("--")
            lbl_val.setFont(theme.FONT_MONO_LARGE)
            lbl_val.setStyleSheet(f"color:{theme.ACCENT}; background:transparent;")
            lbl_val.setFixedWidth(52)

            block_lay.addWidget(lbl_axis)
            block_lay.addWidget(lbl_val)
            pos_lay.addWidget(block)
            setattr(self, attr, lbl_val)

        pos_lay.addStretch()
        lay.addWidget(pos_card)

        # ── Dynamic Mode ─────────────────────────────────────
        lbl_dyn = QLabel("Dynamic Mode")
        lbl_dyn.setFont(theme.font("small", bold=True))
        lay.addWidget(lbl_dyn)

        dyn_card = _card()
        dyn_lay  = QHBoxLayout(dyn_card)
        dyn_lay.setContentsMargins(theme.SP2, theme.SP1, theme.SP2, theme.SP1)
        dyn_lay.setSpacing(theme.SP2)

        self._pl_dyn_group = QButtonGroup(dyn_card)
        for i, (label, val) in enumerate([
            ("Stitched", "clavado"),
            ("Walk",     "paseo"),
            ("Wandering","errante"),
        ]):
            rb = QRadioButton(label)
            rb.setFont(theme.FONT_SMALL)
            rb.setStyleSheet("background:transparent;")
            rb.setProperty("_val", val)
            self._pl_dyn_group.addButton(rb, i)
            dyn_lay.addWidget(rb)
            if val == "errante":
                rb.setChecked(True)

        dyn_lay.addStretch()
        lay.addWidget(dyn_card)

        # ── Movement Speed ────────────────────────────────────
        lbl_spd = QLabel("Movement Speed")
        lbl_spd.setFont(theme.font("small", bold=True))
        lay.addWidget(lbl_spd)

        _pl_spd_w, self._pl_speed_btns = self._make_speed_bar("60")
        lay.addWidget(_pl_spd_w)

        # ── Fila de botones: Save Config | Run Reel | Create | Delete ──
        action_row = QHBoxLayout()
        action_row.setSpacing(theme.SP1)

        btn_run = QPushButton("Run Reel")
        btn_run.setFont(theme.FONT_SMALL)
        btn_run.setFixedSize(140, 40)
        btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_run.setStyleSheet(theme.BTN_STYLE)
        btn_run.clicked.connect(self._run_reel)
        action_row.addWidget(btn_run)

        btn_create = QPushButton("Create")
        btn_create.setFont(theme.FONT_SMALL)
        btn_create.setFixedSize(140, 40)
        btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_create.setStyleSheet(theme.BTN_STYLE)
        btn_create.clicked.connect(self._create_reel_window)
        action_row.addWidget(btn_create)

        btn_del = QPushButton("Delete")
        btn_del.setFont(theme.FONT_SMALL)
        btn_del.setFixedSize(140, 40)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet(theme.DANGER_STYLE)
        btn_del.clicked.connect(self._delete_reel)
        action_row.addWidget(btn_del)
          
        btn_save = QPushButton("Save Config")
        btn_save.setFont(theme.FONT_SMALL)
        btn_save.setFixedSize(140, 40)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(theme.BTN_STYLE)
        btn_save.clicked.connect(self._save_selected_reel_config)
        action_row.addWidget(btn_save)

        action_row.addStretch()
        lay.addLayout(action_row)
        lay.addStretch()

    # =========================================================
    # Carga y guardado de configuracion
    # =========================================================

    def _load_or_create_config(self):
        if os.path.exists(CONFIG_FILE):
            self.config.read(CONFIG_FILE, encoding="utf-8")
        else:
            self.config["General"] = {
                "active_sprite": "Default",
                "position_x": "1339",
                "position_y": "508"
            }
            self._save_config_file()

    def _load_or_create_positions(self):
        if not os.path.exists(POSITIONS_FILE):
            self.positions_config["Default"] = {"x": "100", "y": "100"}
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                self.positions_config.write(f)
        else:
            self.positions_config.read(POSITIONS_FILE, encoding="utf-8")

    def _load_or_create_reel(self):
        if not os.path.exists(REEL_FILE):
            with open(REEL_FILE, "w", encoding="utf-8") as f:
                f.write("# Solo Reel Configuration\n")
        else:
            self.reel_config.read(REEL_FILE, encoding="utf-8")

        if not os.path.exists(REEL_POSITIONS_FILE):
            with open(REEL_POSITIONS_FILE, "w", encoding="utf-8") as f:
                f.write("# Playlist Positions\n")
        else:
            self.reel_positions_config.read(
                REEL_POSITIONS_FILE, encoding="utf-8"
            )

        if not os.path.exists(REEL_CONFIG_FILE):
            with open(REEL_CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write("# Playlist Configurations\n")
        else:
            self.reel_params_config.read(REEL_CONFIG_FILE, encoding="utf-8")

    def _save_config_file(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            self.config.write(f)

    def _get_solo_list(self, force_refresh=False):
        if not os.path.exists(SPRITES_DIR):
            os.makedirs(SPRITES_DIR)
        return [
            d for d in os.listdir(SPRITES_DIR)
            if os.path.isdir(os.path.join(SPRITES_DIR, d))
        ]

    # =========================================================
    # Galeria
    # =========================================================

    def _load_solo_gallery(self):
        sprites = self._get_solo_list()
        self.solo_gallery.load_sprites(sprites, self._selected_solo)

    def _on_solo_selected(self, sprite_name: str):
        self._selected_solo = sprite_name
        self._load_sprite_config()

    def _select_solo_folder(self):
        zip_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select sprite ZIP (or Cancel to choose folder)",
            "",
            "Sprite ZIP (*.zip)"
        )
        if zip_path:
            self._import_solo_zip(zip_path)
            return

        path = QFileDialog.getExistingDirectory(
            self, "Select sprite folder", ""
        )
        if not path:
            return

        name      = os.path.basename(path)
        full_path = os.path.join(SPRITES_DIR, name)

        # Verificar que la carpeta tenga al menos un PNG
        pngs = [f for f in os.listdir(path) if f.lower().endswith(".png")]
        if not pngs:
            show_error(
                "Error",
                f"The folder '{name}' has no PNG files inside.\n"
                "A sprite folder must contain at least one .png file.",
                parent=self,
            )
            return

        # Si la carpeta ya esta dentro de sprites/, usarla directamente
        if os.path.abspath(path) == os.path.abspath(full_path):
            pass
        else:
            # Si ya existe una carpeta con ese nombre en sprites/, preguntar
            if os.path.exists(full_path):
                if not ask_yes_no(
                    "Folder already exists",
                    f"A sprite named '{name}' already exists.\nReplace it?",
                    parent=self,
                ):
                    return
                import shutil
                shutil.rmtree(full_path)

            # Copiar la carpeta dentro de sprites/
            import shutil
            try:
                shutil.copytree(path, full_path)
            except Exception as e:
                show_error("Error", f"Could not copy folder:\n{e}", parent=self)
                return

        self._selected_solo = name
        if self.solo_gallery:
            self.solo_gallery._cache.clear()

        self._load_solo_gallery()
        self.solo_gallery.select_sprite(name)
        if self.config.has_section(f"Sprite_{name}"):
            self._load_sprite_config()
        else:
            self._reset_to_defaults()

        show_info(
            "Sprite added",
            f"'{name}' was added to your sprite library.",
            parent=self,
        )

    def _import_solo_zip(self, zip_path: str):
        import shutil
        from pathlib import Path

        if not zip_path.lower().endswith(".zip"):
            show_error("Error", "Selected file is not a .zip package.", parent=self)
            return

        name = os.path.splitext(os.path.basename(zip_path))[0]
        full_path = os.path.join(SPRITES_DIR, name)

        if os.path.exists(full_path):
            if not ask_yes_no(
                "Folder already exists",
                f"A sprite named '{name}' already exists.\nReplace it?",
                parent=self,
            ):
                return
            shutil.rmtree(full_path)

        os.makedirs(full_path, exist_ok=True)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmpdir)

                png_files = sorted(Path(tmpdir).rglob("*.png"))
                if not png_files:
                    shutil.rmtree(full_path, ignore_errors=True)
                    show_error(
                        "Error",
                        f"The ZIP '{os.path.basename(zip_path)}' has no PNG files.\n"
                        "A sprite package must contain at least one .png file.",
                        parent=self,
                    )
                    return

                for idx, src in enumerate(png_files, start=1):
                    dst_name = src.name
                    dst = Path(full_path) / dst_name
                    if dst.exists():
                        dst = Path(full_path) / f"{src.stem}_{idx}{src.suffix}"
                    shutil.copy2(src, dst)
        except Exception as e:
            shutil.rmtree(full_path, ignore_errors=True)
            show_error("Error", f"Could not import ZIP:\n{e}", parent=self)
            return

        self._selected_solo = name
        if self.solo_gallery:
            self.solo_gallery._cache.clear()

        self._load_solo_gallery()
        self.solo_gallery.select_sprite(name)
        if self.config.has_section(f"Sprite_{name}"):
            self._load_sprite_config()
        else:
            self._reset_to_defaults()

        show_info(
            "Sprite added",
            f"ZIP imported as '{name}' in your sprite library.",
            parent=self,
        )

    def _filter_solo(self, text: str):
        text = text.lower().strip()
        if not text:
            self._load_solo_gallery()
        else:
            sprites  = self._get_solo_list()
            filtered = [s for s in sprites if text in s.lower()]
            self.solo_gallery.load_sprites(filtered, self._selected_solo)
        self.solo_gallery.scroll_to_top()

    # =========================================================
    # Configuracion del solo
    # =========================================================

    def _write_solo_config(self, sprite_name: str) -> bool:
        """
        Lee los widgets de la UI y escribe la config del solo al disco.
        Silencioso — no muestra dialogos. Devuelve True si tuvo exito.
        """
        section = f"Sprite_{sprite_name}"
        if not self.config.has_section(section):
            self.config.add_section(section)

        cpu_delays = [
            (0,  20, int(self._cpu_entries[0].text() or 200)),
            (21, 40, int(self._cpu_entries[1].text() or 150)),
            (41, 60, int(self._cpu_entries[2].text() or 120)),
            (61, 80, int(self._cpu_entries[3].text() or 90)),
            (81, 100,int(self._cpu_entries[4].text() or 60)),
        ]

        dyn_val = "errante"
        for btn in self._dyn_group.buttons():
            if btn.isChecked():
                dyn_val = btn.property("_val")
                break

        delay_val = "cpu"
        for btn in self._delay_group.buttons():
            if btn.isChecked():
                delay_val = btn.property("_val")
                break

        self.config.set(section, "aspect_locked",      "1" if self._aspect_ratio_locked else "0")
        self.config.set(section, "frame_width",        self._width_entry.text()  or "150")
        self.config.set(section, "frame_height",       self._height_entry.text() or "150")
        self.config.set(section, "delay_mode",         delay_val)
        self.config.set(section, "fixed_delay",        self._fixed_delay_entry.text() or "30")
        self.config.set(section, "cpu_delays",         str(cpu_delays))
        self.config.set(section, "presentacion_delay", self._pres_delay_entry.text() or "2")
        self.config.set(section, "dynamic_mode",       dyn_val)
        self.config.set(section, "fps",                self._get_speed_bar(self._speed_btns))
        self.config.set("General", "active_sprite",    sprite_name)

        self._save_config_file()
        return True

    def _save_solo_config(self):
        """Boton Save Config — guarda y muestra confirmacion."""
        sprite_name = self._selected_solo.strip()
        if not sprite_name:
            show_warning("Warning", "Select a sprite first.", parent=self)
            return
        if sprite_name not in self._get_solo_list():
            show_error("Error", "Sprite does not exist.", parent=self)
            return
        self._write_solo_config(sprite_name)
        show_info("Saved", f"Configuration for '{sprite_name}' saved.", parent=self)

    def _load_sprite_config(self):
        sprite_name = self._selected_solo.strip()
        if not sprite_name:
            return

        section = f"Sprite_{sprite_name}"
        if not self.config.has_section(section):
            self._reset_to_defaults()
            return

        g = self.config[section]
        self._updating_size = True
        self._width_entry.setText(g.get("frame_width",  "150"))
        self._height_entry.setText(g.get("frame_height", "150"))
        self._updating_size = False

        delay_mode = g.get("delay_mode", "cpu")
        for btn in self._delay_group.buttons():
            if btn.property("_val") == delay_mode:
                btn.setChecked(True)

        dyn_mode = g.get("dynamic_mode", "errante")
        for btn in self._dyn_group.buttons():
            if btn.property("_val") == dyn_mode:
                btn.setChecked(True)

        self._fixed_delay_entry.setText(g.get("fixed_delay", "30"))
        self._pres_delay_entry.setText(g.get("presentacion_delay", "2"))

        saved_fps = g.get("fps", "60")
        self._set_speed_bar(self._speed_btns, saved_fps)

        try:
            import ast
            cpu_delays = ast.literal_eval(g.get(
                "cpu_delays",
                "[(0,20,200),(21,40,150),(41,60,120),(61,80,90),(81,100,60)]"
            ))
            for i, (_, _, ms) in enumerate(cpu_delays):
                if i < len(self._cpu_entries):
                    self._cpu_entries[i].setText(str(ms))
        except Exception:
            for ent, val in zip(self._cpu_entries, [200,150,120,90,60]):
                ent.setText(str(val))

        # Leer dimensiones reales del primer frame
        try:
            sprite_folder = os.path.join(SPRITES_DIR, sprite_name)
            images = sorted([
                f for f in os.listdir(sprite_folder)
                if f.lower().endswith((".png",".jpg",".jpeg",".gif",".bmp",".webp"))
            ])
            if images:
                from PIL import Image as PILImage
                with PILImage.open(os.path.join(sprite_folder, images[0])) as img:
                    self._real_img_width, self._real_img_height = img.size
            else:
                self._real_img_width = self._real_img_height = 0
        except Exception:
            self._real_img_width = self._real_img_height = 0

        # Restaurar estado del lock
        # Siempre recalcular el ratio desde las dimensiones reales del sprite activo
        if self._real_img_width > 0 and self._real_img_height > 0:
            self._aspect_ratio = self._real_img_width / self._real_img_height
        else:
            self._aspect_ratio = 1.0

        locked = g.get("aspect_locked", "0") == "1"
        self._aspect_ratio_locked = locked
        if locked:
            self._lock_btn.setText("locked")
            self._start_lock_pulse()
        else:
            self._lock_btn.setText("unlocked")
            self._stop_lock_pulse()

        self._update_delay_ui()
        self._status_bar.showMessage(f"Sprite loaded: {sprite_name}")

    def _reset_to_defaults(self):
        # Leer dimensiones reales del sprite antes de aplicar valores
        sprite_name = self._selected_solo.strip()
        if sprite_name:
            try:
                sprite_folder = os.path.join(SPRITES_DIR, sprite_name)
                images = sorted([
                    f for f in os.listdir(sprite_folder)
                    if f.lower().endswith((".png",".jpg",".jpeg",".gif",".bmp",".webp"))
                ])
                if images:
                    from PIL import Image as PILImage
                    with PILImage.open(os.path.join(sprite_folder, images[0])) as img:
                        self._real_img_width, self._real_img_height = img.size
                else:
                    self._real_img_width = self._real_img_height = 0
            except Exception:
                self._real_img_width = self._real_img_height = 0

        self._aspect_ratio_locked = True
        if self._real_img_width > 0 and self._real_img_height > 0:
            self._aspect_ratio = self._real_img_width / self._real_img_height
            # Calcular ancho manteniendo alto 150 como base
            self._updating_size = True
            new_w = round(150 * self._aspect_ratio)
            self._width_entry.setText(str(new_w))
            self._height_entry.setText("150")
            self._updating_size = False
        else:
            self._aspect_ratio = 1.0
            self._updating_size = True
            self._width_entry.setText("150")
            self._height_entry.setText("150")
            self._updating_size = False

        self._lock_btn.setText("locked")
        self._start_lock_pulse()
        for btn in self._delay_group.buttons():
            if btn.property("_val") == "cpu":
                btn.setChecked(True)
        for btn in self._dyn_group.buttons():
            if btn.property("_val") == "errante":
                btn.setChecked(True)
        self._fixed_delay_entry.setText("30")
        for ent, val in zip(self._cpu_entries, [200,150,120,90,60]):
            ent.setText(str(val))
        self._pres_delay_entry.setText("2")
        self._set_speed_bar(self._speed_btns, "60")
        self._update_delay_ui()

    def _update_delay_ui(self, *args):
        """Muestra solo el sub-panel de delay correspondiente al modo activo."""
        delay_val = "cpu"
        for btn in self._delay_group.buttons():
            if btn.isChecked():
                delay_val = btn.property("_val")
                break

        self._fixed_delay_card.setVisible(delay_val == "fixed")
        self._cpu_card.setVisible(delay_val == "cpu")
        self._pres_card.setVisible(delay_val == "presentacion")

    # =========================================================
    # Aspect ratio lock
    # =========================================================

    def _toggle_aspect_lock(self):
        self._aspect_ratio_locked = not self._aspect_ratio_locked
        if self._aspect_ratio_locked:
            if self._real_img_width > 0 and self._real_img_height > 0:
                self._aspect_ratio = self._real_img_width / self._real_img_height
            else:
                self._aspect_ratio = 1.0
            try:
                h     = int(self._height_entry.text())
                new_w = round(h * self._aspect_ratio)
                self._updating_size = True
                self._width_entry.setText(str(new_w))
                self._updating_size = False
            except (ValueError, ZeroDivisionError):
                self._updating_size = False
            self._lock_btn.setText("locked")
            self._start_lock_pulse()
        else:
            self._lock_btn.setText("unlocked")
            self._stop_lock_pulse()

    def _start_lock_pulse(self):
        """Aplica estilo azul al boton locked."""
        if self._lock_btn is None:
            return
        self._lock_btn.setStyleSheet(
            f"QPushButton {{ color: {theme.ACCENT}; background-color: transparent;"
            f" border: 1px solid {theme.ACCENT}; border-radius: {theme.RADIUS}px;"
            f" padding: 7px 16px; font-size: 10pt; min-height: 32px; }}"
            f"QPushButton:hover {{ background-color: {theme.ACCENT_DIM}; color: {theme.ACCENT}; }}"
            f"QPushButton:pressed {{ background-color: {theme.ACCENT}; color: #ffffff; }}"
        )

    def _stop_lock_pulse(self):
        """Restaura el estilo original del boton."""
        if self._lock_btn is None:
            return
        self._lock_btn.setStyleSheet(theme.BTN_STYLE)

    def _on_width_changed(self, text: str):
        if self._updating_size or not self._aspect_ratio_locked:
            return
        try:
            w     = int(text)
            new_h = round(w / self._aspect_ratio)
            self._updating_size = True
            self._height_entry.setText(str(new_h))
            self._updating_size = False
        except (ValueError, ZeroDivisionError):
            self._updating_size = False

    def _on_height_changed(self, text: str):
        if self._updating_size or not self._aspect_ratio_locked:
            return
        try:
            h     = int(text)
            new_w = round(h * self._aspect_ratio)
            self._updating_size = True
            self._width_entry.setText(str(new_w))
            self._updating_size = False
        except (ValueError, ZeroDivisionError):
            self._updating_size = False

    # =========================================================
    # Coordenadas
    # =========================================================

    def _start_coord_timer(self):
        """Inicia el QTimer que actualiza las coordenadas cada 500ms."""
        self._coord_timer = QTimer(self)
        self._coord_timer.timeout.connect(self._update_coordinates)
        self._coord_timer.start(500)

    def _update_coordinates(self):
        if self._coord_x_label is None or self._coord_y_label is None:
            return
        sprite_name = self._selected_solo.strip()
        if not sprite_name:
            return
        try:
            if os.path.exists(POSITIONS_FILE):
                temp = configparser.ConfigParser()
                temp.read(POSITIONS_FILE, encoding="utf-8")
                if temp.has_section(sprite_name):
                    x = temp.getint(sprite_name, "x", fallback=0)
                    y = temp.getint(sprite_name, "y", fallback=0)
                    self._coord_x_label.setText(str(x))
                    self._coord_y_label.setText(str(y))
        except Exception:
            pass

    def _save_current_position(self):
        sprite_name = self._selected_solo.strip()
        if not sprite_name:
            show_warning("Warning", "Select a sprite first.", parent=self)
            return
        if os.path.exists(POSITIONS_FILE):
            temp = configparser.ConfigParser()
            temp.read(POSITIONS_FILE, encoding="utf-8")
            if temp.has_section(sprite_name):
                x = temp.getint(sprite_name, "x", fallback=100)
                y = temp.getint(sprite_name, "y", fallback=100)
                show_info(
                    "Success", f"Position saved:\nX={x}, Y={y}", parent=self)
                return
        show_warning("Warning", "Run the sprite first.", parent=self)

    # =========================================================
    # Escenas
    # =========================================================

    def _load_scenes(self):
        if not os.path.exists(SCENES_FILE):
            with open(SCENES_FILE, "w", encoding="utf-8") as f:
                f.write("# Scenes configuration\n")
            return []
        cfg = configparser.ConfigParser()
        cfg.read(SCENES_FILE, encoding="utf-8")
        return [
            s.replace("Scene_", "")
            for s in cfg.sections()
            if s.startswith("Scene_")
        ]

    def _refresh_scenes_list(self):
        self.scenes_list = self._load_scenes()
        cfg = configparser.ConfigParser()
        if os.path.exists(SCENES_FILE):
            cfg.read(SCENES_FILE, encoding="utf-8")
        items = []
        for name in self.scenes_list:
            sprites_str = cfg.get(f"Scene_{name}", "sprites", fallback="")
            sprites = [s.strip() for s in sprites_str.split(",") if s.strip()]
            items.append((name, sprites))
        self._scenes_list_widget.load(items)

    def _on_scene_selected(self, name: str):
        if name and name in self.scenes_list:
            pass  # aqui puedes cargar config de la escena si en el futuro se necesita
            
    def _create_scene_window(self):
        """Dialogo para crear una nueva escena con QDialog nativo Qt."""
        from PySide6.QtWidgets import QDialog, QScrollArea

        win = QDialog(self)
        win.setWindowTitle("Create New Scene")
        win.setFixedSize(440, 548)
        win.setStyleSheet(theme.get_stylesheet())

        lay = QVBoxLayout(win)
        lay.setContentsMargins(theme.SP3, theme.SP3, theme.SP3, theme.SP3)
        lay.setSpacing(theme.SP2)

        lbl_title = QLabel("Create New Scene")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color:{theme.ACCENT};")
        lay.addWidget(lbl_title)
        lay.addWidget(_hsep())

        lbl_name = QLabel("Scene Name:")
        lbl_name.setFont(theme.FONT_SMALL)
        lay.addWidget(lbl_name)

        name_entry = QLineEdit()
        name_entry.setFixedHeight(34)
        lay.addWidget(name_entry)

        lbl_sprites = QLabel("Select Sprite:")
        lbl_sprites.setFont(theme.FONT_SMALL)
        lay.addWidget(lbl_sprites)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(260)
        scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.BG_RAISED};"
            f"border:1px solid {theme.BORDER_MID}; border-radius:{theme.RADIUS}px; }}"
            f"QScrollArea > QWidget > QWidget {{ background:{theme.BG_RAISED}; }}"
        )

        THUMB     = 72
        COLS      = 4
        CELL_W    = THUMB + 8
        CELL_H    = THUMB + 24  # espacio para el nombre debajo

        grid_container = QWidget()
        grid_container.setStyleSheet(f"background:{theme.BG_RAISED};")
        grid_lay = QGridLayout(grid_container)
        grid_lay.setContentsMargins(theme.SP1, theme.SP1, theme.SP1, theme.SP1)
        grid_lay.setSpacing(6)

        sprites      = self._get_solo_list()
        checkbox_map = {}

        def _load_thumb(sprite_name):
            """Carga el primer PNG del sprite como QPixmap THUMB x THUMB."""
            from PySide6.QtGui import QPixmap, QImage
            from PIL import Image as PILImage
            try:
                folder = os.path.join(SPRITES_DIR, sprite_name)
                pngs   = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
                if not pngs:
                    raise FileNotFoundError
                img = PILImage.open(os.path.join(folder, pngs[0])).convert("RGBA")
                bg_hex = theme.BG_RAISED
                bg_rgb = tuple(int(bg_hex.lstrip("#")[i:i+2], 16) for i in (0,2,4))
                bg = PILImage.new("RGBA", img.size, bg_rgb + (255,))
                bg.paste(img, mask=img.split()[3])
                bg.thumbnail((THUMB, THUMB), PILImage.Resampling.LANCZOS)
                data   = bg.tobytes("raw", "RGBA")
                qimg   = QImage(data, bg.width, bg.height, QImage.Format.Format_RGBA8888)
                qimg._ref = data
                return QPixmap.fromImage(qimg)
            except Exception:
                from PySide6.QtGui import QPixmap
                pm = QPixmap(THUMB, THUMB)
                pm.fill(theme.BG_SURFACE)
                return pm

        if not sprites:
            lbl_none = QLabel("No sprites available")
            lbl_none.setStyleSheet(f"color:{theme.TEXT_MUTED};")
            grid_lay.addWidget(lbl_none, 0, 0)
        else:
            for i, sp in enumerate(sprites):
                row, col = divmod(i, COLS)

                cell = QWidget()
                cell.setStyleSheet("background:transparent;")
                cell.setFixedSize(CELL_W, CELL_H)
                cell_lay = QVBoxLayout(cell)
                cell_lay.setContentsMargins(0, 0, 0, 0)
                cell_lay.setSpacing(2)

                # Miniatura con checkbox superpuesto
                thumb_container = QWidget()
                thumb_container.setFixedSize(THUMB, THUMB)
                thumb_container.setStyleSheet("background:transparent;")

                lbl_img = QLabel(thumb_container)
                lbl_img.setFixedSize(THUMB, THUMB)
                lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_img.setPixmap(_load_thumb(sp))

                chk = QCheckBox(thumb_container)
                chk.setStyleSheet("background:transparent;")
                chk.move(2, 2)

                # Nombre debajo
                lbl_name = QLabel(sp)
                lbl_name.setFont(theme.FONT_TINY)
                lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_name.setStyleSheet(f"color:{theme.TEXT_MUTED}; background:transparent;")
                lbl_name.setFixedWidth(CELL_W)
                lbl_name.setWordWrap(False)

                cell_lay.addWidget(thumb_container, 0, Qt.AlignmentFlag.AlignHCenter)
                cell_lay.addWidget(lbl_name,        0, Qt.AlignmentFlag.AlignHCenter)

                checkbox_map[sp] = chk
                grid_lay.addWidget(cell, row, col, Qt.AlignmentFlag.AlignTop)

        grid_lay.setRowStretch(grid_lay.rowCount(), 1)
        scroll.setWidget(grid_container)
        lay.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(theme.SP1)

        def save_scene():
            scene_name = name_entry.text().strip()
            if not scene_name:
                show_warning("Warning", "Enter a name.", parent=win)
                return
            selected_sprites = [
                n for n, c in checkbox_map.items() if c.isChecked()
            ]
            if not selected_sprites:
                show_warning("Warning", "Select at least one sprite.", parent=win)
                return
            cfg = configparser.ConfigParser()
            if os.path.exists(SCENES_FILE):
                cfg.read(SCENES_FILE, encoding="utf-8")
            section = f"Scene_{scene_name}"
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, "sprites", ",".join(selected_sprites))
            with open(SCENES_FILE, "w", encoding="utf-8") as f:
                cfg.write(f)
            show_info("Success", f"Scene '{scene_name}' created!", parent=win)
            win.accept()
            self._refresh_scenes_list()

        btn_save = QPushButton("Save")
        btn_save.setFont(theme.FONT_SMALL)
        btn_save.setFixedSize(140, 40)
        btn_save.setStyleSheet(theme.BTN_STYLE)
        btn_save.clicked.connect(save_scene)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(theme.FONT_SMALL)
        btn_cancel.setFixedSize(140, 40)
        btn_cancel.setStyleSheet(theme.BTN_STYLE)
        btn_cancel.clicked.connect(win.reject)

        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        win.exec()

    def _run_scene(self):
        row = self._scenes_list_widget.current_row()
        if row < 0 or not self.scenes_list:
            show_warning("Warning", "Select a scene to run.", parent=self)
            return

        scene_name = self.scenes_list[row]
        cfg = configparser.ConfigParser()
        cfg.read(SCENES_FILE, encoding="utf-8")
        section = f"Scene_{scene_name}"

        if not cfg.has_section(section):
            show_error("Error", "Scene not found.", parent=self)
            return

        sprites_str = cfg.get(section, "sprites", fallback="")
        sprite_list = [s.strip() for s in sprites_str.split(",") if s.strip()]

        if not sprite_list:
            show_warning("Warning", "Scene has no sprites.", parent=self)
            return

        import time
        exe, use_pythonw = self._get_solo_executable()
        if exe is None:
            return

        prev = len(self.process_manager.get_running_sprites())

        launchable = [sp for sp in sprite_list if sp in self._get_solo_list()]
        sync_group = f"scene_{int(time.time()*1000)}"
        sync_expected = max(1, len(launchable))

        for sp in launchable:
            if sp not in self._get_solo_list():
                continue
            try:
                if use_pythonw:
                    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                    subprocess.Popen(
                        [pythonw, exe, sp, "--scene", scene_name, "--sync-group", sync_group, "--sync-expected", str(sync_expected)],
                        cwd=BASE_DIR
                    )
                else:
                    subprocess.Popen(
                        [exe, sp, "--scene", scene_name, "--sync-group", sync_group, "--sync-expected", str(sync_expected)],
                        cwd=BASE_DIR
                    )
            except Exception as e:
                print(f"Error launching {sp}: {e}")
            time.sleep(0.3)

        self._status_bar.showMessage(
            f"Scene '{scene_name}' launching...",
            3500
        )
        _show_launch_toast(
            self,
            "Spryta ejecutándose...",
            f"Scene '{scene_name}' · {len(sprite_list)} sprite(s)"
        )
        self._start_process_watcher(prev)

    def _delete_scene(self):
        row = self._scenes_list_widget.current_row()
        if row < 0 or not self.scenes_list:
            show_warning("Warning", "Select a scene to delete.", parent=self)
            return

        scene_name = self.scenes_list[row]
        if not ask_yes_no("Confirm Delete", f"Delete scene '{scene_name}'?", parent=self):
            return

        cfg = configparser.ConfigParser()
        cfg.read(SCENES_FILE, encoding="utf-8")
        section = f"Scene_{scene_name}"
        if cfg.has_section(section):
            cfg.remove_section(section)
            with open(SCENES_FILE, "w", encoding="utf-8") as f:
                cfg.write(f)
            show_info("Success", f"Scene '{scene_name}' deleted.", parent=self)
            self._refresh_scenes_list()

    # =========================================================
    # Reel
    # =========================================================

    def _load_reel(self):
        if not os.path.exists(REEL_FILE):
            with open(REEL_FILE, "w", encoding="utf-8") as f:
                f.write("# Solo Reel Configuration\n")
            return []
        self.reel_config.read(REEL_FILE, encoding="utf-8")
        return [
            s.replace("Reel_", "")
            for s in self.reel_config.sections()
            if s.startswith("Reel_")
        ]

    def _refresh_reel_list(self):
        self.reel_list = self._load_reel()
        self.reel_config.read(REEL_FILE, encoding="utf-8")
        items = []
        for name in self.reel_list:
            sprites_str = self.reel_config.get(f"Reel_{name}", "sprites", fallback="")
            sprites = [s.strip() for s in sprites_str.split(",") if s.strip()]
            items.append((name, sprites))
        self._reel_list_widget.load(items)

    def _on_reel_selected_name(self, name: str):
        if name and name in self.reel_list:
            self.selected_reel_name = name
            self._load_reel_config_to_ui(name)
        
    def _on_reel_selected_name(self, name: str):
        if name and name in self.reel_list:
            self.selected_reel_name = name
            self._load_reel_config_to_ui(name)

    def _load_reel_config_to_ui(self, reel_name: str):
        pc = configparser.ConfigParser()
        if os.path.exists(REEL_CONFIG_FILE):
            pc.read(REEL_CONFIG_FILE, encoding="utf-8")
        section = f"Reel_{reel_name}"

        # Actualizar coordenadas
        self._pl_coord_x_label.setText("--")
        self._pl_coord_y_label.setText("--")
        if os.path.exists(REEL_POSITIONS_FILE):
            pp = configparser.ConfigParser()
            pp.read(REEL_POSITIONS_FILE, encoding="utf-8")
            if pp.has_section(reel_name):
                x = pp.getint(reel_name, "x", fallback=0)
                y = pp.getint(reel_name, "y", fallback=0)
                self._pl_coord_x_label.setText(str(x))
                self._pl_coord_y_label.setText(str(y))

        if not pc.has_section(section):
            for btn in self._pl_dyn_group.buttons():
                if btn.property("_val") == "errante":
                    btn.setChecked(True)
            self._set_speed_bar(self._pl_speed_btns, "60")
            return

        g = pc[section]

        dyn = g.get("dynamic_mode", "errante")
        for btn in self._pl_dyn_group.buttons():
            if btn.property("_val") == dyn:
                btn.setChecked(True)

        saved_fps = g.get("fps", "60")
        self._set_speed_bar(self._pl_speed_btns, saved_fps)

        pass  # Delay mode se toma de cada sprite individual

    def _save_reel_config_from_ui(self, reel_name: str):
        """Guarda config del Reel usando los widgets _pl_*."""
        section = f"Reel_{reel_name}"
        pc = configparser.ConfigParser()
        if os.path.exists(REEL_CONFIG_FILE):
            pc.read(REEL_CONFIG_FILE, encoding="utf-8")
        if not pc.has_section(section):
            pc.add_section(section)

        dyn_val = "errante"
        for btn in self._pl_dyn_group.buttons():
            if btn.isChecked():
                dyn_val = btn.property("_val")
                break

        # Frame size y Delay Mode NO se guardan — se toman de cada sprite individual
        pc.set(section, "dynamic_mode", dyn_val)
        pc.set(section, "fps",          self._get_speed_bar(self._pl_speed_btns))

        with open(REEL_CONFIG_FILE, "w", encoding="utf-8") as f:
            pc.write(f)

    def _save_selected_reel_config(self):
        """Boton Save Config de la pagina de Reel."""
        if not self.selected_reel_name:
            show_warning("Warning", "Select a Reel first.", parent=self)
            return
        self._save_reel_config_from_ui(self.selected_reel_name)
        show_info("Success", f"Config saved for '{self.selected_reel_name}'.", parent=self)

    def _save_current_reel_position(self):
        """Guarda la posicion actual del Reel seleccionado."""
        if not self.selected_reel_name:
            show_warning("Warning", "Select a Reel first.", parent=self)
            return
        if os.path.exists(REEL_POSITIONS_FILE):
            pp = configparser.ConfigParser()
            pp.read(REEL_POSITIONS_FILE, encoding="utf-8")
            if pp.has_section(self.selected_reel_name):
                x = pp.getint(self.selected_reel_name, "x", fallback=100)
                y = pp.getint(self.selected_reel_name, "y", fallback=100)
                show_info("Success", f"Position saved:  X={x}  Y={y}", parent=self)
                return
        show_warning("Warning", "Run the Reel first.", parent=self)



    def _create_reel_window(self):
        """Dialogo para crear una nueva playlist con QDialog nativo Qt."""
        from PySide6.QtWidgets import QDialog, QAbstractItemView

        win = QDialog(self)
        win.setWindowTitle("Create New Reel")
        win.setFixedSize(520, 620)
        win.setStyleSheet(theme.get_stylesheet())

        lay = QVBoxLayout(win)
        lay.setContentsMargins(theme.SP3, theme.SP3, theme.SP3, theme.SP3)
        lay.setSpacing(theme.SP1)

        lbl_title = QLabel("Create New Reel")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color:{theme.ACCENT};")
        lay.addWidget(lbl_title)
        lay.addWidget(_hsep())

        # ── Nombre y ciclos en una fila ───────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(theme.SP2)

        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        lbl_name = QLabel("Reel Name:")
        lbl_name.setFont(theme.FONT_SMALL)
        name_entry = QLineEdit()
        name_entry.setFixedHeight(34)
        name_col.addWidget(lbl_name)
        name_col.addWidget(name_entry)

        cycles_col = QVBoxLayout()
        cycles_col.setSpacing(4)
        lbl_cycles = QLabel("Cycles per sprite:")
        lbl_cycles.setFont(theme.FONT_SMALL)
        cycles_entry = QLineEdit("10")
        cycles_entry.setValidator(QIntValidator(1, 9999))
        cycles_entry.setFixedSize(80, 34)
        cycles_col.addWidget(lbl_cycles)
        cycles_col.addWidget(cycles_entry)

        top_row.addLayout(name_col, 1)
        top_row.addLayout(cycles_col, 0)
        lay.addLayout(top_row)

        # ── Estilo compartido para ambas listas ───────────────
        list_style = f"""
            QListWidget {{
                background:{theme.BG_RAISED}; color:{theme.TEXT_BRIGHT};
                border:1px solid {theme.BORDER_MID};
                border-radius:{theme.RADIUS}px;
                outline:none; padding:4px;
            }}
            QListWidget::item {{
                padding:6px; border-radius:{theme.RADIUS_SMALL}px;
            }}
            QListWidget::item:hover   {{ background:{theme.BG_HOVER}; }}
            QListWidget::item:selected {{ background:{theme.ACCENT_DIM}; }}
        """

        # ── Available Sprites — grid de miniaturas ───────────
        lbl_avail = QLabel("Available Sprite:  (doble clic para agregar)")
        lbl_avail.setFont(theme.FONT_SMALL)
        lbl_avail.setStyleSheet(f"color:{theme.TEXT_NORMAL};")
        lay.addWidget(lbl_avail)

        THUMB  = 72
        COLS   = 5
        CELL_W = THUMB + 8
        CELL_H = THUMB + 8

        def _load_thumb_pl(sprite_name):
            from PySide6.QtGui import QPixmap, QImage
            from PIL import Image as PILImage
            try:
                folder = os.path.join(SPRITES_DIR, sprite_name)
                pngs   = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
                if not pngs:
                    raise FileNotFoundError
                img = PILImage.open(os.path.join(folder, pngs[0])).convert("RGBA")
                bg_hex = theme.BG_RAISED
                bg_rgb = tuple(int(bg_hex.lstrip("#")[i:i+2], 16) for i in (0,2,4))
                bg = PILImage.new("RGBA", img.size, bg_rgb + (255,))
                bg.paste(img, mask=img.split()[3])
                bg.thumbnail((THUMB, THUMB), PILImage.Resampling.LANCZOS)
                data = bg.tobytes("raw", "RGBA")
                qimg = QImage(data, bg.width, bg.height, QImage.Format.Format_RGBA8888)
                qimg._ref = data
                return QPixmap.fromImage(qimg)
            except Exception:
                from PySide6.QtGui import QPixmap
                pm = QPixmap(THUMB, THUMB)
                pm.fill(theme.BG_SURFACE)
                return pm

        avail_scroll = QScrollArea()
        avail_scroll.setWidgetResizable(True)
        avail_scroll.setFixedHeight(180)
        avail_scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.BG_RAISED};"
            f"border:1px solid {theme.BORDER_MID}; border-radius:{theme.RADIUS}px; }}"
        )

        avail_container = QWidget()
        avail_container.setStyleSheet(f"background:{theme.BG_RAISED};")
        avail_grid = QGridLayout(avail_container)
        avail_grid.setContentsMargins(theme.SP1, theme.SP1, theme.SP1, theme.SP1)
        avail_grid.setSpacing(6)

        sprites = self._get_solo_list()
        for i, sp in enumerate(sprites):
            row, col = divmod(i, COLS)
            cell = QWidget()
            cell.setStyleSheet("background:transparent;")
            cell.setFixedSize(CELL_W, CELL_H)
            cell_lay = QVBoxLayout(cell)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setSpacing(0)

            lbl_img = QLabel()
            lbl_img.setFixedSize(THUMB, THUMB)
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_img.setPixmap(_load_thumb_pl(sp))
            lbl_img.setProperty("_sprite", sp)
            lbl_img.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl_img.setStyleSheet(
                f"border:2px solid transparent; border-radius:{theme.RADIUS}px;"
            )
            lbl_img.setMouseTracking(True)

            def make_hover_enter(l):
                def h(e): l.setStyleSheet(f"border:2px solid {theme.ACCENT}; border-radius:{theme.RADIUS}px;")
                return h
            def make_hover_leave(l):
                def h(e): l.setStyleSheet(f"border:2px solid transparent; border-radius:{theme.RADIUS}px;")
                return h

            lbl_img.enterEvent = make_hover_enter(lbl_img)
            lbl_img.leaveEvent = make_hover_leave(lbl_img)

            def make_dbl_click(sprite_name):
                def handler(event):
                    selected_list.addItem(QListWidgetItem(sprite_name))
                return handler

            lbl_img.mouseDoubleClickEvent = make_dbl_click(sp)
            cell_lay.addWidget(lbl_img, 0, Qt.AlignmentFlag.AlignHCenter)
            avail_grid.addWidget(cell, row, col, Qt.AlignmentFlag.AlignTop)

        avail_grid.setRowStretch(avail_grid.rowCount(), 1)
        avail_scroll.setWidget(avail_container)
        lay.addWidget(avail_scroll)

        # ── Label fuera y entre los dos campos ───────────────
        lay.addSpacing(4)
        lbl_sel = QLabel("Reel Order:  (doble clic para quitar  |  arrastrar para reordenar)")
        lbl_sel.setFont(theme.FONT_SMALL)
        lbl_sel.setStyleSheet(f"color:{theme.TEXT_NORMAL};")
        lay.addWidget(lbl_sel)

        # ── Reel Order — fila horizontal con drag-drop ───
        # Scroll horizontal con ruedita del mouse
        class _HScrollArea(QScrollArea):
            def wheelEvent(self, event):
                sb = self.horizontalScrollBar()
                delta = event.angleDelta().y()
                sb.setValue(sb.value() - delta // 2)

        sel_scroll = _HScrollArea()
        sel_scroll.setWidgetResizable(True)
        sel_scroll.setFixedHeight(CELL_H + theme.SP2 + 8)
        sel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sel_scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.BG_RAISED};"
            f"border:1px solid {theme.BORDER_MID}; border-radius:{theme.RADIUS}px; }}"
        )

        # Lista interna para mantener el orden
        selected_list = []

        class _SelRow(QWidget):
            """Fila horizontal con drag-drop para reordenar miniaturas."""
            def __init__(self):
                super().__init__()
                self.setStyleSheet(f"background:{theme.BG_RAISED};")
                self.setAcceptDrops(True)
                self._hlay      = QHBoxLayout(self)
                self._hlay.setContentsMargins(theme.SP1, theme.SP1, theme.SP1, theme.SP1 + 8)
                self._hlay.setSpacing(6)
                self._hlay.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self._insert_idx = -1   # posicion del indicador visual

            def rebuild(self):
                while self._hlay.count():
                    item = self._hlay.takeAt(0)
                    if item.widget():
                        item.widget().setParent(None)
                for sp in selected_list:
                    cell = _DragCell(sp, self)
                    self._hlay.addWidget(cell)

            def _dest_index(self, x):
                """Calcula el indice de insercion segun la posicion X."""
                for i in range(self._hlay.count()):
                    item = self._hlay.itemAt(i)
                    if item and item.widget():
                        mid = item.widget().x() + item.widget().width() / 2
                        if x < mid:
                            return i
                return self._hlay.count()

            def _set_insert_indicator(self, idx):
                """Resalta la celda de destino con borde acento."""
                if idx == self._insert_idx:
                    return
                self._insert_idx = idx
                for i in range(self._hlay.count()):
                    item = self._hlay.itemAt(i)
                    if item and item.widget():
                        cell = item.widget()
                        is_target = (i == idx)
                        cell.setStyleSheet(
                            f"background:{theme.ACCENT_DIM}; border-radius:{theme.RADIUS}px;"
                            if is_target else "background:transparent;"
                        )

            def _clear_insert_indicator(self):
                self._insert_idx = -1
                for i in range(self._hlay.count()):
                    item = self._hlay.itemAt(i)
                    if item and item.widget():
                        item.widget().setStyleSheet("background:transparent;")

            def dragEnterEvent(self, event):
                if event.mimeData().hasText():
                    event.acceptProposedAction()

            def dragMoveEvent(self, event):
                if event.mimeData().hasText():
                    idx = self._dest_index(event.position().x())
                    self._set_insert_indicator(idx)
                    event.acceptProposedAction()

            def dragLeaveEvent(self, event):
                self._clear_insert_indicator()

            def dropEvent(self, event):
                self._clear_insert_indicator()
                src = event.mimeData().text()
                if src not in selected_list:
                    return
                dest_idx = self._dest_index(event.position().x())
                src_idx  = selected_list.index(src)
                selected_list.pop(src_idx)
                if dest_idx > src_idx:
                    dest_idx -= 1
                selected_list.insert(dest_idx, src)
                self.rebuild()
                event.acceptProposedAction()

        class _DragCell(QWidget):
            """Celda de miniatura arrastrable con efecto hover."""
            def __init__(self, sprite_name, parent_row):
                super().__init__(parent_row)
                self._sprite = sprite_name
                self._row    = parent_row
                self.setFixedSize(CELL_W, CELL_H)
                self.setStyleSheet("background:transparent;")
                lay_ = QVBoxLayout(self)
                lay_.setContentsMargins(0, 0, 0, 0)
                lay_.setSpacing(0)
                lbl = QLabel()
                lbl.setFixedSize(THUMB, THUMB)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setPixmap(_load_thumb_pl(sprite_name))
                lbl.setStyleSheet(
                    f"border:2px solid transparent;"
                    f"border-radius:{theme.RADIUS}px;"
                )
                lay_.addWidget(lbl, 0, Qt.AlignmentFlag.AlignHCenter)
                self._lbl = lbl

            def enterEvent(self, event):
                self._lbl.setStyleSheet(
                    f"border:2px solid {theme.ACCENT};"
                    f"border-radius:{theme.RADIUS}px;"
                )

            def leaveEvent(self, event):
                self._lbl.setStyleSheet(
                    f"border:2px solid transparent;"
                    f"border-radius:{theme.RADIUS}px;"
                )

            def mouseDoubleClickEvent(self, event):
                if self._sprite in selected_list:
                    selected_list.remove(self._sprite)
                    self._row.rebuild()

            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    # Limpiar hover antes de arrastrar
                    self._lbl.setStyleSheet(
                        f"border:2px solid transparent;"
                        f"border-radius:{theme.RADIUS}px;"
                    )
                    drag = QDrag(self)
                    mime = QMimeData()
                    mime.setText(self._sprite)
                    drag.setMimeData(mime)
                    drag.setPixmap(self._lbl.pixmap().scaled(
                        THUMB // 2, THUMB // 2,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    ))
                    drag.exec(Qt.DropAction.MoveAction)

        sel_row = _SelRow()
        sel_scroll.setWidget(sel_row)
        lay.addWidget(sel_scroll)

        def _rebuild_sel_row():
            sel_row.rebuild()

        # Conexiones — el doble clic en available agrega al orden
        def make_dbl_add(sprite_name):
            def handler(event):
                selected_list.append(sprite_name)
                _rebuild_sel_row()
            return handler

        # Reasignar doble clic en available con la nueva funcion
        for i in range(avail_grid.count()):
            cell_w = avail_grid.itemAt(i).widget()
            if cell_w:
                lbl = cell_w.findChild(QLabel)
                if lbl:
                    sp = lbl.property("_sprite")
                    if sp:
                        lbl.mouseDoubleClickEvent = make_dbl_add(sp)

        # ── Botones Save / Cancel ─────────────────────────────
        lay.addSpacing(theme.SP1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(theme.SP1)

        def save_reel():
            reel_name = name_entry.text().strip()
            if not reel_name:
                show_warning("Warning", "Enter a Reel name.", parent=win)
                return
            if len(selected_list) == 0:
                show_warning("Warning", "Add at least one sprite.", parent=win)
                return
            sprites_list = list(selected_list)
            cycles = int(cycles_entry.text() or "10")
            self.reel_config.read(REEL_FILE, encoding="utf-8")
            section = f"Reel_{reel_name}"
            if not self.reel_config.has_section(section):
                self.reel_config.add_section(section)
            self.reel_config.set(section, "sprites", ",".join(sprites_list))
            self.reel_config.set(section, "cycles",  str(cycles))
            with open(REEL_FILE, "w", encoding="utf-8") as f:
                self.reel_config.write(f)

            self.reel_params_config.read(REEL_CONFIG_FILE, encoding="utf-8")
            if not self.reel_params_config.has_section(section):
                self.reel_params_config.add_section(section)
                sprite_sec = f"Sprite_{sprites_list[0]}"
                if self.config.has_section(sprite_sec):
                    for key, val in self.config.items(sprite_sec):
                        self.reel_params_config.set(section, key, val)
                with open(REEL_CONFIG_FILE, "w", encoding="utf-8") as f:
                    self.reel_params_config.write(f)

            show_info("Success", f"Reel '{reel_name}' created!", parent=win)
            win.accept()
            self._refresh_reel_list()

        btn_save = QPushButton("Save Reel")
        btn_save.setFont(theme.FONT_SMALL)
        btn_save.setFixedSize(140, 40)
        btn_save.setStyleSheet(theme.BTN_STYLE)
        btn_save.clicked.connect(save_reel)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(theme.FONT_SMALL)
        btn_cancel.setFixedSize(140, 40)
        btn_cancel.setStyleSheet(theme.BTN_STYLE)
        btn_cancel.clicked.connect(win.reject)

        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        win.exec()

    def _run_reel(self):
        row = self._reel_list_widget.current_row()
        reel_name = (
            self.selected_reel_name
            if self.selected_reel_name
            else (self.reel_list[row] if row >= 0 else None)
        )
        if not reel_name:
            show_warning("Warning", "Select a Reel to run.", parent=self)
            return

        self._save_reel_config_from_ui(reel_name)
        self.reel_config.read(REEL_FILE, encoding="utf-8")
        section = f"Reel_{reel_name}"
        if not self.reel_config.has_section(section):
            show_error("Error", "Reel not found.", parent=self)
            return

        sprites_str = self.reel_config.get(section, "sprites", fallback="")
        cycles      = self.reel_config.getint(section, "cycles", fallback=10)
        sprite_list = [s.strip() for s in sprites_str.split(",") if s.strip()]

        if not sprite_list:
            show_warning("Warning", "Reel has no sprites.", parent=self)
            return

        exe, use_pythonw = self._get_solo_executable()
        if exe is None:
            return

        prev = len(self.process_manager.get_running_sprites())

        try:
            if use_pythonw:
                pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                subprocess.Popen([pythonw, exe, "--playlist", reel_name], cwd=BASE_DIR)
            else:
                subprocess.Popen([exe, "--playlist", reel_name], cwd=BASE_DIR)
            self._status_bar.showMessage(
                f"Reel '{reel_name}' launching...",
                3500
            )
            _show_launch_toast(
                self,
                "Spryta ejecutándose...",
                f"Reel '{reel_name}' iniciado"
            )
            self._start_process_watcher(prev)
        except Exception as e:
            show_error("Error", f"Could not start Reel: {e}", parent=self)

    def _delete_reel(self):
        row = self._reel_list_widget.current_row()
        if row < 0 or not self.reel_list:
            show_warning("Warning", "Select a Reel to delete.", parent=self)
            return
        reel_name = self.reel_list[row]
        if not ask_yes_no(
            "Confirm Delete", f"Delete Reel '{reel_name}'?", parent=self
        ):
            return
        self.reel_config.read(REEL_FILE, encoding="utf-8")
        section = f"Reel_{reel_name}"
        if self.reel_config.has_section(section):
            self.reel_config.remove_section(section)
            with open(REEL_FILE, "w", encoding="utf-8") as f:
                self.reel_config.write(f)
            show_info("Success", f"Reel '{reel_name}' deleted.", parent=self)
            self._refresh_reel_list()

    # =========================================================
    # Paneles y herramientas
    # =========================================================

    def _update_tool_active_states(self):
        """Sincroniza el estado activo de los tres botones de herramientas."""
        cf_active   = self.left_panel.is_visible() and self.left_panel.current_tool == "create_frame"
        aa_active   = self.left_panel.is_visible() and self.left_panel.current_tool == "ambient_audio"
        proc_active = self.right_panel.is_visible()
        theme.set_active(self._btn_cf,   cf_active)
        theme.set_active(self._btn_aa,   aa_active)
        theme.set_active(self._btn_proc, proc_active)

    def _show_create_frame(self):
        if self.left_panel.is_visible() and self.left_panel.current_tool == "create_frame":
            self.left_panel.close()
        else:
            self.left_panel.show("create_frame", self)
        self._update_tool_active_states()

    def _show_ambient_audio(self):
        if self.left_panel.is_visible() and self.left_panel.current_tool == "ambient_audio":
            self.left_panel.close()
        else:
            self.left_panel.show("ambient_audio", self)
        self._update_tool_active_states()

    def _toggle_process_panel(self):
        if self.right_panel.is_visible():
            self.right_panel.close()
        else:
            self.right_panel.show(self)
        self._update_tool_active_states()

    def _on_left_panel_closed(self):
        self._update_tool_active_states()

    def _on_solo_created(self):
        if self.solo_gallery:
            self.solo_gallery._cache.clear()

        self._load_solo_gallery()

    def _on_right_panel_closed(self):
        self._update_tool_active_states()

    def _on_lasso_sprites_launched(self, expected_count: int, playlist_name: str = None, song: str = None):
        """
        Llamado por LassoManager cuando lanza uno o mas sprites desde lasso.
        Arranca el watcher igual que cuando se lanza un solo, una escena
        o un reel, para que el panel Running se abra automaticamente.
        """
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(
                0,
                lambda: self._on_lasso_sprites_launched(expected_count, playlist_name, song)
            )
            return

        prev = len(self.process_manager.get_running_sprites())
        self._start_process_watcher(prev, expected_count)
        title = "Spryta ejecutándose..."
        if song:
            subtitle = f"Lasso · {song}"
        elif playlist_name:
            subtitle = f"Lasso · Playlist '{playlist_name}'"
        else:
            subtitle = f"Lasso · Cargando {expected_count} sprite(s)"
        _show_launch_toast(self, title, subtitle)
    
    def _refresh_right_panel(self, force_open: bool = False):
        """
        Si el panel de Running esta visible lo refresca.
        Solo lo abre si force_open=True. De lo contrario respeta
        la decision del usuario de haberlo cerrado.
        """
        if self.right_panel.is_visible():
            self.right_panel.refresh()
        elif force_open:
            self.right_panel.show(self)
        self._update_tool_active_states()

    def _start_process_watcher(self, previous_count: int, expected_count: int = 1):
        # Detener cualquier watcher anterior antes de crear uno nuevo
        if hasattr(self, "_watcher_timer") and self._watcher_timer is not None:
            self._watcher_timer.stop()
            self._watcher_timer = None

        self._watcher_attempts = 0
        self._watcher_prev     = previous_count
        self._watcher_expected = max(1, expected_count)

        self._watcher_timer = QTimer(self)
        self._watcher_timer.setInterval(1000)
        self._watcher_timer.timeout.connect(self._poll_process_panel)
        self._watcher_timer.start()

    def _poll_process_panel(self):
        """Llamado cada 1 segundo por el watcher timer."""
        self._watcher_attempts += 1

        current_count = len(self.process_manager.get_running_sprites())
        target        = self._watcher_prev + self._watcher_expected

        if current_count >= target:
            # Todos los solos esperados estan registrados.
            self._watcher_timer.stop()
            self._watcher_timer = None
            self._refresh_right_panel(force_open=True)
            self.save_session()
            return

        if self._watcher_attempts >= 30:
            # Timeout: abrir el panel con lo que haya disponible.
            self._watcher_timer.stop()
            self._watcher_timer = None
            if current_count > self._watcher_prev:
                self._refresh_right_panel(force_open=True)
                self.save_session()

    # =========================================================
    # Ejecucion de solo
    # =========================================================

    def _get_solo_executable(self):
        exe, use_pythonw = resolve_runtime_executable(
            BASE_DIR, "main_runtime", "main.exe", "main.pyw"
        )
        if exe is not None:
            return exe, use_pythonw

        show_error(
            "Error",
            "Sprite executable not found.\n"
            "Looking for: 'main_runtime\\main.exe', 'main.exe' or 'main.pyw'",
            parent=self,
        )
        return None, None

    def _run_main(self):
        sprite = self._selected_solo.strip()
        if not sprite:
            show_warning("Warning", "Select a sprite before running.", parent=self)
            return
        if sprite not in self._get_solo_list():
            show_error("Error", "Sprite does not exist.", parent=self)
            return

        # Guardar todos los ajustes de la UI antes de ejecutar
        self._write_solo_config(sprite)

        exe, use_pythonw = self._get_solo_executable()
        if exe is None:
            return

        prev = len(self.process_manager.get_running_sprites())

        try:
            if use_pythonw:
                pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                subprocess.Popen([pythonw, exe, sprite], cwd=BASE_DIR)
            else:
                subprocess.Popen([exe, sprite], cwd=BASE_DIR)
        except Exception as e:
            show_error("Error", f"Could not launch sprite:\n{e}", parent=self)
            return

        self._status_bar.showMessage(
            f"Ejecutando '{sprite}'... la ventana aparecerá cuando termine de cargar.",
            5000
        )
        _show_launch_toast(
            self,
            "Spryta ejecutándose...",
            f"Cargando '{sprite}'..."
        )
        
        self._start_process_watcher(prev)

    # =========================================================
    # Tema
    # =========================================================

    # =========================================================
    # Bandeja del sistema
    # =========================================================

    def show_window(self):
        """
        Muestra la ventana principal sin pantallazo blanco.

        Patron: opacidad a 0 antes del show, luego restaura en el
        siguiente ciclo de eventos cuando el contenido ya esta pintado.
        Usado por el tray, el flag IPC y cualquier otro punto de entrada.
        """
        self.setWindowOpacity(0)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, lambda: self.setWindowOpacity(1))

    def hide_window(self):
        """
        Oculta la ventana principal y todos los paneles flotantes.
        Si Ambient Audio esta activo, solo oculta el panel sin detener el audio.
        """
        if self.left_panel.is_visible():
            if self.left_panel.current_tool == "ambient_audio":
                self.left_panel.hide_panel()
            else:
                self.left_panel.close()
        if self.right_panel.is_visible():
            self.right_panel.close()
        self.hide()

    def _restore_main_window(self):
        """Alias para compatibilidad con _check_show_flag."""
        self.show_window()

    def _to_background(self):
        """Oculta la ventana principal y los paneles, igual que el tray."""
        self.hide_window()

    def closeEvent(self, event):
        """Intercepta el boton X y cierra la aplicacion correctamente."""
        event.ignore()
        self._finalize_and_exit()
        
    def nativeEvent(self, event_type, message):
        """
        Intercepta mensajes nativos de Windows.
        WM_QUERYENDSESSION y WM_ENDSESSION se envian cuando Windows
        se apaga o reinicia, permitiendo guardar la sesion antes de
        que los procesos sean terminados por la fuerza.
        """
        import ctypes
        import ctypes.wintypes
        WM_QUERYENDSESSION = 0x0011
        WM_ENDSESSION      = 0x0016

        if event_type == b"windows_generic_MSG":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message in (WM_QUERYENDSESSION, WM_ENDSESSION):
                    self.save_session()
            except Exception:
                pass

        return super().nativeEvent(event_type, message)

    # =========================================================
    # Autostart y sesion
    # =========================================================

    def _get_app_path(self):
        base_dir    = get_base_dir()
        startup_path, use_pythonw = resolve_runtime_executable(
            base_dir,
            "startup_runtime",
            "spryta_startup.exe",
            "spryta_startup.pyw",
        )
        if not startup_path:
            return ""
        if not use_pythonw:
            return f'"{startup_path}"'

        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            import shutil
            found = shutil.which("pythonw")
            pythonw = found if found else sys.executable.replace(
                "python.exe", "pythonw.exe"
            )
        return f'"{pythonw}" "{startup_path}"'

    def _is_autostart_enabled(self):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ,
            )
            winreg.QueryValueEx(key, "Spryta")
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def _toggle_autostart(self, checked: bool):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            if checked:
                app_path = self._get_app_path()
                if not app_path:
                    raise FileNotFoundError(
                        "No se encontró spryta_startup.exe ni spryta_startup.pyw."
                    )
                winreg.SetValueEx(key, "Spryta", 0, winreg.REG_SZ, app_path)
                self.save_session()
                show_info(
                    "Start with Windows",
                    "Spryta will start automatically with Windows.",
                    parent=self,
                )
            else:
                try:
                    winreg.DeleteValue(key, "Spryta")
                except FileNotFoundError:
                    pass
                self._clear_session()
                show_info(
                    "Start with Windows",
                    "Spryta will no longer start with Windows.",
                    parent=self,
                )
            winreg.CloseKey(key)
        except Exception as e:
            show_error("Error", f"Could not modify registry:\n{e}", parent=self)
            self._autostart_chk.setChecked(not checked)

    def _finalize_save_session(self):
        """
        Guarda session.ini leyendo sprites_running.txt directamente como JSON,
        sin usar psutil. Se llama ANTES de cerrar cualquier proceso para evitar
        condiciones de carrera donde psutil puede reportar procesos como muertos
        antes de que el sistema operativo los haya liberado completamente.
        """
        import json
        try:
            registry_path = os.path.join(DATA_DIR, "sprites_running.txt")
            if not os.path.exists(registry_path):
                self.save_session()
                return

            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)

            if not registry:
                self.save_session()
                return

            sprites_to_save   = []
            playlists_to_save = []
            scenes_to_save    = []

            for pid_str, data in registry.items():
                display_name = data.get("sprite", "")
                if not display_name:
                    continue
                if data.get("is_lasso", False):
                    continue
                if display_name.startswith("Reel: "):
                    playlists_to_save.append(
                        display_name.replace("Reel: ", "")
                    )
                else:
                    sprites_to_save.append(display_name)

            if not sprites_to_save and not playlists_to_save:
                self.save_session()
                return

            if os.path.exists(SCENES_FILE):
                cfg = configparser.ConfigParser()
                cfg.read(SCENES_FILE, encoding="utf-8")
                for sec in cfg.sections():
                    if not sec.startswith("Scene_"):
                        continue
                    scene_name    = sec.replace("Scene_", "")
                    scene_sprites = [
                        s.strip()
                        for s in cfg.get(sec, "sprites", fallback="").split(",")
                        if s.strip()
                    ]
                    if scene_sprites and all(
                        s in sprites_to_save for s in scene_sprites
                    ):
                        scenes_to_save.append(scene_name)
                        for s in scene_sprites:
                            if s in sprites_to_save:
                                sprites_to_save.remove(s)

            session = configparser.ConfigParser()
            session["Session"] = {"count": str(len(registry))}
            if sprites_to_save:
                session["Sprites"]   = {"list": ",".join(sprites_to_save)}
            if playlists_to_save:
                session["Reels"] = {"list": ",".join(playlists_to_save)}
            if scenes_to_save:
                session["Scenes"]    = {"list": ",".join(scenes_to_save)}

            session_path = os.path.join(get_base_dir(), SESSION_FILE)
            os.makedirs(os.path.dirname(session_path), exist_ok=True)
            with open(session_path, "w", encoding="utf-8") as f:
                session.write(f)

        except Exception as e:
            print(f"Error en _finalize_save_session: {e}")
            self.save_session()
    
    def save_session(self):
        try:
            running = self.process_manager.get_running_sprites()
            session = configparser.ConfigParser()
            session["Session"] = {"count": str(len(running))}

            sprites_to_save   = []
            playlists_to_save = []
            scenes_to_save    = []

            for pid, display_name, proc in running:
                # Los Lasso no se guardan en sesion. Su ciclo de vida
                # depende de la musica, no del arranque de Windows.
                if display_name.startswith("Lasso:"):
                    continue
                if display_name.startswith("Reel: "):
                    playlists_to_save.append(
                        display_name.replace("Reel: ", "")
                    )
                else:
                    sprites_to_save.append(display_name)

            if os.path.exists(SCENES_FILE):
                cfg = configparser.ConfigParser()
                cfg.read(SCENES_FILE, encoding="utf-8")
                for sec in cfg.sections():
                    if not sec.startswith("Scene_"):
                        continue
                    scene_name    = sec.replace("Scene_", "")
                    scene_sprites = [
                        s.strip()
                        for s in cfg.get(sec, "sprites", fallback="").split(",")
                        if s.strip()
                    ]
                    if scene_sprites and all(
                        s in sprites_to_save for s in scene_sprites
                    ):
                        scenes_to_save.append(scene_name)
                        for s in scene_sprites:
                            if s in sprites_to_save:
                                sprites_to_save.remove(s)

            if sprites_to_save:
                session["Sprites"]   = {"list": ",".join(sprites_to_save)}
            if playlists_to_save:
                session["Reels"] = {"list": ",".join(playlists_to_save)}
            if scenes_to_save:
                session["Scenes"]    = {"list": ",".join(scenes_to_save)}

            session_path = os.path.join(get_base_dir(), SESSION_FILE)
            with open(session_path, "w", encoding="utf-8") as f:
                session.write(f)
        except Exception as e:
            print(f"Error guardando sesion: {e}")
    
    def _clear_session(self):
        """Limpia session.ini cuando el usuario desactiva Start with Windows."""
        try:
            session = configparser.ConfigParser()
            session["Session"] = {"count": "0"}
            session_path = os.path.join(get_base_dir(), SESSION_FILE)
            with open(session_path, "w", encoding="utf-8") as f:
                session.write(f)
        except Exception as e:
            print(f"Error limpiando sesion: {e}")
            
    def restore_session(self, delay_seconds: int = 8):
        # Guardia: si ya hay sprites corriendo (startup los lanzo), no duplicar
        if self.process_manager.get_running_sprites():
            return

        session_path = os.path.join(get_base_dir(), SESSION_FILE)
        if not os.path.exists(session_path):
            return
        try:
            session = configparser.ConfigParser()
            session.read(session_path, encoding="utf-8")

            has_something = (
                session.has_section("Sprites")
                or session.has_section("Reels")
                or session.has_section("Scenes")
            )
            if not has_something:
                return

            def launch_after_delay():
                import time
                time.sleep(delay_seconds)
                QTimer.singleShot(
                    0,
                    lambda: _show_launch_toast(
                        self,
                        "Spryta ejecutándose...",
                        "Restaurando sesión"
                    )
                )
                time.sleep(2.0)

                base_dir = get_base_dir()
                executable, use_pythonw = resolve_runtime_executable(
                    base_dir, "main_runtime", "main.exe", "main.pyw"
                )

                if executable is None:
                    return

                def launch(args):
                    try:
                        if use_pythonw:
                            pythonw = os.path.join(
                                os.path.dirname(sys.executable), "pythonw.exe"
                            )
                            subprocess.Popen([pythonw, executable] + args)
                        else:
                            subprocess.Popen([executable] + args)
                        time.sleep(0.3)
                    except Exception as e:
                        print(f"Error lanzando: {e}")

                if session.has_section("Sprites"):
                    for sp in [
                        s.strip()
                        for s in session.get("Sprites", "list", fallback="").split(",")
                        if s.strip()
                    ]:
                        launch([sp])

                if session.has_section("Reels"):
                    for pl in [
                        p.strip()
                        for p in session.get("Reels", "list", fallback="").split(",")
                        if p.strip()
                    ]:
                        launch(["--playlist", pl])

                if session.has_section("Scenes"):
                    cfg = configparser.ConfigParser()
                    if os.path.exists(SCENES_FILE):
                        cfg.read(SCENES_FILE, encoding="utf-8")
                    for sc in [
                        s.strip()
                        for s in session.get("Scenes", "list", fallback="").split(",")
                        if s.strip()
                    ]:
                        sec = f"Scene_{sc}"
                        if cfg.has_section(sec):
                            for sp in [
                                s.strip()
                                for s in cfg.get(sec, "sprites", fallback="").split(",")
                                if s.strip()
                            ]:
                                launch([sp])

            threading.Thread(target=launch_after_delay, daemon=True).start()
        except Exception as e:
            print(f"Error restaurando sesion: {e}")

    def _finalize_and_exit(self):
        """Guarda sesion, detiene audio y cierra la aplicacion."""
        # Guardar PRIMERO, antes de cerrar paneles o matar procesos.
        # Usa lectura directa del registro para evitar condiciones de carrera.
        self._finalize_save_session()

        if self.left_panel.is_visible():
            self.left_panel.close()
        if self.right_panel.is_visible():
            self.right_panel.close()

        if self.audio_manager.is_playing:
            self.audio_manager.stop()

        if self.tray:
            self.tray.hide()

        self.process_manager.terminate_process_by_name("main.pyw")
        self.process_manager.terminate_process_by_name("main.exe")
        self.process_manager.terminate_process_by_name("ambient_audio.pyw")

        QApplication.quit()


# ============================================================
# Splash screen al iniciar
# ============================================================

def show_splash():
    """Muestra una pantalla de carga pygame mientras arranca la app."""
    import pygame
    import win32gui
    import win32con
    import win32api
    import time

    pygame.init()
    width, height     = 300, 250
    transparent_color = (0, 255, 0)

    screen = pygame.display.set_mode((width, height), pygame.NOFRAME)
    screen.fill(transparent_color)

    # Obtener el handle de la ventana inmediatamente
    hwnd = pygame.display.get_wm_info()["window"]

    # Aplicar LAYERED con alpha=0 de inmediato para que la ventana sea
    # completamente invisible mientras se prepara todo.
    # Esto elimina el cuadro negro que aparecia al inicio.
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    ex_style |= win32con.WS_EX_LAYERED | win32con.WS_EX_TOOLWINDOW
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
    win32gui.SetLayeredWindowAttributes(hwnd, 0, 0, win32con.LWA_ALPHA)

    # Calcular posicion centrada en pantalla
    try:
        screen_width  = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        x = (screen_width  - width)  // 2
        y = (screen_height - height) // 2
    except Exception:
        info = pygame.display.Info()
        x = (info.current_w - width)  // 2
        y = (info.current_h - height) // 2

    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST, x, y, 0, 0,
        win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
    )

    # Preparar el splash
    try:
        splash_path = os.path.join("assets", "icons", "splash.png")
        if os.path.exists(splash_path):
            img  = pygame.image.load(splash_path).convert_alpha()
            img  = pygame.transform.smoothscale(img, (width, height))
            surf = pygame.Surface((width, height))
            surf.fill(transparent_color)
            for sy in range(height):
                for sx in range(width):
                    r, g, b, a = img.get_at((sx, sy))
                    if a > 128:
                        surf.set_at((sx, sy), (r, g, b))
                    else:
                        surf.set_at((sx, sy), transparent_color)
        else:
            surf = pygame.Surface((width, height))
            surf.fill((0, 100, 200))
    except Exception:
        surf = pygame.Surface((width, height))
        surf.fill((0, 100, 200))

    screen.blit(surf, (0, 0))
    pygame.display.flip()

    # Ahora que el contenido esta dibujado, cambiar de alpha=0 a colorkey.
    # La ventana aparece directamente con el splash visible, sin negro previo.
    win32gui.SetLayeredWindowAttributes(
        hwnd, win32api.RGB(*transparent_color), 0, win32con.LWA_COLORKEY
    )

    start   = time.time()
    running = True
    while running and (time.time() - start) < 2.0:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        pygame.time.wait(10)

    pygame.display.quit()
    pygame.quit()


# ============================================================
# Punto de entrada
# ============================================================

if __name__ == "__main__":
    # Identificador unico para que Windows asocie el icono correcto
    # a esta aplicacion en la barra de tareas y el Alt+Tab.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u'Spryta.Desktop.Settings.1'
        )
    except Exception:
        pass
    start_minimized = "--minimized" in sys.argv

    if not start_minimized:
        show_splash()

    app = QApplication(sys.argv)
    app.setStyleSheet(theme.get_stylesheet())
    app.setPalette(theme.get_palette())

    window = SettingsApp()

    if start_minimized:
        window.showMinimized()
        window.restore_session()          # arranca con Windows: espera 8 seg
    else:
        # Centrar en pantalla
        try:
            import win32api, win32con
            work_area    = win32api.GetMonitorInfo(
                win32api.MonitorFromPoint((0, 0))
            )["Work"]
            sw = work_area[2] - work_area[0]
            sh = work_area[3] - work_area[1]
            sx = work_area[0]
            sy = work_area[1]
        except Exception:
            sx = sy = 0
            sw = app.primaryScreen().availableSize().width()
            sh = app.primaryScreen().availableSize().height()

        x = sx + (sw - theme.MAIN_WINDOW_WIDTH)  // 2
        y = sy + (sh - theme.MAIN_WINDOW_HEIGHT) // 2
        window.move(x, y)
        window.show()
        from PySide6.QtCore import QTimer
        from session import offer_restore_session
        QTimer.singleShot(400, lambda: offer_restore_session(window, window.process_manager))

    sys.exit(app.exec())
