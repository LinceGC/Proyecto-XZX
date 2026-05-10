# -*- coding: utf-8 -*-
"""
Modulo de extraccion de frames de video/GIF
"""
import os
import cv2
from PIL import Image

class FrameExtractor:
    """Extractor de frames de videos y GIFs"""
    
    def __init__(self):
        self.sprites_dir = os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "Spryta", "sprites"
        )
        os.makedirs(self.sprites_dir, exist_ok=True)
    
    def extract_from_video(self, video_path, output_folder, target_fps=0):
        """
        Extrae frames de un video
        
        Args:
            video_path: Ruta al archivo de video
            output_folder: Carpeta donde guardar frames
            target_fps: FPS objetivo (0 = todos los frames)
        
        Returns:
            int: Numero de frames extraidos
        """
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise Exception("Could not open video file")
        
        os.makedirs(output_folder, exist_ok=True)
        
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        
        if target_fps == 0:
            frame_interval = 1
        else:
            frame_interval = max(1, int(video_fps / target_fps))
        
        frame_count = 0
        saved_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_count % frame_interval == 0:
                frame_filename = os.path.join(output_folder, f"frame_{saved_count:04d}.png")
                cv2.imwrite(frame_filename, frame)
                saved_count += 1
            
            frame_count += 1
        
        cap.release()
        return saved_count
    
    def extract_from_gif(self, gif_path, output_folder, target_fps=0):
        """
        Extrae frames de un GIF animado
        
        Args:
            gif_path: Ruta al archivo GIF
            output_folder: Carpeta donde guardar frames
            target_fps: FPS objetivo (0 = todos los frames)
        
        Returns:
            int: Numero de frames extraidos
        """
        os.makedirs(output_folder, exist_ok=True)
        
        with Image.open(gif_path) as gif:
            if target_fps == 0:
                frame_interval = 1
            else:
                try:
                    gif_duration = gif.info.get('duration', 100)
                    gif_fps = 1000 / gif_duration if gif_duration > 0 else 10
                except:
                    gif_fps = 10
                
                frame_interval = max(1, int(gif_fps / target_fps))
            
            frame_count = 0
            saved_count = 0
            
            try:
                while True:
                    if frame_count % frame_interval == 0:
                        frame = gif.convert("RGB")
                        frame_filename = os.path.join(output_folder, f"frame_{saved_count:04d}.png")
                        frame.save(frame_filename, "PNG")
                        saved_count += 1
                    
                    frame_count += 1
                    gif.seek(gif.tell() + 1)
            except EOFError:
                pass
        
        return saved_count
    
    def extract_frames(self, file_path, output_name, target_fps=0):
        """
        Extrae frames de video o GIF automaticamente
        
        Args:
            file_path: Ruta al archivo
            output_name: Nombre de la carpeta de salida
            target_fps: FPS objetivo
        
        Returns:
            tuple: (numero_frames, ruta_output)
        """
        output_folder = os.path.join(self.sprites_dir, output_name)
        _, ext = os.path.splitext(file_path.lower())
        
        if ext == '.gif':
            count = self.extract_from_gif(file_path, output_folder, target_fps)
        else:
            count = self.extract_from_video(file_path, output_folder, target_fps)
        
        return count, output_folder