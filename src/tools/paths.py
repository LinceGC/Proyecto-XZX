# src/tools/paths.py
# -*- coding: utf-8 -*-
"""
Modulo central de rutas de Spryta.

Separacion de responsabilidades:
    INSTALL_DIR   -- carpeta donde esta instalada la app (solo lectura)
    USER_DATA_DIR -- C:\\Users\\USUARIO\\AppData\\Local\\Spryta\\ (datos del usuario)

Todos los modulos del proyecto importan las rutas desde aqui.
Nunca usar rutas relativas directamente en otro archivo.
"""

import os
import sys


# ============================================================
# Funciones privadas de deteccion de rutas
# ============================================================

def _get_install_dir() -> str:
    """
    Devuelve la carpeta donde esta instalada la aplicacion.
    En modo compilado: directorio del .exe
    En modo desarrollo: raiz del proyecto (dos niveles arriba de src/tools/)
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # En desarrollo este archivo esta en src/tools/paths.py
    # Subimos dos niveles para llegar a la raiz del proyecto
    this_file = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(this_file)))


def _get_user_data_dir() -> str:
    """
    Devuelve la carpeta persistente del usuario.
    Resultado: C:\\Users\\USUARIO\\AppData\\Local\\Spryta\\
    """
    appdata_local = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(appdata_local, "Spryta")


# ============================================================
# Directorio de instalacion (assets, ejecutables — solo lectura)
# ============================================================

INSTALL_DIR = _get_install_dir()


# ============================================================
# Directorio de datos del usuario (persistente — lectura/escritura)
# ============================================================

USER_DATA_DIR = _get_user_data_dir()

# Subcarpetas de datos del usuario
SPRITES_DIR = os.path.join(USER_DATA_DIR, "sprites")
AUDIO_DIR   = os.path.join(USER_DATA_DIR, "Audio")
DATA_DIR    = os.path.join(USER_DATA_DIR, "data")

# Archivos de configuracion dentro de DATA_DIR
CONFIG_FILE          = os.path.join(DATA_DIR, "config.ini")
POSITIONS_FILE       = os.path.join(DATA_DIR, "positions.ini")
SCENES_FILE          = os.path.join(DATA_DIR, "scenes.ini")
REEL_FILE            = os.path.join(DATA_DIR, "reel.ini")
REEL_POSITIONS_FILE  = os.path.join(DATA_DIR, "reel_positions.ini")
REEL_CONFIG_FILE     = os.path.join(DATA_DIR, "reel_config.ini")
SESSION_FILE         = os.path.join(DATA_DIR, "session.ini")
LASSOS_FILE          = os.path.join(DATA_DIR, "lassos.json")

# Archivos de registro y comunicacion entre procesos (IPC)
REGISTRY_FILE      = os.path.join(DATA_DIR, "sprites_running.txt")
TOGGLE_FLAG        = os.path.join(DATA_DIR, "toggle_sprites.flag")
SPRITES_STATE_FLAG = os.path.join(DATA_DIR, "sprites_visible_state.flag")
SHOW_FLAG          = os.path.join(DATA_DIR, "show_settings.flag")
LASSO_POS_FILE     = os.path.join(DATA_DIR, "lasso_positions.ini")


# ============================================================
# Creacion de carpetas del usuario en primera ejecucion
# ============================================================

def ensure_user_dirs() -> None:
    """
    Crea las carpetas del usuario si no existen todavia.
    Llamar una sola vez al arrancar la aplicacion, antes de
    cualquier operacion de lectura o escritura de archivos.
    """
    for directory in [USER_DATA_DIR, SPRITES_DIR, AUDIO_DIR, DATA_DIR]:
        os.makedirs(directory, exist_ok=True)
