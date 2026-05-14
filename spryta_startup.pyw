# -*- coding: utf-8 -*-
"""
spryta_startup.pyw  —  Spryta Startup (PySide6)

Archivo de inicio de Spryta cuando Windows arranca.
Se encarga de TRES cosas:
  1. Mostrar una ventana de notificacion en la esquina inferior derecha.
  2. Leer session.ini y lanzar main.pyw para cada sprite/playlist/escena.
  3. Mostrar el tray unificado (SpryTrayIcon) para que el usuario pueda
     interactuar con Spryta sin necesidad de abrir Settings manualmente.

setting.pyw NO interviene en este flujo.
El usuario abre Settings desde el tray del startup.
Cuando Settings abre, crea su propio tray y el tray del startup se oculta
para evitar que convivan dos iconos en la bandeja del sistema.
"""

import os
import sys
import time
import threading
import configparser
import subprocess

from PySide6.QtCore       import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui        import QPixmap, QPainter, QColor, QBrush
from PySide6.QtWidgets    import (
    QApplication, QWidget,
    QHBoxLayout, QVBoxLayout,
    QLabel, QFrame,
)


# ============================================================
# Rutas base
# ============================================================

def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.basename(exe_dir).lower() == "startup_runtime":
            return os.path.dirname(exe_dir)
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


def resolve_main_executable(base_dir: str):
    runtime_exe = os.path.join(base_dir, "main_runtime", "main.exe")
    root_exe = os.path.join(base_dir, "main.exe")
    root_script = os.path.join(base_dir, "main.pyw")
    if os.path.exists(runtime_exe):
        return runtime_exe, False
    if os.path.exists(root_exe):
        return root_exe, False
    if os.path.exists(root_script):
        return root_script, True
    return None, None

BASE_DIR = get_base_dir()
os.chdir(BASE_DIR)

SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from tools.process_manager import ProcessManager
from ui.tray_icon          import SpryTrayIcon


# ============================================================
# Colores (sin importar theme.py para mantener dependencias minimas)
# ============================================================

BG_SURFACE  = "#16161e"
BORDER_MID  = "#2c2c3c"
ACCENT      = "#358cfe"
TEXT_BRIGHT = "#eaeaf2"
TEXT_NORMAL = "#a0a0bc"


# ============================================================
# Configuracion
# ============================================================

DISPLAY_MS  = 2500    # tiempo que se muestra la notificacion antes del fade
FADE_MS     = 350     # duracion del fade-out en milisegundos
WIDTH       = 300
HEIGHT      = 80
MARGIN      = 18
DELAY_S     = 0.2     # pausa entre sprites al lanzar varios


# ============================================================
# Utilidades
# ============================================================

def get_pythonw() -> str:
    """Devuelve la ruta de pythonw.exe para lanzar scripts sin consola."""
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        import shutil
        found   = shutil.which("pythonw")
        pythonw = found if found else sys.executable.replace(
            "python.exe", "pythonw.exe"
        )
    return pythonw


# ============================================================
# Restaurar sesion
# ============================================================

def restore_session():
    """
    Lee session.ini y lanza main.pyw para cada sprite,
    playlist y escena guardada. Se ejecuta en un hilo separado
    (no-daemon) para que el proceso no muera cuando la ventana
    de notificacion desaparezca.
    """
    from tools.paths import SESSION_FILE as session_path, SCENES_FILE as scenes_path

    if not os.path.exists(session_path):
        return

    session = configparser.ConfigParser()
    session.read(session_path, encoding="utf-8")

    has_something = (
        session.has_section("Sprites")
        or session.has_section("Reels")
        or session.has_section("Scenes")
    )
    if not has_something:
        return

    # Esperar a que el escritorio de Windows este completamente listo
    try:
        import ctypes
        ctypes.windll.user32.WaitForInputIdle(
            ctypes.windll.kernel32.GetCurrentProcess(), 10000
        )
    except Exception:
        pass

    executable, use_pythonw = resolve_main_executable(BASE_DIR)

    if executable is None:
        return

    def launch(args):
        """Lanza el ejecutable de sprites con los argumentos dados."""
        try:
            if use_pythonw:
                subprocess.Popen(
                    [get_pythonw(), executable] + args,
                    cwd=BASE_DIR
                )
            else:
                subprocess.Popen([executable] + args, cwd=BASE_DIR)
            time.sleep(DELAY_S)
        except Exception as e:
            print(f"Error launching: {e}")

    # Sprites individuales
    if session.has_section("Sprites"):
        for sp in [
            s.strip()
            for s in session.get("Sprites", "list", fallback="").split(",")
            if s.strip()
        ]:
            launch([sp])

    # Playlists
    if session.has_section("Reels"):
        for pl in [
            p.strip()
            for p in session.get("Reels", "list", fallback="").split(",")
            if p.strip()
        ]:
            launch(["--playlist", pl])

    # Escenas
    if session.has_section("Scenes"):
        scenes_cfg = configparser.ConfigParser()
        if os.path.exists(scenes_path):
            scenes_cfg.read(scenes_path, encoding="utf-8")
        for sc in [
            s.strip()
            for s in session.get("Scenes", "list", fallback="").split(",")
            if s.strip()
        ]:
            sec = f"Scene_{sc}"
            if scenes_cfg.has_section(sec):
                for sp in [
                    s.strip()
                    for s in scenes_cfg.get(sec, "sprites", fallback="").split(",")
                    if s.strip()
                ]:
                    launch([sp])


# ============================================================
# Stub de audio para el tray
# ============================================================

class _NullAudioManager:
    """
    Implementacion minima de audio para el tray del startup.
    No reproduce nada ni importa pygame.
    Satisface exactamente la interfaz que TrayMenu consume.
    """
    is_playing       = False
    is_paused        = False
    is_playlist_mode = False

    def get_current_filename(self): return None
    def get_volume(self):           return 0.8
    def set_volume(self, v):        pass
    def pause(self):                pass
    def resume(self):               pass
    def stop(self):                 pass
    def prev_track(self):           pass
    def next_track(self):           pass


# ============================================================
# Stub de ventana principal para el tray
# ============================================================

class _StartupMainWindow(QWidget):
    """
    Ventana stub (nunca visible) que satisface la interfaz que
    SpryTrayIcon y TrayMenu esperan de la ventana principal.

    - hide_window / show_window : controlan Settings, no esta ventana.
    - show_window               : lanza setting.pyw y oculta este tray.
    - _finalize_and_exit        : cierra todos los sprites y sale.
    """

    def __init__(self, process_manager: ProcessManager):
        super().__init__()
        self._process_manager = process_manager
        self._tray            = None
        # Este widget nunca se muestra; solo existe para satisfacer la interfaz.
        self.hide()

    def set_tray(self, tray: SpryTrayIcon):
        """Guarda referencia al tray para poder ocultarlo cuando sea necesario."""
        self._tray = tray

    # QWidget ya implementa isVisible() e isMinimized() correctamente.
    # Como el widget esta siempre oculto, ambos devuelven False,
    # lo que hace que el boton del tray diga "Mostrar Settings". Correcto.

    def hide_window(self):
        """Settings no esta abierto desde startup; no hay nada que ocultar."""
        pass

    def show_window(self):
        """
        Lanza setting.pyw y oculta el tray del startup para evitar
        que convivan dos iconos en la bandeja del sistema.
        """
        try:
            exe_path = os.path.join(BASE_DIR, "Spryta.exe")
            pyw_path = os.path.join(BASE_DIR, "setting.pyw")

            if os.path.exists(exe_path):
                subprocess.Popen([exe_path], cwd=BASE_DIR)
            elif os.path.exists(pyw_path):
                subprocess.Popen(
                    [get_pythonw(), pyw_path],
                    cwd=BASE_DIR
                )
        except Exception as e:
            print(f"[StartupMainWindow] Error opening Settings: {e}")

        # Ocultar el tray del startup: Settings creara el suyo propio.
        if self._tray is not None:
            self._tray.hide()
        QApplication.quit()

    def save_session(self):
        """
        Guarda en session.ini los sprites activos en este momento.
        Debe llamarse ANTES de cerrar los sprites.
        """
        try:
            running = self._process_manager.get_running_sprites()
            session = configparser.ConfigParser()
            session["Session"] = {"count": str(len(running))}

            sprites_to_save   = []
            playlists_to_save = []

            for pid, display_name, proc in running:
                if display_name.startswith("Playlist: "):
                    playlists_to_save.append(
                        display_name.replace("Playlist: ", "")
                    )
                else:
                    sprites_to_save.append(display_name)

            if sprites_to_save:
                session["Sprites"]   = {"list": ",".join(sprites_to_save)}
            if playlists_to_save:
                session["Reels"] = {"list": ",".join(playlists_to_save)}

            from tools.paths import SESSION_FILE as session_path, DATA_DIR
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(session_path, "w", encoding="utf-8") as f:
                session.write(f)

        except Exception as e:
            print(f"[StartupMainWindow] Error saving session: {e}")

    def _finalize_and_exit(self):
        """
        Guarda sesion, cierra todos los sprites activos y termina el proceso.
        Se llama cuando el usuario elige 'Salir de Spryta' desde el tray.
        """
        # Primero guardar, despues cerrar. El orden es critico.
        self.save_session()

        try:
            self._process_manager.close_all_sprites()
        except Exception as e:
            print(f"[StartupMainWindow] Error closing sprites: {e}")

        if self._tray is not None:
            self._tray.hide()

        QApplication.quit()


# ============================================================
# Ventana de notificacion
# ============================================================

class StartupNotification(QWidget):
    """
    Ventana sin borde en la esquina inferior derecha de la pantalla.
    Se muestra DISPLAY_MS milisegundos y luego hace un fade-out de FADE_MS ms.
    """

    def __init__(self):
        super().__init__()

        # ── Configuracion de ventana ──────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)

        # Posicionar en la esquina inferior derecha
        screen   = QApplication.primaryScreen().availableGeometry()
        x        = screen.right()  - WIDTH  - MARGIN
        y        = screen.bottom() - HEIGHT - MARGIN
        self.move(x, y)

        # ── Layout ────────────────────────────────────────────
        outer = QFrame(self)
        outer.setGeometry(0, 0, WIDTH, HEIGHT)
        outer.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_MID};
                border-radius: 6px;
            }}
        """)

        lay = QHBoxLayout(outer)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        # ── Icono ─────────────────────────────────────────────
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setStyleSheet("background: transparent; border: none;")

        icon_path = os.path.join(BASE_DIR, "assets", "icons", "icon.png")
        loaded    = False
        if os.path.exists(icon_path):
            try:
                from PIL import Image
                import io
                img = Image.open(icon_path).convert("RGBA").resize(
                    (36, 36), Image.LANCZOS
                )
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                pix = QPixmap()
                pix.loadFromData(buf.read())
                icon_lbl.setPixmap(pix)
                loaded = True
            except Exception:
                pass

        if not loaded:
            pix = QPixmap(36, 36)
            pix.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor(ACCENT)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(2, 2, 32, 32)
            painter.end()
            icon_lbl.setPixmap(pix)

        lay.addWidget(icon_lbl)

        # ── Textos ────────────────────────────────────────────
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        lbl_title = QLabel("Spryta starting...")
        lbl_title.setStyleSheet(
            f"color: {TEXT_BRIGHT}; font-family: 'Segoe UI'; "
            f"font-size: 10pt; font-weight: bold; background: transparent; border: none;"
        )

        lbl_sub = QLabel("Restoring previous session")
        lbl_sub.setStyleSheet(
            f"color: {TEXT_NORMAL}; font-family: 'Segoe UI'; "
            f"font-size: 8pt; background: transparent; border: none;"
        )

        text_col.addWidget(lbl_title)
        text_col.addWidget(lbl_sub)
        lay.addLayout(text_col, 1)

        # ── Animacion de fade-out ─────────────────────────────
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(FADE_MS)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._anim.finished.connect(self.close)

        # Iniciar fade despues de DISPLAY_MS
        QTimer.singleShot(DISPLAY_MS, self._anim.start)

        # Lanzar restauracion de sesion en hilo no-daemon
        threading.Thread(target=restore_session, daemon=False).start()


# ============================================================
# Punto de entrada
# ============================================================

if __name__ == "__main__":
    # Icono correcto en la barra de tareas para el proceso de startup.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u'Spryta.Desktop.Startup.1'
        )
    except Exception:
        pass
    app = QApplication(sys.argv)

    # La app no muere cuando la notificacion se cierra.
    # El tray la mantiene viva hasta que el usuario elija Salir.
    app.setQuitOnLastWindowClosed(False)

    # Notificacion de arranque (lanza restore_session en hilo interno)
    notification = StartupNotification()
    notification.show()

    # Infraestructura del tray unificado
    process_manager = ProcessManager()
    audio_manager   = _NullAudioManager()
    app_window      = _StartupMainWindow(process_manager)

    tray = SpryTrayIcon(app_window, audio_manager, process_manager)
    app_window.set_tray(tray)
    tray.show()

    sys.exit(app.exec())
