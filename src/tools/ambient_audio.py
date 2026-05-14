# -*- coding: utf-8 -*-
"""
Modulo de Ambient Audio - Gestor de reproduccion de audio ambiental
"""
import os
import pygame
import threading

class AmbientAudioManager:
    """Gestor de reproduccion de audio ambiental"""
    
    def __init__(self):
        self.audio_files = []
        self.is_playing = False
        self.is_paused  = False
        self.is_playlist_mode = False
        self.current_audio_path = None
        self.current_playlist_index = 0
        self.audio_dir = os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "Spryta", "Audio"
        )
        self.is_track_transitioning = False

        # Estado previo para poder reanudar tras stop()
        self._last_audio_path     = None
        self._last_playlist_mode  = False
        self._last_playlist_index = 0
        self.before_track_start   = None   # callback opcional: fn(filename) -> None
        
        # Crear directorio si no existe
        if not os.path.exists(self.audio_dir):
            os.makedirs(self.audio_dir)
        
        # Inicializar pygame si no esta ya
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=4096)
                pygame.mixer.init()
                pygame.mixer.music.set_volume(0.8)
            except Exception as e:
                print(f"Error initializing pygame: {e}")
    
    def get_audio_files(self):
        """Obtiene lista de archivos de audio disponibles"""
        self.audio_files = []
        for f in sorted(os.listdir(self.audio_dir)):
            if f.lower().endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac')):
                self.audio_files.append(f)
        return self.audio_files
    
    def play_loop(self, filename):
        """Reproduce un archivo en loop infinito"""
        path = os.path.join(self.audio_dir, filename)
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        if not pygame.mixer.get_init():
            raise RuntimeError("Audio system not initialized")

        # Cortar audio previo para que haya silencio durante el tiempo de gracia.
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

        if callable(self.before_track_start):
            self.before_track_start(filename)
        
        pygame.mixer.music.load(path)
        pygame.mixer.music.play(loops=-1)

        self.is_playing         = True
        self.is_playlist_mode   = False
        self.current_audio_path = path

        # Sincronizar _last_* para que resume() pueda reiniciar tras stop()
        self._last_audio_path     = path
        self._last_playlist_mode  = False
        self._last_playlist_index = 0

        return True
    
    def play_playlist(self, start_index=0):
        """Inicia reproduccion de playlist"""
        self.current_playlist_index = start_index
        self.is_playlist_mode = True
        return self._play_next_in_playlist()
    
    def _play_next_in_playlist(self):
        """Reproduce siguiente cancion en playlist"""
        if not self.audio_files:
            self.stop()
            return False
        
        if self.current_playlist_index >= len(self.audio_files):
            self.current_playlist_index = 0
        
        filename = self.audio_files[self.current_playlist_index]
        path = os.path.join(self.audio_dir, filename)
        
        if not os.path.exists(path):
            self.current_playlist_index += 1
            return self._play_next_in_playlist()
        
        self.is_track_transitioning = True
        try:
            # Cortar la pista actual antes de preparar la siguiente.
            # Esto garantiza silencio mientras se espera al sprite.
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            if callable(self.before_track_start):
                self.before_track_start(filename)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(loops=0)
            self.current_audio_path = path
            self.is_playing = True
            # Mantener _last_audio_path sincronizado para que resume() funcione
            self._last_audio_path     = path
            self._last_playlist_mode  = True
            self._last_playlist_index = self.current_playlist_index
            return True
        except Exception as e:
            print(f"Error playing {filename}: {e}")
            return False
        finally:
            self.is_track_transitioning = False
    
    def check_and_advance_playlist(self):
        """Verifica si termino la cancion y avanza. No avanza si esta pausado."""
        if not self.is_playlist_mode or not pygame.mixer.get_init():
            return False

        # Evitar doble salto mientras _play_next_in_playlist esta esperando
        # a Lasso/sprites antes de iniciar el track.
        if self.is_track_transitioning:
            return True

        # get_busy() devuelve False cuando esta pausado tambien,
        # por eso hay que excluir el estado pausado antes de avanzar.
        if not self.is_paused and not pygame.mixer.music.get_busy():
            # Cancion termino, avanzar
            self.current_playlist_index += 1
            return self._play_next_in_playlist()

        return True
    
    def stop(self):
        """Detiene la reproduccion. Conserva la ruta y el modo para poder reanudar."""
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

        # Solo actualizar _last_* si hay una pista activa.
        # Si ya fue detenido antes, current_audio_path es None y no se pisa
        # el estado guardado, preservando la capacidad de reanudar.
        if self.current_audio_path:
            self._last_audio_path     = self.current_audio_path
            self._last_playlist_mode  = self.is_playlist_mode
            self._last_playlist_index = self.current_playlist_index

        self.is_playing             = False
        self.is_paused              = False
        self.is_playlist_mode       = False
        self.is_track_transitioning = False
        self.current_audio_path     = None
        self.current_playlist_index = 0
    
    def set_volume(self, volume):
        """Ajusta volumen (0.0 a 1.0)"""
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(float(volume))

    def get_volume(self):
        """Retorna el volumen actual del mixer (0.0 a 1.0)."""
        if pygame.mixer.get_init():
            return pygame.mixer.music.get_volume()
        return 0.8

    def pause(self):
        """Pausa la reproduccion sin perder la posicion."""
        if pygame.mixer.get_init() and self.is_playing and not self.is_paused:
            pygame.mixer.music.pause()
            self.is_paused = True

    def resume(self):
        """
        Reanuda o reinicia la reproduccion segun el estado actual.

        Caso 1 — pausado: llama unpause(), continua desde donde estaba.
        Caso 2 — detenido via stop(): recarga el ultimo archivo guardado.
        Caso 3 — is_playing=True pero mixer inactivo (pista termino
                 naturalmente y el panel aun no actualizo el estado):
                 sincroniza is_playing y recarga desde _last_audio_path.
        """
        if not pygame.mixer.get_init():
            return

        mixer_busy = pygame.mixer.music.get_busy()

        if self.is_paused and self.current_audio_path:
            # Caso 1: estaba pausado — continuar desde donde estaba
            pygame.mixer.music.unpause()
            self.is_paused = False

        elif not self.is_playing and self._last_audio_path:
            # Caso 2: fue detenido con stop() — recargar desde el ultimo archivo
            self._restart_from_last()

        elif self.is_playing and not mixer_busy and self._last_audio_path:
            # Caso 3: is_playing quedo True pero el mixer ya termino
            # Sincronizar estado y reiniciar
            self.is_playing = False
            self._restart_from_last()

    def _restart_from_last(self):
        """
        Reinicia la reproduccion desde el ultimo estado conocido.
        - Modo loop:     carga el archivo y reproduce en loop infinito.
        - Modo playlist: restaura el indice y delega en _play_next_in_playlist
                         para que use la logica correcta de indices y archivos.
        """
        if not self._last_audio_path:
            return
        try:
            if self._last_playlist_mode:
                # Restaurar indice y usar el flujo normal de playlist
                self.is_playlist_mode       = True
                self.current_playlist_index = self._last_playlist_index
                self.is_playing             = False   # _play_next_in_playlist lo activa
                self.is_paused              = False
                self._play_next_in_playlist()
            else:
                # Modo loop: cargar y reproducir en loop infinito
                path = self._last_audio_path
                pygame.mixer.music.load(path)
                pygame.mixer.music.play(loops=-1)
                self.current_audio_path = path
                self.is_playlist_mode   = False
                self.is_playing         = True
                self.is_paused          = False
        except Exception as e:
            print(f"Error reanudando audio: {e}")

    def next_track(self):
        """Avanza a la siguiente pista (solo en modo playlist)."""
        if not self.is_playlist_mode:
            return
        self.current_playlist_index += 1
        if self.current_playlist_index >= len(self.audio_files):
            self.current_playlist_index = 0
        self.is_paused = False
        self._play_next_in_playlist()

    def prev_track(self):
        """Retrocede a la pista anterior (solo en modo playlist)."""
        if not self.is_playlist_mode:
            return
        self.current_playlist_index -= 1
        if self.current_playlist_index < 0:
            self.current_playlist_index = max(0, len(self.audio_files) - 1)
        self.is_paused = False
        self._play_next_in_playlist()
    
    def get_current_filename(self):
        """Obtiene nombre del archivo actual"""
        if self.current_audio_path:
            return os.path.basename(self.current_audio_path)
        return None
    
    def add_audio_file(self, source_path):
        """Copia un archivo de audio a la biblioteca"""
        import shutil
        
        filename = os.path.basename(source_path)
        dest_path = os.path.join(self.audio_dir, filename)
        
        if os.path.exists(dest_path):
            raise FileExistsError(f"File already exists: {filename}")
        
        shutil.copy2(source_path, dest_path)
        self.get_audio_files()  # Refrescar lista
        return filename
