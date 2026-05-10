import os
import sys
import threading
import configparser
import random
import ast
import time
import json
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
import pygame
import psutil
import tkinter as tk
from tkinter import messagebox
try:
    import GPUtil
except ImportError:
    GPUtil = None

# Windows
try:
    import win32gui
    import win32con
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    raise RuntimeError("Only works on Windows. Install: pip install pywin32")

# Obtener la carpeta base correctamente tanto en .pyw como en .exe compilado
def get_base_dir():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.basename(exe_dir).lower() == "main_runtime":
            return os.path.dirname(exe_dir)
        return exe_dir
    else:
        return os.path.dirname(os.path.abspath(__file__))

# Cambiar directorio de trabajo a la carpeta del programa
os.chdir(get_base_dir())

_USER_DOCS  = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Spryta")
DATA_DIR    = os.path.join(_USER_DOCS, "data")
SPRITES_DIR = os.path.join(_USER_DOCS, "sprites")

os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE          = os.path.join(DATA_DIR, "config.ini")
POSITIONS_FILE       = os.path.join(DATA_DIR, "positions.ini")
REGISTRY_FILE        = os.path.join(DATA_DIR, "sprites_running.txt")
TOGGLE_FLAG          = os.path.join(DATA_DIR, "toggle_sprites.flag")
SPRITES_STATE_FLAG   = os.path.join(DATA_DIR, "sprites_visible_state.flag")
REEL_FILE            = os.path.join(DATA_DIR, "reel.ini")
REEL_POSITIONS_FILE  = os.path.join(DATA_DIR, "reel_positions.ini")
REEL_CONFIG_FILE     = os.path.join(DATA_DIR, "reel_config.ini")
LASSO_POSITIONS_FILE = os.path.join(DATA_DIR, "lasso_positions.ini")

class SpriteApp:
    def __init__(self, sprite_override=None, playlist_name=None, scene_name=None, lasso_playlist=None, lasso_song=None, sync_group=None, sync_expected=1):
        pygame.init()
        self.scene_name = scene_name
        self.transparent_color = (0, 255, 0)

        # --- Variables de modo Lasso ---
        self.lasso_playlist     = lasso_playlist
        self.lasso_song         = lasso_song
        self.is_lasso_mode      = lasso_playlist is not None
        self.sync_group         = sync_group
        self.sync_expected      = max(1, int(sync_expected or 1))
        self.animation_frozen  = False
        self._last_lasso_cmd_ts = 0.0
        self._last_toggle_ts   = 0.0

        # --- Variables de playlist ---
        self.is_playlist_mode = False
        self.playlist_name = None
        self.playlist_sprites = []
        self.playlist_cycles = 10
        self.current_playlist_index = 0
        self.current_cycle_count = 0

        # --- Configuracion ---
        self.config = configparser.ConfigParser()
        if not os.path.exists(CONFIG_FILE):
            raise FileNotFoundError("Config.ini not found, run setting first")
        self.config.read(CONFIG_FILE, encoding='utf-8')

        # Determinar si es modo playlist o sprite individual
        if playlist_name:
            self.is_playlist_mode = True
            self.playlist_name = playlist_name
            self.load_playlist_config()
            # Empezar con el primer sprite de la playlist
            if self.playlist_sprites:
                self.sprite_name = self.playlist_sprites[0]
            else:
                raise ValueError(f"Playlist '{playlist_name}' is empty")
            pygame.display.set_caption(f"Reel: {playlist_name}")
        elif sprite_override:
            self.sprite_name = sprite_override
            pygame.display.set_caption(self.sprite_name)
        elif self.config.has_section("General"):
            self.sprite_name = self.config.get("General", "active_sprite", fallback="Default")
            pygame.display.set_caption(self.sprite_name)
        else:
            self.sprite_name = self.config.get("General", "sprite_name", fallback="Default")
            pygame.display.set_caption(self.sprite_name)

        # Determinar de donde cargar configuracion
        if self.is_playlist_mode:
            # Intentar cargar config especifica de playlist
            playlist_config = configparser.ConfigParser()
            if os.path.exists(REEL_CONFIG_FILE):
                playlist_config.read(REEL_CONFIG_FILE, encoding='utf-8')
            
            playlist_section = f"Reel_{self.playlist_name}"
            if playlist_config.has_section(playlist_section):
                g = dict(playlist_config.items(playlist_section))
            else:
                # Si no existe config de playlist, usar valores por defecto
                g = {}
        else:
            # Modo sprite normal
            sprite_section = f"Sprite_{self.sprite_name}"
            if self.config.has_section(sprite_section):
                g = dict(self.config.items(sprite_section))
            else:
                g = dict(self.config.items("General")) if self.config.has_section("General") else {}

        self.frame_width = int(g.get("frame_width", "150"))
        self.frame_height = int(g.get("frame_height", "150"))
        self.delay_mode = g.get("delay_mode", "cpu")
        self.fixed_delay = int(g.get("fixed_delay", "30"))
        self.presentacion_delay = int(g.get("presentacion_delay", "2")) * 1000

        cpu_key = g.get("cpu_delays", "[(0,20,200),(21,40,150),(41,60,120),(61,80,90),(81,100,60)]")
        try:
            self.cpu_delays = ast.literal_eval(cpu_key)
        except:
            self.cpu_delays = [(0,20,200),(21,40,150),(41,60,120),(61,80,90),(81,100,60)]

        gpu_key = g.get("gpu_delays", "[]")
        try:
            self.gpu_delays = ast.literal_eval(gpu_key)
        except:
            self.gpu_delays = []

        self.dynamic_mode = g.get("dynamic_mode", "errante").lower()
        
        # --- INTERPRETAR "fps" COMO VELOCIDAD, NO COMO FPS REAL ---
        speed_setting = int(g.get("fps", "60"))
        self.speed_factor = {30: 0.5, 60: 1.0, 90: 1.5, 120: 2.0}.get(speed_setting, 1.0)

        try:
            self.errante_min_speed = max(1, int(g.get("errante_min_speed", "3")))
            self.errante_max_speed = max(self.errante_min_speed + 1, int(g.get("errante_max_speed", "7")))
        except:
            self.errante_min_speed, self.errante_max_speed = 3, 7

        # Cargar posicion
        if self.is_lasso_mode:
            self.load_position_from_lasso_file()
        elif self.is_playlist_mode:
            self.load_position_from_playlist_file()
        else:
            self.load_position_from_file()

        # --- Crear ventana con color clave ---
        self.screen = pygame.display.set_mode((self.frame_width, self.frame_height), pygame.NOFRAME)
        self.screen.fill(self.transparent_color)
        self.frames_lock = threading.Lock()

        # --- Configurar transparencia y ocultar de la barra de tareas en Windows ---
        if WIN32_AVAILABLE:
            hwnd = pygame.display.get_wm_info()['window']

            # Agregar WS_EX_TOOLWINDOW para evitar que aparezca en la barra de tareas
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= win32con.WS_EX_TOOLWINDOW
            ex_style |= win32con.WS_EX_LAYERED
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

            win32gui.SetLayeredWindowAttributes(hwnd,
                win32api.RGB(*self.transparent_color), 0, win32con.LWA_COLORKEY)

            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                self.x, self.y, 0, 0, win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            # Mantener la ventana oculta hasta tener al menos el primer frame listo.
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            
        # --- Cargar frames con manejo de errores mejorado ---
        load_started_at = time.time()
        sprite_path = os.path.join(SPRITES_DIR, self.sprite_name)

        # Verificar si existe la carpeta del sprite activo
        if not os.path.exists(sprite_path):
            # Buscar cualquier sprite disponible como fallback
            available_sprites = [d for d in os.listdir(SPRITES_DIR) 
                                if os.path.isdir(os.path.join(SPRITES_DIR, d))]
            
            if available_sprites:
                # Usar el primer sprite disponible
                self.sprite_name = available_sprites[0]
                sprite_path = os.path.join(SPRITES_DIR, self.sprite_name)
                print(f"Sprite '{self.sprite_name}' no encontrado. Usando '{available_sprites[0]}' como fallback.")
            else:
                # No hay sprites en absoluto â†’ error amigable
                pygame.quit()
                messagebox.showerror(
                    "Error: No sprites found",
                    "No se encontraron sprites en la carpeta 'sprites/'.\n\n"
                    "Por favor ejecuta primero 'setting.pyw' para:\n"
                    "1. Crear una carpeta de sprites\n"
                    "2. Configurar los parametros\n"
                    "3. Guardar la configuracion"
                )
                os._exit(1)

        # Cargar todos los frames antes de mostrar la ventana del sprite
        self.frames = self.load_frames(sprite_path)
        if not self.frames:
            pygame.quit()
            messagebox.showerror(
                "Error: Empty sprite",
                f"No se encontraron archivos PNG en '{sprite_path}'.\n\n"
                "El sprite debe contener al menos un archivo .png"
            )
            os._exit(1)
        
        # Dibujar el primer frame y mostrar la ventana recien cuando ya existe contenido real
        self.screen.fill(self.transparent_color)
        self.screen.blit(self.frames[0], (0, 0))
        pygame.display.flip()

        # Tiempo de gracia global para que la notificacion tenga
        # al menos 2s visibles antes de mostrar el sprite.
        min_grace_s = 2.0
        elapsed = time.time() - load_started_at
        if elapsed < min_grace_s:
            time.sleep(min_grace_s - elapsed)
        self._wait_for_sync_group_ready(timeout_s=10.0)

        if WIN32_AVAILABLE:
            hwnd = pygame.display.get_wm_info()['window']
            win32gui.ShowWindow(hwnd, 5)

        # --- Estado ---
        self.frame_index = 0
        self.running = True
        self.movement_paused = False
        self.dragging = False
        self.drag_offset_x = self.drag_offset_y = 0
        
        # --- Pre-carga del siguiente sprite en playlist ---
        self.preloaded_frames = None
        self.preloaded_sprite_name = None
        self.preload_lock = threading.Lock()

        # --- APLICAR FACTOR DE VELOCIDAD ---
        if self.dynamic_mode == "paseo":
            base_speed = int(g.get("paseo_speed", "6"))
            self.dx = -abs(base_speed) * self.speed_factor
            self.dy = 0
        elif self.dynamic_mode == "errante":
            speed = random.randint(self.errante_min_speed, self.errante_max_speed) * self.speed_factor
            self.dx = random.choice([-1, 1]) * speed
            self.dy = random.choice([-1, 1]) * speed
        else:
            self.dx = self.dy = 0

        self.banner_y = self.y

        # Registrar este sprite como ejecutandose
        self.register_sprite()

        # Inicializar estado antes de arrancar hilos para evitar AttributeError
        self.visible         = True   # Estado inicial: visible
        self._last_saved_x   = None   # Ultima posicion X guardada en disco
        self._last_saved_y   = None   # Ultima posicion Y guardada en disco

        # --- Hilos ---
        threading.Thread(target=self.animation_loop, daemon=True).start()
        threading.Thread(target=self.movement_loop, daemon=True).start()
        # Pre-cargar el siguiente sprite si es modo playlist
        if self.is_playlist_mode:
            threading.Thread(target=self.preload_next_sprite, daemon=True).start()
        
        # Registrar hotkey global Ctrl+Alt+S para mostrar/ocultar
        if KEYBOARD_AVAILABLE:
            keyboard.add_hotkey('ctrl+alt+s', self.toggle_visibility)
    
    def load_position_from_file(self):
        """Carga la posicion desde positions.ini"""
        import configparser
        try:
            pos_config = configparser.ConfigParser()
            if os.path.exists(POSITIONS_FILE):
                pos_config.read(POSITIONS_FILE, encoding='utf-8')
                if pos_config.has_section(self.sprite_name):
                    self.x = pos_config.getint(self.sprite_name, "x", fallback=100)
                    self.y = pos_config.getint(self.sprite_name, "y", fallback=100)
                    self.banner_y = self.y
                    return
            # Si no existe, usar valores por defecto
            self.x = 100
            self.y = 100
            self.banner_y = self.y
        except Exception as e:
            print(f"Error cargando posicion: {e}")
            self.x = 100
            self.y = 100
            self.banner_y = self.y
            
    def load_playlist_config(self):
        """Carga configuracion de la playlist"""
        if not os.path.exists(REEL_FILE):
            raise FileNotFoundError(f"Playlists file not found")
        
        playlists_config = configparser.ConfigParser()
        playlists_config.read(REEL_FILE, encoding='utf-8')
        
        section_name = f"Reel_{self.playlist_name}"
        
        if not playlists_config.has_section(section_name):
            raise ValueError(f"Playlist '{self.playlist_name}' not found")
        
        # Cargar sprites y ciclos
        sprites_str = playlists_config.get(section_name, "sprites", fallback="")
        self.playlist_sprites = [s.strip() for s in sprites_str.split(",") if s.strip()]
        self.playlist_cycles = playlists_config.getint(section_name, "cycles", fallback=10)
        
        if not self.playlist_sprites:
            raise ValueError(f"Playlist '{self.playlist_name}' has no sprites")
    
    def load_position_from_playlist_file(self):
        """Carga posicion desde reel_positions.ini"""
        try:
            pos_config = configparser.ConfigParser()
            if os.path.exists(REEL_POSITIONS_FILE):
                pos_config.read(REEL_POSITIONS_FILE, encoding='utf-8')
                if pos_config.has_section(self.playlist_name):
                    self.x = pos_config.getint(self.playlist_name, "x", fallback=100)
                    self.y = pos_config.getint(self.playlist_name, "y", fallback=100)
                    self.banner_y = self.y
                    return
            # Si no existe, usar valores por defecto
            self.x = 100
            self.y = 100
            self.banner_y = self.y
        except Exception as e:
            print(f"Error cargando posicion de playlist: {e}")
            self.x = 100
            self.y = 100
            self.banner_y = self.y

    def load_position_from_lasso_file(self):
        """Carga posicion desde lasso_positions.ini (modo lasso)."""
        try:
            pos_config = configparser.ConfigParser()
            if os.path.exists(LASSO_POSITIONS_FILE):
                pos_config.read(LASSO_POSITIONS_FILE, encoding='utf-8')
                section = f"{self.lasso_playlist}::{self.sprite_name}"
                if pos_config.has_section(section):
                    self.x = pos_config.getint(section, "x", fallback=100)
                    self.y = pos_config.getint(section, "y", fallback=100)
                    self.banner_y = self.y
                    return
            self.x = 100
            self.y = 100
            self.banner_y = self.y
        except Exception as e:
            print(f"Error cargando posicion vinculada: {e}")
            self.x = 100
            self.y = 100
            self.banner_y = self.y
    
    def save_playlist_position(self):
        """Guarda posicion de la playlist"""
        if not self.is_playlist_mode:
            return
        
        try:
            pos_config = configparser.ConfigParser()
            if os.path.exists(REEL_POSITIONS_FILE):
                pos_config.read(REEL_POSITIONS_FILE, encoding='utf-8')
            
            if not pos_config.has_section(self.playlist_name):
                pos_config.add_section(self.playlist_name)
            
            pos_config.set(self.playlist_name, "x", str(int(self.x)))
            pos_config.set(self.playlist_name, "y", str(int(self.y)))
            
            with open(REEL_POSITIONS_FILE, "w", encoding='utf-8') as f:
                pos_config.write(f)
        except Exception as e:
            print(f"Error guardando posicion de playlist: {e}")
    
    def load_frames(self, folder):
        frames = []
        png_files = self._list_sprite_png_files(folder)
        for file in png_files:
            frame = self._load_processed_frame(os.path.join(folder, file))
            if frame is not None:
                frames.append(frame)
        return frames

    def _list_sprite_png_files(self, folder):
        import re

        def natural_sort_key(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

        png_files = [f for f in os.listdir(folder) if f.lower().endswith(".png")]
        png_files.sort(key=natural_sort_key)
        return png_files

    def _load_processed_frame(self, file_path):
        img = pygame.image.load(file_path).convert_alpha()
        img = pygame.transform.smoothscale(img, (self.frame_width, self.frame_height))
        surf = pygame.Surface((self.frame_width, self.frame_height))
        surf.fill(self.transparent_color)
        for y in range(img.get_height()):
            for x in range(img.get_width()):
                r, g, b, a = img.get_at((x, y))
                if a > 128:
                    surf.set_at((x, y), (r, g, b))
                else:
                    surf.set_at((x, y), self.transparent_color)
        return surf

    def save_current_position(self):
        """Guarda el punto de origen en positions.ini o reel_positions.ini.

        Solo se invoca cuando el usuario suelta el sprite tras arrastrarlo.
        Walk y Wandering son trayectorias temporales que no se almacenan.
        """
        import configparser
        try:
            # Determinar que archivo y seccion usar
            if self.is_lasso_mode:
                pos_file     = LASSO_POSITIONS_FILE
                section_name = f"{self.lasso_playlist}::{self.sprite_name}"
            elif self.is_playlist_mode:
                pos_file     = REEL_POSITIONS_FILE
                section_name = self.playlist_name
            else:
                pos_file     = POSITIONS_FILE
                section_name = self.sprite_name
            
            # Cargar configuracion existente
            pos_config = configparser.ConfigParser()
            if os.path.exists(pos_file):
                pos_config.read(pos_file, encoding='utf-8')
            
            # Crear seccion si no existe
            if not pos_config.has_section(section_name):
                pos_config.add_section(section_name)
            
            # Verificar si la posicion cambio respecto a la ultima guardada
            current_x = int(self.x)
            current_y = int(self.y)
            if current_x == self._last_saved_x and current_y == self._last_saved_y:
                return  # Posicion identica — no escribir al disco

            # Guardar posicion
            pos_config.set(section_name, "x", str(current_x))
            pos_config.set(section_name, "y", str(current_y))

            # Escribir archivo
            with open(pos_file, "w", encoding='utf-8') as f:
                pos_config.write(f)

            # Actualizar memoria de posicion guardada
            self._last_saved_x = current_x
            self._last_saved_y = current_y
        except Exception as e:
            print(f"Error guardando posicion: {e}")
           
    def preload_next_sprite(self):
        """Pre-carga los frames del siguiente sprite en un hilo separado"""
        if not self.is_playlist_mode:
            return
        
        next_index = (self.current_playlist_index + 1) % len(self.playlist_sprites)
        next_sprite_name = self.playlist_sprites[next_index]
        
        # Si ya esta pre-cargado, no hacer nada
        with self.preload_lock:
            if self.preloaded_sprite_name == next_sprite_name:
                return
        
        def do_preload():
            sprite_path = os.path.join(SPRITES_DIR, next_sprite_name)
            if not os.path.exists(sprite_path):
                return
            
            try:
                frames = self.load_frames(sprite_path)
                with self.preload_lock:
                    self.preloaded_frames = frames
                    self.preloaded_sprite_name = next_sprite_name
            except:
                pass
        
        threading.Thread(target=do_preload, daemon=True).start()
    
    def switch_to_next_playlist_sprite(self):
        """Cambia al siguiente sprite en la playlist usando frames pre-cargados si estan disponibles"""
        if not self.is_playlist_mode:
            return
        
        # Avanzar al siguiente sprite
        self.current_playlist_index = (self.current_playlist_index + 1) % len(self.playlist_sprites)
        self.current_cycle_count = 0
        
        new_sprite_name = self.playlist_sprites[self.current_playlist_index]
        self.sprite_name = new_sprite_name
        
        # Intentar usar frames pre-cargados primero
        with self.preload_lock:
            if self.preloaded_sprite_name == new_sprite_name and self.preloaded_frames:
                with self.frames_lock:
                    self.frames = self.preloaded_frames
                self.preloaded_frames = None
                self.preloaded_sprite_name = None
                self.frame_index = 0
                # Pre-cargar el siguiente ya
                threading.Thread(target=self.preload_next_sprite, daemon=True).start()
                return
        
        # Si no habia pre-carga lista, cargar normalmente
        sprite_path = os.path.join(SPRITES_DIR, self.sprite_name)
        
        if os.path.exists(sprite_path):
            loaded_frames = self.load_frames(sprite_path)
            if loaded_frames:
                with self.frames_lock:
                    self.frames = loaded_frames
                self.frame_index = 0
            else:
                self.switch_to_next_playlist_sprite()
                return
        else:
            self.switch_to_next_playlist_sprite()
            return
        
        # Pre-cargar el siguiente
        threading.Thread(target=self.preload_next_sprite, daemon=True).start()
            
    def get_delay(self):
        # Si es modo playlist, leer delay del sprite individual desde config.ini
        if self.is_playlist_mode:
            return self._get_delay_for_sprite(self.sprite_name)
        
        if self.delay_mode == "fixed":
            return self.fixed_delay
        elif self.delay_mode == "cpu":
            try:
                cpu = psutil.cpu_percent()
                for min_u, max_u, delay in self.cpu_delays:
                    if min_u <= cpu < max_u:
                        return int(delay)
            except:
                pass
        elif self.delay_mode == "gpu" and GPUtil:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0].load * 100
                    for min_u, max_u, delay in self.gpu_delays:
                        if min_u <= gpu < max_u:
                            return int(delay)
            except:
                pass
        elif self.delay_mode == "presentacion":
            return self.presentacion_delay
        return self.fixed_delay
    
    def _get_delay_for_sprite(self, sprite_name):
        """Lee el delay del sprite individual desde config.ini"""
        try:
            sprite_section = f"Sprite_{sprite_name}"
            if not self.config.has_section(sprite_section):
                return self.fixed_delay
            
            g = self.config[sprite_section]
            mode = g.get("delay_mode", "fixed")
            
            if mode == "fixed":
                return int(g.get("fixed_delay", "60"))
            elif mode == "cpu":
                try:
                    import ast
                    cpu = psutil.cpu_percent()
                    cpu_delays_str = g.get("cpu_delays", "[(0,20,200),(21,40,150),(41,60,120),(61,80,90),(81,100,60)]")
                    cpu_delays = ast.literal_eval(cpu_delays_str)
                    for min_u, max_u, delay in cpu_delays:
                        if min_u <= cpu < max_u:
                            return int(delay)
                except:
                    pass
            elif mode == "presentacion":
                return int(g.get("presentacion_delay", "2")) * 1000
            
            return int(g.get("fixed_delay", "60"))
        except:
            return self.fixed_delay

    def animation_loop(self):
        try:
            while self.running:
                should_switch_playlist_sprite = False
                if not self.animation_frozen:
                    with self.frames_lock:
                        frame_count = len(self.frames)
                        if frame_count > 1:
                            self.frame_index = (self.frame_index + 1) % frame_count
                            if self.frame_index == 0 and self.is_playlist_mode:
                                self.current_cycle_count += 1
                                if self.current_cycle_count >= self.playlist_cycles:
                                    should_switch_playlist_sprite = True
                if should_switch_playlist_sprite:
                    self.switch_to_next_playlist_sprite()
                self.redraw()
                pygame.time.wait(max(1, self.get_delay()))
        except Exception as e:
            import traceback
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write("=== animation_loop ===\n")
                traceback.print_exc(file=f)

    def movement_loop(self):
        import traceback
        clock = pygame.time.Clock()
        try:
            while self.running:
                if not self.movement_paused and not self.dragging:
                    w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                    h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                    if self.dynamic_mode == "paseo":
                        self.x += self.dx
                        if self.x + self.frame_width < 0:
                            self.x = w
                        elif self.x > w:
                            self.x = -self.frame_width
                        self.y = self.banner_y
                    elif self.dynamic_mode == "errante":
                        self.x += self.dx
                        self.y += self.dy
                        if self.x <= 0:
                            self.x = 0
                            self.dx = abs(self.dx)
                        elif self.x + self.frame_width >= w:
                            self.x = w - self.frame_width
                            self.dx = -abs(self.dx)
                        if self.y <= 0:
                            self.y = 0
                            self.dy = abs(self.dy)
                        elif self.y + self.frame_height >= h:
                            self.y = h - self.frame_height
                            self.dy = -abs(self.dy)
                        if self.dx == 0:
                            speed = random.randint(self.errante_min_speed, self.errante_max_speed) * self.speed_factor
                            self.dx = random.choice([-1, 1]) * speed
                        if self.dy == 0:
                            speed = random.randint(self.errante_min_speed, self.errante_max_speed) * self.speed_factor
                            self.dy = random.choice([-1, 1]) * speed
                    if WIN32_AVAILABLE:
                        hwnd = pygame.display.get_wm_info()['window']
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                            int(self.x), int(self.y), 0, 0,
                            win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                clock.tick(120)
        except Exception as e:
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write("=== movement_loop ===\n")
                traceback.print_exc(file=f)

    def redraw(self):
        self.screen.fill(self.transparent_color)
        with self.frames_lock:
            frame_count = len(self.frames)
            if frame_count == 0:
                return
            if self.frame_index >= frame_count:
                self.frame_index = 0
            current_frame = self.frames[self.frame_index]
        self.screen.blit(current_frame, (0, 0))
        pygame.display.flip()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
            elif event.type == pygame.KEYDOWN:
                pass  # Hotkeys manejados globalmente por la libreria keyboard
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if 0 <= mx < self.frame_width and 0 <= my < self.frame_height:
                    with self.frames_lock:
                        pixel = self.frames[self.frame_index].get_at((mx, my))
                    # get_at() devuelve (R, G, B, A) — comparar solo RGB ignorando alfa
                    if (pixel[0], pixel[1], pixel[2]) != self.transparent_color:
                        self.dragging = True
                        self.drag_offset_x, self.drag_offset_y = mx, my
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.dragging:
                    self.dragging = False
                    # Guardar posicion inmediatamente al soltar
                    threading.Thread(target=self.save_current_position, daemon=True).start()
                else:
                    self.movement_paused = not self.movement_paused
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                if WIN32_AVAILABLE:
                    mx, my = event.pos
                    hwnd = pygame.display.get_wm_info()['window']
                    rx, ry, _, _ = win32gui.GetWindowRect(hwnd)
                    nx = rx + (mx - self.drag_offset_x)
                    ny = ry + (my - self.drag_offset_y)
                    self.x, self.y = nx, ny
                    if self.dynamic_mode == "paseo":
                        self.banner_y = ny
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                        int(nx), int(ny), 0, 0,
                        win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                        
    def _check_toggle_flag(self):
        """
        Lee el archivo TOGGLE_FLAG escrito por el tray de setting.pyw.
        Formato del archivo: "hide:1234567890.123" o "show:1234567890.123"
        Solo actua si el timestamp es mas reciente que el ultimo procesado,
        evitando que el mismo comando se ejecute dos veces.
        """
        try:
            if not os.path.exists(TOGGLE_FLAG):
                return
            with open(TOGGLE_FLAG, "r", encoding="utf-8") as f:
                content = f.read().strip()
            parts = content.split(":", 1)
            if len(parts) != 2:
                return
            command, ts_str = parts
            ts = float(ts_str)
            if ts <= self._last_toggle_ts:
                return  # Comando ya procesado por esta instancia
            self._last_toggle_ts = ts
            if command == "hide" and self.visible:
                self.toggle_visibility()
            elif command == "show" and not self.visible:
                self.toggle_visibility()
        except Exception:
            pass

    def _check_lasso_cmd_flag(self):
        """Lee data/lasso_cmd_{pid}.flag y ejecuta hide/show/freeze/unfreeze."""
        if not self.is_lasso_mode:
            return
        try:
            flag_path = os.path.join(DATA_DIR, f"lasso_cmd_{os.getpid()}.flag")
            if not os.path.exists(flag_path):
                return
            with open(flag_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            parts = content.split(":", 1)
            if len(parts) != 2:
                return
            command, ts_str = parts
            ts = float(ts_str)
            if ts <= self._last_lasso_cmd_ts:
                return
            self._last_lasso_cmd_ts = ts
            if command == "hide":
                if self.visible:
                    self.toggle_visibility()
            elif command == "show":
                if not self.visible:
                    self.toggle_visibility()
            elif command == "freeze":
                self.animation_frozen = True
            elif command == "unfreeze":
                self.animation_frozen = False
        except Exception:
            pass

    def toggle_visibility(self):
        if not WIN32_AVAILABLE:
            return
        hwnd = pygame.display.get_wm_info()['window']
        if self.visible:
            # Ocultar ventana
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            self.visible = False
        else:
            # Mostrar ventana
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                int(self.x), int(self.y), 0, 0,
                win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            self.visible = True

        # Escribir el estado actual para que el tray pueda sincronizarse
        try:
            with open(SPRITES_STATE_FLAG, "w", encoding="utf-8") as f:
                f.write("visible" if self.visible else "hidden")
        except Exception:
            pass

    def save_position(self):
        """Guarda posicion final al cerrar la aplicacion."""
        self.save_current_position()

    def quit(self):
        self.running = False
        self.unregister_sprite()
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.remove_hotkey('ctrl+alt+s')
            except:
                pass
        if self.is_lasso_mode:
            try:
                flag_path = os.path.join(DATA_DIR, f"lasso_cmd_{os.getpid()}.flag")
                if os.path.exists(flag_path):
                    os.remove(flag_path)
            except Exception:
                pass
        pygame.quit()
        os._exit(0)

    def main_loop(self):
        clock = pygame.time.Clock()
        _tick = 0
        while self.running:
            self.handle_events()
            _tick += 1
            if _tick % 30 == 0:  # ~4 veces por segundo a 120 FPS
                self._check_toggle_flag()
                self._check_lasso_cmd_flag()
            clock.tick(120)
        pygame.quit()
    
    def register_sprite(self):
        """Registra este sprite como ejecutandose"""
        try:
            registry = {}
            
            # Leer registro existente
            if os.path.exists(REGISTRY_FILE):
                try:
                    with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                        registry = json.load(f)
                except:
                    registry = {}
            
            # Agregar este proceso
            pid = os.getpid()
            
            if self.is_playlist_mode:
                display_name = f"Reel: {self.playlist_name}"
            else:
                display_name = self.sprite_name
            
            registry[str(pid)] = {
                'sprite':        display_name,
                'pid':           pid,
                'is_playlist':   self.is_playlist_mode,
                'scene':         self.scene_name,
                'is_lasso':      self.is_lasso_mode,
                'lasso_playlist': self.lasso_playlist,
                'lasso_song':     self.lasso_song,
            }
            
            # Guardar
            with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
                json.dump(registry, f, indent=2)
                
        except Exception as e:
            print(f"Error registrando sprite: {e}")
    
    def unregister_sprite(self):
        """Desregistra este sprite al cerrar"""
        try:
            if not os.path.exists(REGISTRY_FILE):
                return
            
            # Leer registro
            with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                registry = json.load(f)
            
            # Remover este proceso
            pid = str(os.getpid())
            if pid in registry:
                del registry[pid]
            
            # Guardar
            with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
                json.dump(registry, f, indent=2)
                
        except Exception as e:
            print(f"Error desregistrando sprite: {e}")

    def _wait_for_sync_group_ready(self, timeout_s: float = 10.0):
        if not self.sync_group or self.sync_expected <= 1:
            return

        os.makedirs(DATA_DIR, exist_ok=True)
        sync_path = os.path.join(DATA_DIR, f"sync_{self.sync_group}.json")
        me = str(os.getpid())
        start = time.time()

        while time.time() - start < timeout_s:
            data = {"expected": self.sync_expected, "ready": []}
            try:
                if os.path.exists(sync_path):
                    with open(sync_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
            except Exception:
                pass

            ready = set(str(x) for x in data.get("ready", []))
            ready.add(me)
            data["ready"] = list(ready)
            data["expected"] = max(int(data.get("expected", self.sync_expected)), self.sync_expected)

            try:
                with open(sync_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

            if len(ready) >= data["expected"]:
                return
            time.sleep(0.05)
            
if __name__ == "__main__":
    # Salir silenciosamente si se ejecuta sin argumentos
    if len(sys.argv) <= 1:
        sys.exit(0)

    # Icono correcto en la barra de tareas para cada instancia de sprite.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u'Spryta.Desktop.Sprite.1'
        )
    except Exception:
        pass
    sprite_name   = None
    playlist_name = None
    scene_name    = None
    lasso_playlist = None
    sync_group = None
    sync_expected = 1

    if len(sys.argv) > 1:
        if "--playlist" in sys.argv:
            playlist_idx = sys.argv.index("--playlist")
            if len(sys.argv) > playlist_idx + 1:
                playlist_name = sys.argv[playlist_idx + 1]
        else:
            sprite_name = sys.argv[1]

    if "--scene" in sys.argv:
        scene_idx = sys.argv.index("--scene")
        if len(sys.argv) > scene_idx + 1:
            scene_name = sys.argv[scene_idx + 1]

    if "--lasso" in sys.argv:
        link_idx = sys.argv.index("--lasso")
        if len(sys.argv) > link_idx + 1:
            lasso_playlist = sys.argv[link_idx + 1]

    lasso_song = None
    if "--lasso-song" in sys.argv:
        song_idx = sys.argv.index("--lasso-song")
        if len(sys.argv) > song_idx + 1:
            lasso_song = sys.argv[song_idx + 1] or None

    if "--sync-group" in sys.argv:
        grp_idx = sys.argv.index("--sync-group")
        if len(sys.argv) > grp_idx + 1:
            sync_group = sys.argv[grp_idx + 1]

    if "--sync-expected" in sys.argv:
        exp_idx = sys.argv.index("--sync-expected")
        if len(sys.argv) > exp_idx + 1:
            try:
                sync_expected = int(sys.argv[exp_idx + 1])
            except Exception:
                sync_expected = 1

    try:
        app = SpriteApp(
            sprite_override=sprite_name,
            playlist_name=playlist_name,
            scene_name=scene_name,
            lasso_playlist=lasso_playlist,
            lasso_song=lasso_song,
            sync_group=sync_group,
            sync_expected=sync_expected,
        )
        app.main_loop()
    except Exception:
        import traceback
        err = traceback.format_exc()
        with open("crash.log", "a", encoding="utf-8") as f:
            f.write("=== main entry point ===\n")
            f.write(f"argv: {sys.argv}\n")
            f.write(err)
        try:
            messagebox.showerror("Sprite Error", err[:800])
        except Exception:
            pass

#Hola Brian
