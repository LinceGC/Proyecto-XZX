# -*- coding: utf-8 -*-
"""
Modulo de gestion de procesos de sprites
Maneja el registro, monitoreo y cierre de sprites en ejecucion
"""
import os
import json
import psutil

_USER_DATA   = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Spryta", "data")
REGISTRY_FILE = os.path.join(_USER_DATA, "sprites_running.txt")

class ProcessManager:
    """Gestor de procesos de sprites"""
    
    def __init__(self):
        self.registry_file = REGISTRY_FILE
    
    def get_running_sprites(self):
        """
        Obtiene lista de sprites en ejecucion.
        Solo lee el registro — no escribe al disco para evitar
        condiciones de carrera cuando el tray y el panel consultan
        al mismo tiempo.

        Returns:
            list: Lista de tuplas (pid, sprite_name, process_object)
        """
        running = []

        if not os.path.exists(self.registry_file):
            return running

        try:
            with open(self.registry_file, 'r', encoding='utf-8') as f:
                registry = json.load(f)
        except Exception:
            return running

        for pid_str, data in registry.items():
            pid = int(pid_str)
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    sprite_name = data.get('sprite', 'Unknown')
                    running.append((pid, sprite_name, proc))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return running
    
    def close_process(self, pid):
        """
        Cierra un proceso especifico
        
        Args:
            pid: ID del proceso a cerrar
        
        Returns:
            bool: True si se cerro exitosamente
        """
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            
            # Esperar un momento para asegurar cierre
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"Error cerrando proceso {pid}: {e}")
            return False
    
    def close_all_sprites(self):
        """
        Cierra todos los sprites en ejecucion
        
        Returns:
            int: Numero de procesos cerrados
        """
        running = self.get_running_sprites()
        closed = 0
        
        for pid, sprite_name, proc in running:
            if self.close_process(pid):
                closed += 1
        
        # Limpiar registro
        self._save_registry({})
        
        return closed
    
    def terminate_process_by_name(self, process_name):
        """
        Termina procesos por nombre de archivo
        
        Args:
            process_name: Nombre del archivo (ej: "main.pyw", "ambient_audio.pyw")
        
        Returns:
            int: Numero de procesos terminados
        """
        count = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any(process_name in s for s in cmdline):
                    proc.terminate()
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return count
    
    def _save_registry(self, registry_data):
        """Guarda el registro de procesos"""
        try:
            with open(self.registry_file, 'w', encoding='utf-8') as f:
                json.dump(registry_data, f, indent=2)
        except Exception as e:
            print(f"Error guardando registro: {e}")
    
    def get_running_sprites_for_display(self):
        """
        Igual que get_running_sprites() pero con nombres formateados para el panel.
          - Solo individual  : "Sprite:  Ganyu"
          - Reel               : "Reel:  Dragon Saga"
          - Escena            : "Scene:  Mis amores   >   Ganyu"
        """
        if not os.path.exists(self.registry_file):
            return []

        try:
            with open(self.registry_file, 'r', encoding='utf-8') as f:
                registry = json.load(f)
        except Exception:
            return []

        result         = []
        active_registry = {}

        for pid_str, data in registry.items():
            pid = int(pid_str)
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    active_registry[pid_str] = data
                    raw_name   = data.get('sprite', 'Unknown')
                    scene      = data.get('scene', None)
                    is_lasso   = data.get('is_lasso', False)
                    lasso_song = data.get('lasso_song', None)

                    if scene:
                        formatted = f"Scene:  {scene}   \u203a   {raw_name}"
                    elif raw_name.startswith("Reel: "):
                        formatted = raw_name.replace("Reel: ", "Reel:  ", 1)
                    elif is_lasso:
                        if lasso_song:
                            formatted = f"Lasso:  {raw_name}   \u203a   {lasso_song}"
                        else:
                            formatted = f"Lasso:  {raw_name}"
                    else:
                        formatted = f"Solo:  {raw_name}"

                    result.append((pid, formatted, proc))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if len(active_registry) != len(registry):
            self._save_registry(active_registry)

        return result