import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
import cv2
import mss
import numpy as np
import os
import subprocess
from datetime import datetime, timedelta

class ScreenRecorder:
    def __init__(self, master):
        self.master = master
        master.title("Запись экрана")
        
        master.geometry("450x50") 
        master.resizable(False, False) 
        
        master.attributes('-topmost', True) 

        self.recording = False
        self.paused = False
        self.output_filename = "" 
        self.video_writer = None
        self.record_thread = None

        self.record_x = 0
        self.record_y = 0
        self.record_width = 1920
        self.record_height = 1080

        self.start_time = None
        self.pause_start_time = None
        self.elapsed_time_on_pause = timedelta(seconds=0)
        self.timer_id = None

        self.create_widgets()

    def create_widgets(self):
        button_frame = tk.Frame(self.master)
        button_frame.pack(expand=True, fill=tk.BOTH)

        self.start_button = tk.Button(button_frame, text="▶️", font=("Segoe UI Symbol", 14), command=self.start_recording)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.pause_button = tk.Button(button_frame, text="⏸️", font=("Segoe UI Symbol", 14), command=self.pause_recording, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.stop_button = tk.Button(button_frame, text="⏹️", font=("Segoe UI Symbol", 14), command=self.stop_recording, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Кнопка для скриншота
        self.screenshot_button = tk.Button(button_frame, text="📷", font=("Segoe UI Symbol", 14), command=self.take_screenshot)
        self.screenshot_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.open_folder_button = tk.Button(button_frame, text="📁", font=("Segoe UI Symbol", 14), command=self.open_output_folder)
        self.open_folder_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.timer_label = tk.Label(button_frame, text="00:00:00", font=("Segoe UI", 14), fg="red")
        self.timer_label.pack(side=tk.RIGHT, padx=5, pady=5)

    def update_timer(self):
        if self.recording and not self.paused and self.start_time:
            current_elapsed_time = (datetime.now() - self.start_time) - self.elapsed_time_on_pause
            
            total_seconds = int(current_elapsed_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
            self.timer_label.config(text=time_str)
        
        self.timer_id = self.master.after(1000, self.update_timer)

    def record_screen(self):
        sct = mss.mss()
        monitor = {"top": self.record_y, "left": self.record_x,
                   "width": self.record_width, "height": self.record_height}

        fps = 60
        fourcc = cv2.VideoWriter_fourcc(*'avc1') 

        width_aligned = self.record_width - (self.record_width % 2)
        height_aligned = self.record_height - (self.record_height % 2)

        self.video_writer = cv2.VideoWriter(self.output_filename, fourcc, fps, (width_aligned, height_aligned))

        if not self.video_writer.isOpened():
            messagebox.showerror("Ошибка", "Не удалось инициализировать VideoWriter. Возможно, кодек 'avc1' не поддерживается вашей установкой OpenCV или ОС.")
            self.stop_recording()
            return

        while self.recording:
            if not self.paused:
                try:
                    sct_img = sct.grab(monitor)
                    img = np.array(sct_img)
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

                    if img_rgb.shape[1] != width_aligned or img_rgb.shape[0] != height_aligned:
                        img_rgb = cv2.resize(img_rgb, (width_aligned, height_aligned))

                    self.video_writer.write(img_rgb)
                except mss.exception.ScreenShotError as e:
                    print(f"Ошибка захвата экрана: {e}. Возможно, область записи выходит за границы экрана.")
                    self.stop_recording()
                    break
                except Exception as e:
                    print(f"Произошла ошибка во время записи: {e}")
                    self.stop_recording()
                    break
            time.sleep(1 / fps)

        if self.video_writer:
            self.video_writer.release()
        print(f"Видео сохранено в: {os.path.abspath(self.output_filename)}")

    def start_recording(self):
        if self.recording:
            return

        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        self.output_filename = f"screen_record_{timestamp}.mov"

        self.recording = True
        self.paused = False
        
        self.start_time = datetime.now()
        self.pause_start_time = None
        self.elapsed_time_on_pause = timedelta(seconds=0)
        self.timer_label.config(text="00:00:00") 
        self.update_timer()

        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        self.screenshot_button.config(state=tk.DISABLED) 

        self.record_thread = threading.Thread(target=self.record_screen)
        self.record_thread.start()

    def pause_recording(self):
        if self.recording:
            self.paused = not self.paused
            if self.paused:
                self.pause_button.config(text="▶️")
                if self.timer_id:
                    self.master.after_cancel(self.timer_id)
                self.pause_start_time = datetime.now() 
            else:
                self.pause_button.config(text="⏸️")
                if self.pause_start_time:
                    self.elapsed_time_on_pause += (datetime.now() - self.pause_start_time)
                self.pause_start_time = None
                self.update_timer()

    def stop_recording(self):
        if not self.recording:
            return

        self.recording = False
        if self.timer_id:
            self.master.after_cancel(self.timer_id)
        self.timer_label.config(text="00:00:00")

        if self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=5)
            if self.record_thread.is_alive():
                print("Предупреждение: Поток записи не завершился вовремя.")

        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED, text="⏸️")
        self.stop_button.config(state=tk.DISABLED)
        self.screenshot_button.config(state=tk.NORMAL) 
        
        print(f"Видео сохранено в: {os.path.abspath(self.output_filename)}")

    def take_screenshot(self):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] 
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                img_rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                
                now = datetime.now()
                timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
                
                output_dir = os.path.dirname(self.output_filename) if self.output_filename else os.getcwd()
                os.makedirs(output_dir, exist_ok=True)
                
                screenshot_filename = os.path.join(output_dir, f"screenshot_{timestamp}.jpg")
                
                cv2.imwrite(screenshot_filename, img_rgb)
                
                # --- Изменения здесь: Обратная связь на кнопке ---
                self.screenshot_button.config(text="✅") # Меняем текст на кнопке на галочку
                self.master.after(1000, lambda: self.screenshot_button.config(text="📷")) # Возвращаем через 1 секунду
                # --- Конец изменений ---

                print(f"Скриншот сохранен в: {os.path.abspath(screenshot_filename)}")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сделать скриншот: {e}")
            print(f"Ошибка скриншота: {e}")

    def open_output_folder(self):
        folder_path = os.path.dirname(self.output_filename)
        if not folder_path or not os.path.exists(folder_path): 
            folder_path = os.getcwd()

        try:
            if os.name == 'nt':
                os.startfile(folder_path)
            elif os.uname().sysname == 'Darwin':
                subprocess.run(['open', folder_path])
            else:
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть папку: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenRecorder(root)
    root.mainloop()
