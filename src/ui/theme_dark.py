# -*- coding: utf-8 -*-
"""
src/ui/theme_dark.py  —  Spryta Dark Theme

EDITA ESTE ARCHIVO para cambiar los colores del modo OSCURO.
No necesitas tocar ningun otro archivo.

Para probar un cambio:
  1. Cambia un color aqui
  2. Guarda
  3. Reinicia la app y activa el modo oscuro
"""

# ── Fondos (de mas oscuro a mas claro) ──────────────────────────
BG_BASE    = "#0e0e12"   # ventana principal
BG_SURFACE = "#16161e"   # sidebar, header, cards, paneles
BG_RAISED  = "#1e1e28"   # inputs, listboxes, elementos interactivos
BG_HOVER   = "#252534"   # estado hover

# ── Bordes ───────────────────────────────────────────────────────
BORDER_DIM = "#1e1e28"   # borde casi invisible
BORDER_MID = "#2c2c3c"   # borde estandar (cards, inputs)
BORDER_HI  = "#3c3c54"   # borde resaltado (focus, hover)

# ── Acento: AZUL ─────────────────────────────────────────────────
ACCENT       = "#358cfe"   # azul principal
ACCENT_HOVER = "#5aa3ff"   # azul al pasar el mouse
ACCENT_DIM   = "#0d2a5a"   # fondo de seleccion activa

# ── Textos ───────────────────────────────────────────────────────
TEXT_BRIGHT = "#eaeaf2"   # texto principal
TEXT_NORMAL = "#a0a0bc"   # texto secundario
TEXT_MUTED  = "#50506a"   # texto atenuado / hints

# ── Estados ──────────────────────────────────────────────────────
COLOR_SUCCESS = "#358cfe"   # exito (mismo azul)
COLOR_WARNING = "#f4a020"   # advertencia (naranja)
COLOR_DANGER  = "#e63946"   # peligro — SOLO Exit y eliminar

# ── Seleccion de texto ───────────────────────────────────────────
SELECT_BG = "#0d2a5a"   # fondo de texto seleccionado
SELECT_FG = "#eaeaf2"   # color de texto seleccionado