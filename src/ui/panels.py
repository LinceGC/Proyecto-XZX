# -*- coding: utf-8 -*-
"""
src/ui/panels.py  —  Spryta Tool Panels (PySide6)

Paneles flotantes de herramientas de Spryta.

    LeftToolPanel      -- panel con Create Frame y Ambient Audio
    RightProcessPanel  -- panel de procesos corriendo

API PUBLICA — identica al panels.py anterior de tkinter:

    LeftToolPanel(master, audio_manager, frame_extractor,
                  on_close_callback=None, on_solo_created_callback=None)
        .show(tool_type="create_frame", main_window=None)
        .switch_tool(tool_type)
        .close()
        .is_visible()  -> bool

    RightProcessPanel(master, process_manager,
                      on_close_callback=None, on_process_closed_callback=None)
        .show(main_window=None)
        .refresh()
        .close_selected()
        .close_all()
        .close()
        .is_visible()  -> bool

Uso (sin cambiar nada en setting.pyw):
    from ui.panels import LeftToolPanel, RightProcessPanel
"""

import os
import threading
import time

from PySide6.QtCore    import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui     import QIcon, QFont
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel,
    QLineEdit, QSlider, QProgressBar,
    QListWidget, QListWidgetItem,
    QFileDialog, QSizePolicy,
    QAbstractItemView,
    QApplication,
    QGraphicsOpacityEffect,
)

from ui import theme
from ui.widgets import AudioListWidget, LassoAudioWidget
from ui.dialog  import show_info, show_warning, show_error, ask_yes_no, ask_string


# ============================================================
# HELPER INTERNO: ventana flotante base
# Ambos paneles son QDialog no modales con el mismo estilo.
# ============================================================

def _make_panel_window(title: str, parent: QWidget,
                       width: int, height: int) -> QDialog:
    """
    Crea un QDialog flotante con el estilo Spryta.
    No bloquea la ventana principal (modal=False).

    Parametros:
        title  -- texto de la barra de titulo
        parent -- QWidget padre para centrado e icono
        width  -- ancho en pixeles
        height -- alto en pixeles
    """
    win = QDialog(parent)
    win.setWindowTitle(title)
    win.setModal(False)
    win.resize(width, height)
    win.setMinimumWidth(width)

    icon_path = os.path.join("assets", "icons", "icon.ico")
    if os.path.exists(icon_path):
        win.setWindowIcon(QIcon(icon_path))

    return win


def _make_separator() -> QFrame:
    """Crea un separador horizontal de 1px."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(
        f"background-color: {theme.BORDER_MID}; border: none;"
    )
    return sep


# ============================================================
# PANEL IZQUIERDO: Create Frame + Ambient Audio
# ============================================================

class LeftToolPanel:
    """
    Panel flotante izquierdo con dos herramientas:
      - Create Frame  : extrae frames de un video o GIF
      - Ambient Audio : reproduce musica de fondo

    Parametros del constructor:
        master                     -- QWidget principal de Settings
        audio_manager              -- instancia de AmbientAudioManager
        frame_extractor            -- instancia de FrameExtractor
        on_close_callback          -- funcion llamada al cerrar el panel
        on_solo_created_callback   -- funcion llamada al crear un solo nuevo
    """

    def __init__(self, master, audio_manager, frame_extractor,
                 on_close_callback=None, on_solo_created_callback=None,
                 lasso_manager=None):

        self.master                    = master
        self.audio_manager             = audio_manager
        self.frame_extractor           = frame_extractor
        self.on_close_callback         = on_close_callback
        self.on_solo_created_callback  = on_solo_created_callback
        self.lasso_manager              = lasso_manager

        self.window       = None
        self.current_tool = None

        # Ventana de editor de vinculos (persiste entre cambios de herramienta)
        self._lasso_window         = None
        self._lasso_playlist_combo = None
        self._sync_timer          = None   # QTimer que sincroniza posiciones de sprites vinculados
        # Ultima seleccion del combo Lasso — persiste aunque el panel se cierre y reabra
        self._last_lasso_selection = None

        # Referencias a widgets de Ambient Audio
        self.audio_listbox_widget = None   # AudioListWidget
        self.loop_btn             = None   # QPushButton
        self.playlist_btn         = None   # QPushButton
        self._volume_slider       = None   # QSlider
        self._btn_play_pause      = None   # QPushButton - reproducir / pausar playlist
        self._eff_play_pause      = None   # QGraphicsOpacityEffect para btn play/pause
        self._anim_play_pause     = None   # QPropertyAnimation para btn play/pause
        self._btn_anterior        = None   # QPushButton - navegar playlist anterior
        self._btn_siguiente       = None   # QPushButton - navegar playlist siguiente
        self._eff_anterior        = None   # QGraphicsOpacityEffect para btn anterior
        self._eff_siguiente       = None   # QGraphicsOpacityEffect para btn siguiente
        self._anim_anterior       = None   # QPropertyAnimation para btn anterior
        self._anim_siguiente      = None   # QPropertyAnimation para btn siguiente
        self._last_playlist_idx   = -1     # indice de la ultima cancion resaltada

        # Referencia al widget de progreso de Create Frame
        self._progress_bar = None   # QProgressBar

        # Variable de FPS (en Qt usamos QLineEdit en lugar de tk.IntVar)
        self._fps_entry = None    # QLineEdit

        # Contenedor intercambiable de herramientas
        self._tool_container        = None   # QWidget
        self._tool_container_layout = None   # QVBoxLayout

        # Guard para bloquear cambios rapidos que causan crash
        self._switching = False

        # Lista de botones FPS activos (para resaltado)
        self._fps_btns = []

    # ----------------------------------------------------------
    # Mostrar / ocultar
    # ----------------------------------------------------------

    def show(self, tool_type: str = "create_frame", main_window=None):
        """
        Muestra el panel con la herramienta indicada.
        Si ya estaba abierto, lo trae al frente y cambia la herramienta.

        Parametros:
            tool_type   -- "create_frame" o "ambient_audio"
            main_window -- QWidget de referencia para posicionar el panel
        """
        # Si la ventana ya existe y esta visible, traerla al frente
        if self.window is not None and self.window.isVisible():
            self.window.raise_()
            self.window.activateWindow()
            self.switch_tool(tool_type)
            return

        # Calcular posicion: a la izquierda de la ventana principal
        panel_w = theme.PANEL_SIDE_WIDTH
        panel_h = theme.MAIN_WINDOW_HEIGHT

        self.window = _make_panel_window("Tools", self.master, panel_w, panel_h)
        self.window.closeEvent = self._on_window_close

        if main_window is not None:
            geo    = main_window.frameGeometry()
            x      = geo.x() - panel_w - 5
            y      = geo.y()
            self.window.move(x, y)

        # ── Layout raiz ───────────────────────────────────────
        root = QVBoxLayout(self.window)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Contenedor intercambiable ─────────────────────────
        self._tool_container = QWidget()
        self._tool_container.setStyleSheet(
            f"background-color: {theme.BG_BASE};"
        )
        self._tool_container_layout = QVBoxLayout(self._tool_container)
        self._tool_container_layout.setContentsMargins(
            theme.SP2, theme.SP2, theme.SP2, theme.SP2
        )
        self._tool_container_layout.setSpacing(theme.SP1)
        root.addWidget(self._tool_container, 1)

        # ── Mostrar herramienta inicial ───────────────────────
        try:
            self.switch_tool(tool_type)
        except Exception as _e:
            import traceback
            traceback.print_exc()
        self.window.show()

    def switch_tool(self, tool_type: str):
        """
        Cambia entre Create Frame y Ambient Audio.
        Limpia el contenedor y reconstruye la UI de la herramienta.

        Parametros:
            tool_type -- "create_frame" o "ambient_audio"
        """
        # Guard: bloquea llamadas reentrantes durante la transicion
        if self._switching:
            return
        if self._tool_container_layout is None:
            return

        self._switching = True
        try:
            # Limpiar recursivamente: maneja widgets Y sub-layouts anidados
            self._clear_layout(self._tool_container_layout)

            # Resetear todas las referencias de widgets de las herramientas
            self.audio_listbox_widget = None
            self.loop_btn             = None
            self.playlist_btn         = None
            self._volume_slider       = None
            self._progress_bar        = None
            self._fps_entry           = None
            self._fps_btns            = []
            self._btn_play_pause      = None
            self._eff_play_pause      = None
            self._anim_play_pause     = None
            self._btn_anterior        = None
            self._btn_siguiente       = None
            self._eff_anterior        = None
            self._eff_siguiente       = None
            self._anim_anterior       = None
            self._anim_siguiente      = None
            self._lasso_playlist_combo = None
            # Detener el timer de sincronizacion al cambiar de herramienta
            if self._sync_timer is not None:
                self._sync_timer.stop()
                self._sync_timer = None

            # Actualizar estado visual de los botones de pestana
            if tool_type == "create_frame":
                self._load_create_frame_ui()
            else:
                self._load_ambient_audio_ui()

            self.current_tool = tool_type
        finally:
            self._switching = False

    @staticmethod
    def _clear_layout(layout):
        """
        Elimina de forma recursiva todos los widgets y sub-layouts
        de un QLayout. Necesario porque takeAt() solo actua en el
        primer nivel — los QHBoxLayout/QVBoxLayout anidados y sus
        hijos quedarian vivos sin esto.
        """
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                LeftToolPanel._clear_layout(item.layout())
            # QSpacerItem: takeAt() ya lo elimino del layout, no necesita tratamiento adicional.

    # ----------------------------------------------------------
    # Herramienta: Create Frame
    # ----------------------------------------------------------

    def _load_create_frame_ui(self):
        """Construye la interfaz de extraccion de frames."""
        lay = self._tool_container_layout

        # Titulo
        lbl_title = QLabel("Extract Video Frames")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color: {theme.ACCENT};")
        lay.addWidget(lbl_title)

        lay.addWidget(_make_separator())
        lay.addSpacing(theme.SP1)

        # Descripcion
        lbl_desc = QLabel("Select a video or GIF file to extract frames.")
        lbl_desc.setFont(theme.FONT_SMALL)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {theme.TEXT_NORMAL};")
        lay.addWidget(lbl_desc)

        lay.addSpacing(theme.SP2)

        # ── Selector de FPS ───────────────────────────────────
        fps_container = QWidget()
        fps_container.setStyleSheet("background: transparent;")
        fps_lay = QVBoxLayout(fps_container)
        fps_lay.setContentsMargins(0, 0, 0, 0)
        fps_lay.setSpacing(theme.SP2)

        # Fila superior: label + entrada de valor personalizado
        row_top = QHBoxLayout()
        row_top.setSpacing(theme.SP1)

        lbl_fps = QLabel("Frames per second")
        lbl_fps.setFont(theme.font("small", bold=True))
        lbl_fps.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        row_top.addWidget(lbl_fps)

        row_top.addStretch()

        self._fps_entry = QLineEdit("0")
        self._fps_entry.setFont(theme.FONT_MONO)
        self._fps_entry.setFixedSize(64, 32)
        self._fps_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fps_entry.setToolTip("Custom value (0 = all frames)")
        row_top.addWidget(self._fps_entry)

        fps_lay.addLayout(row_top)

        # Botones de seleccion rapida — ancho completo, una fila
        _FPS_OPTIONS = [
            (0,  "All",  "All frames"),
            (15, "15",   "15 fps"),
            (24, "24",   "24 fps"),
            (30, "30",   "30 fps"),
            (60, "60",   "60 fps"),
        ]

        _BTN_H = 44

        _btn_base = f"""
            QPushButton {{
                background-color: {theme.BG_RAISED};
                color: {theme.TEXT_NORMAL};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS_SMALL}px;
                font-size: 11pt;
                font-weight: bold;
                min-height: {_BTN_H}px;
                max-height: {_BTN_H}px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {theme.BG_HOVER};
                border-color: {theme.ACCENT};
                color: {theme.TEXT_BRIGHT};
            }}
            QPushButton:pressed {{
                background-color: {theme.ACCENT_DIM};
                border-color: {theme.ACCENT};
                color: {theme.ACCENT};
            }}
        """

        fps_grid = QHBoxLayout()
        fps_grid.setSpacing(6)

        self._fps_btns = []
        for fps_val, label, tip in _FPS_OPTIONS:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_btn_base)
            btn.clicked.connect(
                lambda checked=False, v=fps_val, b=btn: self._set_fps(v, b)
            )
            fps_grid.addWidget(btn)
            self._fps_btns.append((fps_val, btn))

        fps_lay.addLayout(fps_grid)

        lbl_hint = QLabel("0 = extract all frames from the video")
        lbl_hint.setFont(theme.FONT_TINY)
        lbl_hint.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        fps_lay.addWidget(lbl_hint)

        lay.addWidget(fps_container)

        lay.addSpacing(theme.SP2)

        # ── Boton principal ───────────────────────────────────
        btn_select = QPushButton("Select Video / GIF")
        btn_select.setFont(theme.FONT_NORMAL)
        btn_select.setFixedHeight(40)
        btn_select.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_select.setStyleSheet(theme.BTN_STYLE)
        btn_select.clicked.connect(self._select_video)
        lay.addWidget(btn_select)

        # ── Barra de progreso (oculta hasta que inicie extraccion) ──
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # modo indeterminado
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.hide()
        lay.addWidget(self._progress_bar)

        lay.addStretch()

    def _set_fps(self, value: int, active_btn: QPushButton):
        """
        Pone el valor en el entry y resalta el boton seleccionado.
        min-height y max-height identicos a los del stylesheet base
        garantizan que el tamano no cambie al seleccionar.
        """
        if self._fps_entry is None:
            return
        self._fps_entry.setText(str(value))

        _BTN_H = 44

        _btn_normal = f"""
            QPushButton {{
                background-color: {theme.BG_RAISED};
                color: {theme.TEXT_NORMAL};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS_SMALL}px;
                font-size: 11pt;
                font-weight: bold;
                min-height: {_BTN_H}px;
                max-height: {_BTN_H}px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {theme.BG_HOVER};
                border-color: {theme.ACCENT};
                color: {theme.TEXT_BRIGHT};
            }}
        """
        _btn_active = f"""
            QPushButton {{
                background-color: {theme.ACCENT_DIM};
                color: {theme.ACCENT};
                border: 1px solid {theme.ACCENT};
                border-radius: {theme.RADIUS_SMALL}px;
                font-size: 11pt;
                font-weight: bold;
                min-height: {_BTN_H}px;
                max-height: {_BTN_H}px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {theme.ACCENT_DIM};
                border-color: {theme.ACCENT};
                color: {theme.ACCENT};
            }}
        """
        for _, btn in self._fps_btns:
            try:
                btn.setStyleSheet(_btn_active if btn is active_btn else _btn_normal)
            except RuntimeError:
                pass

    def _select_video(self):
        """Abre el dialogo para seleccionar el archivo de video o GIF."""
        video_path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Select video or GIF",
            "",
            "Videos y GIFs (*.mp4 *.avi *.mov *.mkv *.flv *.wmv "
            "*.webm *.mpeg *.mpg *.gif);;"
            "Video files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.webm *.mpeg *.mpg);;"
            "Animated GIFs (*.gif);;"
            "All files (*.*)"
        )

        if not video_path:
            return

        default_name = os.path.splitext(os.path.basename(video_path))[0]

        folder_name = ask_string(
            "Folder name",
            "Enter folder name for frames:\n(will be saved in 'sprites' folder)",
            parent=self.window,
            initial=default_name,
        )

        if not folder_name:
            return

        # Mostrar barra de progreso e iniciar hilo
        if self._progress_bar:
            self._progress_bar.show()

        threading.Thread(
            target=self._extract_frames_thread,
            args=(video_path, folder_name),
            daemon=True,
        ).start()

    def _extract_frames_thread(self, video_path: str, folder_name: str):
        """
        Hilo que realiza la extraccion de frames.
        Al terminar llama al metodo de la UI en el hilo principal via QTimer.
        """
        try:
            # Leer FPS del entry (puede estar vacio o tener texto invalido)
            try:
                target_fps = int(self._fps_entry.text())
            except (ValueError, AttributeError):
                target_fps = 0

            count, output_path = self.frame_extractor.extract_frames(
                video_path, folder_name, target_fps
            )
            # Volver al hilo principal con QTimer de tiempo 0
            QTimer.singleShot(
                0,
                lambda: self._on_extraction_complete(count, output_path)
            )
        except Exception as e:
            err_msg = str(e)
            QTimer.singleShot(
                0,
                lambda: self._on_extraction_error(err_msg)
            )

    def _on_extraction_complete(self, count: int, output_path: str):
        """Llamado en el hilo principal cuando la extraccion termino bien."""
        if self._progress_bar:
            self._progress_bar.hide()

        show_info(
            "Success",
            f"{count} frames extracted in:\n{output_path}",
            parent=self.window,
        )
        if self.on_solo_created_callback:
            self.on_solo_created_callback()

    def _on_extraction_error(self, error: str):
        """Llamado en el hilo principal cuando la extraccion fallo."""
        if self._progress_bar:
            self._progress_bar.hide()

        show_error(
            "Error",
            f"Could not process file:\n{error}",
            parent=self.window,
        )

    # ----------------------------------------------------------
    # Herramienta: Ambient Audio
    # ----------------------------------------------------------

    def _load_ambient_audio_ui(self):
        """Construye la interfaz del reproductor de audio ambiental."""
        try:
            self._build_ambient_audio_ui()
        except Exception as _e:
            import traceback
            traceback.print_exc()
            lbl_err = QLabel(f"Error building UI:\n{_e}")
            lbl_err.setWordWrap(True)
            lbl_err.setStyleSheet(f"color: {theme.COLOR_DANGER};")
            self._tool_container_layout.addWidget(lbl_err)

    def _build_ambient_audio_ui(self):
        lay = self._tool_container_layout

        # Titulo
        lbl_title = QLabel("Ambient Audio")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color: {theme.ACCENT};")
        lay.addWidget(lbl_title)

        lay.addWidget(_make_separator())
        lay.addSpacing(theme.SP1)

        # Subtitulo lista
        lbl_avail = QLabel("Available Audio:")
        lbl_avail.setFont(theme.FONT_SMALL)
        lbl_avail.setStyleSheet(f"color: {theme.TEXT_NORMAL};")
        lay.addWidget(lbl_avail)

        # Lista de archivos de audio
        self.audio_listbox_widget = AudioListWidget(
            self._tool_container,
            self.audio_manager,
            on_select_callback=self._update_audio_buttons,
        )
        lay.addWidget(self.audio_listbox_widget)

        self.audio_listbox_widget.refresh()

        lay.addSpacing(theme.SP2)

        # ── Botones de control: grid 3x2 ─────────────────────────
        # Fila 0: Anterior / Siguiente  (ocultos hasta activar playlist)
        # Fila 1: Upload Audio / Play Loop (Stop Loop)
        # Fila 2: Play List (Stop List) / Stop
        from PySide6.QtWidgets import QGridLayout

        btn_grid = QGridLayout()
        btn_grid.setSpacing(theme.SP1)

        _BTN_H = 40

        # ── Fila 0: boton Reproducir / Pausar (oculto hasta activar playlist) ──
        self._btn_play_pause = QPushButton("▶  Reproduce")
        self._btn_play_pause.setFont(theme.FONT_SMALL)
        self._btn_play_pause.setFixedHeight(_BTN_H)
        self._btn_play_pause.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_play_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play_pause.setStyleSheet("QPushButton { background: transparent; color: transparent; border: 1px solid transparent; }")
        self._btn_play_pause.clicked.connect(self._panel_play_pause)
        self._btn_play_pause.setEnabled(False)
        self._eff_play_pause = QGraphicsOpacityEffect(self._btn_play_pause)
        self._eff_play_pause.setOpacity(0.0)
        self._btn_play_pause.setGraphicsEffect(self._eff_play_pause)

        # ── Fila 1: botones de navegacion de playlist (ocultos) ──
        self._btn_anterior = QPushButton("before")
        self._btn_anterior.setFont(theme.FONT_SMALL)
        self._btn_anterior.setFixedHeight(_BTN_H)
        self._btn_anterior.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_anterior.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_anterior.setStyleSheet(theme.BTN_STYLE)
        self._btn_anterior.clicked.connect(self._playlist_prev)
        self._btn_anterior.setEnabled(False)
        self._btn_anterior.setStyleSheet("QPushButton { background: transparent; color: transparent; border: 1px solid transparent; }")
        self._eff_anterior = QGraphicsOpacityEffect(self._btn_anterior)
        self._eff_anterior.setOpacity(0.0)
        self._btn_anterior.setGraphicsEffect(self._eff_anterior)

        self._btn_siguiente = QPushButton("next")
        self._btn_siguiente.setFont(theme.FONT_SMALL)
        self._btn_siguiente.setFixedHeight(_BTN_H)
        self._btn_siguiente.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_siguiente.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_siguiente.setStyleSheet("QPushButton { background: transparent; color: transparent; border: 1px solid transparent; }")
        self._btn_siguiente.clicked.connect(self._playlist_next)
        self._btn_siguiente.setEnabled(False)
        self._eff_siguiente = QGraphicsOpacityEffect(self._btn_siguiente)
        self._eff_siguiente.setOpacity(0.0)
        self._btn_siguiente.setGraphicsEffect(self._eff_siguiente)

        # ── Fila 1: Upload Audio + Play Loop ─────────────────────
        btn_upload = QPushButton("Upload Audio")
        btn_upload.setFont(theme.FONT_SMALL)
        btn_upload.setFixedHeight(_BTN_H)
        btn_upload.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_upload.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_upload.setStyleSheet(theme.BTN_STYLE)
        btn_upload.clicked.connect(self._upload_audio)

        self.loop_btn = QPushButton("")
        self.loop_btn.setFont(theme.FONT_SMALL)
        self.loop_btn.setFixedHeight(_BTN_H)
        self.loop_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.loop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.loop_btn.clicked.connect(self._toggle_loop)

        # ── Fila 2: Play List + Stop ──────────────────────────────
        self.playlist_btn = QPushButton("")
        self.playlist_btn.setFont(theme.FONT_SMALL)
        self.playlist_btn.setFixedHeight(_BTN_H)
        self.playlist_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.playlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_btn.clicked.connect(self._toggle_playlist)

        btn_link = QPushButton("Lasso Sprites")
        btn_link.setFont(theme.FONT_SMALL)
        btn_link.setFixedHeight(_BTN_H)
        btn_link.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_link.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_link.setStyleSheet(theme.BTN_STYLE)
        btn_link.clicked.connect(self._open_lasso_window)

        btn_grid.addWidget(self._btn_anterior,   0, 0)
        btn_grid.addWidget(self._btn_siguiente,  0, 1)
        btn_grid.addWidget(self._btn_play_pause, 1, 0, 1, 2)
        btn_grid.addWidget(self.playlist_btn,    2, 0)
        btn_grid.addWidget(self.loop_btn,        2, 1)
        btn_grid.addWidget(btn_upload,           3, 0)
        btn_grid.addWidget(btn_link,             3, 1)

        # Columnas con el mismo peso → ambas mitades iguales
        btn_grid.setColumnStretch(0, 1)
        btn_grid.setColumnStretch(1, 1)

        lay.addLayout(btn_grid)

        lay.addSpacing(theme.SP2)

        # ── Control de volumen ────────────────────────────────
        lbl_vol = QLabel("Volume:")
        lbl_vol.setFont(theme.FONT_SMALL)
        lbl_vol.setStyleSheet(f"color: {theme.TEXT_NORMAL}; background: transparent;")
        lay.addWidget(lbl_vol)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(80)
        self._volume_slider.setFixedHeight(20)
        self._volume_slider.valueChanged.connect(
            lambda v: self.audio_manager.set_volume(v / 100.0)
        )
        lay.addWidget(self._volume_slider)

        lay.addSpacing(theme.SP1)

        # ── Selector de playlist de vinculos ─────────────────
        if self.lasso_manager is not None:
            from PySide6.QtWidgets import QComboBox
            row_link = QHBoxLayout()
            row_link.setSpacing(theme.SP1)

            lbl_link = QLabel("Lasso:")
            lbl_link.setFont(theme.FONT_SMALL)
            lbl_link.setStyleSheet(
                f"color: {theme.TEXT_NORMAL}; background: transparent;"
            )
            row_link.addWidget(lbl_link)

            self._lasso_playlist_combo = QComboBox()
            self._lasso_playlist_combo.setFont(theme.FONT_SMALL)
            self._lasso_playlist_combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self._lasso_playlist_combo.currentIndexChanged.connect(
                self._on_lasso_combo_changed
            )
            row_link.addWidget(self._lasso_playlist_combo, 1)
            lay.addLayout(row_link)
            self._refresh_lasso_combo()

        lay.addStretch()

        # Actualizar estado de botones al cargar
        self._update_audio_buttons()

        # Arrancar timer de sincronizacion de posiciones (cada 2 segundos)
        # Lee lasso_positions.ini y actualiza lassos.json cuando el usuario
        # arrastra un sprite vinculado en pantalla.
        if self.lasso_manager is not None:
            self._sync_timer = QTimer(self.window)
            self._sync_timer.setInterval(2000)
            self._sync_timer.timeout.connect(self._sync_lasso_positions)
            self._sync_timer.start()

    def _upload_audio(self):
        """Copia un archivo de audio a la biblioteca."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Select audio file",
            "",
            "Audio files (*.mp3 *.wav *.ogg *.flac *.aac)"
        )
        if not file_path:
            return

        try:
            filename = self.audio_manager.add_audio_file(file_path)
            self.audio_listbox_widget.refresh()
            show_info("Success", f"'{filename}' added", parent=self.window)
        except FileExistsError as e:
            if ask_yes_no("File exists", f"{str(e)}\n\nReplace?", parent=self.window):
                import shutil
                shutil.copy2(
                    file_path,
                    os.path.join("Audio", os.path.basename(file_path))
                )
                self.audio_listbox_widget.refresh()
        except Exception as e:
            show_error("Error", str(e), parent=self.window)

    def _toggle_loop(self):
        """Inicia o detiene la reproduccion en loop."""
        if self.audio_manager.is_playing and not self.audio_manager.is_playlist_mode:
            self._stop_audio()
        else:
            filename = self.audio_listbox_widget.get_selected()
            if not filename:
                show_warning("Warning", "Select an audio file", parent=self.window)
                return
            try:
                self._sync_lasso_before_track_start()
                self.audio_manager.play_loop(filename)
                self.audio_listbox_widget.highlight_current()
                self._update_audio_buttons()
            except Exception as e:
                show_error("Error", str(e), parent=self.window)

    def _toggle_playlist(self):
        """Inicia o detiene la reproduccion de la lista completa."""
        if self.audio_manager.is_playing and self.audio_manager.is_playlist_mode:
            self._stop_audio()
        else:
            self._sync_lasso_before_track_start()
            pl = self._get_active_lasso_playlist()
            if pl and self.lasso_manager:
                # Modo Lasso activo: reproducir solo las canciones que tienen
                # al menos un sprite enlazado, igual que lo que muestra la lista.
                all_songs = self.lasso_manager.get_songs(pl)
                bindings  = self.lasso_manager.get_all_bindings(pl)
                songs = [s for s in all_songs if bindings.get(s, [])]
                if not songs:
                    return
                # Obtener indice de la cancion seleccionada dentro de la lista filtrada
                selected  = self.audio_listbox_widget.get_selected()
                start_idx = songs.index(selected) if selected in songs else 0
                # Restringir audio_manager a solo las canciones con sprites enlazados
                self.audio_manager.audio_files = list(songs)
                self.audio_manager.play_playlist(start_idx)
            else:
                # Modo normal: usar toda la biblioteca
                # Restaurar lista completa por si fue restringida antes
                self.audio_manager.get_audio_files()
                # Obtener indice seleccionado usando getattr para compatibilidad
                # con AudioListWidget (._list) y LassoAudioWidget (._selected_idx)
                if hasattr(self.audio_listbox_widget, '_list'):
                    row = self.audio_listbox_widget._list.currentRow()
                else:
                    row = getattr(self.audio_listbox_widget, '_selected_idx', 0)
                start_idx = row if row >= 0 else 0
                self.audio_manager.play_playlist(start_idx)

            self.audio_listbox_widget.highlight_current()
            self._update_audio_buttons()
            self._check_playlist()

    def _sync_lasso_before_track_start(self):
        """
        Configura callback para que Lasso dispare/cargue sprites
        ANTES de iniciar cada track de audio.
        """
        pl = self._get_active_lasso_playlist()
        if self.lasso_manager and pl:
            def _before_track_start(filename):
                bound_sprites = self.lasso_manager.get_bindings(pl, filename)
                if bound_sprites and hasattr(self.master, "_on_lasso_sprites_launched"):
                    self.master._on_lasso_sprites_launched(len(bound_sprites), pl, filename)

                done = threading.Event()
                error_box = {"err": None}

                def _worker():
                    try:
                        self.lasso_manager.on_song_play(pl, filename, notify_ui=False)
                    except Exception as e:
                        error_box["err"] = e
                    finally:
                        done.set()

                threading.Thread(target=_worker, daemon=True).start()

                # Mantener la UI viva para que el toast se pinte completo
                # mientras esperamos sprites listos.
                while not done.is_set():
                    QApplication.processEvents()
                    time.sleep(0.01)

                if error_box["err"] is not None:
                    raise error_box["err"]
            self.audio_manager.before_track_start = _before_track_start
        else:
            self.audio_manager.before_track_start = None

    def _check_playlist(self):
        """
        Verifica si la cancion actual termino y avanza a la siguiente.
        Solo actualiza el resaltado cuando la cancion cambia, para no
        interferir con la navegacion manual del usuario en la lista.
        """
        if self.audio_manager.check_and_advance_playlist():
            current  = self.audio_manager.get_current_filename()
            files    = self.audio_manager.audio_files
            idx      = files.index(current) if current in files else -1
            if idx != self._last_playlist_idx:
                self._last_playlist_idx = idx
                self.audio_listbox_widget.highlight_current(scroll=False)
            QTimer.singleShot(100, self._check_playlist)
        else:
            self._last_playlist_idx = -1
            self._update_audio_buttons()
    
    def _fade_nav_buttons(self, show: bool, show_play_pause_only: bool = False):
        """
        Anima la aparicion o desaparicion de los botones de navegacion y play/pause.

        show                 -- True: mostrar Anterior, Siguiente y Play/Pause (playlist activa)
        show_play_pause_only -- True: mostrar solo Play/Pause (loop activo)
        """
        mostrar_play_pause = show or show_play_pause_only
        pares = [
            (self._btn_play_pause, self._eff_play_pause, "_anim_play_pause", mostrar_play_pause),
            (self._btn_anterior,   self._eff_anterior,   "_anim_anterior",   show),
            (self._btn_siguiente,  self._eff_siguiente,  "_anim_siguiente",  show),
        ]

        for btn, eff, anim_attr, visible in pares:
            if btn is None or eff is None:
                continue

            # Detener animacion previa si aun corre
            anim_prev = getattr(self, anim_attr)
            if anim_prev is not None:
                anim_prev.stop()

            if visible:
                # Aplicar estilo visible antes de que empiece el fade in
                btn.setEnabled(True)
                btn.setStyleSheet(theme.BTN_STYLE)

            anim = QPropertyAnimation(eff, b"opacity")
            anim.setDuration(220)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anim.setStartValue(eff.opacity())
            anim.setEndValue(1.0 if visible else 0.0)

            if not visible:
                # Al terminar el fade out: desactivar el boton y volverlo transparente
                def _on_fade_out_done(b=btn):
                    b.setEnabled(False)
                    b.setStyleSheet(
                        "QPushButton { background: transparent;"
                        " color: transparent; border: 1px solid transparent; }"
                    )
                anim.finished.connect(_on_fade_out_done)

            setattr(self, anim_attr, anim)
            anim.start()
    
    def _panel_play_pause(self):
        """
        Reproducir o pausar desde el panel.
        Logica identica al boton Play/Pause del Tray.
        """
        am = self.audio_manager
        is_paused  = getattr(am, 'is_paused',  False)

        try:
            import pygame
            mixer_busy = pygame.mixer.get_init() and pygame.mixer.music.get_busy()
        except Exception:
            mixer_busy = False

        if mixer_busy and not is_paused:
            am.pause()
            if self.lasso_manager:
                self.lasso_manager.on_song_pause()
        else:
            am.resume()
            if self.lasso_manager:
                self.lasso_manager.on_song_resume()

        self._update_audio_buttons()
    
    def _playlist_prev(self):
        """Retrocede a la cancion anterior de la playlist."""
        self.audio_manager.prev_track()
        if self.audio_listbox_widget:
            self.audio_listbox_widget.highlight_current()

    def _playlist_next(self):
        """Avanza a la siguiente cancion de la playlist."""
        self.audio_manager.next_track()
        if self.audio_listbox_widget:
            self.audio_listbox_widget.highlight_current()
    
    def _stop_audio(self):
        """Detiene la reproduccion y termina los sprites vinculados."""
        if self.lasso_manager:
            self.lasso_manager.on_song_stop()
        self.audio_manager.before_track_start = None
        self.audio_manager.stop()
        # Restaurar la lista completa de archivos por si fue restringida
        # durante Play List en modo Lasso
        self.audio_manager.get_audio_files()
        if self.audio_listbox_widget:
            try:
                self.audio_listbox_widget._list.clearSelection()
            except AttributeError:
                pass   # LassoAudioWidget no tiene ._list
        self._update_audio_buttons()

    def _update_audio_buttons(self):
        """Actualiza textos y estados de los botones segun si esta reproduciendo."""
        if not self.loop_btn or not self.playlist_btn:
            return
        
        # ── Boton Reproducir / Pausar (playlist) ─────────────
        if self._btn_play_pause:
            is_paused = getattr(self.audio_manager, 'is_paused', False)
            if self.audio_manager.is_playing and not is_paused:
                self._btn_play_pause.setText("⏸  Pause")
            else:
                self._btn_play_pause.setText("▶  Reproduce")
        
        # ── Boton Play Loop / Stop Loop ───────────────────────
        if self.audio_manager.is_playing and not self.audio_manager.is_playlist_mode:
            self.loop_btn.setText("Stop Loop")
            self.loop_btn.setEnabled(True)
            self.loop_btn.setStyleSheet(theme.DANGER_STYLE)
        else:
            has_selection = self.audio_listbox_widget.get_selected() is not None
            self.loop_btn.setText("Play Loop")
            self.loop_btn.setEnabled(has_selection)
            self.loop_btn.setStyleSheet(theme.BTN_STYLE if has_selection else "")

        # ── Boton Play List / Stop List ───────────────────────
        playlist_activa = (
            self.audio_manager.is_playing and self.audio_manager.is_playlist_mode
        )
        if playlist_activa:
            self.playlist_btn.setText("Stop List")
            self.playlist_btn.setEnabled(True)
            self.playlist_btn.setStyleSheet(theme.DANGER_STYLE)
        else:
            has_files = bool(self.audio_manager.audio_files)
            self.playlist_btn.setText("Play List")
            self.playlist_btn.setEnabled(has_files)
            self.playlist_btn.setStyleSheet(theme.BTN_STYLE if has_files else "")

        # ── Boton Play/Pause (fade in/out segun loop o playlist activa) ──
        # ── Botones Anterior / Siguiente (fade in/out solo en playlist) ──
        loop_activo = self.audio_manager.is_playing and not self.audio_manager.is_playlist_mode
        self._fade_nav_buttons(playlist_activa, loop_activo)

    # ----------------------------------------------------------
    # Lassos cancion-sprite (Lasso)
    # ----------------------------------------------------------

    def _sync_lasso_positions(self) -> None:
        """
        Llamado cada 2 segundos por _sync_timer.

        Lee lasso_positions.ini para cada sprite vinculado activo y
        actualiza lassos.json si la posicion cambio (el usuario lo arrastro).
        Solo actua cuando hay una playlist de vinculos activa y sprites corriendo.
        """
        if self.lasso_manager is None:
            return
        pl_name = self._get_active_lasso_playlist()
        if not pl_name:
            return
        lasso_pids = self.lasso_manager.get_lasso_pids()
        if not lasso_pids:
            return
        for sprite_name in lasso_pids:
            self.lasso_manager.sync_position_from_sprite(pl_name, sprite_name)

    def _open_lasso_window(self):
        """Abre la ventana del editor de vinculos cancion-sprite."""
        try:
            if self.lasso_manager is None:
                show_warning(
                    "Not available",
                    "LassoManager is not configured.",
                    parent=self.window,
                )
                return
            try:
                from ui.lasso_window import LassoWindow
            except ImportError:
                from lasso_window import LassoWindow
            if self._lasso_window is None:
                self._lasso_window = LassoWindow(
                    self.master,
                    self.lasso_manager,
                    self.audio_manager,
                    on_playlist_changed=self._refresh_lasso_combo,
                )
            self._refresh_lasso_combo()
            self._lasso_window.show(main_window=self.window)
            QTimer.singleShot(800, self._refresh_lasso_combo)
        except Exception as _e:
            import traceback
            traceback.print_exc()
            show_error("Lasso Sprites Error",
                       f"Could not open Lasso window:\n{_e}",
                       parent=self.window)

    def _get_active_lasso_playlist(self) -> "str | None":
        """Devuelve el nombre de la playlist activa en el combo Lasso, o None."""
        if self._lasso_playlist_combo is None:
            return None
        text = self._lasso_playlist_combo.currentText().strip()
        return text if text and text != "None" else None

    def _refresh_lasso_combo(self) -> None:
        """Recarga el QComboBox de playlists de vinculos."""
        if self._lasso_playlist_combo is None or self.lasso_manager is None:
            return
        # Usar la seleccion persistida si el combo estaba vacio (panel recien abierto)
        current_text = self._lasso_playlist_combo.currentText()
        to_restore = current_text if current_text else self._last_lasso_selection
        self._lasso_playlist_combo.blockSignals(True)
        self._lasso_playlist_combo.clear()
        self._lasso_playlist_combo.addItem("None")
        for name in self.lasso_manager.get_playlist_names():
            self._lasso_playlist_combo.addItem(name)
        idx = self._lasso_playlist_combo.findText(to_restore or "")
        self._lasso_playlist_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._lasso_playlist_combo.blockSignals(False)
        # Si la seleccion restaurada no es None, disparar el cambio de widget manualmente
        # porque blockSignals() evito que se disparara al setCurrentIndex.
        if idx > 0:
            self._on_lasso_combo_changed(idx)

    def _on_lasso_combo_changed(self, _idx: int) -> None:
        """Intercambia AudioListWidget <-> LassoAudioWidget segun la seleccion."""
        if self._tool_container_layout is None or self.audio_listbox_widget is None:
            return
        pl_name = self._get_active_lasso_playlist()
        # Persistir seleccion para restaurarla si el panel se cierra y reabre
        self._last_lasso_selection = pl_name
        pos = self._tool_container_layout.indexOf(self.audio_listbox_widget)
        if pos < 0:
            return
        self.audio_listbox_widget.hide()
        self.audio_listbox_widget.setParent(None)
        self.audio_listbox_widget.deleteLater()
        if pl_name and self.lasso_manager:
            new_widget = LassoAudioWidget(
                self._tool_container,
                self.audio_manager,
                self.lasso_manager,
                pl_name,
                on_select_callback=self._update_audio_buttons,
            )
        else:
            new_widget = AudioListWidget(
                self._tool_container,
                self.audio_manager,
                on_select_callback=self._update_audio_buttons,
            )
            new_widget.refresh()
        self._tool_container_layout.insertWidget(pos, new_widget)
        self.audio_listbox_widget = new_widget
        self._update_audio_buttons()

    # ----------------------------------------------------------
    # Evento de cierre de la ventana
    # ----------------------------------------------------------

    def _on_window_close(self, event):
        """Intercepta el boton X de la ventana. Cierra directamente."""
        event.accept()
        self.window = None
        self.current_tool = None
        if self.on_close_callback:
            self.on_close_callback()

    # ----------------------------------------------------------
    # Control del panel — API publica
    # ----------------------------------------------------------

    def set_dark_mode(self, dark_mode: bool):
        """Conservado por compatibilidad. El modo oscuro es fijo."""
        pass

    def close(self):
        """Cierra y destruye la ventana del panel. No detiene el audio."""
        if self.window:
            self.window.close()
            self.window = None
        self.current_tool = None
        if self.on_close_callback:
            self.on_close_callback()

    def hide_panel(self):
        """
        Oculta la ventana del panel sin destruirla ni detener el audio.
        Usada por hide_window() de Settings para que el audio siga sonando
        mientras la interfaz queda oculta.
        """
        if self.window:
            self.window.hide()

    def is_visible(self) -> bool:
        """Devuelve True si la ventana existe y esta visible."""
        return self.window is not None and self.window.isVisible()


# ============================================================
# PANEL DERECHO: Procesos corriendo
# ============================================================

class RightProcessPanel:
    """
    Panel flotante derecho que muestra los sprites en ejecucion.
    Permite cerrar procesos individuales o todos juntos.

    Parametros del constructor:
        master                     -- QWidget principal de Settings
        process_manager            -- instancia de ProcessManager
        on_close_callback          -- funcion llamada al cerrar el panel
        on_process_closed_callback -- funcion llamada al cerrar un proceso
    """

    def __init__(self, master, process_manager,
                 on_close_callback=None, on_process_closed_callback=None,
                 lasso_manager=None, audio_manager=None):

        self.master                    = master
        self.process_manager           = process_manager
        self.on_close_callback         = on_close_callback
        self.on_process_closed_callback = on_process_closed_callback
        self.lasso_manager             = lasso_manager
        self.audio_manager             = audio_manager

        self.window          = None   # QDialog
        self._process_list   = None   # QListWidget
        self._status_label   = None   # QLabel
        self.running_processes = []

    # ----------------------------------------------------------
    # Mostrar
    # ----------------------------------------------------------

    def show(self, main_window=None):
        """
        Muestra el panel de procesos.
        Si ya estaba abierto, lo trae al frente y refresca.

        Parametros:
            main_window -- QWidget de referencia para posicionar el panel
        """
        if self.window is not None and self.window.isVisible():
            self.window.raise_()
            self.refresh()
            return

        panel_w = theme.PANEL_SIDE_WIDTH
        panel_h = theme.MAIN_WINDOW_HEIGHT

        self.window = _make_panel_window(
            "Running", self.master, panel_w, panel_h
        )
        self.window.closeEvent = self._on_window_close

        # Posicionar a la derecha de la ventana principal
        if main_window is not None:
            geo = main_window.frameGeometry()
            x   = geo.x() + geo.width() + 5
            y   = geo.y()
            self.window.move(x, y)

        # ── Layout raiz ───────────────────────────────────────
        root = QVBoxLayout(self.window)
        root.setContentsMargins(theme.SP2, theme.SP2, theme.SP2, theme.SP2)
        root.setSpacing(theme.SP2)

        # ── Encabezado ────────────────────────────────────────
        lbl_title = QLabel("Running")
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color: {theme.ACCENT};")
        root.addWidget(lbl_title)

        root.addWidget(_make_separator())

        # ── Etiqueta de estado ────────────────────────────────
        self._status_label = QLabel("Loading...")
        self._status_label.setFont(theme.FONT_SMALL)
        self._status_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        root.addWidget(self._status_label)

        # ── Lista de procesos ─────────────────────────────────
        self._process_list = QListWidget()
        self._process_list.setFont(theme.FONT_MONO)
        self._process_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._process_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._process_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {theme.BG_RAISED};
                color: {theme.TEXT_BRIGHT};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS}px;
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px {theme.SP1}px;
                border-radius: {theme.RADIUS_SMALL}px;
            }}
            QListWidget::item:hover {{
                background-color: {theme.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {theme.ACCENT_DIM};
                color: {theme.TEXT_BRIGHT};
            }}
        """)
        # Doble clic cierra el proceso seleccionado
        self._process_list.itemDoubleClicked.connect(
            lambda item: self.close_selected()
        )
        root.addWidget(self._process_list, 1)

        # ── Fila de botones: Close Selected + Close All ─
        row1 = QHBoxLayout()
        row1.setSpacing(theme.SP1)

        btn_close_sel = QPushButton("Close Selected")
        btn_close_sel.setFont(theme.FONT_SMALL)
        btn_close_sel.setFixedHeight(34)
        btn_close_sel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close_sel.clicked.connect(self.close_selected)
        row1.addWidget(btn_close_sel)

        btn_close_all = QPushButton("Close All")
        btn_close_all.setFont(theme.FONT_SMALL)
        btn_close_all.setFixedHeight(34)
        btn_close_all.setCursor(Qt.CursorShape.PointingHandCursor)
        theme.set_role(btn_close_all, "danger")
        btn_close_all.clicked.connect(self.close_all)
        row1.addWidget(btn_close_all)

        root.addLayout(row1)

        self.window.show()
        self.refresh()

    # ----------------------------------------------------------
    # Acciones sobre procesos
    # ----------------------------------------------------------

    def refresh(self):
        """Recarga la lista de procesos en ejecucion."""
        if not self._process_list:
            return

        self._process_list.clear()
        self.running_processes = self.process_manager.get_running_sprites_for_display()

        for pid, sprite_name, proc in self.running_processes:
            item = QListWidgetItem(sprite_name)
            self._process_list.addItem(item)

        count = len(self.running_processes)
        if count == 0:
            self._status_label.setText("Nothing running")
            self._status_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
            placeholder = QListWidgetItem("  Nothing running")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._process_list.addItem(placeholder)
        elif count == 1:
            self._status_label.setText("1 running")
            self._status_label.setStyleSheet(f"color: {theme.ACCENT};")
        else:
            self._status_label.setText(f"{count} running")
            self._status_label.setStyleSheet(f"color: {theme.ACCENT};")

    def close_selected(self):
        """Cierra el proceso seleccionado en la lista."""
        row = self._process_list.currentRow()

        if row < 0 or not self.running_processes:
            show_warning("Warning", "Select a process to close", parent=self.window)
            return

        pid, sprite_name, proc = self.running_processes[row]

        if self.process_manager.close_process(pid):
            # Si era un Lasso, detener tambien el audio
            if sprite_name.startswith("Lasso:"):
                self._stop_lasso_audio()
            show_info("Success", f"'{sprite_name}' closed", parent=self.window)
            self.refresh()
            if self.on_process_closed_callback:
                self.on_process_closed_callback()
        else:
            show_error("Error", "Could not close process", parent=self.window)

    def close_all(self):
        """Cierra todos los procesos en ejecucion."""
        if not self.running_processes:
            show_info("Info", "Nothing running", parent=self.window)
            return

        count = len(self.running_processes)
        if ask_yes_no("Confirm", f"Close all {count} process(es)?", parent=self.window):
            # Si hay algun Lasso corriendo, detener el audio tambien
            tiene_lasso = any(
                n.startswith("Lasso:") for _, n, _ in self.running_processes
            )
            if tiene_lasso:
                self._stop_lasso_audio()
            # Guardar sesion ANTES de cerrar para no perder los nombres
            if self.on_process_closed_callback:
                self.on_process_closed_callback()
            closed = self.process_manager.close_all_sprites()
            show_info("Success", f"{closed} process(es) closed", parent=self.window)
            self.refresh()

    # ----------------------------------------------------------
    # Evento de cierre de la ventana
    # ----------------------------------------------------------

    def _stop_lasso_audio(self):
        """
        Detiene el audio y notifica al LassoManager cuando se cierra
        un proceso Lasso desde el panel Running.
        """
        if self.audio_manager:
            try:
                self.audio_manager.stop()
            except Exception as e:
                print(f"[RightProcessPanel] Error stopping audio: {e}")
        if self.lasso_manager:
            try:
                self.lasso_manager.on_song_stop()
            except Exception as e:
                print(f"[RightProcessPanel] Error notifying lasso_manager: {e}")
    
    def _on_window_close(self, event):
        """Intercepta el boton X de la ventana."""
        event.accept()
        self.window = None
        self._process_list = None
        self._status_label = None
        if self.on_close_callback:
            self.on_close_callback()

    # ----------------------------------------------------------
    # Control del panel — API publica
    # ----------------------------------------------------------

    def set_dark_mode(self, dark_mode: bool):
        """Conservado por compatibilidad. El modo oscuro es fijo."""
        pass

    def close(self):
        """Destruye la ventana del panel."""
        if self.window:
            self.window.close()
            self.window = None
        if self.on_close_callback:
            self.on_close_callback()

    def is_visible(self) -> bool:
        """Devuelve True si la ventana existe y esta visible."""
        return self.window is not None and self.window.isVisible()


# ============================================================
# HELPER INTERNO: Card (contenedor elevado)
# Equivalente a theme.make_card() del theme.py de tkinter.
# Se usa internamente en los paneles para agrupar controles.
# ============================================================

class _Card(QFrame):
    """
    Contenedor con fondo elevado y borde redondeado.
    Equivalente visual al make_card() del theme.py anterior.

    Uso:
        card = _Card()
        layout = QVBoxLayout(card)
        layout.addWidget(mi_widget)
        panel_layout.addWidget(card)
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        # Usa las constantes del tema oscuro directamente
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.BG_SURFACE};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS}px;
            }}
        """)
