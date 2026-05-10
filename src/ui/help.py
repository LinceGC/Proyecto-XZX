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
from PySide6.QtGui     import QFont, QIcon, QColor
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

    def __init__(self, parent=None):
        """
        Parametros:
            parent -- QWidget padre (la ventana principal de settings).
                      Se usa para centrar la ventana de ayuda sobre ella.
                      Puede ser None.
        """
        self.parent_widget = parent
        self._window       = None   # QDialog, se crea al llamar show()

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
        builder_fn = self._sections[name]
        builder_fn(content_layout)

        # Espaciado final al fondo
        content_layout.addStretch()

        # Reemplazar el widget interior del QScrollArea
        self._content_area.setWidget(content_widget)
        # Volver al inicio del scroll
        self._content_area.verticalScrollBar().setValue(0)

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
        self._section_title(layout, "Global Keyboard Shortcuts")
        self._shortcut_row(layout, "Ctrl + Alt + S", "Show / Hide all running sprites")
        self._line(layout, "")
        self._line(layout,
            "These shortcuts work at any time, even when "
            "the Settings window is minimized or in the system tray."
        )

        self._section_title(layout, "Sprite Mouse Controls")
        self._shortcut_row(layout, "Left click",        "Pause / Resume movement")
        self._shortcut_row(layout, "Left click + drag", "Move the sprite freely")
        self._shortcut_row(layout, "Tray icon > Close", "Close the sprite")

    def _content_solo(self, layout: QVBoxLayout):
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
        self._line(layout, "Frame Size       Width and height in pixels of the solo window.")
        self._line(layout, "Dynamic Mode     How the solo moves on screen:")
        self._line(layout, "Stitched — stays in a fixed position.", indent=True)
        self._line(layout, "Walk — walks from one side to the other.", indent=True)
        self._line(layout, "Wandering — bounces freely around the screen.", indent=True)
        self._line(layout, "Movement Speed   How fast the solo moves (30 / 60 / 120 fps).")
        self._line(layout, "Delay Mode       Controls animation speed:")
        self._line(layout, "Fixed — constant delay in milliseconds.", indent=True)
        self._line(layout, "CPU — delay adjusts automatically based on CPU usage.", indent=True)
        self._line(layout, "Presentation — long delay per frame, in seconds.", indent=True)

    def _content_reel(self, layout: QVBoxLayout):
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
        lbl_sub = QLabel("Desktop sprite companion for Windows")
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

        # Mensaje de agradecimiento
        self._section_title(layout, "Thank you for using Spryta!")
        self._line(layout,
            "We hope Spryta brings a little joy and personality to your desktop."
        )
        self._line(layout, "")
        self._line(layout,
            "If you enjoy using it, consider sharing it with friends "
            "or contributing new sprite packs to the community."
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
