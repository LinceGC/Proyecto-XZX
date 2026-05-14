# -*- coding: utf-8 -*-
"""
src/ui/help.py  —  Spryta Help Window (PySide6)

Ventana de ayuda con sidebar de navegacion y area de contenido scrollable.

API PUBLICA — identica al help.py anterior de tkinter:

    help_window = HelpWindow(parent)
    help_window.show()

Uso (sin cambiar nada en setting.pyw):
    from ui.help import HelpWindow
    self.help_window = HelpWindow(master)
    self.help_window.show()
"""

import os

from PySide6.QtCore    import Qt, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui     import QFont, QIcon, QColor, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel,
    QScrollArea, QSizePolicy,
    QApplication,
)

from ui import theme


# ============================================================
# SECCION 1: CONSTANTES INTERNAS
# ============================================================

_WIN_W    = 720   # ancho de la ventana de ayuda
_WIN_H    = 680   # alto
_SIDEBAR  = 160   # ancho del sidebar de navegacion
_CONTENT  = _WIN_W - _SIDEBAR - 1   # ancho del area de contenido

def _make_flag_icon(language: str) -> QIcon:
    """Crea una bandera pequena por codigo, sin assets externos."""
    pixmap = QPixmap(28, 20)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    if language == "es":
        painter.fillRect(0, 0, 28, 5, QColor("#AA151B"))
        painter.fillRect(0, 5, 28, 10, QColor("#F1BF00"))
        painter.fillRect(0, 15, 28, 5, QColor("#AA151B"))
        painter.fillRect(7, 8, 3, 5, QColor("#C60B1E"))
    else:
        painter.fillRect(0, 0, 28, 20, QColor("#012169"))

        white_pen = QPen(QColor("#FFFFFF"), 5)
        painter.setPen(white_pen)
        painter.drawLine(0, 0, 28, 20)
        painter.drawLine(28, 0, 0, 20)

        red_pen = QPen(QColor("#C8102E"), 2)
        painter.setPen(red_pen)
        painter.drawLine(0, 0, 28, 20)
        painter.drawLine(28, 0, 0, 20)

        painter.fillRect(11, 0, 6, 20, QColor("#FFFFFF"))
        painter.fillRect(0, 7, 28, 6, QColor("#FFFFFF"))
        painter.fillRect(13, 0, 2, 20, QColor("#C8102E"))
        painter.fillRect(0, 9, 28, 2, QColor("#C8102E"))

    painter.setPen(QPen(QColor("#000000"), 1))
    painter.drawRect(0, 0, 27, 19)
    painter.end()
    return QIcon(pixmap)
    
    
# ============================================================
# SECCION 2: CLASE PRINCIPAL
# ============================================================

class HelpWindow:
    """
    Ventana de ayuda de Spryta.

    Diseno:
        +------------------+----------------------------------+
        | HEADER                                              |
        +------------------+----------------------------------+
        | Sidebar          | Area de contenido scrollable    |
        | [Shortcuts]      |                                  |
        | [Sprites]        | Titulo de seccion               |
        | [Reel]           | ─────────────────                |
        | [Scenes]         | Texto, shortcuts, pasos...      |
        | [Audio]          |                                  |
        | [Create Frame]   |                                  |
        | [About]          |                                  |
        +------------------+----------------------------------+
        | FOOTER                           [Close]           |
        +-----------------------------------------------------+

    Uso:
        hw = HelpWindow(parent_qwidget)
        hw.show()
    """

    def __init__(self, parent=None, on_clear_frame_cache=None):
        """
        Parametros:
            parent -- QWidget padre (la ventana principal de settings).
                      Se usa para centrar la ventana de ayuda sobre ella.
                      Puede ser None.
        """
        self.parent_widget = parent
        self._window       = None   # QDialog, se crea al llamar show()
        self._language     = "en"   # idioma por defecto del contenido explicativo
        self._current_section = None
        self._lang_btns    = {}
        self._on_clear_frame_cache = on_clear_frame_cache
        
    # =========================================================
    # API PUBLICA
    # =========================================================

    def show(self):
        """
        Abre la ventana de ayuda.
        Si ya estaba abierta la trae al frente en lugar de crear una nueva.

        Uso:
            self.help_window.show()
        """
        # Si la ventana ya existe y sigue abierta, traerla al frente
        if self._window is not None and self._window.isVisible():
            self._window.raise_()
            self._window.activateWindow()
            return

        # Crear ventana nueva
        self._window = self._build_window()
        self._center_window()
        self._window.show()

    def set_dark_mode(self, dark_mode: bool):
        """
        Actualiza el tema de la ventana de ayuda.
        Si estaba abierta, la cierra y la reabre con los colores nuevos.
        Si estaba cerrada, simplemente destruye la instancia guardada
        para que la proxima vez que se abra use los colores correctos.

        Uso desde setting.pyw (dentro de _toggle_theme):
            self.help_window.set_dark_mode(self.dark_mode)
        """
        was_visible = self._window is not None and self._window.isVisible()

        # Destruir la ventana actual para forzar recreacion con nuevo tema
        if self._window is not None:
            self._window.close()
            self._window = None

        # Si estaba abierta, reabrirla inmediatamente con el tema nuevo
        if was_visible:
            self.show()

    # =========================================================
    # CONSTRUCCION DE LA VENTANA
    # =========================================================

    def _build_window(self) -> QDialog:
        """
        Construye y devuelve el QDialog completo.
        Se llama una sola vez al abrir la ventana.
        """
        win = QDialog(self.parent_widget)
        win.setWindowTitle("Spryta - Help")
        win.setFixedSize(_WIN_W, _WIN_H)
        win.setModal(False)   # no bloquea la ventana principal

        # Icono de la aplicacion
        icon_path = os.path.join("assets", "icons", "icon.ico")
        if os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))

        # Layout raiz (sin margenes, ocupa toda la ventana)
        root_layout = QVBoxLayout(win)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── 1. Header ─────────────────────────────────────────
        root_layout.addWidget(self._build_header())

        # Separador bajo el header
        root_layout.addWidget(_make_hsep())

        # ── 2. Cuerpo: sidebar + contenido ────────────────────
        body = QWidget()
        body.setObjectName("HelpBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar de navegacion
        self._sidebar_btns = {}   # nombre -> QPushButton
        sidebar_widget = self._build_sidebar()
        body_layout.addWidget(sidebar_widget)

        # Separador vertical entre sidebar y contenido
        body_layout.addWidget(_make_vsep())

        # Area de contenido scrollable
        self._content_area = self._build_content_area()
        body_layout.addWidget(self._content_area, 1)

        root_layout.addWidget(body, 1)

        # ── 3. Footer ─────────────────────────────────────────
        root_layout.addWidget(_make_hsep())
        root_layout.addWidget(self._build_footer(win))

        # Mostrar primera seccion al abrir
        first_section = list(self._sections.keys())[0]
        self._show_section(first_section)

        return win

    # ----------------------------------------------------------
    # Header
    # ----------------------------------------------------------

    def _build_header(self) -> QWidget:
        """Barra superior con titulo y numero de version."""
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(56)
        header.setStyleSheet(f"""
            QWidget#Header {{
                background-color: {theme.BG_SURFACE};
            }}
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(
            theme.PADDING_NORMAL,   # izq  16px
            0,
            theme.PADDING_NORMAL,   # der  16px
            0,
        )

        lbl_title = QLabel("Help & Shortcuts")
        lbl_title.setFont(theme.FONT_TITLE)
        lbl_title.setStyleSheet(f"color: {theme.TEXT_BRIGHT}; background: transparent;")

        lbl_version = QLabel("v1.0.0")
        lbl_version.setFont(theme.FONT_SMALL)
        lbl_version.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")

        layout.addWidget(lbl_title)
        layout.addStretch()
        layout.addWidget(lbl_version)

        return header

    # ----------------------------------------------------------
    # Sidebar
    # ----------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        """
        Panel lateral izquierdo con botones de navegacion.
        Cada boton llama a _show_section() al hacer clic.
        """
        # Definicion de secciones: nombre -> metodo constructor de contenido
        # El orden aqui define el orden visual en el sidebar
        self._sections = {
            "Shortcuts"   : self._content_shortcuts,
            "Solo"        : self._content_solo,
            "Reel"        : self._content_reel,
            "Scenes"      : self._content_scenes,
            "Ambient Audio": self._content_audio,
            "Create Frame": self._content_create_frame,
            "Cache"       : self._content_cache,
            "About"       : self._content_about,
        }

        sidebar = QWidget()
        sidebar.setObjectName("HelpSidebar")
        sidebar.setFixedWidth(_SIDEBAR)
        sidebar.setStyleSheet(f"""
            QWidget#HelpSidebar {{
                background-color: {theme.BG_SURFACE};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(
            theme.SP1,   # izq  8px
            theme.SP2,   # arr  16px
            theme.SP1,   # der  8px
            theme.SP2,   # aba  16px
        )
        layout.setSpacing(2)

        for name in self._sections:
            btn = QPushButton(name)
            btn.setFont(theme.FONT_SMALL)
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(False)
            # Alineacion del texto a la izquierda
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {theme.TEXT_MUTED};
                    border: none;
                    border-radius: {theme.RADIUS}px;
                    padding: 0px {theme.SP1}px;
                    text-align: left;
                    font-size: 9pt;
                }}
                QPushButton:hover {{
                    background-color: {theme.BG_HOVER};
                    color: {theme.TEXT_BRIGHT};
                }}
            """)
            # Conectar el clic a _show_section pasando el nombre
            btn.clicked.connect(lambda checked=False, n=name: self._show_section(n))
            layout.addWidget(btn)
            self._sidebar_btns[name] = btn

        layout.addStretch()
        return sidebar

    # ----------------------------------------------------------
    # Area de contenido
    # ----------------------------------------------------------

    def _build_content_area(self) -> QScrollArea:
        """
        Area scrollable donde se muestra el contenido de cada seccion.
        El QScrollArea contiene un QWidget interior que se reemplaza
        cada vez que el usuario cambia de seccion.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.BG_BASE};
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {theme.BG_BASE};
            }}
        """)

        # Widget interior vacio; se rellena en _show_section()
        placeholder = QWidget()
        placeholder.setStyleSheet(f"background-color: {theme.BG_BASE};")
        scroll.setWidget(placeholder)

        return scroll

    # ----------------------------------------------------------
    # Footer
    # ----------------------------------------------------------

    def _build_footer(self, win: QDialog) -> QWidget:
        """Barra inferior con boton Close."""
        footer = QWidget()
        footer.setObjectName("HelpFooter")
        footer.setFixedHeight(122)
        footer.setStyleSheet(f"""
            QWidget#HelpFooter {{
                background-color: {theme.BG_SURFACE};
            }}
        """)

        layout = QHBoxLayout(footer)

        layout.setContentsMargins(
            theme.PADDING_NORMAL,
            12,
            theme.PADDING_NORMAL,
            4
        )
        layout.setSpacing(theme.SP1)

        # Selector de idioma: queda anclado en la esquina inferior izquierda.
        # Las banderas se dibujan por codigo para mantener compatibilidad con PyInstaller.
        self._lang_btns = {}
        for lang, label in (("es", "ES"), ("en", "EN")):
            btn_lang = QPushButton(label)
            btn_lang.setFont(theme.FONT_SMALL)
            btn_lang.setIcon(_make_flag_icon(lang))
            btn_lang.setIconSize(QSize(28, 20))
            btn_lang.setFixedSize(100, 34)
            btn_lang.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_lang.clicked.connect(lambda checked=False, code=lang: self._set_language(code))
            layout.addWidget(btn_lang)
            self._lang_btns[lang] = btn_lang

        self._refresh_language_buttons()
        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFont(theme.FONT_SMALL)
        btn_close.setFixedSize(100, 34)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.set_role(btn_close, "primary")
        btn_close.clicked.connect(win.close)
        layout.addWidget(btn_close)

        return footer

    # =========================================================
    # NAVEGACION ENTRE SECCIONES
    # =========================================================

    def _show_section(self, name: str):
        """
        Cambia el contenido visible al de la seccion indicada.
        Actualiza el estado visual de los botones del sidebar.

        Parametros:
            name -- nombre de la seccion (debe existir en self._sections)
        """
        # ── Actualizar estado visual de los botones ───────────
        for btn_name, btn in self._sidebar_btns.items():
            if btn_name == name:
                # Boton activo: fondo azul dim, texto azul, negrita
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {theme.ACCENT_DIM};
                        color: {theme.ACCENT};
                        border: none;
                        border-radius: {theme.RADIUS}px;
                        padding: 0px {theme.SP1}px;
                        text-align: left;
                        font-size: 9pt;
                        font-weight: bold;
                    }}
                """)
            else:
                # Boton inactivo: vuelve al estilo normal
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {theme.TEXT_MUTED};
                        border: none;
                        border-radius: {theme.RADIUS}px;
                        padding: 0px {theme.SP1}px;
                        text-align: left;
                        font-size: 9pt;
                    }}
                    QPushButton:hover {{
                        background-color: {theme.BG_HOVER};
                        color: {theme.TEXT_BRIGHT};
                    }}
                """)

        # ── Construir el contenido nuevo ──────────────────────
        # Creamos un QWidget fresco y le pasamos al metodo constructor
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {theme.BG_BASE};")

        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, theme.SP1, theme.SP3)
        content_layout.setSpacing(0)

        # Llamar al metodo que rellena el contenido de esta seccion
        self._current_section = name
        builder_fn = self._sections[name]
        builder_fn(content_layout)

        # Espaciado final al fondo
        content_layout.addStretch()

        # Reemplazar el widget interior del QScrollArea
        self._content_area.setWidget(content_widget)
        # Volver al inicio del scroll
        self._content_area.verticalScrollBar().setValue(0)
        
    def _set_language(self, language: str):
        """Cambia el idioma de las explicaciones sin traducir los conceptos."""
        if language not in ("en", "es") or language == self._language:
            return

        self._language = language
        self._refresh_language_buttons()

        # Reconstruir solo la seccion visible. Si algo aun no esta listo,
        # salir sin romper la apertura de la ventana de ayuda.
        if self._current_section and hasattr(self, "_content_area"):
            self._show_section(self._current_section)

    def _refresh_language_buttons(self):
        """Actualiza el estado visual de los botones EN/ES."""
        for lang, btn in getattr(self, "_lang_btns", {}).items():
            if lang == self._language:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {theme.ACCENT_DIM};
                        color: {theme.ACCENT};
                        border: 1px solid {theme.ACCENT};
                        border-radius: {theme.RADIUS}px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {theme.TEXT_MUTED};
                        border: 1px solid {theme.BORDER_MID};
                        border-radius: {theme.RADIUS}px;
                    }}
                    QPushButton:hover {{
                        background-color: {theme.BG_HOVER};
                        color: {theme.TEXT_BRIGHT};
                    }}
                """)        

    # =========================================================
    # HELPERS DE CONTENIDO
    # Equivalentes a los metodos _section_title, _line, etc.
    # del help.py anterior, pero construyen widgets Qt.
    # =========================================================

    def _section_title(self, layout: QVBoxLayout, text: str):
        """
        Agrega un titulo de seccion azul con separador debajo.
        Equivalente al _section_title() del help.py de tkinter.

        Parametros:
            layout -- QVBoxLayout donde agregar el titulo
            text   -- texto del titulo
        """
        # Espacio antes del titulo
        spacer = QWidget()
        spacer.setFixedHeight(theme.SP3)   # 24px
        spacer.setStyleSheet("background: transparent;")
        layout.addWidget(spacer)

        # Label del titulo
        lbl = QLabel(text)
        lbl.setFont(theme.FONT_SECTION)
        lbl.setStyleSheet(f"""
            color: {theme.ACCENT};
            background: transparent;
            padding-left: {theme.SP2}px;
        """)
        layout.addWidget(lbl)

        # Separador bajo el titulo
        sep = _make_hsep()
        sep.setContentsMargins(theme.SP2, 0, theme.SP2, 0)
        layout.addWidget(sep)

        # Pequeno espacio tras el separador
        spacer2 = QWidget()
        spacer2.setFixedHeight(theme.SP1)   # 8px
        spacer2.setStyleSheet("background: transparent;")
        layout.addWidget(spacer2)

    def _line(self, layout: QVBoxLayout, text: str, indent: bool = False):
        """
        Agrega una linea de texto normal.
        Si text es vacio, agrega espacio vertical.
        Si indent es True, agrega sangria extra (para subitems).

        Equivalente al _line() del help.py de tkinter.
        """
        if text == "":
            spacer = QWidget()
            spacer.setFixedHeight(6)
            spacer.setStyleSheet("background: transparent;")
            layout.addWidget(spacer)
            return

        pad_left = (theme.SP3 + theme.SP1) if indent else theme.SP2   # 32px o 16px

        lbl = QLabel(text)
        lbl.setFont(theme.FONT_SMALL)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"""
            color: {theme.TEXT_NORMAL};
            background: transparent;
            padding-left: {pad_left}px;
            padding-right: {theme.SP2}px;
        """)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(lbl)

        # Pequeno espacio entre lineas
        gap = QWidget()
        gap.setFixedHeight(3)
        gap.setStyleSheet("background: transparent;")
        layout.addWidget(gap)

    def _shortcut_row(self, layout: QVBoxLayout, key: str, description: str):
        """
        Agrega una fila con badge de tecla y descripcion.
        Equivalente al _shortcut_row() del help.py de tkinter.

        Parametros:
            layout      -- QVBoxLayout donde agregar la fila
            key         -- texto de la tecla, ej: "Ctrl + Alt + S"
            description -- descripcion de la accion
        """
        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(theme.SP2, 2, theme.SP2, 2)
        row_layout.setSpacing(theme.SP2)

        # Badge de tecla: fondo oscuro, texto azul, fuente mono
        lbl_key = QLabel(key)
        lbl_key.setFont(theme.FONT_MONO)
        lbl_key.setStyleSheet(f"""
            color: {theme.ACCENT};
            background-color: {theme.BG_RAISED};
            border-radius: {theme.RADIUS_SMALL}px;
            padding: 3px 8px;
        """)
        lbl_key.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        lbl_desc = QLabel(description)
        lbl_desc.setFont(theme.FONT_SMALL)
        lbl_desc.setStyleSheet(f"color: {theme.TEXT_NORMAL}; background: transparent;")

        row_layout.addWidget(lbl_key)
        row_layout.addWidget(lbl_desc, 1)

        layout.addWidget(row_widget)

    def _step_list(self, layout: QVBoxLayout, steps: list):
        """
        Agrega una lista numerada de pasos.
        Equivalente al _step_list() del help.py de tkinter.

        Parametros:
            layout -- QVBoxLayout donde agregar la lista
            steps  -- lista de strings, uno por paso
        """
        for i, step in enumerate(steps, 1):
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(theme.SP2, 2, theme.SP2, 2)
            row_layout.setSpacing(theme.SP1)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            # Numero en azul
            lbl_num = QLabel(f"{i}.")
            lbl_num.setFont(theme.FONT_MONO)
            lbl_num.setFixedWidth(22)
            lbl_num.setStyleSheet(f"color: {theme.ACCENT}; background: transparent;")
            lbl_num.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

            # Texto del paso
            lbl_step = QLabel(step)
            lbl_step.setFont(theme.FONT_SMALL)
            lbl_step.setWordWrap(True)
            lbl_step.setStyleSheet(f"color: {theme.TEXT_NORMAL}; background: transparent;")
            lbl_step.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

            row_layout.addWidget(lbl_num)
            row_layout.addWidget(lbl_step, 1)
            layout.addWidget(row_widget)

    # =========================================================
    # CONTENIDO DE CADA SECCION
    # Identico al contenido del help.py original.
    # Solo cambia el mecanismo: en lugar de tk.Label usamos
    # los helpers _section_title, _line, _shortcut_row, _step_list.
    # =========================================================

    def _content_shortcuts(self, layout: QVBoxLayout):
        if self._language == "es":
            self._section_title(layout, "Atajos globales de teclado")
            self._shortcut_row(layout, "Ctrl + Alt + S", "Mostrar / ocultar todos los sprites en ejecucion")
            self._line(layout, "")
            self._line(layout,
                "Estos atajos funcionan en cualquier momento, incluso cuando "
                "la ventana Settings esta minimizada o en la bandeja del sistema."
            )

            self._section_title(layout, "Controles del mouse para sprites")
            self._shortcut_row(layout, "Clic izquierdo + arrastrar", "Mover el sprite libremente")
            self._shortcut_row(layout, "Icono de la bandeja > Close", "Cerrar el sprite")
            return

        self._section_title(layout, "Global Keyboard Shortcuts")
        self._shortcut_row(layout, "Ctrl + Alt + S", "Show / Hide all running sprites")
        self._line(layout, "")
        self._line(layout,
            "These shortcuts work at any time, even when "
            "the Settings window is minimized or in the system tray."
        )

        self._section_title(layout, "Sprite Mouse Controls")
        self._shortcut_row(layout, "Left click + drag", "Move the sprite freely")
        self._shortcut_row(layout, "Tray icon > Close", "Close the sprite")

    def _content_solo(self, layout: QVBoxLayout):
        if self._language == "es":
            self._section_title(layout, "Que es Solo?")
            self._line(layout,
                "Solo te permite ejecutar un personaje animado individual en tu escritorio. "
                "Se compone de una carpeta con frames PNG que se reproducen en secuencia."
            )

            self._section_title(layout, "Como agregar un Solo")
            self._step_list(layout, [
                "Crea una carpeta dentro del directorio 'sprites/'.",
                "Coloca tus frames PNG dentro de esa carpeta. "
                "Nombralos en orden: frame_0001.png, frame_0002.png, etc.",
                "Haz clic en 'Add Sprite' en Settings, o coloca la carpeta manualmente.",
                "Selecciona el sprite desde la galeria y configura sus parametros.",
                "Haz clic en 'Run Solo' para iniciarlo en tu escritorio.",
            ])

            self._section_title(layout, "Parametros de sprite")
            self._line(layout, "Frame Size: Ancho y alto en pixeles de la ventana de Solo.")
            self._line(layout, "Dynamic Mod: Como se mueve Solo en pantalla:")
            self._line(layout, "Stitched: permanece en una posicion fija.", indent=True)
            self._line(layout, "Walk: camina de un lado al otro.", indent=True)
            self._line(layout, "Wandering: rebota libremente por la pantalla.", indent=True)
            self._line(layout, "Movement Speed: Que tan rapido se mueve Solo (30 / 60 / 120 fps).")
            self._line(layout, "Delay Mode: Controla la velocidad de animacion:")
            self._line(layout, "Fixed: retraso constante en milisegundos.", indent=True)
            self._line(layout, "CPU: el retraso se ajusta automaticamente segun el uso de CPU.", indent=True)
            self._line(layout, "Presentation: retraso largo por frame, en segundos.", indent=True)
            return
            
        self._section_title(layout, "What is Solo?")
        self._line(layout,
            "Solo lets you run a single animated character on your desktop. "
            "It is made of a folder containing PNG frames that play in sequence."
        )

        self._section_title(layout, "How to add a Solo")
        self._step_list(layout, [
            "Create a folder inside the 'sprites/' directory.",
            "Place your PNG frames inside that folder. "
            "Name them in order: frame_0001.png, frame_0002.png, etc.",
            "Click 'Add Sprite' in Settings, or place the folder manually.",
            "Select the sprite from the gallery and configure its parameters.",
            "Click 'Run Solo' to launch it on your desktop.",
        ])

        self._section_title(layout, "Sprite Parameters")
        self._line(layout, "Frame Size: Width and height in pixels of the solo window.")
        self._line(layout, "Dynamic Mode: How the solo moves on screen:")
        self._line(layout, "Stitched: stays in a fixed position.", indent=True)
        self._line(layout, "Walk: walks from one side to the other.", indent=True)
        self._line(layout, "Wandering: bounces freely around the screen.", indent=True)
        self._line(layout, "Movement Speed: How fast the solo moves (30 / 60 / 120 fps).")
        self._line(layout, "Delay Mode: Controls animation speed:")
        self._line(layout, "Fixed: constant delay in milliseconds.", indent=True)
        self._line(layout, "CPU: delay adjusts automatically based on CPU usage.", indent=True)
        self._line(layout, "Presentation: long delay per frame, in seconds.", indent=True)

    def _content_reel(self, layout: QVBoxLayout):
        if self._language == "es":
            self._section_title(layout, "Que es un Reel?")
            self._line(layout,
                "Un Reel es una secuencia de sprites que se reproducen uno despues de otro "
                "en una sola ventana. Cuando un sprite termina sus ciclos, el siguiente "
                "toma el control automaticamente."
            )

            self._section_title(layout, "Como crear un Reel")
            self._step_list(layout, [
                "Haz clic en 'Create' dentro de la seccion Reel.",
                "Ingresa un nombre para el Reel.",
                "Define la cantidad de ciclos por sprite "
                "(cuantas veces se repite cada sprite antes de pasar al siguiente).",
                "Agrega sprites desde la lista disponible y organiza su orden.",
                "Haz clic en 'Save Reel'.",
            ])

            self._section_title(layout, "Parametros de Reel")
            self._line(layout,
                "Frame Size y Dynamic Mode se comparten para todo el Reel. "
                "Delay Mode es individual: cada sprite usa su propia configuracion guardada. "
                "Selecciona un Reel, ajusta los parametros y luego haz clic en 'Run Reel'. "
                "La configuracion se guarda automaticamente al ejecutar el Reel."
            )
            return
        
        self._section_title(layout, "What is a Reel?")
        self._line(layout,
            "A Reel is a sequence of sprites that play one after another "
            "in a single window. When one sprite finishes its cycles, the next "
            "one takes over automatically."
        )

        self._section_title(layout, "How to create a Reel")
        self._step_list(layout, [
            "Click 'Create' in the Reel section.",
            "Enter a name for the Reel.",
            "Set the number of cycles per sprite "
            "(how many times each sprite loops before switching to the next).",
            "Add sprites from the available list and arrange their order.",
            "Click 'Save Reel'.",
        ])

        self._section_title(layout, "Reel Parameters")
        self._line(layout,
            "Frame Size and Dynamic Mode are shared for the whole Reel. "
            "Delay Mode is individual: each sprite uses its own saved delay settings. "
            "Select a Reel, adjust the parameters, then click 'Run Reel'. "
            "The configuration is saved automatically when you run the Reel."
        )

    def _content_scenes(self, layout: QVBoxLayout):
        if self._language == "es":
            self._section_title(layout, "Que es Scenes?")
            self._line(layout,
                "Scenes es un grupo de sprites individuales que se inician juntos "
                "al mismo tiempo, cada uno en su propia ventana. "
                "Es util para preparar un escritorio con varios personajes a la vez."
            )

            self._section_title(layout, "Como crear Scenes")
            self._step_list(layout, [
                "Haz clic en 'Create' dentro de la seccion Scenes.",
                "Ingresa un nombre para Scenes.",
                "Marca los sprites que quieres incluir.",
                "Haz clic en 'Save'.",
                "Selecciona Scenes y haz clic en 'Run Scene' para iniciar todos los sprites.",
            ])

            self._section_title(layout, "Consejos")
            self._line(layout,
                "Cada sprite en Scenes usa su propia configuracion individual. "
                "Puedes reposicionar cada sprite manualmente arrastrandolo, "
                "y su posicion se guardara automaticamente."
            )
            return
        self._section_title(layout, "What is a Scene?")
        self._line(layout,
            "A scene is a group of individual sprites that launch together "
            "at the same time, each in its own window. "
            "Useful for setting up a desktop with multiple characters at once."
        )

        self._section_title(layout, "How to create a Scene")
        self._step_list(layout, [
            "Click 'Create' in the Scenes section.",
            "Enter a name for the scene.",
            "Check the sprites you want to include.",
            "Click 'Save'.",
            "Select the scene and click 'Run Scene' to launch all sprites.",
        ])

        self._section_title(layout, "Tips")
        self._line(layout,
            "Each sprite in a scene uses its own individual configuration. "
            "You can reposition each sprite manually by dragging it, "
            "and its position will be saved automatically."
        )

    def _content_audio(self, layout: QVBoxLayout):
        if self._language == "es":
            self._section_title(layout, "Que es Ambient Audio?")
            self._line(layout,
                "Ambient Audio te permite reproducir musica de fondo o sonidos "
                "mientras tus sprites estan ejecutandose en el escritorio."
            )

            self._section_title(layout, "Como usar Ambient Audio")
            self._step_list(layout, [
                "Haz clic en el boton 'Ambient Audio' en Settings.",
                "Haz clic en 'Upload Audio' para agregar archivos MP3, WAV, OGG, FLAC o AAC.",
                "Selecciona un archivo de la lista.",
                "Haz clic en 'Play Loop' para repetirlo indefinidamente, "
                "o en 'Play List' para reproducir todos los archivos en secuencia.",
                "Usa el control de volumen para ajustar el nivel.",
                "Haz clic en el icono de bandeja para minimizar el panel de audio silenciosamente.",
            ])

            self._section_title(layout, "Consejos")
            self._line(layout,
                "El audio continua reproduciendose incluso cuando Settings esta minimizado en la bandeja. "
                "Usa 'Stop' para silenciarlo en cualquier momento."
            )
            return
            
        self._section_title(layout, "What is Ambient Audio?")
        self._line(layout,
            "Ambient Audio lets you play background music or sounds "
            "while your sprites are running on the desktop."
        )

        self._section_title(layout, "How to use Ambient Audio")
        self._step_list(layout, [
            "Click 'Ambient Audio' button in Settings.",
            "Click 'Upload Audio' to add MP3, WAV, OGG, FLAC or AAC files.",
            "Select a file from the list.",
            "Click 'Play Loop' to repeat it indefinitely, "
            "or 'Play List' to play all files in sequence.",
            "Use the volume slider to adjust the level.",
            "Click the tray icon to minimize the audio panel silently.",
        ])

        self._section_title(layout, "Tips")
        self._line(layout,
            "Audio continues playing even when Settings is minimized to tray. "
            "Use 'Stop' to silence the audio at any time."
        )

    def _content_create_frame(self, layout: QVBoxLayout):
        if self._language == "es":
            self._section_title(layout, "Que es Create Frame?")
            self._line(layout,
                "Create Frame extrae frames PNG individuales desde un archivo de video "
                "o GIF animado, y los guarda como una carpeta de sprite lista para usar."
            )

            self._section_title(layout, "Como usar Create Frame")
            self._step_list(layout, [
                "Haz clic en el boton 'Create Frame' en Settings.",
                "Define los frames por segundo a extraer: "
                "0 = todos los frames, o elige 15 / 24 / 30 / 60.",
                "Haz clic en 'Select Video/GIF' y elige tu archivo.",
                "Ingresa un nombre de carpeta para los frames de salida.",
                "Los frames se guardaran dentro de la carpeta 'sprites/', "
                "listos para usarse como un nuevo sprite.",
            ])

            self._section_title(layout, "Formatos compatibles")
            self._line(layout, "Video:  MP4, AVI, MOV, MKV, FLV, WMV, WEBM, MPEG, MPG")
            self._line(layout, "Imagenes: GIF (animado)")
            
            self._section_title(layout, "Consejos")
            self._line(layout, 
                "Utilizar un editor de imagen para eliminar los fondos "
                "manualmente o una herramienta de IA"
            )
           
            return
            
        self._section_title(layout, "What is Create Frame?")
        self._line(layout,
            "Create Frame extracts individual PNG frames from a video file or "
            "animated GIF, and saves them as a ready-to-use sprite folder."
        )

        self._section_title(layout, "How to use Create Frame")
        self._step_list(layout, [
            "Click 'Create Frame' button in Settings.",
            "Set the frames per second to extract: "
            "0 = every single frame, or choose 15 / 24 / 30 / 60.",
            "Click 'Select Video/GIF' and choose your file.",
            "Enter a folder name for the output frames.",
            "The frames will be saved inside the 'sprites/' folder, "
            "ready to be used as a new sprite.",
        ])

        self._section_title(layout, "Supported formats")
        self._line(layout, "Video:  MP4, AVI, MOV, MKV, FLV, WMV, WEBM, MPEG, MPG")
        self._line(layout, "Images: GIF (animated)")
        
        self._section_title(layout, "Tips")
        self._line(layout, 
            "Use an image editor to remove backgrounds "
            "manually or an AI tool"
        )

    def _content_cache(self, layout: QVBoxLayout):
        """Contenido de ayuda para mantenimiento de cache."""
        if self._language == "es":
            self._section_title(layout, "Cache")
            self._line(layout,
                "Spryta guarda frames procesados en una cache local para que los sprites "
                "carguen mas rapido despues de crearlos o convertirlos."
            )
            self._line(layout,
                "Usa Clear Frame Cache si notas frames antiguos, archivos temporales "
                "acumulados o quieres forzar que Spryta reconstruya esos datos en el "
                "proximo inicio."
            )
            self._line(layout,
                "Esto no elimina tus sprites originales. Solo borra frames procesados "
                "que Spryta puede volver a generar."
            )
        else:
            self._section_title(layout, "Cache")
            self._line(layout,
                "Spryta stores processed frames in a local cache so sprites load faster "
                "after they are created or converted."
            )
            self._line(layout,
                "Use Clear Frame Cache if you notice stale frames, accumulated temporary "
                "files, or want Spryta to rebuild those generated files on the next launch."
            )
            self._line(layout,
                "This does not delete your original sprites. It only removes processed "
                "frames that Spryta can generate again."
            )

        self._line(layout, "")

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(theme.SP2, theme.SP2, theme.SP2, theme.SP2)
        row_layout.setSpacing(theme.SP1)

        btn_clear = QPushButton("Clear Frame Cache")
        btn_clear.setFont(theme.FONT_SMALL)
        btn_clear.setFixedHeight(34)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setEnabled(callable(self._on_clear_frame_cache))
        theme.set_role(btn_clear, "primary")
        btn_clear.clicked.connect(self._clear_frame_cache_from_help)

        row_layout.addWidget(btn_clear)
        row_layout.addStretch()
        layout.addWidget(row)

    def _clear_frame_cache_from_help(self):
        """Ejecuta la accion de limpieza configurada por la ventana principal."""
        if not callable(self._on_clear_frame_cache):
            return
        try:
            self._on_clear_frame_cache()
        except Exception as exc:
            # El callback principal ya maneja los errores esperados. Este guard evita
            # que un fallo inesperado cierre la ayuda o deje el boton sin respuesta.
            from ui.dialog import show_error
            show_error("Frame Cache", f"Could not open frame cache action:\n{exc}", parent=self._window)

    def _content_about(self, layout: QVBoxLayout):
        # Espacio superior
        top_spacer = QWidget()
        top_spacer.setFixedHeight(theme.SP3)
        top_spacer.setStyleSheet("background: transparent;")
        layout.addWidget(top_spacer)

        # Nombre grande
        lbl_name = QLabel("Spryta")
        lbl_name.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        lbl_name.setStyleSheet(f"""
            color: {theme.ACCENT};
            background: transparent;
            padding-left: {theme.SP2}px;
        """)
        layout.addWidget(lbl_name)

        # Subtitulo
        lbl_sub_text = (
            "Complemento de sprites de escritorio para Windows"
            if self._language == "es"
            else "Desktop sprite plugin for Windows"
        )
        lbl_sub = QLabel(lbl_sub_text)
        lbl_sub.setFont(theme.FONT_SMALL)
        lbl_sub.setStyleSheet(f"""
            color: {theme.TEXT_MUTED};
            background: transparent;
            padding-left: {theme.SP2}px;
        """)
        layout.addWidget(lbl_sub)

        # Separador
        sep_widget = QWidget()
        sep_widget.setFixedHeight(theme.SP2)
        sep_widget.setStyleSheet("background: transparent;")
        layout.addWidget(sep_widget)
        layout.addWidget(_make_hsep())
        gap = QWidget()
        gap.setFixedHeight(theme.SP2)
        gap.setStyleSheet("background: transparent;")
        layout.addWidget(gap)

        # Fila version
        ver_row = QWidget()
        ver_row.setStyleSheet("background: transparent;")
        ver_layout = QHBoxLayout(ver_row)
        ver_layout.setContentsMargins(theme.SP2, 0, theme.SP2, 0)
        ver_layout.setSpacing(theme.SP1)

        lbl_ver_label = QLabel("Version")
        lbl_ver_label.setFont(theme.FONT_SMALL)
        lbl_ver_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")

        lbl_ver_value = QLabel("1.0.0")
        lbl_ver_value.setFont(theme.font("small", bold=True))
        lbl_ver_value.setStyleSheet(f"color: {theme.TEXT_BRIGHT}; background: transparent;")

        ver_layout.addWidget(lbl_ver_label)
        ver_layout.addWidget(lbl_ver_value)
        ver_layout.addStretch()
        layout.addWidget(ver_row)

        if self._language == "es":
            self._section_title(layout, "Gracias por usar Spryta!")
            self._line(layout,
                "Esperamos que Spryta aporte un poco de alegria y personalidad a tu escritorio."
            )
            self._line(layout, "")
            self._line(layout, "Gracias por tu apoyo!")
            return
            
        # Mensaje de agradecimiento
        self._section_title(layout, "Thank you for using Spryta!")
        self._line(layout,
            "We hope Spryta brings a little joy and personality to your desktop."
        )
        self._line(layout, "")
        self._line(layout, "Thank you for your support!")

    # =========================================================
    # CENTRADO DE VENTANA
    # =========================================================

    def _center_window(self):
        """Centra la ventana de ayuda sobre el padre o la pantalla."""
        if self._window is None:
            return
        self._window.adjustSize()
        if self.parent_widget and self.parent_widget.isVisible():
            center = self.parent_widget.frameGeometry().center()
        else:
            center = QApplication.primaryScreen().availableGeometry().center()
        geo = self._window.frameGeometry()
        geo.moveCenter(center)
        self._window.move(geo.topLeft())


# ============================================================
# SECCION 3: HELPERS INTERNOS DE WIDGET
# Funciones pequenas que crean separadores visuales.
# ============================================================

def _make_hsep() -> QFrame:
    """
    Crea un separador horizontal de 1px.
    Equivalente a: tk.Frame(parent, bg=theme.BORDER_MID, height=1)
    """
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {theme.BORDER_MID}; border: none;")
    return sep


def _make_vsep() -> QFrame:
    """
    Crea un separador vertical de 1px.
    Equivalente a: tk.Frame(parent, bg=theme.BORDER_MID, width=1)
    """
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFixedWidth(1)
    sep.setStyleSheet(f"background-color: {theme.BORDER_MID}; border: none;")
    return sep
