# -*- coding: utf-8 -*-
"""
lasso_manager.py  —  Motor de lassos Cancion-Sprite para Spryta

Responsabilidades:
    1. Gestionar playlists con canciones y vinculos cancion->sprite (muchos a muchos)
    2. Guardar y cargar datos persistentes en data/lassos.json
    3. Lanzar sprites vinculados cuando una cancion empieza a sonar
    4. Detener, ocultar o congelar sprites cuando la cancion para o se pausa
    5. Gestionar posiciones independientes por playlist y sprite

Sin dependencias de UI (sin PySide6, sin tkinter).
Se conecta con ambient_audio.py y panels.py mediante callbacks.

Ubicacion en el proyecto:
    Guardar este archivo en la carpeta  tools/  junto a ambient_audio.py

Estructura de data/lassos.json:
{
  "playlists": {
    "Genshin Impact": {
      "songs":    ["Rain.mp3", "Wind.mp3"],
      "bindings": {
        "Rain.mp3": ["Paimon", "Lumine"],
        "Wind.mp3": ["Venti"]
      },
      "positions": {
        "Paimon":  {"x": 100, "y": 200},
        "Lumine":  {"x": 400, "y": 300}
      }
    }
  },
  "pause_behavior": "hide"
}

Estado de sesion en memoria (NO se guarda entre sesiones):
    _lasso_pids     : {"sprite_name": pid, ...}
    _current_playlist: nombre de la playlist activa o None
    _current_song    : nombre del archivo de audio actual o None
    _is_paused       : True si el audio esta actualmente pausado

Comunicacion con main.pyw (fase 2 — modificacion de main.pyw):
    Posiciones    : data/lasso_positions.ini  — secciones "playlist::sprite"
    Comandos hide/show/freeze/unfreeze: data/lasso_cmd_{pid}.flag
"""

import os
import sys
import json
import time
import subprocess
import configparser

import psutil


# ================================================================
# Rutas base
# ================================================================

# setting.pyw ejecuta os.chdir() a la raiz del proyecto antes de importar
# cualquier modulo. Todas las rutas son relativas al cwd, igual que en
# process_manager.py, ambient_audio.py y el resto del proyecto.
_USER_DOCS     = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Spryta")
DATA_DIR       = os.path.join(_USER_DOCS, "data")
SPRITES_DIR    = os.path.join(_USER_DOCS, "sprites")
LASSOS_FILE    = os.path.join(DATA_DIR, "lassos.json")
LASSO_POS_FILE = os.path.join(DATA_DIR, "lasso_positions.ini")
# Debe coincidir con REGISTRY_FILE en main.pyw: ahi se registran sprites listos.
REGISTRY_FILE  = os.path.join(DATA_DIR, "sprites_running.txt")

# ================================================================
# Constantes publicas
# ================================================================

PAUSE_HIDE   = "hide"    # Ocultar sprite al pausar la cancion
PAUSE_FREEZE = "freeze"  # Congelar animacion al pausar la cancion


# ================================================================
# LassoManager
# ================================================================

class LassoManager:
    """
    Motor puro de vinculos cancion-sprite.

    No tiene logica de interfaz grafica.
    Todos sus metodos publicos son llamados desde panels.py,
    link_window.py y los callbacks de ambient_audio.py.
    """

    def __init__(self):
        # ── Datos persistidos en lassos.json ───────────────────
        self._playlists: dict     = {}
        self._pause_behavior: str = PAUSE_HIDE

        # ── Estado de sesion (solo en memoria) ────────────────
        self._lasso_pids: dict      = {}    # {sprite_name: pid}
        self._current_playlist: str  = None
        self._current_song: str      = None
        self._is_paused: bool        = False

        # ── Callback opcional para notificar a la UI ──────────
        # Se conecta desde setting.pyw para abrir el panel Running
        # automaticamente cuando se lanza un sprite desde lasso.
        # Firma esperada: on_lasso_launched(expected_count: int)
        self.on_lasso_launched = None

        # Cargar datos del disco al iniciar
        self._load()

    # ----------------------------------------------------------
    # SECCION 1 — Persistencia
    # ----------------------------------------------------------

    def _load(self) -> None:
        """
        Carga lassos.json desde disco.
        Si el archivo no existe comienza con datos vacios sin error.
        """
        if not os.path.exists(LASSOS_FILE):
            return
        try:
            with open(LASSOS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._playlists      = data.get("playlists", {})
            self._pause_behavior = data.get("pause_behavior", PAUSE_HIDE)
        except Exception as e:
            print(f"[LassoManager] Error cargando lassos.json: {e}")

    def save(self) -> None:
        """
        Guarda el estado completo en data/lassos.json.
        Crea el directorio data/ si no existe.
        """
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = {
                "playlists":      self._playlists,
                "pause_behavior": self._pause_behavior,
            }
            with open(LASSOS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[LassoManager] Error guardando lassos.json: {e}")

    # ----------------------------------------------------------
    # SECCION 2 — Gestion de playlists
    # ----------------------------------------------------------

    def get_playlist_names(self) -> list:
        """Devuelve la lista de nombres de playlists creadas por el usuario."""
        return list(self._playlists.keys())

    def create_playlist(self, name: str) -> bool:
        """
        Crea una playlist nueva vacia.

        Devuelve False si el nombre ya existe (sin modificar nada).
        Devuelve True si fue creada exitosamente.
        """
        if not name or name in self._playlists:
            return False
        self._playlists[name] = {
            "songs":     [],
            "bindings":  {},
            "positions": {},
        }
        self.save()
        return True

    def delete_playlist(self, name: str) -> bool:
        """
        Elimina una playlist con todas sus canciones, vinculos y posiciones.

        Devuelve False si el nombre no existe.
        """
        if name not in self._playlists:
            return False
        del self._playlists[name]
        self.save()
        return True

    def rename_playlist(self, old_name: str, new_name: str) -> bool:
        """
        Renombra una playlist.

        Devuelve False si old_name no existe o si new_name ya esta en uso.
        """
        if not new_name:
            return False
        if old_name not in self._playlists:
            return False
        if new_name in self._playlists:
            return False
        self._playlists[new_name] = self._playlists.pop(old_name)
        self.save()
        return True

    def get_playlist(self, name: str) -> dict:
        """
        Devuelve el dict interno de una playlist o None si no existe.

        El dict tiene claves: songs, bindings, positions.
        No modificar directamente — usar los metodos de la API.
        """
        return self._playlists.get(name)

    # ----------------------------------------------------------
    # SECCION 3 — Canciones dentro de una playlist
    # ----------------------------------------------------------

    def get_songs(self, playlist_name: str) -> list:
        """
        Devuelve la lista de canciones de una playlist.
        Devuelve lista vacia si la playlist no existe.
        """
        pl = self._playlists.get(playlist_name)
        if pl is None:
            return []
        return list(pl["songs"])

    def set_songs(self, playlist_name: str, songs: list) -> None:
        """
        Reemplaza la lista completa de canciones de una playlist.
        Elimina los vinculos de las canciones que ya no estan en la lista.
        """
        pl = self._ensure_playlist(playlist_name)
        # Calcular canciones eliminadas para limpiar sus vinculos
        removed = set(pl["songs"]) - set(songs)
        for song in removed:
            pl["bindings"].pop(song, None)
        pl["songs"] = list(songs)
        self.save()

    def add_song(self, playlist_name: str, song: str) -> bool:
        """
        Agrega una cancion a una playlist si no estaba ya.

        Devuelve True si fue agregada, False si ya existia.
        """
        pl = self._ensure_playlist(playlist_name)
        if song in pl["songs"]:
            return False
        pl["songs"].append(song)
        self.save()
        return True

    def remove_song(self, playlist_name: str, song: str) -> bool:
        """
        Elimina una cancion y todos sus vinculos de una playlist.

        Devuelve True si fue eliminada, False si no existia.
        """
        pl = self._playlists.get(playlist_name)
        if pl is None or song not in pl["songs"]:
            return False
        pl["songs"].remove(song)
        pl["bindings"].pop(song, None)
        self.save()
        return True

    # ----------------------------------------------------------
    # SECCION 4 — Vinculos cancion <-> sprite (muchos a muchos)
    # ----------------------------------------------------------

    def add_binding(self, playlist_name: str,
                    song: str, sprite: str) -> bool:
        """
        Vincula un sprite a una cancion dentro de una playlist.

        Relacion muchos a muchos:
          - Una cancion puede tener multiples sprites vinculados.
          - Un sprite puede estar vinculado a multiples canciones.

        Devuelve False si el vinculo ya existia (sin duplicar).
        """
        pl       = self._ensure_playlist(playlist_name)
        bindings = pl["bindings"].setdefault(song, [])
        if sprite in bindings:
            return False
        bindings.append(sprite)
        self.save()
        return True

    def remove_binding(self, playlist_name: str,
                       song: str, sprite: str) -> bool:
        """
        Elimina el vinculo entre una cancion y un sprite.

        Devuelve True si fue eliminado, False si no existia.
        """
        pl = self._playlists.get(playlist_name)
        if pl is None:
            return False
        bindings = pl["bindings"].get(song, [])
        if sprite not in bindings:
            return False
        bindings.remove(sprite)
        # Si la cancion queda sin vinculos, limpiar la entrada
        if not bindings:
            del pl["bindings"][song]
        self.save()
        return True

    def get_bindings(self, playlist_name: str, song: str) -> list:
        """
        Devuelve la lista de sprites vinculados a una cancion.
        Devuelve lista vacia si no hay vinculos o si la playlist no existe.
        """
        pl = self._playlists.get(playlist_name)
        if pl is None:
            return []
        return list(pl["bindings"].get(song, []))

    def get_all_bindings(self, playlist_name: str) -> dict:
        """
        Devuelve el dict completo de vinculos de una playlist.
        Formato: {"cancion.mp3": ["SpriteA", "SpriteB"], ...}
        """
        pl = self._playlists.get(playlist_name)
        if pl is None:
            return {}
        return dict(pl["bindings"])

    def has_any_binding(self, playlist_name: str) -> bool:
        """
        Devuelve True si la playlist tiene al menos un vinculo definido.
        Util para saber si vale la pena activar la logica de vinculos.
        """
        pl = self._playlists.get(playlist_name)
        if pl is None:
            return False
        return any(sprites for sprites in pl["bindings"].values())

    # ----------------------------------------------------------
    # SECCION 5 — Posiciones de sprites por playlist
    # ----------------------------------------------------------

    def set_sprite_position(self, playlist_name: str,
                             sprite: str, x: int, y: int) -> None:
        """
        Guarda la posicion (x, y) de un sprite dentro de una playlist.

        Se llama automaticamente cuando el usuario suelta el sprite
        despues de arrastrarlo en pantalla. Los cambios se persisten
        inmediatamente en lassos.json y en lasso_positions.ini.
        """
        pl = self._ensure_playlist(playlist_name)
        pl["positions"][sprite] = {"x": int(x), "y": int(y)}
        # Persistir en lassos.json
        self.save()
        # Tambien actualizar lasso_positions.ini para que main.pyw lo lea
        self._write_lasso_position(playlist_name, sprite, x, y)

    def get_sprite_position(self, playlist_name: str,
                             sprite: str) -> tuple:
        """
        Devuelve (x, y) guardada para un sprite en una playlist.
        Devuelve (100, 100) si no habia posicion previa.
        """
        pl = self._playlists.get(playlist_name)
        if pl is None:
            return (100, 100)
        pos = pl["positions"].get(sprite, {})
        return (pos.get("x", 100), pos.get("y", 100))

    # ----------------------------------------------------------
    # SECCION 6 — Configuracion global
    # ----------------------------------------------------------

    def get_pause_behavior(self) -> str:
        """
        Devuelve el comportamiento al pausar una cancion.
        Valores posibles: 'hide' o 'freeze'.
        """
        return self._pause_behavior

    def set_pause_behavior(self, behavior: str) -> None:
        """
        Establece que le ocurre al sprite cuando la cancion se pausa.

        Parametros:
            behavior -- 'hide'   : ocultar el sprite (como CTRL+ALT+S)
                        'freeze' : congelar la animacion, sprite sigue visible
        """
        if behavior not in (PAUSE_HIDE, PAUSE_FREEZE):
            return
        self._pause_behavior = behavior
        self.save()

    # ----------------------------------------------------------
    # SECCION 7 — Eventos de reproduccion de audio
    # ----------------------------------------------------------

    def on_song_play(self, playlist_name: str, song: str, notify_ui: bool = True) -> None:
        """
        Llamado por panels.py cuando una cancion empieza a reproducirse.

        Flujo:
          1. Si habia sprites de una cancion anterior, los detiene.
          2. Actualiza el estado de sesion.
          3. Lanza todos los sprites vinculados a la nueva cancion.

        Si la cancion no tiene vinculos, no hace nada con sprites.
        La cancion suena igual sin importar si tiene vinculos o no.

        Parametros:
            playlist_name -- nombre de la playlist activa en LassoManager
            song          -- nombre del archivo de audio (ej: "Rain.mp3")
        """
        # Detener sprites anteriores si la cancion o playlist cambiaron
        cambio_de_cancion = (
            song != self._current_song
            or playlist_name != self._current_playlist
        )
        if cambio_de_cancion:
            # Sincronizar posiciones ANTES de matar los sprites
            # para no perder donde estaban si el timer de 2s no disparo aun
            if self._current_playlist:
                for sprite_name in list(self._lasso_pids.keys()):
                    self.sync_position_from_sprite(self._current_playlist, sprite_name)
            self._stop_all_lasso_sprites()

        self._current_playlist = playlist_name
        self._current_song     = song
        self._is_paused        = False

        sprites = self.get_bindings(playlist_name, song)
        sync_group = f"lasso_{int(time.time() * 1000)}"
        sync_expected = max(1, len(sprites))
        for sprite_name in sprites:
            self._launch_lasso_sprite(
                sprite_name,
                playlist_name,
                sync_group=sync_group,
                sync_expected=sync_expected,
            )

        # Notificar a la UI para que abra el panel Running automaticamente,
        # igual que cuando se lanza un solo, una escena o un reel.
        if notify_ui and sprites and callable(self.on_lasso_launched):
            self.on_lasso_launched(len(sprites), playlist_name, song)

        # Esperar a que los sprites aparezcan en el registro (ya cargados)
        # antes de permitir que arranque el audio.
        if sprites:
            self._wait_until_lasso_sprites_ready(playlist_name, song, sprites, timeout_s=8.0)

    def on_song_pause(self) -> None:
        """
        Llamado por panels.py cuando la cancion se pausa.

        Segun la configuracion global (pause_behavior):
          - 'hide'   : oculta los sprites vinculados activos
          - 'freeze' : congela la animacion de los sprites vinculados activos
        """
        if self._is_paused:
            return   # Ya estaba pausado, evitar doble comando
        self._is_paused = True

        if self._pause_behavior == PAUSE_HIDE:
            for sprite_name in list(self._lasso_pids.keys()):
                self._hide_lasso_sprite(sprite_name)
        else:
            for sprite_name in list(self._lasso_pids.keys()):
                self._freeze_lasso_sprite(sprite_name)

    def on_song_resume(self) -> None:
        """
        Llamado por panels.py cuando la cancion se reanuda tras una pausa.

        Restaura los sprites al estado que tenian antes de la pausa.
        Si habian sido ocultados, los muestra.
        Si habian sido congelados, los descongela.
        """
        if not self._is_paused:
            return   # No estaba pausado, no hay nada que restaurar
        self._is_paused = False

        if self._pause_behavior == PAUSE_HIDE:
            for sprite_name in list(self._lasso_pids.keys()):
                self._show_lasso_sprite(sprite_name)
        else:
            for sprite_name in list(self._lasso_pids.keys()):
                self._unfreeze_lasso_sprite(sprite_name)

    def on_song_stop(self) -> None:
        """
        Llamado por panels.py cuando la cancion se detiene (Stop).

        Termina completamente todos los procesos de sprites vinculados.
        Al hacer Resume despues de un Stop, los sprites se lanzaran
        desde cero con on_song_play.
        """
        # Sincronizar posiciones ANTES de matar los procesos.
        # main.pyw ya escribio la posicion final en lasso_positions.ini
        # cuando el usuario soltó el sprite. Aqui la capturamos a lassos.json
        # mientras _lasso_pids todavia tiene los PIDs activos.
        if self._current_playlist:
            for sprite_name in list(self._lasso_pids.keys()):
                self.sync_position_from_sprite(self._current_playlist, sprite_name)

        self._stop_all_lasso_sprites()
        self._current_song     = None
        self._current_playlist = None
        self._is_paused        = False

    # ----------------------------------------------------------
    # SECCION 8 — Lanzamiento y control de procesos de sprites
    # ----------------------------------------------------------

    def _get_executable(self) -> tuple:
        """
        Devuelve (ruta_ejecutable_absoluta, usar_pythonw).
        Usa ruta absoluta derivada de sys.executable para garantizar que
        funciona sin importar el cwd del proceso en el momento de la llamada.
        """
        base = os.path.dirname(os.path.abspath(sys.executable))
        # En entornos de desarrollo sys.executable apunta al interprete Python
        # dentro de un venv — necesitamos la raiz del proyecto, que es donde
        # vive main.pyw. La raiz la obtenemos del cwd guardado al arrancar.
        # setting.pyw hace os.chdir(BASE_DIR) antes de importar este modulo,
        # por lo que os.getcwd() devuelve la raiz del proyecto.
        project_root = os.getcwd()
        runtime_exe = os.path.join(project_root, "main_runtime", "main.exe")
        exe_path = os.path.join(project_root, "main.exe")
        pyw_path = os.path.join(project_root, "main.pyw")
        if os.path.exists(runtime_exe):
            return runtime_exe, False
        if os.path.exists(exe_path):
            return exe_path, False
        if os.path.exists(pyw_path):
            return pyw_path, True
        return None, False

    def _get_pythonw(self) -> str:
        """Devuelve la ruta de pythonw.exe del Python activo."""
        return os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

    def _launch_lasso_sprite(self, sprite_name: str,
                               playlist_name: str, sync_group: str = None, sync_expected: int = 1) -> None:
        """
        Lanza un sprite como instancia vinculada a musica.

        Diferencias con un sprite lanzado manualmente:
          - Recibe el argumento --lasso <playlist_name> para que main.pyw
            sepa que debe leer su posicion desde lasso_positions.ini
            en lugar de positions.ini.
          - Su PID se registra en _lasso_pids para poder controlarlo
            de forma independiente (ocultar, congelar, detener).
          - Su posicion inicial se escribe en lasso_positions.ini antes
            del lanzamiento para que main.pyw la encuentre inmediatamente.

        Nota: main.pyw requiere modificaciones (fase 2) para leer
        --lasso y lasso_positions.ini. Ver comentarios en Seccion 9.
        """
        # Verificar que la carpeta del sprite existe en disco
        sprite_path = os.path.join(SPRITES_DIR, sprite_name)
        if not os.path.exists(sprite_path):
            print(f"[LassoManager] Sprite no encontrado en disco: {sprite_name}")
            return

        # Si ya hay una instancia vinculada de este sprite corriendo, no duplicar
        if self.is_sprite_running(sprite_name):
            print(f"[LassoManager] Sprite '{sprite_name}' ya esta corriendo vinculado")
            return

        executable, use_pythonw = self._get_executable()
        if executable is None:
            print(f"[LassoManager] ERROR: No se encontro ejecutable. cwd={os.getcwd()}")
            return

        # Escribir posicion en lasso_positions.ini ANTES de lanzar
        x, y = self.get_sprite_position(playlist_name, sprite_name)
        self._write_lasso_position(playlist_name, sprite_name, x, y)

        # Incluir el nombre de la cancion activa para que main.pyw
        # lo guarde en el registro y el panel Running lo pueda mostrar.
        song_arg = self._current_song or ""
        args = [sprite_name, "--lasso", playlist_name, "--lasso-song", song_arg]
        if sync_group:
            args += ["--sync-group", str(sync_group), "--sync-expected", str(max(1, int(sync_expected or 1)))]

        try:
            if use_pythonw:
                pythonw = self._get_pythonw()
                print(f"[LassoManager] Lanzando: {pythonw} {executable} {args}")
                proc = subprocess.Popen([pythonw, executable] + args)
            else:
                print(f"[LassoManager] Lanzando: {executable} {args}")
                proc = subprocess.Popen([executable] + args)

            self._lasso_pids[sprite_name] = proc.pid
            print(f"[LassoManager] OK PID={proc.pid} sprite='{sprite_name}' playlist='{playlist_name}'")
            # Sincronizar posicion desde el archivo en caso de que haya
            # una posicion mas reciente en lasso_positions.ini que en lassos.json
            self.sync_position_from_sprite(playlist_name, sprite_name)
        except Exception as e:
            print(f"[LassoManager] ERROR lanzando '{sprite_name}': {e}")

    def _stop_all_lasso_sprites(self) -> None:
        """Termina todos los procesos de sprites vinculados activos."""
        for sprite_name in list(self._lasso_pids.keys()):
            self._stop_lasso_sprite(sprite_name)

    def _stop_lasso_sprite(self, sprite_name: str) -> None:
        """
        Termina el proceso de un sprite vinculado especifico.
        Si el proceso ya no existe, lo elimina silenciosamente del registro.
        """
        pid = self._lasso_pids.pop(sprite_name, None)
        if pid is None:
            return
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except psutil.TimeoutExpired:
                proc.kill()   # Forzar cierre si no responde en 2 segundos
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass   # El proceso ya termino por su cuenta

    def _hide_lasso_sprite(self, sprite_name: str) -> None:
        """
        Oculta un sprite vinculado activo.

        Escribe el comando "hide" en data/lasso_cmd_{pid}.flag.
        main.pyw lee este archivo periodicamente en su main_loop
        (requiere modificacion de main.pyw — fase 2).
        """
        pid = self._lasso_pids.get(sprite_name)
        if pid is None:
            return
        self._write_sprite_command(pid, "hide")

    def _show_lasso_sprite(self, sprite_name: str) -> None:
        """
        Muestra un sprite vinculado que estaba oculto.
        Escribe el comando "show" en data/lasso_cmd_{pid}.flag.
        """
        pid = self._lasso_pids.get(sprite_name)
        if pid is None:
            return
        self._write_sprite_command(pid, "show")

    def _freeze_lasso_sprite(self, sprite_name: str) -> None:
        """
        Congela la animacion de un sprite vinculado.
        El sprite permanece visible pero su animacion se detiene.
        Escribe el comando "freeze" en data/lasso_cmd_{pid}.flag.
        """
        pid = self._lasso_pids.get(sprite_name)
        if pid is None:
            return
        self._write_sprite_command(pid, "freeze")

    def _unfreeze_lasso_sprite(self, sprite_name: str) -> None:
        """
        Descongela la animacion de un sprite vinculado.
        Escribe el comando "unfreeze" en data/lasso_cmd_{pid}.flag.
        """
        pid = self._lasso_pids.get(sprite_name)
        if pid is None:
            return
        self._write_sprite_command(pid, "unfreeze")

    # ----------------------------------------------------------
    # SECCION 9 — Archivos de control por proceso
    # ----------------------------------------------------------

    def _write_sprite_command(self, pid: int, command: str) -> None:
        """
        Escribe un comando de control en data/lasso_cmd_{pid}.flag.

        main.pyw (modificado en fase 2) lee este archivo periodicamente
        en su main_loop, igual que lee TOGGLE_FLAG para hide/show global.

        Formato del archivo:
            "comando:timestamp_float"
            Ejemplo: "hide:1720000000.123"

        El timestamp evita que el mismo comando se ejecute dos veces
        si main.pyw lee el archivo mas de una vez antes de que cambie.

        Comandos validos:
            "hide"     — ocultar ventana del sprite
            "show"     — mostrar ventana del sprite
            "freeze"   — pausar animacion (visible pero congelado)
            "unfreeze" — reanudar animacion

        Parametros:
            pid     -- ID del proceso del sprite vinculado
            command -- uno de los comandos validos listados arriba
        """
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            flag_path = os.path.join(DATA_DIR, f"lasso_cmd_{pid}.flag")
            with open(flag_path, "w", encoding="utf-8") as f:
                f.write(f"{command}:{time.time()}")
        except Exception as e:
            print(f"[LassoManager] Error escribiendo comando '{command}' para PID {pid}: {e}")

    def _write_lasso_position(self, playlist_name: str,
                              sprite_name: str,
                              x: int, y: int) -> None:
        """
        Escribe la posicion de un sprite vinculado en data/lasso_positions.ini.

        main.pyw (modificado en fase 2) lee este archivo al lanzarse
        con el argumento --lasso para saber donde posicionarse.
        La misma logica de save_current_position en main.pyw escribira
        de vuelta a este archivo al soltar el sprite tras arrastrarlo.

        Formato de seccion: "playlist_name::sprite_name"
        El separador "::" evita colisiones con nombres que contengan
        caracteres comunes.

        Parametros:
            playlist_name -- nombre de la playlist activa
            sprite_name   -- nombre de la carpeta del sprite
            x, y          -- coordenadas en pixeles desde la esquina superior izquierda
        """
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            pos_cfg = configparser.ConfigParser()
            if os.path.exists(LASSO_POS_FILE):
                pos_cfg.read(LASSO_POS_FILE, encoding="utf-8")
            section = f"{playlist_name}::{sprite_name}"
            if not pos_cfg.has_section(section):
                pos_cfg.add_section(section)
            pos_cfg.set(section, "x", str(int(x)))
            pos_cfg.set(section, "y", str(int(y)))
            with open(LASSO_POS_FILE, "w", encoding="utf-8") as f:
                pos_cfg.write(f)
        except Exception as e:
            print(f"[LassoManager] Error escribiendo posicion vinculada: {e}")

    # ----------------------------------------------------------
    # SECCION 10 — Sincronizacion de posiciones desde main.pyw
    # ----------------------------------------------------------

    def sync_position_from_sprite(self, playlist_name: str,
                                   sprite_name: str) -> None:
        """
        Lee la posicion actualizada de lasso_positions.ini y la sincroniza
        en lassos.json.

        Llamado periodicamente desde panels.py para capturar el arrastre
        del usuario. main.pyw (modificado en fase 2) escribe en
        lasso_positions.ini cada vez que el usuario suelta el sprite.

        Parametros:
            playlist_name -- nombre de la playlist del sprite vinculado
            sprite_name   -- nombre del sprite cuya posicion se sincroniza
        """
        try:
            if not os.path.exists(LASSO_POS_FILE):
                return
            pos_cfg = configparser.ConfigParser()
            pos_cfg.read(LASSO_POS_FILE, encoding="utf-8")
            section = f"{playlist_name}::{sprite_name}"
            if not pos_cfg.has_section(section):
                return
            x = pos_cfg.getint(section, "x", fallback=100)
            y = pos_cfg.getint(section, "y", fallback=100)
            # Solo actualizar si la posicion cambio
            current_x, current_y = self.get_sprite_position(playlist_name, sprite_name)
            if x != current_x or y != current_y:
                self.set_sprite_position(playlist_name, sprite_name, x, y)
        except Exception as e:
            print(f"[LassoManager] Error sincronizando posicion de '{sprite_name}': {e}")

    # ----------------------------------------------------------
    # SECCION 11 — Utilidades publicas
    # ----------------------------------------------------------

    def get_lasso_pids(self) -> dict:
        """
        Devuelve una copia del dict {sprite_name: pid} de sesion.
        Solo para lectura — no modificar directamente.
        """
        return dict(self._lasso_pids)

    def is_sprite_running(self, sprite_name: str) -> bool:
        """
        Devuelve True si el sprite vinculado tiene un proceso activo en memoria.
        Limpia automaticamente el PID del registro si el proceso ya murio.
        """
        pid = self._lasso_pids.get(sprite_name)
        if pid is None:
            return False
        try:
            proc = psutil.Process(pid)
            alive = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not alive:
                self._lasso_pids.pop(sprite_name, None)
            return alive
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._lasso_pids.pop(sprite_name, None)
            return False

    def cleanup_dead_pids(self) -> None:
        """
        Elimina del registro interno los PIDs de procesos que ya no corren.
        Llamar periodicamente desde el hilo de UI (por ejemplo, cada 2 segundos).
        """
        dead = [
            name for name in list(self._lasso_pids.keys())
            if not self.is_sprite_running(name)
        ]
        for name in dead:
            self._lasso_pids.pop(name, None)

    def get_current_state(self) -> dict:
        """
        Devuelve un resumen del estado actual de sesion.
        Util para depuracion y para que la UI refleje el estado en tiempo real.

        Retorna:
            {
              "playlist":    str | None,
              "song":        str | None,
              "is_paused":   bool,
              "linked_pids": {sprite_name: pid, ...}
            }
        """
        return {
            "playlist":    self._current_playlist,
            "song":        self._current_song,
            "is_paused":   self._is_paused,
            "linked_pids": dict(self._lasso_pids),
        }

    # ----------------------------------------------------------
    # SECCION 12 — Metodo auxiliar interno
    # ----------------------------------------------------------

    def _ensure_playlist(self, name: str) -> dict:
        """
        Devuelve el dict interno de una playlist.
        La crea en memoria si no existia (sin guardar al disco todavia).
        El llamador debe invocar save() si quiere persistir el resultado.
        """
        if name not in self._playlists:
            self._playlists[name] = {
                "songs":     [],
                "bindings":  {},
                "positions": {},
            }
        return self._playlists[name]

    def _wait_until_lasso_sprites_ready(
        self,
        playlist_name: str,
        song: str,
        sprites: list,
        timeout_s: float = 8.0
    ) -> None:
        """
        Bloquea brevemente hasta que los sprites de la cancion aparezcan
        en REGISTRY_FILE (registro escrito por main.pyw al terminar carga).
        """
        # Esta ruta debe coincidir con main.pyw para no depender del cwd.
        registry_path = REGISTRY_FILE
        expected = set(sprites or [])
        if not expected:
            return

        start = time.time()
        while time.time() - start < timeout_s:
            try:
                if not os.path.exists(registry_path):
                    time.sleep(0.05)
                    continue
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)

                ready = set()
                for data in registry.values():
                    if not data.get("is_lasso", False):
                        continue
                    if data.get("lasso_playlist") != playlist_name:
                        continue
                    if (data.get("lasso_song") or "") != (song or ""):
                        continue
                    sprite_name = data.get("sprite")
                    if sprite_name:
                        ready.add(sprite_name)

                if expected.issubset(ready):
                    return
            except Exception:
                pass

            time.sleep(0.05)
