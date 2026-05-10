# -*- coding: utf-8 -*-
"""
session.py  —  Spryta Session Manager

Modulo dedicado a la logica de sesion de Spryta.

Responsabilidades:
    1. Leer y validar session.ini contra los archivos en disco.
    2. Mostrar la ventana de confirmacion de restauracion.
    3. Lanzar los sprites/reels/escenas disponibles.
    4. Limpiar la sesion si el usuario rechaza o no hay nada disponible.

API publica:
    offer_restore_session(parent, process_manager)
        Punto de entrada unico. Llamar desde setting.pyw al abrir manualmente.

Uso en setting.pyw:
    from session import offer_restore_session
    QTimer.singleShot(400, lambda: offer_restore_session(self, self.process_manager))
"""

import os
import sys
import configparser
import subprocess
import threading

from PySide6.QtCore    import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui     import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame,
    QWidget, QApplication,
    QGraphicsOpacityEffect, QScrollArea,
)


# ============================================================
# Rutas base — identicas a las de setting.pyw
# ============================================================

def _get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR         = _get_base_dir()
_USER_DOCS       = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Spryta")
DATA_DIR         = os.path.join(_USER_DOCS, "data")
SPRITES_DIR      = os.path.join(_USER_DOCS, "sprites")
SESSION_FILE     = os.path.join(DATA_DIR, "session.ini")
SCENES_FILE      = os.path.join(DATA_DIR, "scenes.ini")
REEL_FILE        = os.path.join(DATA_DIR, "reel.ini")

from ui import theme


# ============================================================
# Colores locales (espejo de theme para no depender de imports
# en zonas donde theme puede no estar disponible aun)
# ============================================================

_BG      = theme.BG_BASE
_SURFACE = theme.BG_SURFACE
_RAISED  = theme.BG_RAISED
_HOVER   = theme.BG_HOVER
_BORDER  = theme.BORDER_MID
_ACCENT  = theme.ACCENT
_BRIGHT  = theme.TEXT_BRIGHT
_NORMAL  = theme.TEXT_NORMAL
_MUTED   = theme.TEXT_MUTED
_SUCCESS = theme.COLOR_SUCCESS
_DANGER  = theme.COLOR_DANGER
_WARNING = theme.COLOR_WARNING
_RADIUS  = theme.RADIUS
_RADIUS_L = theme.RADIUS_LARGE


# ============================================================
# SECCION 1: Estructuras de datos
# ============================================================

class _SessionData:
    """
    Resultado de la validacion de session.ini.

    Atributos:
        available_sprites   -- sprites con carpeta existente en disco
        missing_sprites     -- sprites guardados pero sin carpeta
        available_reels -- reels con entrada en reel.ini
        missing_reels   -- reels guardados pero no encontrados
        available_scenes    -- escenas con entrada en scenes.ini
        missing_scenes      -- escenas guardadas pero no encontradas
    """
    def __init__(self):
        self.available_sprites   = []
        self.missing_sprites     = []
        self.available_reels = []
        self.missing_reels   = []
        self.available_scenes    = []
        self.missing_scenes      = []

    @property
    def total_available(self) -> int:
        return (
            len(self.available_sprites)
            + len(self.available_reels)
            + len(self.available_scenes)
        )

    @property
    def total_missing(self) -> int:
        return (
            len(self.missing_sprites)
            + len(self.missing_reels)
            + len(self.missing_scenes)
        )

    @property
    def total_saved(self) -> int:
        return self.total_available + self.total_missing

    @property
    def all_missing_names(self) -> list:
        return (
            self.missing_sprites
            + self.missing_reels
            + self.missing_scenes
        )


# ============================================================
# SECCION 2: Logica de lectura y validacion
# ============================================================

def _read_session() -> "configparser.ConfigParser | None":
    """
    Lee session.ini. Devuelve el ConfigParser o None si no existe
    o no tiene ninguna seccion de datos.
    """
    if not os.path.exists(SESSION_FILE):
        return None

    session = configparser.ConfigParser()
    session.read(SESSION_FILE, encoding="utf-8")

    has_something = (
        session.has_section("Sprites")
        or session.has_section("Reels")
        or session.has_section("Scenes")
    )
    return session if has_something else None


def _validate_session(session: configparser.ConfigParser) -> _SessionData:
    """
    Comprueba en disco cuales items de la sesion guardada existen.
    Devuelve un _SessionData con las listas separadas.
    """
    data = _SessionData()

    # -- Sprites individuales --
    for sp in [
        s.strip()
        for s in session.get("Sprites", "list", fallback="").split(",")
        if s.strip()
    ]:
        path = os.path.join(SPRITES_DIR, sp)
        if os.path.isdir(path):
            data.available_sprites.append(sp)
        else:
            data.missing_sprites.append(sp)

    # -- Reels --
    saved_reels = [
        p.strip()
        for p in session.get("Reels", "list", fallback="").split(",")
        if p.strip()
    ]
    if saved_reels:
        if os.path.exists(REEL_FILE):
            pl_cfg = configparser.ConfigParser()
            pl_cfg.read(REEL_FILE, encoding="utf-8")
            for pl in saved_reels:
                if pl_cfg.has_section(f"Reel_{pl}"):
                    data.available_reels.append(pl)
                else:
                    data.missing_reels.append(pl)
        else:
            data.missing_reels = list(saved_reels)

    # -- Escenas --
    saved_scenes = [
        s.strip()
        for s in session.get("Scenes", "list", fallback="").split(",")
        if s.strip()
    ]
    if saved_scenes:
        if os.path.exists(SCENES_FILE):
            sc_cfg = configparser.ConfigParser()
            sc_cfg.read(SCENES_FILE, encoding="utf-8")
            for sc in saved_scenes:
                if sc_cfg.has_section(f"Scene_{sc}"):
                    data.available_scenes.append(sc)
                else:
                    data.missing_scenes.append(sc)
        else:
            data.missing_scenes = list(saved_scenes)

    return data


def _clear_session() -> None:
    """Resetea session.ini a count = 0 sin secciones de datos."""
    try:
        session = configparser.ConfigParser()
        session["Session"] = {"count": "0"}
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            session.write(f)
    except Exception as e:
        print(f"[session] Error limpiando sesion: {e}")


# ============================================================
# SECCION 3: Logica de lanzamiento
# ============================================================

def _get_executable() -> "tuple[str | None, bool]":
    """
    Devuelve (ruta_ejecutable, use_pythonw).
    use_pythonw = True  -> hay que anteponer pythonw.exe al comando.
    use_pythonw = False -> es un .exe que se lanza directamente.
    """
    runtime_exe = os.path.join(BASE_DIR, "main_runtime", "main.exe")
    exe_path    = os.path.join(BASE_DIR, "main.exe")
    pyw_path    = os.path.join(BASE_DIR, "main.pyw")

    if os.path.exists(exe_path):
        return exe_path, False
    if os.path.exists(pyw_path):
        return pyw_path, True
    return None, False


def _get_pythonw() -> str:
    """Devuelve la ruta de pythonw.exe."""
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        import shutil
        found = shutil.which("pythonw")
        pythonw = found if found else sys.executable.replace(
            "python.exe", "pythonw.exe"
        )
    return pythonw


def _launch_items(data: _SessionData) -> None:
    """
    Lanza en un hilo separado todos los items disponibles de la sesion.
    Solo -> directamente.
    Reels -> con --playlist.
    Escenas -> expand a sprites individuales leyendo scenes.ini.
    """
    import time

    exe, use_pythonw = _get_executable()
    if exe is None:
        return

    def _popen(args):
        try:
            if use_pythonw:
                subprocess.Popen(
                    [_get_pythonw(), exe] + args,
                    cwd=BASE_DIR,
                )
            else:
                subprocess.Popen([exe] + args, cwd=BASE_DIR)
            time.sleep(0.3)
        except Exception as e:
            print(f"[session] Error lanzando {args}: {e}")

    def _do():
        for sp in data.available_sprites:
            _popen([sp])

        for pl in data.available_reels:
            _popen(["--playlist", pl])

        for sc in data.available_scenes:
            if not os.path.exists(SCENES_FILE):
                continue
            sc_cfg = configparser.ConfigParser()
            sc_cfg.read(SCENES_FILE, encoding="utf-8")
            sec = f"Scene_{sc}"
            if not sc_cfg.has_section(sec):
                continue
            for sp in [
                s.strip()
                for s in sc_cfg.get(sec, "sprites", fallback="").split(",")
                if s.strip()
            ]:
                _popen([sp])

    threading.Thread(target=_do, daemon=True).start()


# ============================================================
# SECCION 4: Ventana de confirmacion
# ============================================================

class _RestoreDialog(QDialog):
    """
    Ventana de confirmacion de restauracion de sesion.

    Muestra la lista completa de items guardados con su estado:
        ● Nombre del sprite    [available]
        ● Nombre faltante      [not found]  ✕

    El usuario puede confirmar con "Restore" o rechazar con "No".
    El resultado se lee con .confirmed (bool).
    """

    def __init__(self, data: _SessionData, parent=None):
        super().__init__(parent)
        self.confirmed = False
        self._data     = data

        # -- Configuracion de ventana --
        self.setWindowTitle("Restore Last Session")
        self.setModal(True)
        self.setFixedWidth(460)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Icono de la aplicacion
        icon_path = os.path.join(BASE_DIR, "assets", "icons", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._animate_in()

    # ----------------------------------------------------------
    # Construccion de la interfaz
    # ----------------------------------------------------------

    def _build_ui(self):
        data = self._data

        # Contenedor principal con borde redondeado
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("RestoreCard")
        card.setStyleSheet(f"""
            QFrame#RestoreCard {{
                background-color: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: {_RADIUS_L}px;
            }}
        """)
        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(0)

        # ── Titulo --
        lbl_title = QLabel("Restore Last Session")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color: {_ACCENT};")
        root.addWidget(lbl_title)

        root.addSpacing(4)

        # ── Subtitulo segun escenario --
        if data.total_missing == 0:
            subtitle_text = (
                f"Found {data.total_available} item(s) from your last session."
            )
            subtitle_color = _NORMAL
        else:
            subtitle_text = (
                f"{data.total_available} of {data.total_saved} items are available. "
                f"{data.total_missing} will be skipped."
            )
            subtitle_color = _WARNING

        lbl_sub = QLabel(subtitle_text)
        lbl_sub.setFont(theme.FONT_SMALL)
        lbl_sub.setStyleSheet(f"color: {subtitle_color};")
        lbl_sub.setWordWrap(True)
        root.addWidget(lbl_sub)

        root.addSpacing(16)

        # ── Separador --
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_BORDER}; border: none;")
        root.addWidget(sep)

        root.addSpacing(12)

        # ── Lista de items con scroll si hay muchos --
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        scroll.setMaximumHeight(240)

        list_container = QWidget()
        list_container.setStyleSheet("background: transparent;")
        list_layout    = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)

        # Sprites disponibles
        for name in data.available_sprites:
            list_layout.addWidget(
                self._make_item_row(name, item_type="Sprite", available=True)
            )

        # Reels disponibles
        for name in data.available_reels:
            list_layout.addWidget(
                self._make_item_row(name, item_type="Reel", available=True)
            )

        # Escenas disponibles
        for name in data.available_scenes:
            list_layout.addWidget(
                self._make_item_row(name, item_type="Scene", available=True)
            )

        # Sprites faltantes
        for name in data.missing_sprites:
            list_layout.addWidget(
                self._make_item_row(name, item_type="Sprite", available=False)
            )

        # Reels faltantes
        for name in data.missing_reels:
            list_layout.addWidget(
                self._make_item_row(name, item_type="Reel", available=False)
            )

        # Escenas faltantes
        for name in data.missing_scenes:
            list_layout.addWidget(
                self._make_item_row(name, item_type="Scene", available=False)
            )

        list_layout.addStretch()
        scroll.setWidget(list_container)
        root.addWidget(scroll)

        root.addSpacing(16)

        # ── Separador inferior --
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {_BORDER}; border: none;")
        root.addWidget(sep2)

        root.addSpacing(16)

        # ── Botones --
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        btn_no = QPushButton("No")
        btn_no.setFont(theme.FONT_NORMAL)
        btn_no.setFixedHeight(36)
        btn_no.setMinimumWidth(90)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {_NORMAL};
                border: 1px solid {_BORDER};
                border-radius: {_RADIUS}px;
                padding: 7px 20px;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {_HOVER};
                color: {_BRIGHT};
                border-color: {_BORDER};
            }}
            QPushButton:pressed {{
                background-color: {_RAISED};
            }}
        """)
        btn_no.clicked.connect(self._on_no)

        btn_restore = QPushButton("Restore")
        btn_restore.setFont(theme.FONT_NORMAL)
        btn_restore.setFixedHeight(36)
        btn_restore.setMinimumWidth(100)
        btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_restore.setStyleSheet(f"""
            QPushButton {{
                background-color: {_ACCENT};
                color: #ffffff;
                border: 1px solid {_ACCENT};
                border-radius: {_RADIUS}px;
                padding: 7px 20px;
                font-size: 10pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme.ACCENT_HOVER};
                border-color: {theme.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {theme.ACCENT_HOVER};
            }}
        """)
        btn_restore.clicked.connect(self._on_restore)

        # Si no hay nada disponible, deshabilitar Restore
        if data.total_available == 0:
            btn_restore.setEnabled(False)

        btn_row.addWidget(btn_no)
        btn_row.addWidget(btn_restore)
        root.addLayout(btn_row)

        btn_restore.setFocus()

    def _make_item_row(self, name: str, item_type: str, available: bool) -> QWidget:
        """
        Construye una fila visual para un item de la lista.

        Disponible:  ●  Nombre               Sprite / Reel / Scene
        Faltante:    ●  Nombre               [not found]  ✕
        """
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row.setFixedHeight(32)

        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)

        # Punto indicador
        dot = QLabel("●")
        dot.setFixedWidth(10)
        dot_color = _ACCENT if available else _MUTED
        dot.setStyleSheet(
            f"color: {dot_color}; font-size: 8px; background: transparent;"
        )
        lay.addWidget(dot)

        # Nombre del item
        lbl_name = QLabel(name if len(name) <= 32 else name[:29] + "...")
        lbl_name.setFont(theme.FONT_NORMAL)
        name_color = _BRIGHT if available else _MUTED
        lbl_name.setStyleSheet(
            f"color: {name_color}; background: transparent;"
        )
        lay.addWidget(lbl_name, 1)

        if available:
            # Tipo de item (Sprite / Reel / Scene)
            lbl_type = QLabel(item_type)
            lbl_type.setFont(theme.FONT_TINY)
            lbl_type.setStyleSheet(
                f"color: {_MUTED}; background: transparent;"
            )
            lay.addWidget(lbl_type)
        else:
            # Etiqueta [not found] + icono de error
            lbl_nf = QLabel("[not found]")
            lbl_nf.setFont(theme.FONT_TINY)
            lbl_nf.setStyleSheet(
                f"color: {_WARNING}; background: transparent;"
            )
            lay.addWidget(lbl_nf)

            lbl_x = QLabel("✕")
            lbl_x.setFont(theme.FONT_SMALL)
            lbl_x.setStyleSheet(
                f"color: {_DANGER}; background: transparent;"
            )
            lay.addWidget(lbl_x)

        return row

    # ----------------------------------------------------------
    # Animacion de entrada
    # ----------------------------------------------------------

    def _animate_in(self):
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim.setDuration(200)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    # ----------------------------------------------------------
    # Centrado
    # ----------------------------------------------------------

    def _center_on_parent(self):
        self.adjustSize()
        if self.parent() and self.parent().isVisible():
            p   = self.parent()
            geo = self.frameGeometry()
            geo.moveCenter(p.frameGeometry().center())
            self.move(geo.topLeft())
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            geo    = self.frameGeometry()
            geo.moveCenter(screen.center())
            self.move(geo.topLeft())

    # ----------------------------------------------------------
    # Mostrar y obtener resultado
    # ----------------------------------------------------------

    def open(self) -> bool:
        """Muestra el dialogo y bloquea hasta que el usuario responde."""
        self._center_on_parent()
        self.exec()
        return self.confirmed

    # ----------------------------------------------------------
    # Acciones de botones
    # ----------------------------------------------------------

    def _on_no(self):
        self.confirmed = False
        self.reject()

    def _on_restore(self):
        self.confirmed = True
        self.accept()


# ============================================================
# SECCION 5: Ventana de aviso (sin items disponibles)
# ============================================================

class _NoItemsDialog(QDialog):
    """
    Dialogo informativo cuando ninguno de los items guardados existe.
    Solo tiene boton OK. Limpia la sesion automaticamente al cerrar.
    """

    def __init__(self, missing_names: list, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Session Not Found")
        self.setModal(True)
        self.setFixedWidth(420)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        icon_path = os.path.join(BASE_DIR, "assets", "icons", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui(missing_names)
        self._animate_in()

    def _build_ui(self, missing_names: list):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("NoItemsCard")
        card.setStyleSheet(f"""
            QFrame#NoItemsCard {{
                background-color: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: {_RADIUS_L}px;
            }}
        """)
        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(0)

        # Titulo
        lbl_title = QLabel("Session Not Found")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color: {_WARNING};")
        root.addWidget(lbl_title)

        root.addSpacing(8)

        # Mensaje
        lbl_msg = QLabel(
            "The items from your last session no longer exist.\n"
            "The session will be reset."
        )
        lbl_msg.setFont(theme.FONT_NORMAL)
        lbl_msg.setStyleSheet(f"color: {_NORMAL};")
        lbl_msg.setWordWrap(True)
        root.addWidget(lbl_msg)

        root.addSpacing(16)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_BORDER}; border: none;")
        root.addWidget(sep)

        root.addSpacing(12)

        # Lista de items faltantes
        for name in missing_names:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(8, 0, 8, 0)
            row_lay.setSpacing(10)

            dot = QLabel("●")
            dot.setFixedWidth(10)
            dot.setStyleSheet(
                f"color: {_MUTED}; font-size: 8px; background: transparent;"
            )
            row_lay.addWidget(dot)

            lbl = QLabel(name if len(name) <= 36 else name[:33] + "...")
            lbl.setFont(theme.FONT_NORMAL)
            lbl.setStyleSheet(f"color: {_MUTED}; background: transparent;")
            row_lay.addWidget(lbl, 1)

            lbl_x = QLabel("✕")
            lbl_x.setFont(theme.FONT_SMALL)
            lbl_x.setStyleSheet(
                f"color: {_DANGER}; background: transparent;"
            )
            row_lay.addWidget(lbl_x)

            root.addWidget(row)

        root.addSpacing(16)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {_BORDER}; border: none;")
        root.addWidget(sep2)

        root.addSpacing(16)

        # Boton OK
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_ok = QPushButton("OK")
        btn_ok.setFont(theme.FONT_NORMAL)
        btn_ok.setFixedHeight(36)
        btn_ok.setMinimumWidth(90)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {_ACCENT};
                color: #ffffff;
                border: 1px solid {_ACCENT};
                border-radius: {_RADIUS}px;
                padding: 7px 20px;
                font-size: 10pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme.ACCENT_HOVER};
                border-color: {theme.ACCENT_HOVER};
            }}
        """)
        btn_ok.clicked.connect(self.accept)
        btn_ok.setFocus()

        btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def _animate_in(self):
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim.setDuration(200)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _center_on_parent(self):
        self.adjustSize()
        if self.parent() and self.parent().isVisible():
            p   = self.parent()
            geo = self.frameGeometry()
            geo.moveCenter(p.frameGeometry().center())
            self.move(geo.topLeft())
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            geo    = self.frameGeometry()
            geo.moveCenter(screen.center())
            self.move(geo.topLeft())

    def open(self):
        self._center_on_parent()
        self.exec()


# ============================================================
# SECCION 6: API publica
# ============================================================

def offer_restore_session(parent, process_manager) -> None:
    """
    Punto de entrada unico del modulo.

    Evalua si hay una sesion guardada y si vale la pena ofrecerla
    al usuario. Muestra el dialogo adecuado y actua segun respuesta.

    Parametros:
        parent          -- QWidget padre (ventana de Settings)
        process_manager -- instancia de ProcessManager para verificar
                           sprites ya corriendo y para el watcher
    """
    # -- Guardia 1: sprites ya corriendo (startup los lanzo) --
    if process_manager.get_running_sprites():
        return

    # -- Guardia 2: leer session.ini --
    session = _read_session()
    if session is None:
        return

    # -- Validar existencia en disco --
    data = _validate_session(session)

    if data.total_saved == 0:
        return

    # -- Sub-escenario 3: ninguno existe --
    if data.total_available == 0:
        dlg = _NoItemsDialog(data.all_missing_names, parent=parent)
        dlg.open()
        _clear_session()
        return

    # -- Sub-escenarios 1 y 2: mostrar dialogo de confirmacion --
    dlg = _RestoreDialog(data, parent=parent)
    confirmed = dlg.open()

    if not confirmed:
        _clear_session()
        return

    # -- Lanzar los disponibles --
    _launch_items(data)

    # -- Calcular cuantos procesos se van a lanzar --
    # Sprites y reels = 1 proceso cada uno.
    # Escenas = N procesos (uno por sprite dentro de la escena).
    expected = len(data.available_sprites) + len(data.available_reels)
    if data.available_scenes and os.path.exists(SCENES_FILE):
        sc_cfg = configparser.ConfigParser()
        sc_cfg.read(SCENES_FILE, encoding="utf-8")
        for sc in data.available_scenes:
            sec = f"Scene_{sc}"
            if sc_cfg.has_section(sec):
                scene_sprites = [
                    s.strip()
                    for s in sc_cfg.get(sec, "sprites", fallback="").split(",")
                    if s.strip()
                ]
                expected += len(scene_sprites)

    # -- Activar watcher para que Settings abra el panel automaticamente --
    try:
        prev = len(process_manager.get_running_sprites())
        parent._start_process_watcher(prev, expected_count=expected)
    except Exception as e:
        print(f"[session] Error iniciando watcher: {e}")
