# -*- coding: utf-8 -*-
"""
src/ui/dialog.py  —  Spryta Dialog System (PySide6)

Ventanas de dialogo personalizadas con estilo Spryta.
Reemplazan los messagebox y simpledialog de tkinter.

API PUBLICA — exactamente los mismos nombres y parametros de antes:

    show_info   (title, message, parent=None)
    show_warning(title, message, parent=None)
    show_error  (title, message, parent=None)
    ask_yes_no  (title, message, parent=None)  -> bool
    ask_string  (title, prompt,  parent=None, initial="")  -> str | None

Uso (igual que antes, sin cambiar nada en otros archivos):
    from ui.dialog import show_info, show_warning, show_error, ask_yes_no
    show_warning("Atencion", "Selecciona un sprite primero.")
    ok = ask_yes_no("Confirmar", "Deseas eliminar este sprite?")
"""

import os

from PySide6.QtCore    import Qt, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui     import QFont, QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit,
    QFrame, QWidget, QApplication,
    QGraphicsOpacityEffect,
)

from ui import theme


# ============================================================
# SECCION 1: ICONO SVG DIBUJADO A MANO
# Equivalente al _icon_canvas() del dialog.py anterior.
# En Qt usamos un QLabel con QPixmap pintado con QPainter.
# ============================================================

def _make_icon_pixmap(kind: str, size: int = 32) -> QPixmap:
    """
    Dibuja un icono vectorial en un QPixmap segun el tipo de dialogo.

    Tipos disponibles:
        "info"     — circulo azul con letra i
        "warning"  — triangulo naranja con !
        "error"    — circulo rojo con X
        "question" — circulo azul con ?

    Parametros:
        kind -- tipo de icono (ver arriba)
        size -- tamano en pixeles (ancho y alto iguales)
    """
    color_map = {
        "info":     theme.ACCENT,
        "warning":  theme.COLOR_WARNING,
        "error":    theme.COLOR_DANGER,
        "question": theme.ACCENT,
    }
    hex_color = color_map.get(kind, theme.ACCENT)
    color     = QColor(hex_color)

    # Crear pixmap transparente
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    pen = QPen(color, 2)
    painter.setPen(pen)

    m = 2   # margen interior

    if kind == "warning":
        # Triangulo
        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint as P
        triangle = QPolygon([P(size//2, m), P(size-m, size-m), P(m, size-m)])
        painter.drawPolygon(triangle)
        # Signo !
        painter.setFont(QFont("Consolas", int(size * 0.38), QFont.Weight.Bold))
        painter.drawText(0, 0, size, size - 4, Qt.AlignmentFlag.AlignCenter, "!")

    elif kind == "error":
        # Circulo
        painter.drawEllipse(m, m, size - m*2, size - m*2)
        # Cruz X
        pen2 = QPen(color, 2)
        painter.setPen(pen2)
        pad = int(size * 0.28)
        painter.drawLine(pad, pad, size - pad, size - pad)
        painter.drawLine(size - pad, pad, pad, size - pad)

    elif kind == "question":
        # Circulo
        painter.drawEllipse(m, m, size - m*2, size - m*2)
        # Letra ?
        painter.setFont(QFont("Segoe UI", int(size * 0.40), QFont.Weight.Bold))
        painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, "?")

    else:  # info
        # Circulo
        painter.drawEllipse(m, m, size - m*2, size - m*2)
        # Letra i
        painter.setFont(QFont("Segoe UI", int(size * 0.40), QFont.Weight.Bold))
        painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, "i")

    painter.end()
    return pixmap


# ============================================================
# SECCION 2: CLASE BASE DE DIALOGO
# Toda la logica comun de diseno vive aqui.
# show_info, show_error, etc. son solo wrappers que llaman
# a esta clase con distintos parametros.
# ============================================================

class _SprytaDialog(QDialog):
    """
    Ventana de dialogo base con el estilo visual de Spryta.

    No usar directamente. Usar las funciones publicas:
        show_info(), show_warning(), show_error(), ask_yes_no()

    Parametros:
        title     -- titulo de la ventana y del encabezado
        message   -- mensaje principal del cuerpo
        kind      -- "info" | "warning" | "error" | "question"
        parent    -- ventana padre (QWidget) para centrar sobre ella
        dark_mode -- True = modo oscuro (default)
    """

    def __init__(self, title: str, message: str, kind: str,
                 parent=None, dark_mode: bool = True):
        super().__init__(parent)

        self._result   = False   # para ask_yes_no

        # ── Configuracion de la ventana ─────────────────────
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(420)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint   # sin barra de titulo del OS
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # ── Icono de la aplicacion ───────────────────────────
        icon_path = os.path.join("assets", "icons", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # ── Construir la interfaz ────────────────────────────
        self._build_ui(title, message, kind)

        # ── Animacion de entrada (fade in) ───────────────────
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    # ----------------------------------------------------------
    # Construccion de la interfaz interna
    # ----------------------------------------------------------

    def _build_ui(self, title: str, message: str, kind: str):
        """Construye todo el contenido visual del dialogo."""
        c = theme.get_colors()

        # Colores segun tipo
        title_color_map = {
            "info":     theme.ACCENT,
            "warning":  theme.COLOR_WARNING,
            "error":    theme.COLOR_DANGER,
            "question": theme.ACCENT,
        }
        title_color = title_color_map.get(kind, theme.ACCENT)

        # ── Contenedor principal (la "card" con borde redondeado) ─
        # Usamos un QFrame como contenedor visual con bordes redondeados
        # via stylesheet. El QDialog en si es transparente.
        container = QFrame(self)
        container.setObjectName("DialogCard")
        container.setStyleSheet(f"""
            QFrame#DialogCard {{
                background-color: {c["bg"]};
                border: 1px solid {c["border"]};
                border-radius: {theme.RADIUS_LARGE}px;
            }}
        """)

        # Layout principal del QDialog apunta al container
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)

        # Layout interior del container
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            theme.PADDING_LARGE,   # izquierda  24px
            theme.PADDING_LARGE,   # arriba     24px
            theme.PADDING_LARGE,   # derecha    24px
            theme.PADDING_NORMAL,  # abajo      16px
        )
        layout.setSpacing(0)

        # ── Fila superior: icono + titulo ────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(theme.SP2)   # 16px entre icono y texto
        top_row.setContentsMargins(0, 0, 0, 0)

        # Icono
        icon_label = QLabel()
        icon_label.setPixmap(_make_icon_pixmap(kind, size=28))
        icon_label.setFixedSize(28, 28)
        top_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # Titulo
        lbl_title = QLabel(title)
        lbl_title.setFont(theme.FONT_SUBTITLE)
        lbl_title.setStyleSheet(f"color: {title_color}; background: transparent;")
        top_row.addWidget(lbl_title, 1, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(top_row)

        # ── Separador ────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {c['border']}; background: {c['border']};")
        sep.setFixedHeight(1)
        layout.addSpacing(theme.SP2)    # 16px antes del separador
        layout.addWidget(sep)
        layout.addSpacing(theme.SP2)    # 16px despues del separador

        # ── Mensaje ───────────────────────────────────────────
        lbl_msg = QLabel(message)
        lbl_msg.setFont(theme.FONT_NORMAL)
        lbl_msg.setStyleSheet(f"color: {c['fg_dim']}; background: transparent;")
        lbl_msg.setWordWrap(True)
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(lbl_msg)
        layout.addSpacing(theme.SP3)    # 24px antes de los botones

        # ── Fila de botones ───────────────────────────────────
        # Se guarda como atributo para que las subclases puedan agregar botones
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(theme.SP1)   # 8px entre botones
        self._btn_row.addStretch()            # empuja botones a la derecha
        layout.addLayout(self._btn_row)

    # ----------------------------------------------------------
    # Helper para crear botones uniformes
    # ----------------------------------------------------------

    def _make_button(self, text: str, role: str = "default") -> QPushButton:
        """
        Crea un QPushButton con el estilo del dialogo.

        Parametros:
            text -- texto visible del boton
            role -- "primary" (azul solido) | "default" (outline)

        Ejemplo:
            btn_ok = self._make_button("OK", role="primary")
            self._btn_row.addWidget(btn_ok)
        """
        btn = QPushButton(text)
        btn.setFont(theme.FONT_SMALL)
        btn.setMinimumWidth(88)
        btn.setFixedHeight(34)
        theme.set_role(btn, role)
        return btn

    # ----------------------------------------------------------
    # Centrado sobre el padre
    # ----------------------------------------------------------

    def _center_on_parent(self):
        """Centra el dialogo sobre la ventana padre o la pantalla."""
        self.adjustSize()
        if self.parent() and self.parent().isVisible():
            p      = self.parent()
            center = p.frameGeometry().center()
            geo    = self.frameGeometry()
            geo.moveCenter(center)
            self.move(geo.topLeft())
        else:
            screen_geo = QApplication.primaryScreen().availableGeometry()
            geo        = self.frameGeometry()
            geo.moveCenter(screen_geo.center())
            self.move(geo.topLeft())

    # ----------------------------------------------------------
    # Abrir (mostrar y esperar resultado)
    # ----------------------------------------------------------

    def open_dialog(self) -> bool:
        """
        Muestra el dialogo y bloquea hasta que se cierra.
        Devuelve True si el usuario hizo clic en Yes/OK,
        False si hizo clic en No/Cancel.
        """
        self._center_on_parent()
        self.exec()
        return self._result


# ============================================================
# SECCION 3: SUBCLASES ESPECIALIZADAS
# Cada tipo de dialogo agrega sus propios botones.
# ============================================================

class _AlertDialog(_SprytaDialog):

    def __init__(self, title, message, kind, parent=None):
        super().__init__(title, message, kind, parent)

        btn_ok = self._make_button("OK", role="primary")
        btn_ok.clicked.connect(self._on_ok)
        self._btn_row.addWidget(btn_ok)
        btn_ok.setFocus()

    def _on_ok(self):
        self._result = True
        self.accept()


class _YesNoDialog(_SprytaDialog):

    def __init__(self, title, message, parent=None):
        super().__init__(title, message, "question", parent)

        btn_no  = self._make_button("No",  role="default")
        btn_yes = self._make_button("Yes", role="primary")

        btn_no.clicked.connect(self._on_no)
        btn_yes.clicked.connect(self._on_yes)

        self._btn_row.addWidget(btn_no)
        self._btn_row.addWidget(btn_yes)
        btn_yes.setFocus()

    def _on_no(self):
        self._result = False
        self.reject()

    def _on_yes(self):
        self._result = True
        self.accept()


class _AskStringDialog(_SprytaDialog):
    """
    Dialogo con campo de texto. Usado por ask_string.
    Agrega un QLineEdit entre el mensaje y los botones.
    """

    def __init__(self, title, prompt, parent=None, initial: str = ""):
        # Llamamos al padre con kind="info" y el prompt como mensaje
        super().__init__(title, prompt, "info", parent)

        self._string_result = None

        c = theme.get_colors()

        # ── Agregar el QLineEdit encima de los botones ────────
        # Buscamos el layout del container para insertar antes de los botones.
        # El container es el primer widget del layout del QDialog.
        container     = self.layout().itemAt(0).widget()
        inner_layout  = container.layout()

        # Insertamos la entrada antes de la fila de botones (ultimo elemento)
        self._entry = QLineEdit(initial)
        self._entry.setFont(theme.FONT_NORMAL)
        self._entry.setPlaceholderText("Escribe aqui...")
        self._entry.setFixedHeight(36)
        self._entry.returnPressed.connect(self._on_ok)

        # Posicion: antes del ultimo item (que es _btn_row)
        insert_pos = inner_layout.count() - 1
        inner_layout.insertWidget(insert_pos, self._entry)
        inner_layout.insertSpacing(insert_pos + 1, theme.SP1)

        self._entry.setFocus()

        # ── Botones Cancel / OK ───────────────────────────────
        btn_cancel = self._make_button("Cancel", role="default")
        btn_ok     = self._make_button("OK",     role="primary")

        btn_cancel.clicked.connect(self._on_cancel)
        btn_ok.clicked.connect(self._on_ok)

        self._btn_row.addWidget(btn_cancel)
        self._btn_row.addWidget(btn_ok)

    def _on_cancel(self):
        self._string_result = None
        self.reject()

    def _on_ok(self):
        val = self._entry.text().strip()
        self._string_result = val if val else None
        self.accept()

    def get_string(self) -> "str | None":
        """Abre el dialogo y devuelve el texto o None si cancelo."""
        self._center_on_parent()
        self.exec()
        return self._string_result


# ============================================================
# SECCION 4: API PUBLICA
# Estas son las funciones que el resto del proyecto llama.
# Nombres y firmas IDENTICOS al dialog.py anterior de tkinter.
# ============================================================

def show_info(title: str, message: str, parent=None) -> None:
    """
    Muestra un dialogo de informacion con boton OK.
    Reemplaza: messagebox.showinfo()

    Parametros:
        title   -- titulo del dialogo
        message -- texto del cuerpo
        parent  -- QWidget padre (opcional, para centrar)

    Ejemplo:
        show_info("Listo", "El sprite fue guardado correctamente.")
    """
    dlg = _AlertDialog(title, message, "info", parent)
    dlg.open_dialog()


def show_warning(title: str, message: str, parent=None) -> None:
    """
    Muestra un dialogo de advertencia con boton OK.
    Reemplaza: messagebox.showwarning()

    Parametros:
        title   -- titulo del dialogo
        message -- texto del cuerpo
        parent  -- QWidget padre (opcional)

    Ejemplo:
        show_warning("Atencion", "Selecciona un sprite primero.")
    """
    dlg = _AlertDialog(title, message, "warning", parent)
    dlg.open_dialog()


def show_error(title: str, message: str, parent=None) -> None:
    """
    Muestra un dialogo de error con boton OK.
    Reemplaza: messagebox.showerror()

    Parametros:
        title   -- titulo del dialogo
        message -- texto del cuerpo
        parent  -- QWidget padre (opcional)

    Ejemplo:
        show_error("Error", "No se encontro el archivo config.ini.")
    """
    dlg = _AlertDialog(title, message, "error", parent)
    dlg.open_dialog()


def ask_yes_no(title: str, message: str, parent=None) -> bool:
    """
    Muestra un dialogo de confirmacion con botones No / Yes.
    Reemplaza: messagebox.askyesno()

    Parametros:
        title   -- titulo del dialogo
        message -- pregunta a mostrar
        parent  -- QWidget padre (opcional)

    Devuelve:
        True  si el usuario hizo clic en "Yes"
        False si el usuario hizo clic en "No" o cerro la ventana

    Ejemplo:
        if ask_yes_no("Confirmar", "Deseas eliminar este sprite?"):
            eliminar_sprite()
    """
    dlg = _YesNoDialog(title, message, parent)
    return dlg.open_dialog()


def ask_string(title: str, prompt: str,
               parent=None, initial: str = "") -> "str | None":
    """
    Muestra un dialogo con campo de texto para ingresar un valor.
    Reemplaza: simpledialog.askstring()

    Parametros:
        title   -- titulo del dialogo
        prompt  -- instruccion o pregunta para el usuario
        parent  -- QWidget padre (opcional)
        initial -- texto inicial del campo (default: vacio)

    Devuelve:
        El string ingresado (sin espacios al inicio/fin)
        None si el usuario hizo clic en "Cancel" o cerro la ventana

    Ejemplo:
        nombre = ask_string("Nueva Escena", "Nombre de la escena:")
        if nombre:
            crear_escena(nombre)
    """
    dlg = _AskStringDialog(title, prompt, parent, initial)
    return dlg.get_string()
