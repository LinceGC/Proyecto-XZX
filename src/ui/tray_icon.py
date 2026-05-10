# -*- coding: utf-8 -*-
"""
tray_icon.py  —  Spryta System Tray unificado

Componente QSystemTrayIcon con menu personalizado de estilo Spryta.
Reemplaza los tres trays separados (main.pyw, panels.py, setting.pyw).

Funciones del menu:
    - Mostrar / Ocultar ventana de Settings
    - Mostrar / Ocultar todos los sprites activos
    - Lista de sprites en ejecucion con boton de cierre individual
    - Controles de Ambient Audio (prev/stop/play/next + volumen)
    - Salir de Spryta

IPC con main.pyw:
    Escribe data/toggle_sprites.flag con el formato "comando:timestamp"
    donde comando es "hide" o "show". Cada instancia de main.pyw
    lee el archivo periodicamente y actua si el timestamp es mas reciente
    que el ultimo que proceso.

Uso en setting.pyw:
    from ui.tray_icon import SpryTrayIcon
    self.tray = SpryTrayIcon(self, self.audio_manager, self.process_manager)
    self.tray.show()
"""

import os
import time

from PySide6.QtCore    import Qt, QTimer
from PySide6.QtGui     import QIcon, QCursor, QPixmap, QColor
from PySide6.QtWidgets import (
    QSystemTrayIcon, QWidget,
    QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QFrame,
    QApplication, QSizePolicy,
    QGraphicsDropShadowEffect, QScrollArea,
)

# ── Rutas de archivos IPC ────────────────────────────────────
DATA_DIR           = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Spryta", "data")
TOGGLE_FLAG        = os.path.join(DATA_DIR, "toggle_sprites.flag")
SPRITES_STATE_FLAG = os.path.join(DATA_DIR, "sprites_visible_state.flag")

# ── Version mostrada en la cabecera ─────────────────────────
VERSION = "1.0"

# ── Colores del tema oscuro de Spryta ────────────────────────
# Importados desde la fuente de verdad para que los cambios
# en theme_dark.py se reflejen automaticamente aqui.
from ui import theme_dark as _td

C_BG_SURFACE  = _td.BG_SURFACE
C_BG_RAISED   = _td.BG_RAISED
C_BG_HOVER    = _td.BG_HOVER
C_BORDER_MID  = _td.BORDER_MID
C_BORDER_HI   = _td.BORDER_HI
C_ACCENT      = _td.ACCENT
C_ACCENT_HVR  = _td.ACCENT_HOVER
C_TEXT_BRIGHT = _td.TEXT_BRIGHT
C_TEXT_NORM   = _td.TEXT_NORMAL
C_TEXT_MUTED  = _td.TEXT_MUTED
C_DANGER      = _td.COLOR_DANGER

FONT          = "Segoe UI"
MENU_WIDTH    = 288


# ============================================================
# Widgets internos del menu
# ============================================================

class _Divider(QFrame):
    """Linea separadora horizontal de 1px."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(
            f"background: {C_BORDER_MID}; border: none;"
        )


class _SectionLabel(QLabel):
    """Etiqueta de titulo de seccion en mayusculas y color atenuado."""

    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"color: {C_TEXT_MUTED};"
            f"font-family: '{FONT}';"
            f"font-size: 9px;"
            f"font-weight: 700;"
            f"letter-spacing: 1px;"
            f"background: transparent;"
            f"border: none;"
            f"padding: 0;"
        )


class _MenuButton(QPushButton):
    """
    Boton de opcion de menu con icono de texto y hover en estilo Spryta.

    Parametros:
        text     -- texto visible del boton
        icon_chr -- caracter unicode que actua de icono (opcional)
        danger   -- True para colorear en rojo (boton de salir)
    """

    def __init__(self, text, icon_chr="", danger=False, parent=None):
        label = f"{icon_chr}   {text}" if icon_chr else text
        super().__init__(label, parent)
        fg        = C_DANGER if danger else C_TEXT_BRIGHT
        hover_bg  = "#2a0a0e" if danger else C_BG_HOVER
        hover_fg  = C_DANGER if danger else C_ACCENT
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {fg};
                font-family: '{FONT}';
                font-size: 12px;
                font-weight: 400;
                text-align: left;
                padding: 8px 16px;
                border: none;
                border-radius: 0px;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                color: {hover_fg};
            }}
            QPushButton:pressed {{
                background: {C_BG_RAISED};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(MENU_WIDTH)


class _CtrlButton(QPushButton):
    """Boton de control de audio con altura fija y ancho expandible."""

    def __init__(self, symbol, parent=None):
        super().__init__(symbol, parent)
        self.setFixedHeight(32)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {C_BG_RAISED};
                color: {C_TEXT_NORM};
                font-size: 13px;
                border: 1px solid {C_BORDER_MID};
                border-radius: 6px;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {C_BG_HOVER};
                color: {C_TEXT_BRIGHT};
                border-color: {C_BORDER_HI};
            }}
            QPushButton:pressed {{
                background: {C_ACCENT};
                color: #ffffff;
                border-color: {C_ACCENT};
            }}
            QPushButton:disabled {{
                background: {C_BG_RAISED};
                color: {C_TEXT_MUTED};
                border-color: {C_BORDER_MID};
            }}
        """)


class _SpriteRow(QWidget):
    """
    Fila de un sprite activo: indicador de color + nombre + boton de cierre.

    Parametros:
        pid      -- PID del proceso del sprite
        name     -- nombre a mostrar
        on_close -- callable(pid) que se llama al presionar el boton de cierre
    """

    def __init__(self, pid, name, on_close, parent=None):
        super().__init__(parent)
        self.setFixedWidth(MENU_WIDTH)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 3, 8, 3)
        lay.setSpacing(8)

        # Punto indicador de estado activo
        dot = QLabel("●")
        dot.setFixedWidth(10)
        dot.setStyleSheet(
            f"color: {C_ACCENT}; font-size: 8px;"
            f"background: transparent; border: none;"
        )
        lay.addWidget(dot)

        # Nombre del sprite (truncado si es demasiado largo)
        display = name if len(name) <= 38 else name[:35] + "..."
        lbl = QLabel(display)
        lbl.setStyleSheet(
            f"color: {C_TEXT_BRIGHT}; font-family: '{FONT}';"
            f"font-size: 12px; background: transparent; border: none;"
        )
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(lbl)

        # Boton de cierre
        btn = QPushButton("✕")
        btn.setFixedSize(20, 20)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Cerrar sprite")
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C_TEXT_MUTED};
                font-size: 10px;
                border: none;
                border-radius: 4px;
                padding: 0;
            }}
            QPushButton:hover {{
                background: #2a0a0e;
                color: {C_DANGER};
            }}
        """)
        btn.clicked.connect(lambda: on_close(pid))
        lay.addWidget(btn)


# ============================================================
# Ventana del menu personalizado
# ============================================================

class TrayMenu(QWidget):
    """
    Ventana frameless con el menu del tray de estilo Spryta.

    Se construye una sola vez y se reutiliza en cada apertura.
    Al abrirse, llama a _refresh() para actualizar todos los datos
    (sprites activos, estado de audio, estado de la ventana).
    """

    def __init__(self, main_window, audio_manager, process_manager, lasso_manager=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup
        )
        self.main_window     = main_window
        self.audio_manager   = audio_manager
        self.process_manager = process_manager
        self.lasso_manager    = lasso_manager   # puede ser None si no esta configurado

        # Estado local del toggle de sprites
        self._sprites_visible = True

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(MENU_WIDTH + 16)  # +16 para el padding de la sombra

        self._build_ui()

    # ----------------------------------------------------------
    # Construccion del UI (se ejecuta una sola vez)
    # ----------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        # Tarjeta principal con borde y fondo oscuro
        self._card = QFrame()
        self._card.setObjectName("SpryTrayCard")
        self._card.setStyleSheet(f"""
            QFrame#SpryTrayCard {{
                background: {C_BG_SURFACE};
                border: 1px solid {C_BORDER_MID};
                border-radius: 10px;
            }}
        """)
        root.addWidget(self._card)

        # Sombra exterior
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        self._card.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Secciones
        self._build_header(lay)
        lay.addWidget(_Divider())
        self._build_app_controls(lay)
        lay.addWidget(_Divider())
        self._build_sprites_section(lay)
        lay.addWidget(_Divider())
        self._build_audio_section(lay)
        lay.addWidget(_Divider())
        self._build_exit_button(lay)

    def _build_header(self, parent_layout):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 13, 14, 13)
        lay.setSpacing(10)

        # Icono de la app
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(30, 30)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        icon_path = os.path.join("assets", "icons", "icon.ico")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(
                30, 30,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_lbl.setPixmap(pix)
        lay.addWidget(icon_lbl)

        # Nombre y version
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)

        lbl_name = QLabel("SPRYTA")
        lbl_name.setStyleSheet(
            f"color: {C_TEXT_BRIGHT}; font-family: '{FONT}';"
            f"font-size: 12px; font-weight: 700;"
            f"background: transparent; border: none;"
        )
        lbl_ver = QLabel(f"v{VERSION}")
        lbl_ver.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-family: '{FONT}';"
            f"font-size: 10px; background: transparent; border: none;"
        )
        col.addWidget(lbl_name)
        col.addWidget(lbl_ver)
        lay.addLayout(col)
        lay.addStretch()

        parent_layout.addWidget(row)

    def _build_app_controls(self, parent_layout):
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(0)

        self._btn_settings = _MenuButton("Mostrar Settings", "⚙")
        self._btn_settings.clicked.connect(self._toggle_settings)
        lay.addWidget(self._btn_settings)

        self._btn_sprites = _MenuButton("Ocultar Sprites", "👁")
        self._btn_sprites.clicked.connect(self._toggle_sprites)
        lay.addWidget(self._btn_sprites)

        parent_layout.addWidget(wrapper)

    def _build_sprites_section(self, parent_layout):
        self._sprites_outer = QWidget()
        self._sprites_outer.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self._sprites_outer)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(0)

        # Encabezado de seccion
        hdr = QWidget()
        hdr.setStyleSheet("background: transparent;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 0, 16, 6)
        hdr_lay.addWidget(_SectionLabel("Sprites activos"))
        hdr_lay.addStretch()
        lay.addWidget(hdr)

        # Widget contenedor de las filas — vive dentro del scroll
        self._sprites_content = QWidget()
        self._sprites_content.setStyleSheet("background: transparent;")
        self._sprites_body = QVBoxLayout(self._sprites_content)
        self._sprites_body.setSpacing(0)
        self._sprites_body.setContentsMargins(0, 0, 0, 0)
        self._sprites_body.addStretch()

        # Area de scroll: altura maxima de 4 filas (~28px c/u = 112px)
        # Si hay menos filas, el area se encoge automaticamente.
        # Si hay mas, aparece el scroll sin afectar el resto del menu.
        self._sprites_scroll = QScrollArea()
        self._sprites_scroll.setWidget(self._sprites_content)
        self._sprites_scroll.setWidgetResizable(True)
        self._sprites_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._sprites_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._sprites_scroll.setFixedHeight(112)
        self._sprites_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self._sprites_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {C_BG_RAISED};
                width: 4px;
                margin: 0;
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {C_BORDER_HI};
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C_ACCENT};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        lay.addWidget(self._sprites_scroll)
        parent_layout.addWidget(self._sprites_outer)

    def _build_audio_section(self, parent_layout):
        section = QWidget()
        section.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(section)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(8)

        # Titulo de seccion
        lay.addWidget(_SectionLabel("Ambient Audio"))

        # Nombre de la pista activa
        self._lbl_track = QLabel("Sin audio")
        self._lbl_track.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-family: '{FONT}';"
            f"font-size: 11px; background: transparent; border: none;"
        )
        lay.addWidget(self._lbl_track)

        # Fila de controles de reproduccion
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)
        ctrl_row.setContentsMargins(0, 0, 0, 0)

        self._btn_prev = _CtrlButton("⏮")
        self._btn_stop = _CtrlButton("⏹")
        self._btn_play = _CtrlButton("▶")
        self._btn_next = _CtrlButton("⏭")

        self._btn_prev.setToolTip("Anterior (solo en Reel)")
        self._btn_stop.setToolTip("Detener")
        self._btn_play.setToolTip("Reproducir / Pausar")
        self._btn_next.setToolTip("Siguiente (solo en Reel)")

        self._btn_prev.clicked.connect(self._audio_prev)
        self._btn_stop.clicked.connect(self._audio_stop)
        self._btn_play.clicked.connect(self._audio_play_pause)
        self._btn_next.clicked.connect(self._audio_next)

        ctrl_row.addWidget(self._btn_prev)
        ctrl_row.addWidget(self._btn_stop)
        ctrl_row.addWidget(self._btn_play)
        ctrl_row.addWidget(self._btn_next)
        lay.addLayout(ctrl_row)

        # Fila de volumen
        vol_row = QHBoxLayout()
        vol_row.setSpacing(8)
        vol_row.setContentsMargins(0, 0, 0, 0)

        lbl_vol = QLabel("Vol")
        lbl_vol.setFixedWidth(22)
        lbl_vol.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-family: '{FONT}';"
            f"font-size: 10px; background: transparent; border: none;"
        )

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: {C_BG_RAISED};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {C_ACCENT};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px;
                height: 12px;
                margin: -4px 0;
                background: {C_TEXT_BRIGHT};
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {C_ACCENT_HVR};
            }}
        """)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)

        self._lbl_vol_pct = QLabel("80%")
        self._lbl_vol_pct.setFixedWidth(30)
        self._lbl_vol_pct.setStyleSheet(
            f"color: {C_TEXT_NORM}; font-family: '{FONT}';"
            f"font-size: 10px; background: transparent; border: none;"
        )

        vol_row.addWidget(lbl_vol)
        vol_row.addWidget(self._vol_slider)
        vol_row.addWidget(self._lbl_vol_pct)
        lay.addLayout(vol_row)

        parent_layout.addWidget(section)

    def _build_exit_button(self, parent_layout):
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        w_lay = QVBoxLayout(wrapper)
        w_lay.setContentsMargins(0, 4, 0, 4)
        w_lay.setSpacing(0)
        btn = _MenuButton("Salir de Spryta", "⏻", danger=True)
        btn.clicked.connect(self._exit_app)
        w_lay.addWidget(btn)
        parent_layout.addWidget(wrapper)

    # ----------------------------------------------------------
    # Mostrar el menu y refrescar contenido
    # ----------------------------------------------------------

    def show_near_tray(self):
        """Refresca los datos y muestra el menu posicionado sobre el tray."""
        self._refresh()
        self.adjustSize()

        screen = QApplication.primaryScreen().availableGeometry()
        w = self.width()
        h = self.height()
        cursor = QCursor.pos()

        # Horizontal: centrado en el cursor, sin salir de pantalla
        x = min(
            max(cursor.x() - w // 2, screen.left() + 8),
            screen.right() - w - 8
        )
        # Vertical: siempre encima de la barra de tareas
        y = screen.bottom() - h - 8

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    # ----------------------------------------------------------
    # Refresco de contenido dinamico
    # ----------------------------------------------------------

    def _refresh(self):
        self._refresh_settings_button()
        self._refresh_sprites_visible_state()
        self._refresh_sprites()
        self._refresh_audio()

    def _refresh_settings_button(self):
        """Actualiza el texto del boton segun visibilidad de la ventana."""
        visible = (
            self.main_window.isVisible()
            and not self.main_window.isMinimized()
        )
        self._btn_settings.setText(
            "⚙   Ocultar Settings" if visible else "⚙   Mostrar Settings"
        )
    
    def _refresh_sprites_visible_state(self):
        """Lee el archivo de estado escrito por main.pyw y sincroniza el boton."""
        if os.path.exists(SPRITES_STATE_FLAG):
            try:
                with open(SPRITES_STATE_FLAG, "r", encoding="utf-8") as f:
                    state = f.read().strip()
                self._sprites_visible = (state == "visible")
            except Exception:
                pass
        self._btn_sprites.setText(
            "👁   Ocultar Sprites" if self._sprites_visible else "👁   Mostrar Sprites"
        )
    
    def _refresh_sprites(self):
        """Limpia y reconstruye la lista de sprites activos."""
        # Eliminar todas las filas anteriores pero conservar el stretch final
        while self._sprites_body.count() > 1:
            item = self._sprites_body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sprites = self.process_manager.get_running_sprites_for_display()

        if sprites:
            for pid, name, _ in sprites:
                row = _SpriteRow(pid, name, self._on_close_sprite)
                self._sprites_body.insertWidget(
                    self._sprites_body.count() - 1, row
                )
        else:
            lbl = QLabel("Sin sprites activos")
            lbl.setStyleSheet(
                f"color: {C_TEXT_MUTED}; font-family: '{FONT}';"
                f"font-size: 11px; background: transparent; border: none;"
                f"padding: 2px 16px;"
            )
            self._sprites_body.insertWidget(0, lbl)

    def _refresh_audio(self):
        """Actualiza nombre de pista, icono de play/pause y volumen."""
        filename = self.audio_manager.get_current_filename()

        if filename:
            name = filename if len(filename) <= 36 else filename[:33] + "..."
            self._lbl_track.setText(f"♪  {name}")
            self._lbl_track.setStyleSheet(
                f"color: {C_TEXT_BRIGHT}; font-family: '{FONT}';"
                f"font-size: 11px; background: transparent; border: none;"
            )
        else:
            self._lbl_track.setText("Sin audio")
            self._lbl_track.setStyleSheet(
                f"color: {C_TEXT_MUTED}; font-family: '{FONT}';"
                f"font-size: 11px; background: transparent; border: none;"
            )

        # Icono de play o pause segun estado
        is_playing = getattr(self.audio_manager, 'is_playing', False)
        is_paused  = getattr(self.audio_manager, 'is_paused',  False)
        self._btn_play.setText("⏸" if (is_playing and not is_paused) else "▶")

        # Prev / next habilitados solo en modo Reel
        in_playlist = getattr(self.audio_manager, 'is_playlist_mode', False)
        self._btn_prev.setEnabled(in_playlist)
        self._btn_next.setEnabled(in_playlist)

        # Leer volumen actual del mixer
        try:
            vol = int(self.audio_manager.get_volume() * 100)
        except Exception:
            vol = 80

        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(vol)
        self._vol_slider.blockSignals(False)
        self._lbl_vol_pct.setText(f"{vol}%")

    # ----------------------------------------------------------
    # Acciones del menu
    # ----------------------------------------------------------

    def _toggle_settings(self):
        self.hide()
        win = self.main_window
        if win.isVisible() and not win.isMinimized():
            win.hide_window()
        else:
            win.show_window()

    def _toggle_sprites(self):
        """Escribe el flag de comando para que todos los sprites reaccionen."""
        self.hide()
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            command = "hide" if self._sprites_visible else "show"
            ts      = time.time()
            with open(TOGGLE_FLAG, "w", encoding="utf-8") as f:
                f.write(f"{command}:{ts}")
            self._sprites_visible = not self._sprites_visible
            self._btn_sprites.setText(
                "👁   Mostrar Sprites"
                if not self._sprites_visible
                else "👁   Ocultar Sprites"
            )
        except Exception as e:
            print(f"[TrayMenu] Error escribiendo toggle flag: {e}")

    def _on_close_sprite(self, pid):
        """Cierra un sprite y refresca la lista tras un breve retraso."""
        # Verificar si el proceso que se cierra es un Lasso
        # para detener el audio junto con el sprite.
        sprites = self.process_manager.get_running_sprites_for_display()
        es_lasso = any(
            p == pid and name.startswith("Lasso:")
            for p, name, _ in sprites
        )
        self.process_manager.close_process(pid)
        if es_lasso:
            if self.audio_manager:
                try:
                    self.audio_manager.stop()
                except Exception as e:
                    print(f"[TrayMenu] Error deteniendo audio: {e}")
            if self.lasso_manager:
                try:
                    self.lasso_manager.on_song_stop()
                except Exception as e:
                    print(f"[TrayMenu] Error notificando lasso_manager: {e}")
        QTimer.singleShot(700, self._refresh_sprites)

    def _audio_play_pause(self):
        """
        Pausa si hay algo reproduciendose activamente.
        Reanuda si esta pausado o si fue detenido y habia una pista previa.
        Si no habia ninguna pista anterior, inicia la primera disponible en loop.
        """
        am = self.audio_manager
        is_paused  = getattr(am, 'is_paused',  False)

        try:
            import pygame
            mixer_busy = pygame.mixer.get_init() and pygame.mixer.music.get_busy()
        except Exception:
            mixer_busy = False

        if mixer_busy and not is_paused:
            # Mixer activo y sin pausa: pausar
            am.pause()
            if self.lasso_manager:
                self.lasso_manager.on_song_pause()
        elif is_paused:
            # Estaba pausado: reanudar
            am.resume()
            if self.lasso_manager:
                self.lasso_manager.on_song_resume()
        else:
            # Nada activo: intentar reanudar desde el ultimo estado conocido
            last_path = getattr(am, '_last_audio_path', None)
            if last_path:
                am.resume()
                if self.lasso_manager:
                    self.lasso_manager.on_song_resume()
            else:
                # Sin historial: cargar el primer archivo disponible y reproducir en loop
                try:
                    files = am.get_audio_files()
                    if files:
                        am.play_playlist(0)
                except Exception as e:
                    print(f"[TrayMenu] Error iniciando audio: {e}")

        self._refresh_audio()

    def _audio_stop(self):
        if self.lasso_manager:
            self.lasso_manager.on_song_stop()
        self.audio_manager.stop()
        self._refresh_audio()

    def _audio_prev(self):
        if getattr(self.audio_manager, 'is_playlist_mode', False):
            self.audio_manager.prev_track()
            self._refresh_audio()

    def _audio_next(self):
        if getattr(self.audio_manager, 'is_playlist_mode', False):
            self.audio_manager.next_track()
            self._refresh_audio()

    def _on_volume_changed(self, value):
        self.audio_manager.set_volume(value / 100.0)
        self._lbl_vol_pct.setText(f"{value}%")

    def _exit_app(self):
        self.hide()
        self.main_window._finalize_and_exit()


# ============================================================
# Icono del System Tray
# ============================================================

class SpryTrayIcon(QSystemTrayIcon):
    """
    Icono de bandeja del sistema unificado de Spryta.

    Clic izquierdo  → muestra / oculta la ventana de Settings.
    Clic derecho    → abre el menu personalizado TrayMenu.

    Parametros:
        main_window     -- instancia de SettingsApp (QMainWindow)
        audio_manager   -- instancia de AmbientAudioManager
        process_manager -- instancia de ProcessManager
    """

    def __init__(self, main_window, audio_manager, process_manager):
        icon_path = os.path.join("assets", "icons", "icon.ico")
        icon      = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        super().__init__(icon, main_window)

        lasso_manager = getattr(main_window, "lasso_manager", None)
        self._menu = TrayMenu(main_window, audio_manager, process_manager, lasso_manager)
        self._main = main_window

        self.setToolTip("Spryta")
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        """Distribuye la accion segun el tipo de clic."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Clic izquierdo: toggle show/hide Settings y paneles
            if self._main.isVisible() and not self._main.isMinimized():
                self._main.hide_window()
            else:
                self._main.show_window()

        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # Clic derecho: menu personalizado
            self._menu.show_near_tray()
