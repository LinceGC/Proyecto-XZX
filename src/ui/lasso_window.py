# -*- coding: utf-8 -*-
"""
lasso_window.py  —  Ventana de editor de vinculos Cancion-Sprite (Spryta)

Abre una ventana flotante con un editor de nodos al estilo N8N / ComfyUI:
  - Panel izquierdo : nodos de canciones (de la biblioteca de audio)
  - Panel derecho   : nodos de sprites   (de la carpeta sprites/)
  - Canvas central  : hilos de conexion dibujados entre los nodos

Interaccion:
  - Clic en el puerto de una cancion  → inicia un hilo
  - Clic en el puerto de un sprite   → completa el hilo (vinculo creado)
  - Clic derecho sobre un hilo       → elimina ese vinculo
  - Clic en puerto ya conectado      → tambien inicia un hilo nuevo
    (un mismo nodo puede tener multiples conexiones)

Selector de playlist arriba: permite crear, renombrar y eliminar playlists.

Guardar persiste inmediatamente en lassos.json via LassoManager.

Ubicacion en el proyecto:
    Guardar este archivo en la carpeta  ui/  junto a panels.py

Uso desde panels.py:
    from ui.lasso_window import LassoWindow
    self._lasso_window = LassoWindow(parent, lasso_manager, audio_manager)
    self._lasso_window.show(main_window=self.window)
"""

import os
import sys

from PySide6.QtCore  import Qt, QPoint, QRect, QSize, QTimer
from PySide6.QtGui   import (
    QPainter, QPen, QBrush, QColor, QPainterPath,
    QFont, QCursor,
)
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox,
    QScrollArea, QSizePolicy,
    QApplication, QButtonGroup, QRadioButton,
)

from ui import theme
from ui.dialog import (
    show_info, show_warning, show_error,
    ask_yes_no, ask_string,
)
try:
    from tools.paths import SPRITES_DIR as USER_SPRITES_DIR
except Exception:
    USER_SPRITES_DIR = os.path.join(
        os.path.expanduser("~"), "AppData", "Local", "Spryta", "sprites"
    )

# ================================================================
# Constantes de diseno del canvas de nodos
# ================================================================

_NODE_W      = 220   # ancho de cada nodo en pixeles
_NODE_H      =  42   # alto de cada nodo en pixeles
_NODE_GAP    =  10   # espacio vertical entre nodos
_PORT_R      =   7   # radio del circulo de puerto
_CANVAS_PAD  =  20   # margen interior del canvas
_COL_GAP     = 160   # espacio horizontal entre columnas de nodos (zona de hilos)

# Colores de los nodos (distintos de los del tema para destacar)
_C_SONG_BG      = "#1a2a4a"   # fondo nodo cancion (azul oscuro)
_C_SONG_BORDER  = "#2a4a8a"   # borde nodo cancion
_C_SONG_PORT    = "#358cfe"   # puerto cancion (acento azul)
_C_SPR_BG       = "#1a3a2a"   # fondo nodo sprite (verde oscuro)
_C_SPR_BORDER   = "#2a6a4a"   # borde nodo sprite
_C_SPR_PORT     = "#3bc86a"   # puerto sprite (verde)
_C_WIRE         = "#358cfe"   # hilo de conexion
_C_WIRE_PENDING = "#f4a020"   # hilo en construccion (naranja)
_C_WIRE_SEL     = "#e63946"   # hilo seleccionado (rojo para eliminar)
_C_TEXT         = "#eaeaf2"
_C_TEXT_MUTED   = "#50506a"
_C_CANVAS_BG    = "#0e0e12"


# ================================================================
# Clase de datos interna: _Node
# Representa un nodo visual (cancion o sprite) en el canvas.
# ================================================================

class _Node:
    """
    Contiene la informacion de posicion y tipo de un nodo.

    Atributos:
        name     -- nombre del archivo o carpeta
        kind     -- "song" o "sprite"
        rect     -- QRect del cuerpo del nodo en el canvas
        port     -- QPoint del centro del circulo de puerto
    """
    __slots__ = ("name", "kind", "rect", "port")

    def __init__(self, name: str, kind: str, rect: QRect):
        self.name = name
        self.kind = kind
        self.rect = rect
        # Puerto al borde derecho del nodo (canciones) o izquierdo (sprites)
        cy = rect.top() + rect.height() // 2
        if kind == "song":
            self.port = QPoint(rect.right(), cy)
        else:
            self.port = QPoint(rect.left(), cy)

    def port_hit(self, pos: QPoint) -> bool:
        """Devuelve True si pos esta dentro del area clickeable del puerto."""
        dx = pos.x() - self.port.x()
        dy = pos.y() - self.port.y()
        return (dx * dx + dy * dy) <= (_PORT_R + 6) ** 2


# ================================================================
# Widget principal del canvas de nodos
# ================================================================

class _NodeCanvas(QWidget):
    """
    Canvas personalizado que dibuja nodos y hilos de conexion.

    No usa layouts de Qt para los nodos: los calcula y dibuja
    directamente en paintEvent, igual que ComfyUI o N8N.

    Estado interno:
        _songs       -- lista de nombres de canciones
        _sprites     -- lista de nombres de sprites disponibles
        _connections -- lista de tuplas (song_name, sprite_name)
        _pending     -- nodo desde el cual empieza un hilo en construccion
        _mouse_pos   -- posicion actual del mouse (para hilo en construccion)
        _hover_wire  -- indice del hilo bajo el cursor (o -1)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setMinimumSize(700, 400)

        self._songs:       list  = []
        self._sprites:     list  = []
        self._connections: list  = []   # [(song_name, sprite_name), ...]

        self._song_nodes:   list = []   # lista de _Node
        self._sprite_nodes: list = []   # lista de _Node

        self._pending:   "_Node | None" = None
        self._mouse_pos: QPoint         = QPoint(0, 0)
        self._hover_wire: int           = -1

    # ----------------------------------------------------------
    # API publica
    # ----------------------------------------------------------

    def set_data(self, songs: list, sprites: list,
                 connections: list) -> None:
        """
        Carga los datos en el canvas y recalcula los nodos.

        Parametros:
            songs       -- lista de nombres de archivos de audio
            sprites     -- lista de nombres de carpetas de sprites
            connections -- lista de (song_name, sprite_name)
        """
        self._songs       = list(songs)
        self._sprites     = list(sprites)
        self._connections = list(connections)
        self._pending     = None
        self._hover_wire  = -1
        self._recalc_nodes()
        self._adjust_height()
        self.update()

    def get_connections(self) -> list:
        """Devuelve la lista actual de vinculos como lista de tuplas."""
        return list(self._connections)

    # ----------------------------------------------------------
    # Calculo de posiciones de nodos
    # ----------------------------------------------------------

    def _recalc_nodes(self) -> None:
        """Recalcula los QRect de todos los nodos segun el tamano del canvas."""
        w = self.width()

        # Columna izquierda (canciones): margen izquierdo + ancho nodo
        left_x = _CANVAS_PAD
        # Columna derecha (sprites): empieza al otro lado del canvas
        right_x = w - _CANVAS_PAD - _NODE_W

        self._song_nodes   = []
        self._sprite_nodes = []

        for i, name in enumerate(self._songs):
            y    = _CANVAS_PAD + i * (_NODE_H + _NODE_GAP)
            rect = QRect(left_x, y, _NODE_W, _NODE_H)
            self._song_nodes.append(_Node(name, "song", rect))

        for i, name in enumerate(self._sprites):
            y    = _CANVAS_PAD + i * (_NODE_H + _NODE_GAP)
            rect = QRect(right_x, y, _NODE_W, _NODE_H)
            self._sprite_nodes.append(_Node(name, "sprite", rect))

    def _adjust_height(self) -> None:
        """Ajusta la altura minima del canvas al contenido."""
        n     = max(len(self._songs), len(self._sprites), 1)
        h_min = _CANVAS_PAD * 2 + n * (_NODE_H + _NODE_GAP)
        self.setMinimumHeight(max(400, h_min))

    # ----------------------------------------------------------
    # Dibujo
    # ----------------------------------------------------------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fondo del canvas
        p.fillRect(self.rect(), QColor(_C_CANVAS_BG))

        # Dibujar hilos existentes
        for idx, (song_name, spr_name) in enumerate(self._connections):
            song_node = self._find_node(song_name, "song")
            spr_node  = self._find_node(spr_name,  "sprite")
            if song_node and spr_node:
                color = _C_WIRE_SEL if idx == self._hover_wire else _C_WIRE
                self._draw_wire(p, song_node.port, spr_node.port, color, width=2)

        # Hilo en construccion (pendiente)
        if self._pending is not None:
            self._draw_wire(
                p, self._pending.port, self._mouse_pos,
                _C_WIRE_PENDING, width=2, dashed=True,
            )

        # Dibujar nodos encima de los hilos
        for node in self._song_nodes:
            self._draw_node(p, node)
        for node in self._sprite_nodes:
            self._draw_node(p, node)

        # Encabezados de columna
        p.setFont(theme.font("small", bold=True))
        p.setPen(QColor(theme.TEXT_MUTED))
        if self._songs:
            p.drawText(
                _CANVAS_PAD, _CANVAS_PAD - 4,
                "SONGS"
            )
        if self._sprites:
            right_x = self.width() - _CANVAS_PAD - _NODE_W
            p.drawText(right_x, _CANVAS_PAD - 4, "SPRITES")

        # Mensaje cuando no hay datos
        if not self._songs and not self._sprites:
            p.setPen(QColor(theme.TEXT_MUTED))
            p.setFont(theme.font("normal"))
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Select a playlist and add songs\nto start linking sprites",
            )

        p.end()

    def _draw_node(self, p: QPainter, node: "_Node") -> None:
        """Dibuja el rectangulo del nodo y su circulo de puerto."""
        is_song   = node.kind == "song"
        bg_color  = _C_SONG_BG    if is_song else _C_SPR_BG
        brd_color = _C_SONG_BORDER if is_song else _C_SPR_BORDER
        prt_color = _C_SONG_PORT   if is_song else _C_SPR_PORT

        # Resaltar si el nodo es el pendiente
        if node is self._pending:
            brd_color = _C_WIRE_PENDING
            bg_color  = "#2a1a00"

        # Fondo del nodo
        p.setBrush(QBrush(QColor(bg_color)))
        p.setPen(QPen(QColor(brd_color), 1))
        p.drawRoundedRect(node.rect, theme.RADIUS_SMALL, theme.RADIUS_SMALL)

        # Texto del nombre (truncado si es muy largo)
        p.setPen(QColor(_C_TEXT))
        p.setFont(theme.font("small"))
        text_rect = node.rect.adjusted(10, 0, -20, 0)
        name      = node.name
        # Quitar extension de archivo para canciones
        if is_song and "." in name:
            name = name.rsplit(".", 1)[0]
        fm   = p.fontMetrics()
        name = fm.elidedText(name, Qt.TextElideMode.ElideRight, text_rect.width())
        p.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            name,
        )

        # Puerto (circulo)
        p.setBrush(QBrush(QColor(prt_color)))
        p.setPen(QPen(QColor(_C_CANVAS_BG), 2))
        p.drawEllipse(node.port, _PORT_R, _PORT_R)

    def _draw_wire(self, p: QPainter,
                   src: QPoint, dst: QPoint,
                   color: str, width: int = 2,
                   dashed: bool = False) -> None:
        """
        Dibuja un hilo curvo (bezier cubico) entre dos puntos.
        La curva sale horizontalmente del puerto origen y llega
        horizontalmente al puerto destino, igual que en N8N.
        """
        path = QPainterPath()
        path.moveTo(src)
        # Puntos de control: desplazados hacia el centro horizontal
        ctrl_offset = max(60, abs(dst.x() - src.x()) * 0.5)
        cp1 = QPoint(int(src.x() + ctrl_offset), src.y())
        cp2 = QPoint(int(dst.x() - ctrl_offset), dst.y())
        path.cubicTo(cp1, cp2, dst)

        pen = QPen(QColor(color), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    # ----------------------------------------------------------
    # Deteccion de clicks sobre hilos
    # ----------------------------------------------------------

    def _wire_hit(self, pos: QPoint) -> int:
        """
        Devuelve el indice del hilo mas cercano a pos (dentro de 8px),
        o -1 si no hay ninguno cerca.

        Aproxima la bezier muestreandola en 40 puntos.
        """
        THRESHOLD = 8.0
        for idx, (song_name, spr_name) in enumerate(self._connections):
            sn = self._find_node(song_name, "song")
            sp = self._find_node(spr_name,  "sprite")
            if not sn or not sp:
                continue
            src = sn.port
            dst = sp.port
            ctrl_offset = max(60, abs(dst.x() - src.x()) * 0.5)
            cp1x = src.x() + ctrl_offset
            cp1y = src.y()
            cp2x = dst.x() - ctrl_offset
            cp2y = dst.y()
            # Muestrear la curva bezier
            for step in range(41):
                t  = step / 40.0
                t1 = 1 - t
                bx = (t1**3 * src.x()
                      + 3 * t1**2 * t * cp1x
                      + 3 * t1 * t**2 * cp2x
                      + t**3 * dst.x())
                by = (t1**3 * src.y()
                      + 3 * t1**2 * t * cp1y
                      + 3 * t1 * t**2 * cp2y
                      + t**3 * dst.y())
                if (bx - pos.x())**2 + (by - pos.y())**2 < THRESHOLD**2:
                    return idx
        return -1

    # ----------------------------------------------------------
    # Eventos de mouse
    # ----------------------------------------------------------

    def mousePressEvent(self, event):
        pos = event.position().toPoint()

        # Clic derecho: eliminar hilo bajo el cursor
        if event.button() == Qt.MouseButton.RightButton:
            idx = self._wire_hit(pos)
            if idx >= 0:
                self._connections.pop(idx)
                self._hover_wire = -1
                self.update()
            return

        # Clic izquierdo: iniciar o completar conexion
        if event.button() == Qt.MouseButton.LeftButton:
            # Buscar puerto golpeado
            node = self._port_at(pos)
            if node is None:
                # Click en vacio cancela la conexion pendiente
                self._pending = None
                self.update()
                return

            if self._pending is None:
                # Primera mitad: iniciar hilo
                self._pending   = node
                self._mouse_pos = pos
                self.update()
            else:
                # Segunda mitad: completar hilo
                a = self._pending
                b = node
                self._pending = None

                # Los dos nodos deben ser de tipos distintos
                if a.kind == b.kind:
                    self.update()
                    return

                # Garantizar orden (song, sprite)
                if a.kind == "sprite":
                    a, b = b, a
                song_name = a.name
                spr_name  = b.name

                # Verificar que el vinculo no exista ya
                if (song_name, spr_name) not in self._connections:
                    self._connections.append((song_name, spr_name))
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self._mouse_pos = pos

        # Detectar hover sobre hilos (solo cuando no hay conexion pendiente)
        if self._pending is None:
            new_hover = self._wire_hit(pos)
            if new_hover != self._hover_wire:
                self._hover_wire = new_hover
                # Cambiar cursor para indicar que se puede eliminar
                if new_hover >= 0:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                self.update()
        else:
            self.update()   # redibujar hilo en construccion

    def mouseReleaseEvent(self, _event):
        pass

    def resizeEvent(self, _event):
        """Recalcula posiciones cuando cambia el tamano del canvas."""
        self._recalc_nodes()
        self.update()

    # ----------------------------------------------------------
    # Utilidades internas
    # ----------------------------------------------------------

    def _port_at(self, pos: QPoint) -> "_Node | None":
        """Devuelve el nodo cuyo puerto esta en pos, o None."""
        for node in self._song_nodes + self._sprite_nodes:
            if node.port_hit(pos):
                return node
        return None

    def _find_node(self, name: str, kind: str) -> "_Node | None":
        """Busca un nodo por nombre y tipo."""
        lista = self._song_nodes if kind == "song" else self._sprite_nodes
        for node in lista:
            if node.name == name:
                return node
        return None


# ================================================================
# Ventana flotante principal
# ================================================================

class LassoWindow:
    """
    Ventana flotante del editor de vinculos cancion-sprite.

    Uso desde panels.py:
        from ui.lasso_window import LassoWindow
        self._link_win = LassoWindow(parent, lasso_manager, audio_manager)
        self._link_win.show(main_window=self.window)

    Parametros del constructor:
        parent        -- QWidget padre (ventana de Settings)
        lasso_manager  -- instancia de LassoManager
        audio_manager -- instancia de AmbientAudioManager
    """

    # Directorio de sprites del usuario (AppData\Local\Spryta\sprites)
    SPRITES_DIR = USER_SPRITES_DIR

    def __init__(self, parent, lasso_manager, audio_manager,
                 on_playlist_changed=None):
        self.parent               = parent
        self.lasso_manager        = lasso_manager
        self.audio_manager        = audio_manager
        self.on_playlist_changed  = on_playlist_changed

        self.window: "QDialog | None" = None
        self._canvas:    "_NodeCanvas | None" = None
        self._pl_combo:  "QComboBox | None"   = None
        self._lbl_hint:  "QLabel | None"      = None

    # ----------------------------------------------------------
    # Mostrar / ocultar
    # ----------------------------------------------------------

    def show(self, main_window=None) -> None:
        """
        Muestra la ventana del editor de vinculos.
        Si ya estaba abierta la trae al frente.
        """
        if self.window is not None and self.window.isVisible():
            self.window.raise_()
            self.window.activateWindow()
            return

        W, H = 900, 680
        self.window = QDialog(self.parent)
        self.window.setWindowTitle("Lasso Sprites")
        self.window.setModal(False)
        self.window.resize(W, H)
        self.window.setMinimumSize(700, 500)
        self.window.closeEvent = self._on_close

        # Icono
        icon_path = os.path.join("assets", "icons", "icon.ico")
        from PySide6.QtGui import QIcon
        if os.path.exists(icon_path):
            self.window.setWindowIcon(QIcon(icon_path))

        # Posicionar centrado respecto a la ventana principal
        # Centrar en la pantalla disponible, garantizando que no quede fuera.
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width()  - W) // 2
        y = screen.y() + (screen.height() - H) // 2
        self.window.move(x, y)

        self._build_ui()
        self._refresh_playlist_combo()
        self.window.show()

    def close(self) -> None:
        """Cierra la ventana si esta abierta."""
        if self.window:
            self.window.close()
            self.window = None

    def is_visible(self) -> bool:
        """Devuelve True si la ventana existe y es visible."""
        return self.window is not None and self.window.isVisible()

    # ----------------------------------------------------------
    # Construccion de la UI
    # ----------------------------------------------------------

    def _build_ui(self) -> None:
        """Construye todos los widgets de la ventana."""
        root = QVBoxLayout(self.window)
        root.setContentsMargins(theme.SP2, theme.SP2, theme.SP2, theme.SP2)
        root.setSpacing(theme.SP2)

        # ── Titulo ────────────────────────────────────────────
        lbl_title = QLabel("Lasso Sprites")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color: {theme.ACCENT};")
        root.addWidget(lbl_title)

        root.addWidget(self._make_separator())

        # ── Barra de playlist ─────────────────────────────────
        root.addLayout(self._build_playlist_bar())

        # ── Instrucciones ─────────────────────────────────────
        self._lbl_hint = QLabel(
            "Click a song port  \u25b6  then click a sprite port to lasso them.   "
            "Right-click a wire to remove it."
        )
        self._lbl_hint.setFont(theme.FONT_TINY)
        self._lbl_hint.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        root.addWidget(self._lbl_hint)

        # ── Canvas dentro de un QScrollArea ───────────────────
        self._canvas = _NodeCanvas()
        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.BG_BASE};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS}px;
            }}
        """)
        root.addWidget(scroll, 1)

        # ── Barra inferior ────────────────────────────────────
        root.addWidget(self._make_separator())
        root.addLayout(self._build_footer_bar())

    def _build_playlist_bar(self) -> QHBoxLayout:
        """Fila superior: selector de playlist + botones Nuevo / Renombrar / Eliminar."""
        row = QHBoxLayout()
        row.setSpacing(theme.SP1)

        lbl = QLabel("Playlist:")
        lbl.setFont(theme.FONT_SMALL)
        lbl.setStyleSheet(f"color: {theme.TEXT_NORMAL};")
        row.addWidget(lbl)

        self._pl_combo = QComboBox()
        self._pl_combo.setFont(theme.FONT_SMALL)
        self._pl_combo.setMinimumWidth(200)
        self._pl_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._pl_combo.currentIndexChanged.connect(self._on_playlist_changed)
        row.addWidget(self._pl_combo, 1)

        btn_new = QPushButton("+ New")
        btn_new.setFont(theme.FONT_SMALL)
        btn_new.setFixedHeight(34)
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.setStyleSheet(theme.BTN_STYLE)
        btn_new.clicked.connect(self._create_playlist)
        row.addWidget(btn_new)

        btn_ren = QPushButton("Rename")
        btn_ren.setFont(theme.FONT_SMALL)
        btn_ren.setFixedHeight(34)
        btn_ren.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ren.setStyleSheet(theme.BTN_STYLE)
        btn_ren.clicked.connect(self._rename_playlist)
        row.addWidget(btn_ren)

        btn_del = QPushButton("Delete")
        btn_del.setFont(theme.FONT_SMALL)
        btn_del.setFixedHeight(34)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet(theme.DANGER_STYLE)
        btn_del.clicked.connect(self._delete_playlist)
        row.addWidget(btn_del)

        return row

    def _build_footer_bar(self) -> QHBoxLayout:
        """Fila inferior: configuracion de pausa + boton Guardar + boton Cerrar."""
        row = QHBoxLayout()
        row.setSpacing(theme.SP2)

        # -- Opcion de comportamiento al pausar --
        lbl_pause = QLabel("On Pause:")
        lbl_pause.setFont(theme.FONT_SMALL)
        lbl_pause.setStyleSheet(f"color: {theme.TEXT_NORMAL};")
        row.addWidget(lbl_pause)

        self._rb_hide   = QRadioButton("Hide Sprite")
        self._rb_freeze = QRadioButton("Freeze Sprite")
        self._rb_hide.setFont(theme.FONT_SMALL)
        self._rb_freeze.setFont(theme.FONT_SMALL)

        current = self.lasso_manager.get_pause_behavior()
        self._rb_hide.setChecked(current == "hide")
        self._rb_freeze.setChecked(current == "freeze")

        self._rb_group = QButtonGroup(self.window)
        self._rb_group.addButton(self._rb_hide,   0)
        self._rb_group.addButton(self._rb_freeze, 1)

        row.addWidget(self._rb_hide)
        row.addWidget(self._rb_freeze)

        row.addStretch()

        # -- Boton Guardar --
        btn_save = QPushButton("Save")
        btn_save.setFont(theme.FONT_SMALL)
        btn_save.setFixedHeight(36)
        btn_save.setMinimumWidth(100)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.ACCENT};
                color: #ffffff;
                border: 1px solid {theme.ACCENT};
                border-radius: {theme.RADIUS}px;
                padding: 7px 20px;
                font-size: 10pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme.ACCENT_HOVER};
                border-color: {theme.ACCENT_HOVER};
            }}
        """)
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)

        # -- Boton Cerrar --
        btn_close = QPushButton("Close")
        btn_close.setFont(theme.FONT_SMALL)
        btn_close.setFixedHeight(36)
        btn_close.setMinimumWidth(90)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_close)

        return row

    # ----------------------------------------------------------
    # Logica de playlists
    # ----------------------------------------------------------

    def _refresh_playlist_combo(self) -> None:
        """Recarga el QComboBox con los nombres de playlists actuales."""
        if self._pl_combo is None:
            return
        self._pl_combo.blockSignals(True)
        prev = self._pl_combo.currentText()
        self._pl_combo.clear()
        names = self.lasso_manager.get_playlist_names()
        self._pl_combo.addItems(names)
        # Restaurar seleccion previa si sigue existiendo
        idx = self._pl_combo.findText(prev)
        if idx >= 0:
            self._pl_combo.setCurrentIndex(idx)
        self._pl_combo.blockSignals(False)
        self._load_canvas_for_current_playlist()

    def _current_playlist_name(self) -> "str | None":
        """Devuelve el nombre de la playlist actualmente seleccionada, o None."""
        if self._pl_combo is None:
            return None
        name = self._pl_combo.currentText().strip()
        return name if name else None

    def _on_playlist_changed(self, _idx: int) -> None:
        """Recarga el canvas cuando el usuario cambia de playlist."""
        self._load_canvas_for_current_playlist()

    def _load_canvas_for_current_playlist(self) -> None:
        """
        Carga canciones, sprites y vinculos de la playlist seleccionada
        en el canvas de nodos.
        """
        if self._canvas is None:
            return

        pl_name = self._current_playlist_name()
        if pl_name is None:
            self._canvas.set_data([], [], [])
            return

        # Canciones de la playlist
        songs = self.lasso_manager.get_songs(pl_name)

        # Sprites disponibles en disco
        sprites = self._get_available_sprites()

        # Vinculos actuales
        bindings = self.lasso_manager.get_all_bindings(pl_name)
        connections = []
        for song, spr_list in bindings.items():
            for spr in spr_list:
                connections.append((song, spr))

        self._canvas.set_data(songs, sprites, connections)

    def _get_available_sprites(self) -> list:
        """Devuelve la lista de carpetas de sprites disponibles en disco."""
        if not os.path.exists(self.SPRITES_DIR):
            return []
        return sorted([
            d for d in os.listdir(self.SPRITES_DIR)
            if os.path.isdir(os.path.join(self.SPRITES_DIR, d))
        ])

    def _get_available_audio(self) -> list:
        """Devuelve la lista de archivos de audio de la biblioteca."""
        return self.audio_manager.get_audio_files()

    # ----------------------------------------------------------
    # Acciones de playlist
    # ----------------------------------------------------------

    def _create_playlist(self) -> None:
        """Pide un nombre y crea una playlist nueva."""
        name = ask_string(
            "New Playlist",
            "Enter playlist name:",
            parent=self.window,
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return

        # Mostrar selector de canciones de la biblioteca
        songs = self._get_available_audio()
        if not songs:
            show_warning(
                "No Audio",
                "No audio files found in the Audio folder.\n"
                "Upload audio files first.",
                parent=self.window,
            )
            return

        if not self.lasso_manager.create_playlist(name):
            show_warning(
                "Name in use",
                f"A playlist named '{name}' already exists.",
                parent=self.window,
            )
            return

        # Agregar todas las canciones de la biblioteca como punto de partida
        # El usuario elimina las que no quiera desde el canvas
        for song in songs:
            self.lasso_manager.add_song(name, song)

        self._refresh_playlist_combo()
        # Seleccionar la nueva playlist
        idx = self._pl_combo.findText(name)
        if idx >= 0:
            self._pl_combo.setCurrentIndex(idx)
        # Notificar al panel de Ambient Audio para que refresque su combo
        if callable(self.on_playlist_changed):
            self.on_playlist_changed()
        show_info("Created", f"Playlist '{name}' created.", parent=self.window)

    def _rename_playlist(self) -> None:
        """Pide un nuevo nombre y renombra la playlist actual."""
        pl_name = self._current_playlist_name()
        if pl_name is None:
            show_warning("No Playlist", "Select a playlist first.", parent=self.window)
            return

        new_name = ask_string(
            "Rename Playlist",
            f"New name for '{pl_name}':",
            parent=self.window,
            initial=pl_name,
        )
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()

        if not self.lasso_manager.rename_playlist(pl_name, new_name):
            show_warning(
                "Error",
                f"Could not rename. '{new_name}' may already exist.",
                parent=self.window,
            )
            return

        self._refresh_playlist_combo()
        idx = self._pl_combo.findText(new_name)
        if idx >= 0:
            self._pl_combo.setCurrentIndex(idx)
        if callable(self.on_playlist_changed):
            self.on_playlist_changed()

    def _delete_playlist(self) -> None:
        """Elimina la playlist actual tras confirmacion."""
        pl_name = self._current_playlist_name()
        if pl_name is None:
            show_warning("No Playlist", "Select a playlist first.", parent=self.window)
            return

        if not ask_yes_no(
            "Delete Playlist",
            f"Delete '{pl_name}' and all its lassos?\nThis cannot be undone.",
            parent=self.window,
        ):
            return

        self.lasso_manager.delete_playlist(pl_name)
        self._refresh_playlist_combo()
        if callable(self.on_playlist_changed):
            self.on_playlist_changed()

    # ----------------------------------------------------------
    # Guardar
    # ----------------------------------------------------------

    def _save(self) -> None:
        """
        Lee el estado actual del canvas y lo persiste en LassoManager.

        Flujo:
          1. Leer la playlist activa.
          2. Leer los vinculos del canvas.
          3. Borrar los vinculos previos de esa playlist en LassoManager.
          4. Escribir los vinculos nuevos del canvas.
          5. Guardar el comportamiento al pausar.
          6. Llamar a lasso_manager.save() para persistir en disco.
        """
        pl_name = self._current_playlist_name()
        if pl_name is None:
            show_warning("No Playlist", "Select a playlist first.", parent=self.window)
            return

        if self._canvas is None:
            return

        # Guardar comportamiento al pausar
        behavior = "hide" if self._rb_hide.isChecked() else "freeze"
        self.lasso_manager.set_pause_behavior(behavior)

        # Obtener vinculos del canvas
        canvas_connections = self._canvas.get_connections()

        # Reconstruir vinculos en LassoManager para esta playlist:
        # primero limpiar todos los vinculos existentes de esta playlist
        pl_data = self.lasso_manager.get_playlist(pl_name)
        if pl_data is not None:
            pl_data["bindings"] = {}   # limpia en memoria

        # Ahora escribir los vinculos del canvas
        for song_name, spr_name in canvas_connections:
            self.lasso_manager.add_binding(pl_name, song_name, spr_name)

        # Persistir en disco
        self.lasso_manager.save()

        show_info(
            "Saved",
            f"Playlist '{pl_name}' saved with "
            f"{len(canvas_connections)} lasso(s).",
            parent=self.window,
        )

    # ----------------------------------------------------------
    # Evento de cierre
    # ----------------------------------------------------------

    def _on_close(self, event) -> None:
        """Intercepta el boton X de la ventana."""
        event.accept()
        self.window = None
        self._canvas    = None
        self._pl_combo  = None
        self._lbl_hint  = None

    # ----------------------------------------------------------
    # Helpers visuales
    # ----------------------------------------------------------

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(
            f"background-color: {theme.BORDER_MID}; border: none;"
        )
        return sep
