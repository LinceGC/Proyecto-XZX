# -*- coding: utf-8 -*-
"""
src/ui/widgets.py  —  Spryta Widgets (PySide6)

Widgets reutilizables de interfaz para Spryta.

API PUBLICA — identica al widgets.py anterior de tkinter:

    SpriteGalleryWidget(parent, sprites_dir, on_select_callback,
                        fixed_height=250)
        .pack(**kwargs)
        .load_sprites(sprites_list, selected_sprite=None)
        .select_sprite(sprite_name)
        .scroll_to_top()

    AudioListWidget(parent, audio_manager, on_select_callback=None)
        .pack(**kwargs)
        .refresh()
        .get_selected()  -> str | None
        .highlight_current()

Uso (sin cambiar nada en setting.pyw ni panels.py):
    from ui.widgets import SpriteGalleryWidget, AudioListWidget
"""

import os

from PySide6.QtCore    import Qt, QSize, Signal, QObject
from PySide6.QtGui     import (
    QPixmap, QImage, QPainter, QColor, QFont,
    QBrush,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout,
    QScrollArea, QListWidget, QListWidgetItem,
    QSizePolicy, QPushButton,
    QAbstractItemView,
)
from PIL import Image

from ui import theme
from tools.paths import SPRITES_DIR as USER_SPRITES_DIR

# ============================================================
# HELPERS INTERNOS: conversion PIL → QPixmap
# ============================================================

def _pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """
    Convierte una imagen PIL/Pillow a un QPixmap listo para
    mostrar en un QLabel o QListWidgetItem.

    Parametros:
        pil_img -- imagen PIL en modo RGBA o RGB

    Devuelve:
        QPixmap con la imagen lista para mostrar
    """
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")

    data   = pil_img.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        pil_img.width, pil_img.height,
        QImage.Format.Format_RGBA8888,
    )
    # Guardamos una referencia para que Python no libere el buffer
    qimage._data_ref = data
    return QPixmap.fromImage(qimage)


def _make_placeholder_pixmap(size: int = 88) -> QPixmap:
    """
    Crea un QPixmap de placeholder cuando no se puede cargar
    la imagen del sprite. Dibuja un rectangulo con el texto
    'No Preview' centrado.

    Parametros:
        size -- ancho y alto del cuadrado en pixeles
    """
    bg_hex   = theme.BG_RAISED
    text_hex = theme.TEXT_MUTED

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(bg_hex))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(text_hex))
    painter.setFont(QFont("Segoe UI", 8))
    painter.drawText(
        0, 0, size, size,
        Qt.AlignmentFlag.AlignCenter,
        "No\nPreview",
    )
    painter.end()
    return pixmap


# ============================================================
# GALERIA DE SPRITES
# ============================================================

class SpriteGalleryWidget(QWidget):
    """
    Widget de galeria de sprites con tarjetas (cards) y scroll.

    Muestra cada sprite como una card con miniatura y nombre.
    El usuario hace clic en una card para seleccionarla.

    Diferencias visuales respecto al widget de tkinter:
      - Miniaturas mas grandes (72x72 px) con borde redondeado
      - Card completa resaltada al seleccionar (no solo el boton)
      - Hover suave sobre cada card
      - Scrollbar delgado estilo Qt

    Parametros del constructor (identicos al widget anterior):
        parent              -- QWidget padre
        sprites_dir         -- ruta a la carpeta 'sprites/'
        on_select_callback  -- funcion(sprite_name) llamada al seleccionar
        fixed_height        -- altura fija del area de scroll en pixeles
    """

    def __init__(self, parent: QWidget, sprites_dir: str,
                 on_select_callback=None,
                 fixed_height: int = 340):

        super().__init__(parent)

        self.sprites_dir         = sprites_dir
        self.on_select_callback  = on_select_callback
        self.fixed_height        = fixed_height

        # Cache de miniaturas: ruta -> QPixmap
        self._cache: dict[str, QPixmap] = {}

        # Mapa nombre_sprite -> SpriteCard (para resaltado)
        self._cards: dict[str, "_SpriteCard"] = {}

        # Nombre del sprite actualmente seleccionado
        self._selected: str | None = None

        self._build_ui()

    # ----------------------------------------------------------
    # Construccion
    # ----------------------------------------------------------

    def _build_ui(self):
        """Construye el QScrollArea con el contenedor de cards."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Area scrollable
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setFixedHeight(self.fixed_height)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.BG_RAISED};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS}px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {theme.BG_RAISED};
            }}
        """)

        # Contenedor interior de las cards
        self._inner = QWidget()
        self._inner.setStyleSheet(
            f"background-color: {theme.BG_RAISED};"
        )
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(
            theme.SP1, theme.SP1,
            theme.SP1, theme.SP1,
        )
        self._inner_layout.setSpacing(4)
        self._inner_layout.addStretch()   # empuja las cards hacia arriba

        self._scroll.setWidget(self._inner)
        root_layout.addWidget(self._scroll)

    # ----------------------------------------------------------
    # API publica
    # ----------------------------------------------------------

    def pack(self, **kwargs):
        """
        Compatibilidad con el codigo de tkinter que llamaba .pack().
        En Qt simplemente no hace nada; el widget ya fue agregado
        al layout por el codigo que lo crea.

        El widget debe ser agregado al layout padre con:
            layout.addWidget(gallery_widget)
        o con:
            gallery_widget.setParent(parent_widget)
        """
        # No hace nada: en Qt el posicionamiento lo maneja el layout padre.
        # Este metodo existe solo para no romper el codigo existente que
        # llama a self.sprite_gallery.pack(fill="both", expand=True)
        pass

    def load_sprites(self, sprites_list: list, selected_sprite: str = None):
        """
        Carga y muestra la lista de sprites como cards con miniatura.

        Limpia las cards anteriores y construye las nuevas.

        Parametros:
            sprites_list    -- lista de nombres de carpetas de sprites
            selected_sprite -- nombre del sprite a resaltar al cargar
        """
        # ── Limpiar cards anteriores ──────────────────────────
        self._cards.clear()
        self._selected = None

        # Eliminar todos los widgets del layout interior
        # excepto el ultimo item que es el stretch
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # ── Caso sin sprites ─────────────────────────────────
        if not sprites_list:
            lbl = QLabel("No sprites found\n\nAdd sprites to 'sprites/' folder")
            lbl.setFont(theme.FONT_SMALL)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; background: transparent;"
            )
            lbl.setWordWrap(True)
            # Insertar antes del stretch
            self._inner_layout.insertWidget(0, lbl)
            return

        # ── Crear una card por sprite ─────────────────────────
        for i, sprite_name in enumerate(sprites_list):
            sprite_path = os.path.join(self.sprites_dir, sprite_name)
            thumbnail   = self._get_thumbnail(sprite_path)

            card = _SpriteCard(
                name      = sprite_name,
                thumbnail = thumbnail,
                on_click  = self._on_card_click,
            )
            # Insertar antes del stretch (posicion i)
            self._inner_layout.insertWidget(i, card)
            self._cards[sprite_name] = card

        # ── Resaltar el seleccionado si existe ────────────────
        if selected_sprite and selected_sprite in self._cards:
            self.select_sprite(selected_sprite)

    def select_sprite(self, sprite_name: str):
        """
        Resalta visualmente la card del sprite indicado.
        Quita el resaltado de todas las demas cards.

        Parametros:
            sprite_name -- nombre del sprite a seleccionar
        """
        self._selected = sprite_name
        for name, card in self._cards.items():
            card.set_selected(name == sprite_name)

    def set_dark_mode(self, dark_mode: bool):
        """Conservado por compatibilidad. El modo oscuro es fijo."""
        pass

    def scroll_to_top(self):
        """Desplaza el scroll hasta el inicio de la galeria."""
        self._scroll.verticalScrollBar().setValue(0)

    # ----------------------------------------------------------
    # Internos
    # ----------------------------------------------------------

    def _on_card_click(self, sprite_name: str):
        """Maneja el clic sobre una card."""
        self.select_sprite(sprite_name)
        if self.on_select_callback:
            self.on_select_callback(sprite_name)

    def _get_thumbnail(self, sprite_path: str) -> QPixmap:
        """
        Devuelve el QPixmap de miniatura para el sprite indicado.
        Usa el cache correspondiente al modo actual.
        Si no esta en cache, lo genera y lo guarda.

        Parametros:
            sprite_path -- ruta completa a la carpeta del sprite
        """
        cache = self._cache

        if sprite_path in cache:
            return cache[sprite_path]

        pixmap = self._generate_thumbnail(sprite_path)
        cache[sprite_path] = pixmap
        return pixmap

    def _generate_thumbnail(self, sprite_path: str) -> QPixmap:
        """
        Genera un QPixmap de 72x72 px con el primer PNG del sprite.
        Si falla, devuelve el placeholder.

        Parametros:
            sprite_path -- ruta completa a la carpeta del sprite
        """
        THUMB_SIZE = 88

        try:
            if not os.path.isdir(sprite_path):
                raise FileNotFoundError(f"No existe: {sprite_path}")

            png_files = sorted(
                f for f in os.listdir(sprite_path)
                if f.lower().endswith(".png")
            )
            if not png_files:
                raise FileNotFoundError("No hay PNG en la carpeta")

            img_path = os.path.join(sprite_path, png_files[0])
            img      = Image.open(img_path).convert("RGBA")

            # Composicion sobre fondo del tema para evitar transparencias
            bg_hex = theme.BG_RAISED
            bg_rgb = tuple(
                int(bg_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)
            )
            background = Image.new("RGBA", img.size, bg_rgb + (255,))
            background.paste(img, mask=img.split()[3])   # canal alpha

            # Escalar manteniendo proporcion dentro de THUMB_SIZE x THUMB_SIZE
            background.thumbnail(
                (THUMB_SIZE, THUMB_SIZE),
                Image.Resampling.LANCZOS,
            )
            return _pil_to_qpixmap(background)

        except Exception as e:
            print(f"[SpriteGalleryWidget] Error generando miniatura: {e}")
            return _make_placeholder_pixmap(THUMB_SIZE)


# ============================================================
# CARD DE SPRITE (widget interno de la galeria)
# ============================================================

class _SpriteCard(QFrame):
    """
    Tarjeta individual de la galeria de sprites.

    Muestra la miniatura a la izquierda y el nombre a la derecha.
    Cambia de color al hacer hover y al estar seleccionada.

    No se usa directamente; SpriteGalleryWidget la crea internamente.

    Layout interno:
        +------------------------------------------+
        | [miniatura 72x72]  Nombre del sprite      |
        +------------------------------------------+
    """

    def __init__(self, name: str, thumbnail: QPixmap,
                 on_click=None):
        super().__init__()

        self.sprite_name = name
        self._on_click   = on_click
        self._selected   = False

        self.setFixedHeight(100)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Layout horizontal: miniatura | nombre
        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.SP1, theme.SP1, theme.SP2, theme.SP1)
        layout.setSpacing(theme.SP2)

        # Miniatura
        self._lbl_img = QLabel()
        self._lbl_img.setFixedSize(88, 88)
        self._lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_img.setStyleSheet("background: transparent;")
        self._lbl_img.setPixmap(
            thumbnail.scaled(
                88, 88,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        # Nombre del sprite — oculto, se muestra como tooltip
        self._lbl_name = QLabel(name)
        self._lbl_name.setFont(theme.FONT_SMALL)
        self._lbl_name.setWordWrap(False)
        self._lbl_name.setStyleSheet("background: transparent;")
        self._lbl_name.hide()

        # Tooltip con el nombre al pasar el mouse
        self.setToolTip(name)

        layout.addWidget(self._lbl_img)

        # Aplicar estilo inicial
        self._apply_style()

    # ----------------------------------------------------------
    # Estado visual
    # ----------------------------------------------------------

    def set_selected(self, selected: bool):
        """
        Cambia el estado de seleccion y actualiza el estilo visual.

        Parametros:
            selected -- True = resaltado azul, False = normal
        """
        self._selected = selected
        self._apply_style()

    def update_theme(self, dark_mode: bool):
        """Conservado por compatibilidad. El modo oscuro es fijo."""
        pass

    def _apply_style(self):
        """Aplica el stylesheet correcto segun estado de seleccion."""
        if self._selected:
            bg       = theme.ACCENT
            border   = theme.ACCENT
            fg       = "#ffffff"
            hover_bg = theme.ACCENT_HOVER
        else:
            bg       = theme.BG_SURFACE
            border   = theme.BORDER_MID
            fg       = theme.TEXT_NORMAL
            hover_bg = theme.BG_HOVER

        self.setStyleSheet(f"""
            _SpriteCard, QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {theme.RADIUS}px;
            }}
            _SpriteCard:hover, QFrame:hover {{
                border-color: {theme.ACCENT};
                background-color: {hover_bg};
            }}
        """)
        self._lbl_name.setStyleSheet(
            f"color: {fg}; background: transparent;"
            + (" font-weight: bold;" if self._selected else "")
        )

    # ----------------------------------------------------------
    # Eventos del mouse
    # ----------------------------------------------------------

    def mousePressEvent(self, event):
        """Dispara el callback al hacer clic en cualquier parte de la card."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._on_click:
                self._on_click(self.sprite_name)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """Hover: oscurecer un poco si no esta seleccionada."""
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme.ACCENT_DIM};
                    border: 1px solid transparent;
                    border-radius: {theme.RADIUS_SMALL}px;
                }}
            """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Quitar hover."""
        self._apply_style()
        super().leaveEvent(event)


# ============================================================
# LISTA DE AUDIO
# ============================================================

class _AudioRow(QFrame):
    """
    Una fila de AudioListWidget.
    Muestra el nombre del archivo de audio sin extension.
    Identica en estructura a _LassoSongRow para coherencia visual.
    """

    _ROW_H = 40

    def __init__(self, filename: str, on_click=None, parent=None):
        super().__init__(parent)

        self._filename = filename
        self._on_click = on_click
        self._selected = False
        self.setFixedHeight(self._ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(0)

        display = filename.rsplit(".", 1)[0] if "." in filename else filename
        lbl = QLabel(display)
        lbl.setFont(theme.FONT_SMALL)
        lbl.setStyleSheet("background: transparent;")
        lbl.setToolTip(filename)
        row.addWidget(lbl, 1)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme.ACCENT_DIM};
                    border: 1px solid transparent;
                    border-radius: {theme.RADIUS_SMALL}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: {theme.RADIUS_SMALL}px;
                }}
                QFrame:hover {{
                    background-color: {theme.BG_HOVER};
                    border-color: {theme.BORDER_MID};
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)


class AudioListWidget(QWidget):
    """
    Widget de lista de archivos de audio con scroll.
    Usa la misma estructura visual que LassoAudioWidget para
    coherencia visual al cambiar entre modo None y modo Lasso.

    API publica:
        .refresh()
        .get_selected()       -> str | None  (nombre CON extension)
        .highlight_current(scroll=True)
        .set_dark_mode(bool)
        .pack(**kwargs)
    """

    def __init__(self, parent: QWidget, audio_manager,
                 on_select_callback=None):
        super().__init__(parent)

        self.audio_manager      = audio_manager
        self.on_select_callback = on_select_callback

        self._files: list       = []
        self._rows:  list       = []
        self._selected_idx: int = -1

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setFixedHeight(theme.SP5 * 4)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.BG_RAISED};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS}px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {theme.BG_RAISED};
            }}
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background-color: {theme.BG_RAISED};")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(6, 5, 4, 4)
        self._inner_layout.setSpacing(2)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll)

    # ----------------------------------------------------------
    # API publica
    # ----------------------------------------------------------

    def pack(self, **kwargs):
        pass

    def refresh(self):
        """Recarga la lista de archivos desde el gestor de audio."""
        self._rows.clear()
        self._selected_idx = -1
        self._files = []

        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        files = self.audio_manager.get_audio_files()

        if not files:
            lbl = QLabel("No audio files found.")
            lbl.setFont(theme.FONT_SMALL)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
            self._inner_layout.insertWidget(0, lbl)
            return

        for idx, filename in enumerate(files):
            row = _AudioRow(
                filename,
                on_click=lambda i=idx: self._select(i),
                parent=self._inner,
            )
            self._inner_layout.insertWidget(idx, row)
            self._rows.append(row)
            self._files.append(filename)

        if self._files and not self.audio_manager.is_playing:
            self._select(0)

    def get_selected(self) -> "str | None":
        """Devuelve el nombre del archivo seleccionado con extension."""
        if 0 <= self._selected_idx < len(self._files):
            return self._files[self._selected_idx]
        return None

    def highlight_current(self, scroll: bool = True):
        """Resalta el archivo que esta sonando actualmente."""
        current = self.audio_manager.get_current_filename()
        if current and current in self._files:
            idx = self._files.index(current)
            self._select(idx)
            if scroll and 0 <= idx < len(self._rows):
                self._scroll.ensureWidgetVisible(self._rows[idx])

    def set_dark_mode(self, dark_mode: bool):
        pass

    # ----------------------------------------------------------
    # Internos
    # ----------------------------------------------------------

    def _select(self, idx: int):
        if self._selected_idx >= 0 and self._selected_idx < len(self._rows):
            self._rows[self._selected_idx].set_selected(False)
        self._selected_idx = idx
        if 0 <= idx < len(self._rows):
            self._rows[idx].set_selected(True)
        if self.on_select_callback:
            self.on_select_callback()


# ============================================================
# LISTA DE AUDIO VINCULADA (modo Lasso playlist)
# ============================================================

class LassoAudioWidget(QWidget):
    """
    Reemplaza a AudioListWidget cuando el usuario tiene una Lasso playlist
    activa en el combo "Lasso:" del panel de Ambient Audio.

    Cada fila muestra:
      - Nombre de la cancion (sin extension) alineado a la izquierda
      - Miniaturas de los sprites vinculados alineadas a la derecha

    La interfaz publica es identica a la de AudioListWidget para que
    panels.py pueda intercambiarlos sin cambiar el resto del codigo:
        .refresh()
        .get_selected()  -> str | None   (nombre CON extension)
        .highlight_current(scroll=True)

    Parametros del constructor:
        parent            -- QWidget padre
        audio_manager     -- instancia de AmbientAudioManager
        lasso_manager      -- instancia de LassoManager
        playlist_name     -- nombre de la playlist de vinculos activa
        on_select_callback -- funcion() llamada al seleccionar una fila
    """

    THUMB_SIZE   = 32    # px de cada miniatura de sprite
    # Usar la misma carpeta real que Settings/LassoWindow: AppData\Local\Spryta\sprites.
    SPRITES_DIR  = USER_SPRITES_DIR

    def __init__(self, parent: QWidget, audio_manager,
                 lasso_manager, playlist_name: str,
                 on_select_callback=None):
        super().__init__(parent)

        self.audio_manager      = audio_manager
        self.lasso_manager       = lasso_manager
        self.playlist_name      = playlist_name
        self.on_select_callback = on_select_callback

        # Lista de canciones de la playlist (con extension, en orden)
        self._songs: list = []

        # Cache de miniaturas: sprite_name -> QPixmap
        self._thumb_cache: dict = {}

        self._build_ui()
        self.refresh()

    # ----------------------------------------------------------
    # Construccion
    # ----------------------------------------------------------

    def _build_ui(self):
        """Construye el scroll area con filas de canciones."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setFixedHeight(theme.SP5 * 4)   # ~160px igual que AudioListWidget
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.BG_RAISED};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS}px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {theme.BG_RAISED};
            }}
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background-color: {theme.BG_RAISED};")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(6, 5, 4, 4)
        self._inner_layout.setSpacing(2)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll)

        # Guardar filas para poder resaltarlas
        self._rows: list = []    # lista de _LassoSongRow
        self._selected_idx: int = -1

    # ----------------------------------------------------------
    # API publica (identica a AudioListWidget)
    # ----------------------------------------------------------

    def refresh(self):
        """Recarga las canciones de la playlist y sus miniaturas."""
        # Limpiar filas anteriores
        self._rows.clear()
        self._selected_idx = -1
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Obtener canciones de la playlist de vinculos
        self._songs = self.lasso_manager.get_songs(self.playlist_name)

        if not self._songs:
            lbl = QLabel("No songs in this playlist.\nOpen Lasso Sprites to add songs.")
            lbl.setFont(theme.FONT_SMALL)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
            lbl.setWordWrap(True)
            self._inner_layout.insertWidget(0, lbl)
            return

        # Construir una fila por cancion, mostrando solo las que tienen
        # al menos un sprite enlazado.
        bindings = self.lasso_manager.get_all_bindings(self.playlist_name)
        visible_idx = 0
        for song in self._songs:
            sprites = bindings.get(song, [])
            if not sprites:
                # Cancion sin sprites enlazados: no mostrar en la lista
                continue
            thumbs = [self._get_thumb(s) for s in sprites]
            row    = _LassoSongRow(
                song, thumbs,
                on_click=lambda idx=visible_idx: self._select(idx),
                parent=self._inner,
            )
            self._inner_layout.insertWidget(visible_idx, row)
            self._rows.append(row)
            visible_idx += 1
        # Reemplazar self._songs por solo las canciones visibles
        # para que get_selected() y highlight_current() funcionen correctamente
        self._songs = [
            s for s in self._songs if bindings.get(s, [])
        ]

        # Seleccionar la primera fila por defecto
        if self._rows:
            self._select(0)

    def get_selected(self) -> "str | None":
        """
        Devuelve el nombre del archivo de audio seleccionado (con extension).
        Devuelve None si no hay seleccion.
        """
        if self._selected_idx < 0 or self._selected_idx >= len(self._songs):
            return None
        return self._songs[self._selected_idx]

    def highlight_current(self, scroll: bool = True):
        """Resalta la fila cuya cancion esta sonando actualmente."""
        current = self.audio_manager.get_current_filename()
        if current and current in self._songs:
            idx = self._songs.index(current)
            self._select(idx, fire_callback=False)
            if scroll and idx < len(self._rows):
                self._scroll.ensureWidgetVisible(self._rows[idx])

    # ----------------------------------------------------------
    # Internos
    # ----------------------------------------------------------

    def _select(self, idx: int, fire_callback: bool = True):
        """Resalta la fila indicada y deselecciona la anterior."""
        # Deseleccionar anterior
        if 0 <= self._selected_idx < len(self._rows):
            self._rows[self._selected_idx].set_selected(False)
        self._selected_idx = idx
        if 0 <= idx < len(self._rows):
            self._rows[idx].set_selected(True)
        if fire_callback and self.on_select_callback:
            self.on_select_callback()

    def _get_thumb(self, sprite_name: str) -> QPixmap:
        """
        Devuelve la miniatura del primer frame del sprite.
        Usa cache para no recargar desde disco en cada refresh.
        """
        if sprite_name in self._thumb_cache:
            return self._thumb_cache[sprite_name]

        sprite_dir = os.path.join(self.SPRITES_DIR, sprite_name)
        pixmap     = None

        if os.path.isdir(sprite_dir):
            # Buscar el primer PNG del sprite
            pngs = sorted([
                f for f in os.listdir(sprite_dir)
                if f.lower().endswith(".png")
            ])
            if pngs:
                try:
                    img = Image.open(
                        os.path.join(sprite_dir, pngs[0])
                    ).convert("RGBA")
                    img     = img.resize(
                        (self.THUMB_SIZE, self.THUMB_SIZE),
                        Image.LANCZOS,
                    )
                    pixmap  = _pil_to_qpixmap(img)
                except Exception:
                    pass

        if pixmap is None:
            pixmap = _make_placeholder_pixmap(self.THUMB_SIZE)

        self._thumb_cache[sprite_name] = pixmap
        return pixmap


class _LassoSongRow(QFrame):
    """
    Una fila de LassoAudioWidget.
    Izquierda: nombre de la cancion. Derecha: miniaturas de sprites.
    """

    _ROW_H = 40

    def __init__(self, song_name: str, thumbs: list,
                 on_click=None, parent=None):
        super().__init__(parent)

        self._on_click = on_click
        self.setFixedHeight(self._ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False
        self._apply_style()

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(6)

        # Nombre sin extension
        name_display = song_name.rsplit(".", 1)[0] if "." in song_name else song_name
        lbl_name = QLabel(name_display)
        lbl_name.setFont(theme.FONT_SMALL)
        lbl_name.setStyleSheet("background: transparent;")
        lbl_name.setToolTip(song_name)
        row.addWidget(lbl_name, 1)

        # Miniaturas de sprites (max 4 para no desbordar)
        for pm in thumbs[:4]:
            lbl_img = QLabel()
            lbl_img.setFixedSize(LassoAudioWidget.THUMB_SIZE,
                                 LassoAudioWidget.THUMB_SIZE)
            lbl_img.setPixmap(pm)
            lbl_img.setStyleSheet("background: transparent;")
            lbl_img.setToolTip("")
            row.addWidget(lbl_img)

        # Indicador si hay mas de 4 sprites
        if len(thumbs) > 4:
            lbl_more = QLabel(f"+{len(thumbs) - 4}")
            lbl_more.setFont(theme.FONT_TINY)
            lbl_more.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; background: transparent;"
            )
            row.addWidget(lbl_more)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme.ACCENT_DIM};
                    border: 1px solid transparent;
                    border-radius: {theme.RADIUS_SMALL}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: {theme.RADIUS_SMALL}px;
                }}
                QFrame:hover {{
                    background-color: {theme.BG_HOVER};
                    border-color: {theme.BORDER_MID};
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)
        
# ============================================================
# SceneListWidget — lista de escenas/reels con miniaturas
# Usado en la pagina Scenes y en la pagina Reel.
# ============================================================

class _SceneRow(QFrame):
    """
    Una fila de SceneListWidget.
    Izquierda: nombre de la escena o reel. Derecha: miniaturas de sprites.
    """

    _ROW_H   = 40
    _THUMB_S = 32

    def __init__(self, name: str, thumbs: list,
                 on_click=None, parent=None):
        super().__init__(parent)

        self._on_click = on_click
        self.setFixedHeight(self._ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False
        self._apply_style()

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(6)

        lbl_name = QLabel(name)
        lbl_name.setFont(theme.FONT_SMALL)
        lbl_name.setStyleSheet("background: transparent;")
        row.addWidget(lbl_name, 1)

        for pm in thumbs[:4]:
            lbl_img = QLabel()
            lbl_img.setFixedSize(self._THUMB_S, self._THUMB_S)
            lbl_img.setPixmap(pm)
            lbl_img.setStyleSheet("background: transparent;")
            row.addWidget(lbl_img)

        if len(thumbs) > 4:
            lbl_more = QLabel(f"+{len(thumbs) - 4}")
            lbl_more.setFont(theme.FONT_TINY)
            lbl_more.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; background: transparent;"
            )
            row.addWidget(lbl_more)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme.ACCENT_DIM};
                    border: 1px solid transparent;
                    border-radius: {theme.RADIUS_SMALL}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: {theme.RADIUS_SMALL}px;
                }}
                QFrame:hover {{
                    background-color: {theme.BG_HOVER};
                    border-color: {theme.BORDER_MID};
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)


class SceneListWidget(QWidget):
    """
    Lista con scroll de escenas o reels, mostrando miniaturas de sprites.

    Uso:
        widget = SceneListWidget(parent, sprites_dir, on_select_callback)
        widget.load([("nombre", ["sprite1", "sprite2"]), ...])
        nombre = widget.get_selected()   # devuelve el nombre o None
        row    = widget.current_row()    # devuelve el indice o -1
    """

    THUMB_SIZE  = 32
    LIST_HEIGHT = 200

    def __init__(self, parent: QWidget, sprites_dir: str,
                 on_select_callback=None, fixed_height: int = None):
        super().__init__(parent)

        self.sprites_dir        = sprites_dir
        self.on_select_callback = on_select_callback
        self._items: list       = []   # lista de nombres en orden
        self._rows:  list       = []   # lista de _SceneRow
        self._selected_idx: int = -1
        self._thumb_cache: dict = {}

        self._build_ui(fixed_height or self.LIST_HEIGHT)

    def _build_ui(self, height: int):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setFixedHeight(height)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.BG_RAISED};
                border: 1px solid {theme.BORDER_MID};
                border-radius: {theme.RADIUS}px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {theme.BG_RAISED};
            }}
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background-color: {theme.BG_RAISED};")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)
        self._inner_layout.setSpacing(2)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll)

    def load(self, items: list):
        """
        Carga la lista. items es una lista de tuplas (nombre, [sprites]).
        """
        # Limpiar filas anteriores
        self._rows.clear()
        self._selected_idx = -1
        self._items = []
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not items:
            lbl = QLabel("Nothing here yet.")
            lbl.setFont(theme.FONT_SMALL)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
            self._inner_layout.insertWidget(0, lbl)
            return

        for idx, (name, sprites) in enumerate(items):
            thumbs = [self._get_thumb(s) for s in sprites]
            row = _SceneRow(
                name, thumbs,
                on_click=lambda i=idx: self._select(i),
                parent=self._inner,
            )
            self._inner_layout.insertWidget(idx, row)
            self._rows.append(row)
            self._items.append(name)

        if self._rows:
            self._select(0)

    def _select(self, idx: int):
        if self._selected_idx >= 0 and self._selected_idx < len(self._rows):
            self._rows[self._selected_idx].set_selected(False)
        self._selected_idx = idx
        if 0 <= idx < len(self._rows):
            self._rows[idx].set_selected(True)
        if self.on_select_callback:
            self.on_select_callback(self._items[idx] if idx < len(self._items) else None)

    def get_selected(self) -> "str | None":
        if 0 <= self._selected_idx < len(self._items):
            return self._items[self._selected_idx]
        return None

    def current_row(self) -> int:
        return self._selected_idx

    def _get_thumb(self, sprite_name: str):
        if sprite_name in self._thumb_cache:
            return self._thumb_cache[sprite_name]

        pixmap  = None
        sp_dir  = os.path.join(self.sprites_dir, sprite_name)

        if os.path.isdir(sp_dir):
            pngs = sorted([
                f for f in os.listdir(sp_dir)
                if f.lower().endswith(".png")
            ])
            if pngs:
                try:
                    img = Image.open(
                        os.path.join(sp_dir, pngs[0])
                    ).convert("RGBA")
                    img    = img.resize(
                        (self.THUMB_SIZE, self.THUMB_SIZE),
                        Image.LANCZOS,
                    )
                    pixmap = _pil_to_qpixmap(img)
                except Exception:
                    pass

        if pixmap is None:
            pixmap = _make_placeholder_pixmap(self.THUMB_SIZE)

        self._thumb_cache[sprite_name] = pixmap
        return pixmap
