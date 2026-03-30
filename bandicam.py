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
import json
import webbrowser   # ← добавлено для открытия ссылок

# ─── Палитра цветов ───────────────────────────────────────────────────────────
BG       = "#000205" # "#1a1a2e" 
BG2      = "#16213e"
ACCENT   = "#e94560"
ACCENT2  = "#0f3460"
FG       = "#eaeaea"
FG2      = "#888aaa"
BTN_BG   = "#0f3460"
BTN_HOV  = "#1a4a8a"
MEDIA_BG  = "#1565a8"   # голубой — кнопки play/pause/stop
MEDIA_HOV = "#1e82d4"   # hover голубой

# Рамка захвата — тёмно-серый
REC_CLR       = "#1565a8"
REC_TITLEBAR  = "#2b2b2b"
REC_TITLE_FG  = "#cccccc"
REC_CLOSE_HOV = "#c0392b"
# ─────────────────────────────────────────────────────────────────────────────

TITLEBAR_H = 22   # высота псевдо-заголовка
T          = 4    # толщина боковых/нижней рамок
CORNER     = 14   # размер угловых ручек


class ScreenRecorder:
    def __init__(self, master):
        self.master = master
        master.withdraw()

        sw = master.winfo_screenwidth()
        sh = master.winfo_screenheight()

        self.record_width  = 742
        self.record_height = 340
        self.fps           = 60
        self.output_folder = os.getcwd()
        self.video_format  = ".wmv"
        self.window_width  = 660
        self.window_height = 32
        self.window_x      = None
        self.window_y      = None
        self.is_full_screen_mode = tk.BooleanVar(value=False)

        self.load_settings()

        if self.window_x is None:
            self.window_x = sw / 2 - self.window_width  / 2
        if self.window_y is None:
            self.window_y = sh / 2 - self.window_height / 2 - 100

        if self.is_full_screen_mode.get():
            self.record_width  = 742
            self.record_height = 340

        master.geometry(f"{int(self.window_width)}x{int(self.window_height)}"
                        f"+{int(self.window_x)}+{int(self.window_y)}")
        master.deiconify()
        master.overrideredirect(True)   # убираем стандартный titlebar Windows
        master.attributes('-topmost', True)
        master.configure(bg=BG)

        self.recording        = False
        self.paused           = False
        self.output_filename  = ""
        self.video_writer     = None
        self.record_thread    = None

        self.record_x = 0
        self.record_y = 0

        # True — область захвата двигается вместе с главным окном
        self.snapped = True

        self.start_time            = None
        self.pause_start_time      = None
        self.elapsed_time_on_pause = timedelta(seconds=0)
        self.timer_id              = None

        # frames[0] = titlebar, [1]=bottom, [2]=left, [3]=right,
        # [4]=corner-bottom-left, [5]=corner-bottom-right
        self.frames = []

        self.resize_mode     = None
        self.initial_width   = self.record_width
        self.initial_height  = self.record_height
        self._initial_area_x = 0
        self._initial_area_y = 0

        self._drag_start_x_root = 0
        self._drag_start_y_root = 0
        self._drag_start_area_x = 0
        self._drag_start_area_y = 0
        self.is_dragging = False

        self._main_drag_x = 0
        self._main_drag_y = 0

        self.video_format_var = tk.StringVar(self.master)
        self.video_format_var.set(self.video_format)
        self.video_format_var.trace('w', self.save_format_setting)

        self.create_widgets()
        self.default_start_bg = self.start_button.cget('bg')

        self.create_frames()
        self.master.bind("<Configure>", self.on_main_window_move)
        self.update_window_title()
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        # Первоначальное позиционирование после полной отрисовки окна
        self.master.after(50, self._initial_snap)

    # ══════════════════════════════════════════════════════════════════════════
    #  Главный UI
    # ══════════════════════════════════════════════════════════════════════════
    def create_widgets(self):
        bar = tk.Frame(self.master, bg=BG, cursor="fleur")
        bar.pack(expand=True, fill=tk.BOTH)

        # Перетаскивание главного окна (т.к. titlebar убран)
        bar.bind("<ButtonPress-1>",   self._main_drag_start)
        bar.bind("<B1-Motion>",       self._main_drag)

        def mk_btn(parent, text, cmd=None, state=tk.NORMAL, width=2, bg=BTN_BG, hov=BTN_HOV):
            b = tk.Button(
                parent, text=text, command=cmd, state=state,
                bg=bg, fg=FG, activebackground=hov, activeforeground=FG,
                relief=tk.FLAT, bd=0, padx=3, pady=0,
                font=("Segoe UI Symbol", 8), cursor="hand2", width=width
            )
            b.bind("<Enter>", lambda e: b.config(bg=hov))
            b.bind("<Leave>", lambda e: b.config(bg=bg))
            return b

        self.start_button = mk_btn(bar, "▶", self.start_recording, bg=MEDIA_BG, hov=MEDIA_HOV)
        self.start_button.pack(side=tk.LEFT, padx=(3, 1), pady=1)

        self.pause_button = mk_btn(bar, "⏸", self.pause_recording, tk.DISABLED, bg=MEDIA_BG, hov=MEDIA_HOV)
        self.pause_button.pack(side=tk.LEFT, padx=1, pady=1)

        self.stop_button = mk_btn(bar, "⏹", self.stop_recording, tk.DISABLED, bg=MEDIA_BG, hov=MEDIA_HOV)
        self.stop_button.pack(side=tk.LEFT, padx=1, pady=1)

        tk.Frame(bar, bg=ACCENT2, width=1, height=14).pack(side=tk.LEFT, padx=4, pady=2)

        self.screenshot_button = mk_btn(bar, "📷", self.take_screenshot, width=2)
        self.screenshot_button.pack(side=tk.LEFT, padx=1, pady=1)

        self.open_folder_button = mk_btn(bar, "📁", width=2)
        self.open_folder_button.pack(side=tk.LEFT, padx=1, pady=1)
        self.open_folder_button.bind("<Button-1>", self.open_output_folder)
        self.open_folder_button.bind("<Button-3>", self.ask_output_folder)

        tk.Frame(bar, bg=ACCENT2, width=1, height=14).pack(side=tk.LEFT, padx=4, pady=2)

        tk.Label(bar, text="Fmt", bg=BG, fg=FG2,
                 font=("Segoe UI", 6)).pack(side=tk.LEFT, padx=(0, 1))
        fmt_menu = tk.OptionMenu(bar, self.video_format_var, ".wmv", ".mp4")
        fmt_menu.config(bg=BTN_BG, fg=FG, activebackground=BTN_HOV,
                        activeforeground=FG, relief=tk.FLAT, bd=0,
                        font=("Segoe UI", 7), highlightthickness=0, pady=0)
        fmt_menu["menu"].config(bg=BG2, fg=FG, activebackground=ACCENT2, activeforeground=FG)
        fmt_menu.pack(side=tk.LEFT, padx=(0, 3), pady=1)

        # ── НОВАЯ КНОПКА ШЕСТЕРЁНКА (между форматом и чекбоксом Full) ──
        self.settings_button = mk_btn(bar, "⚙", self.show_about_window, width=2)
        self.settings_button.pack(side=tk.LEFT, padx=(3, 1), pady=1)

        # Кнопка закрытия — крайняя справа
        close_btn = tk.Button(
            bar, text="✕", command=self.on_closing,
            bg=BG, fg=FG2, activebackground=REC_CLOSE_HOV, activeforeground="white",
            relief=tk.FLAT, bd=0, padx=5, pady=0,
            font=("Segoe UI", 8, "bold"), cursor="hand2"
        )
        close_btn.pack(side=tk.RIGHT, pady=1)
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg=REC_CLOSE_HOV, fg="white"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg=BG, fg=FG2))

        tk.Label(bar, text="FPS", bg=BG, fg=FG2,
                 font=("Segoe UI", 6)).pack(side=tk.RIGHT, padx=(0, 1))
        self.fps_entry = tk.Entry(bar, width=3, font=("Segoe UI", 7),
                                  bg=BG2, fg=FG, insertbackground=FG,
                                  relief=tk.FLAT, bd=0)
        self.fps_entry.insert(0, str(self.fps))
        self.fps_entry.pack(side=tk.RIGHT, padx=(0, 3), pady=1)

        self.timer_label = tk.Label(bar, text="00:00:00",
                                    font=("Segoe UI", 8, "bold"), bg=BG, fg=ACCENT)
        self.timer_label.pack(side=tk.RIGHT, padx=3, pady=1)

        self.capture_mode_switch = tk.Checkbutton(
            bar, text="Full", variable=self.is_full_screen_mode,
            command=self.toggle_capture_mode,
            bg=BG, fg=FG2, selectcolor=BG2,
            activebackground=BG, activeforeground=FG, font=("Segoe UI", 7)
        )
        self.capture_mode_switch.pack(side=tk.RIGHT, padx=2, pady=1)

    # ── Перетаскивание главного окна ─────────────────────────────────────────
    def _main_drag_start(self, event):
        self._main_drag_x = event.x_root - self.master.winfo_x()
        self._main_drag_y = event.y_root - self.master.winfo_y()

    def _main_drag(self, event):
        nx = event.x_root - self._main_drag_x
        ny = event.y_root - self._main_drag_y
        self.master.geometry(f"+{nx}+{ny}")

    def save_format_setting(self, *args):
        self.video_format = self.video_format_var.get()
        self.save_settings()

    # ══════════════════════════════════════════════════════════════════════════
    #  Рамки захвата
    # ══════════════════════════════════════════════════════════════════════════
    def create_frames(self):
        if not self.frames:
            for _ in range(7):
                f = tk.Toplevel(self.master)
                f.overrideredirect(True)
                f.attributes('-topmost', True)
                f.config(bg=REC_CLR)
                self.frames.append(f)

        # ── [0] Псевдо-titlebar ─────────────────────────────────────────────
        tb = self.frames[0]
        tb.config(bg=REC_TITLEBAR, cursor="fleur")
        tb.bind("<ButtonPress-1>",   self._tb_press)
        tb.bind("<B1-Motion>",       self._tb_drag)
        tb.bind("<ButtonRelease-1>", self._tb_release)

        close_btn = tk.Button(
            tb, text="✕", fg=REC_TITLE_FG, bg=REC_TITLEBAR,
            activebackground=REC_CLOSE_HOV, activeforeground="white",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0,
            padx=8, pady=0, cursor="hand2",
            command=self.close_capture_frames
        )
        close_btn.pack(side=tk.RIGHT, fill=tk.Y)

        self._cap_title_lbl = tk.Label(
            tb, text="Окно захвата", fg=REC_TITLE_FG, bg=REC_TITLEBAR,
            font=("Segoe UI", 8), anchor="w", padx=6
        )
        self._cap_title_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._cap_title_lbl.bind("<ButtonPress-1>",   self._tb_press)
        self._cap_title_lbl.bind("<B1-Motion>",       self._tb_drag)
        self._cap_title_lbl.bind("<ButtonRelease-1>", self._tb_release)

        # ── [1] Нижняя рамка ────────────────────────────────────────────────
        self.frames[1].config(cursor="sb_v_double_arrow")
        self.frames[1].bind("<ButtonPress-1>",
            lambda e: (self._start_resize(e, 'height'), self.on_frame_drag_start(e)))
        self.frames[1].bind("<B1-Motion>",       self.on_resize_or_drag)
        self.frames[1].bind("<ButtonRelease-1>",
            lambda e: (self._end_resize(e), self.on_frame_drag_end(e)))

        # ── [2] Левая рамка ─────────────────────────────────────────────────
        self.frames[2].config(cursor="fleur")
        self.frames[2].bind("<ButtonPress-1>",   self.on_frame_drag_start)
        self.frames[2].bind("<B1-Motion>",       self.on_frame_drag)
        self.frames[2].bind("<ButtonRelease-1>", self.on_frame_drag_end)

        # ── [3] Правая рамка ────────────────────────────────────────────────
        self.frames[3].config(cursor="sb_h_double_arrow")
        self.frames[3].bind("<ButtonPress-1>",
            lambda e: (self._start_resize(e, 'right'), self.on_frame_drag_start(e)))
        self.frames[3].bind("<B1-Motion>",       self.on_resize_or_drag)
        self.frames[3].bind("<ButtonRelease-1>",
            lambda e: (self._end_resize(e), self.on_frame_drag_end(e)))

        # ── [4] Угол левый-нижний ────────────────────────────────────────────
        self.frames[4].config(cursor="size_nw_se")
        self.frames[4].bind("<ButtonPress-1>",
            lambda e: (self._start_resize(e, 'bottom_left'), self.on_frame_drag_start(e)))
        self.frames[4].bind("<B1-Motion>",       self.on_resize_or_drag)
        self.frames[4].bind("<ButtonRelease-1>",
            lambda e: (self._end_resize(e), self.on_frame_drag_end(e)))

        # ── [5] Угол правый-нижний ───────────────────────────────────────────
        self.frames[5].config(cursor="size_nw_se")
        self.frames[5].bind("<ButtonPress-1>",
            lambda e: (self._start_resize(e, 'bottom_right'), self.on_frame_drag_start(e)))
        self.frames[5].bind("<B1-Motion>",       self.on_resize_or_drag)
        self.frames[5].bind("<ButtonRelease-1>",
            lambda e: (self._end_resize(e), self.on_frame_drag_end(e)))

        # ── [6] Угол правый-верхний (ресайз ширины вправо + высоты вверх) ───
        self.frames[6].config(cursor="size_ne_sw")
        self.frames[6].bind("<ButtonPress-1>",
            lambda e: (self._start_resize(e, 'top_right'), self.on_frame_drag_start(e)))
        self.frames[6].bind("<B1-Motion>",       self.on_resize_or_drag)
        self.frames[6].bind("<ButtonRelease-1>",
            lambda e: (self._end_resize(e), self.on_frame_drag_end(e)))

        if not self.is_full_screen_mode.get():
            self.show_frames()
        else:
            self.hide_frames()

    # ── Titlebar drag ────────────────────────────────────────────────────────
    def _tb_press(self, event):
        self._drag_start_x_root = event.x_root
        self._drag_start_y_root = event.y_root
        self._drag_start_area_x = self.record_x
        self._drag_start_area_y = self.record_y
        self.is_dragging = True

    def _tb_drag(self, event):
        if not self.is_dragging:
            return
        dx = event.x_root - self._drag_start_x_root
        dy = event.y_root - self._drag_start_y_root
        if dx != 0 or dy != 0:
            self.snapped = False
        self.record_x = self._drag_start_area_x + dx
        self.record_y = self._drag_start_area_y + dy
        self._reposition_frames()
        self._update_cap_title()

    def _tb_release(self, event):
        self.is_dragging = False

    # ── Рамочный drag ────────────────────────────────────────────────────────
    def on_frame_drag_start(self, event):
        self._drag_start_x_root = event.x_root
        self._drag_start_y_root = event.y_root
        self._drag_start_area_x = self.record_x
        self._drag_start_area_y = self.record_y
        self.is_dragging = True

    def on_frame_drag(self, event):
        if not self.is_dragging or self.resize_mode:
            return
        dx = event.x_root - self._drag_start_x_root
        dy = event.y_root - self._drag_start_y_root
        if dx != 0 or dy != 0:
            self.snapped = False
        self.record_x = self._drag_start_area_x + dx
        self.record_y = self._drag_start_area_y + dy
        self._reposition_frames()
        self._update_cap_title()

    def on_frame_drag_end(self, event):
        self.is_dragging = False

    # ── Ресайз ──────────────────────────────────────────────────────────────
    def _start_resize(self, event, mode):
        self.resize_mode     = mode
        self.start_x         = event.x_root
        self.start_y         = event.y_root
        self.initial_width   = self.record_width
        self.initial_height  = self.record_height
        self._initial_area_x = self.record_x
        self._initial_area_y = self.record_y
        self.snapped = False

    def _end_resize(self, event):
        self.resize_mode = None

    def on_resize_or_drag(self, event):
        if self.resize_mode:
            dx = event.x_root - self.start_x
            dy = event.y_root - self.start_y

            if self.resize_mode == 'right':
                nw = self.initial_width + dx
                if nw > 60:
                    self.record_width = nw

            elif self.resize_mode == 'height':
                nh = self.initial_height + dy
                if nh > 60:
                    self.record_height = nh

            elif self.resize_mode == 'bottom_left':
                nw = self.initial_width  - dx
                nh = self.initial_height + dy
                if nw > 60:
                    self.record_width  = nw
                    self.record_x      = self._initial_area_x + dx
                if nh > 60:
                    self.record_height = nh

            elif self.resize_mode == 'bottom_right':
                nw = self.initial_width  + dx
                nh = self.initial_height + dy
                if nw > 60:
                    self.record_width  = nw
                if nh > 60:
                    self.record_height = nh

            elif self.resize_mode == 'top_right':
                # Правый верхний: ширина вправо, высота вверх (верхний край двигается)
                nw = self.initial_width  + dx
                nh = self.initial_height - dy
                if nw > 60:
                    self.record_width  = nw
                if nh > 60:
                    self.record_height = nh
                    self.record_y      = self._initial_area_y + dy

            self._reposition_frames()
            self._update_cap_title()
        elif self.is_dragging:
            self.on_frame_drag(event)

    # ══════════════════════════════════════════════════════════════════════════
    #  Позиционирование рамок
    # ══════════════════════════════════════════════════════════════════════════
    def _reposition_frames(self):
        """
        Все рамки — СНАРУЖИ области захвата (не перекрывают её).

          [0 titlebar H=TITLEBAR_H] — над областью, y = record_y - TITLEBAR_H
          [2 left  w=T]  [  capture area  ]  [3 right w=T]
                         [1 bottom h=T]
          [4 corner BL]                       [5 corner BR]
        """
        x  = int(self.record_x)
        y  = int(self.record_y)
        w  = int(self.record_width)
        h  = int(self.record_height)

        # [0] Titlebar
        self.frames[0].geometry(f"{w}x{TITLEBAR_H}+{x}+{y - TITLEBAR_H}")
        # [1] Нижняя рамка
        self.frames[1].geometry(f"{w}x{T}+{x}+{y + h}")
        # [2] Левая рамка
        self.frames[2].geometry(f"{T}x{h}+{x - T}+{y}")
        # [3] Правая рамка
        self.frames[3].geometry(f"{T}x{h}+{x + w}+{y}")
        # [4] Угол левый-нижний
        self.frames[4].geometry(f"{CORNER}x{CORNER}+{x - T}+{y + h}")
        # [5] Угол правый-нижний
        self.frames[5].geometry(f"{CORNER}x{CORNER}+{x + w - CORNER + T}+{y + h}")
        # [6] Угол правый-верхний — на правой рамке, у верхнего края capture area
        self.frames[6].geometry(f"{CORNER}x{CORNER}+{x + w}+{y - CORNER // 2}")

    def _update_cap_title(self):
        try:
            self._cap_title_lbl.config(
                text=f"Окно захвата  {int(self.record_width)}×{int(self.record_height)} px"
            )
        except Exception:
            pass

    def update_window_title(self):
        if not self.frames:
            return
        try:
            if self.is_full_screen_mode.get():
                self.master.title("📸 Запись — ВЕСЬ ЭКРАН")
            else:
                self.master.title(
                    f"📸 Запись  {int(self.record_width)}×{int(self.record_height)} px")
        except tk.TclError:
            self.master.title("📸 Запись экрана")
        self._update_cap_title()

    def _initial_snap(self):
        """Вызывается один раз после полной отрисовки — точно позиционирует окно захвата."""
        if self.is_full_screen_mode.get():
            return
        self.master.update_idletasks()
        mx = self.master.winfo_x()
        my = self.master.winfo_y()
        mh = self.master.winfo_height()
        # record_y — верхний край области захвата.
        # Titlebar рисуется ВЫШЕ (y - TITLEBAR_H), поэтому зазор считаем от низа главного окна:
        # главное окно заканчивается на my+mh, далее 4px зазор, потом titlebar (TITLEBAR_H), потом capture
        self.record_x = mx
        self.record_y = my + mh + 1 + TITLEBAR_H
        self.snapped  = True
        self._reposition_frames()
        self._update_cap_title()

    # ══════════════════════════════════════════════════════════════════════════
    #  Привязка к главному окну (snap)
    # ══════════════════════════════════════════════════════════════════════════
    def on_main_window_move(self, event):
        if self.is_full_screen_mode.get() or not self.frames:
            return

        mx = self.master.winfo_x()
        my = self.master.winfo_y()
        mh = self.master.winfo_height()

        if self.snapped:
            self.record_x = mx
            self.record_y = my + mh + 1 + TITLEBAR_H
            self._reposition_frames()

        self.update_window_title()

    def show_frames(self):
        for f in self.frames:
            f.deiconify()
        self.snapped = True
        self._initial_snap()

    def hide_frames(self):
        for f in self.frames:
            f.withdraw()

    def close_capture_frames(self):
        self.is_full_screen_mode.set(True)
        self.toggle_capture_mode()

    def toggle_capture_mode(self):
        if self.is_full_screen_mode.get():
            self.hide_frames()
            self.capture_mode_switch.config(text="Область")
            with mss.mss() as sct:
                m = sct.monitors[1]
                self.record_x      = m['left']
                self.record_y      = m['top']
                self.record_width  = m['width']
                self.record_height = m['height']
        else:
            self.capture_mode_switch.config(text="Весь экран")
            self.record_width  = 742
            self.record_height = 340
            self.snapped       = True
            self.show_frames()
            self.master.update()
        self.update_window_title()

    # ══════════════════════════════════════════════════════════════════════════
    #  Запись
    # ══════════════════════════════════════════════════════════════════════════
    def record_screen(self):
        try:
            fps = int(self.fps_entry.get())
            if fps <= 0:
                fps = 30
        except (ValueError, IndexError):
            fps = 30

        sct = mss.mss()

        if self.is_full_screen_mode.get():
            monitor = sct.monitors[1]
        else:
            monitor = {"top":    int(self.record_y),
                       "left":   int(self.record_x),
                       "width":  int(self.record_width),
                       "height": int(self.record_height)}

        fourcc    = cv2.VideoWriter_fourcc(*('mp4v' if self.video_format == ".mp4" else 'WMV2'))
        extension = self.video_format

        w_al = monitor["width"]  - (monitor["width"]  % 2)
        h_al = monitor["height"] - (monitor["height"] % 2)

        os.makedirs(self.output_folder, exist_ok=True)
        self.output_filename = os.path.join(
            self.output_folder,
            f"screen_record_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}{extension}"
        )
        self.video_writer = cv2.VideoWriter(
            self.output_filename, fourcc, fps, (w_al, h_al))

        if not self.video_writer.isOpened():
            messagebox.showerror("Ошибка",
                f"Не удалось инициализировать VideoWriter для {extension}.")
            self.stop_recording()
            return

        while self.recording:
            frame_start = time.perf_counter()

            if not self.paused:
                try:
                    # Читаем координаты каждый кадр — так перемещение работает при записи
                    if not self.is_full_screen_mode.get():
                        monitor = {
                            "top":    int(self.record_y),
                            "left":   int(self.record_x),
                            "width":  w_al,
                            "height": h_al,
                        }
                    sct_img = sct.grab(monitor)
                    img     = np.array(sct_img)
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                    if img_rgb.shape[1] != w_al or img_rgb.shape[0] != h_al:
                        img_rgb = cv2.resize(img_rgb, (w_al, h_al))
                    self.video_writer.write(img_rgb)
                except mss.exception.ScreenShotError as e:
                    print(f"Ошибка захвата: {e}")
                    self.stop_recording()
                    break
                except Exception as e:
                    print(f"Ошибка записи: {e}")
                    self.stop_recording()
                    break

            # Точный тайминг: спим ровно столько сколько осталось до следующего кадра
            elapsed = time.perf_counter() - frame_start
            sleep_time = (1.0 / fps) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        if self.video_writer:
            self.video_writer.release()
        print(f"Видео сохранено: {os.path.abspath(self.output_filename)}")

    def start_recording(self):
        if self.recording:
            return
        self.recording = True
        self.paused    = False
        self.start_time            = datetime.now()
        self.pause_start_time      = None
        self.elapsed_time_on_pause = timedelta(seconds=0)
        self.timer_label.config(text="00:00:00")
        self.update_timer()

        self.start_button.config(state=tk.DISABLED, bg=ACCENT)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        self.screenshot_button.config(state=tk.DISABLED)

        self.record_thread = threading.Thread(target=self.record_screen)
        self.record_thread.start()

    def pause_recording(self):
        if not self.recording:
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_button.config(text="▶")
            if self.timer_id:
                self.master.after_cancel(self.timer_id)
            self.pause_start_time = datetime.now()
        else:
            self.pause_button.config(text="⏸")
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

        self.start_button.config(state=tk.NORMAL, bg=MEDIA_BG)
        self.pause_button.config(state=tk.DISABLED, text="⏸")
        self.stop_button.config(state=tk.DISABLED)
        self.screenshot_button.config(state=tk.NORMAL)
        print(f"Видео сохранено: {os.path.abspath(self.output_filename)}")

    def update_timer(self):
        if self.recording and not self.paused and self.start_time:
            elapsed = (datetime.now() - self.start_time) - self.elapsed_time_on_pause
            total   = int(elapsed.total_seconds())
            h, rem  = divmod(total, 3600)
            m, s    = divmod(rem, 60)
            self.timer_label.config(text=f"{h:02}:{m:02}:{s:02}")
        self.timer_id = self.master.after(1000, self.update_timer)

    # ══════════════════════════════════════════════════════════════════════════
    #  Скриншот
    # ══════════════════════════════════════════════════════════════════════════
    def take_screenshot(self):
        try:
            with mss.mss() as sct:
                if self.is_full_screen_mode.get():
                    monitor = sct.monitors[1]
                else:
                    monitor = {"top":    int(self.record_y),
                               "left":   int(self.record_x),
                               "width":  int(self.record_width),
                               "height": int(self.record_height)}
                sct_img = sct.grab(monitor)
                img     = np.array(sct_img)
                img_rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

                os.makedirs(self.output_folder, exist_ok=True)
                ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                path = os.path.join(self.output_folder, f"screenshot_{ts}.jpg")
                ok, buf = cv2.imencode(".jpg", img_rgb)
                if ok:
                    with open(path, "wb") as f:
                        f.write(buf)
                else:
                    raise Exception("Ошибка кодирования")

                self.screenshot_button.config(text="✅")
                self.master.after(1000, lambda: self.screenshot_button.config(text="📷"))
                print(f"Скриншот: {os.path.abspath(path)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сделать скриншот: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  Папка
    # ══════════════════════════════════════════════════════════════════════════
    def open_output_folder(self, event=None):
        folder = self.output_folder if os.path.exists(self.output_folder) else os.getcwd()
        try:
            if os.name == 'nt':
                os.startfile(folder)
            elif os.uname().sysname == 'Darwin':
                subprocess.run(['open', folder])
            else:
                subprocess.run(['xdg-open', folder])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть папку: {e}")

    def ask_output_folder(self, event=None):
        new_folder = filedialog.askdirectory(initialdir=self.output_folder)
        if new_folder:
            self.output_folder = new_folder
            self.open_folder_button.config(fg="green")
            self.master.after(1000, lambda: self.open_folder_button.config(fg=FG))
            self.save_settings()

    # ══════════════════════════════════════════════════════════════════════════
    #  Настройки
    # ══════════════════════════════════════════════════════════════════════════
    def load_settings(self):
        try:
            with open("settings.json", "r") as f:
                s = json.load(f)
            self.record_width  = s.get("record_width",  self.record_width)
            self.record_height = s.get("record_height", self.record_height)
            self.fps           = s.get("fps",           self.fps)
            self.output_folder = s.get("output_folder", self.output_folder)
            self.video_format  = s.get("video_format",  self.video_format)
            self.window_x      = s.get("window_x",      None)
            self.window_y      = s.get("window_y",      None)
            self.window_width  = s.get("window_width",  self.window_width)
            self.is_full_screen_mode.set(s.get("is_full_screen_mode", False))
        except (FileNotFoundError, json.JSONDecodeError):
            print("Настройки не найдены, используем defaults.")

    def save_settings(self):
        try:
            fps_val = int(self.fps_entry.get())
        except (ValueError, AttributeError):
            fps_val = self.fps

        settings = {
            "record_width":        self.record_width,
            "record_height":       self.record_height,
            "fps":                 fps_val,
            "output_folder":       self.output_folder,
            "video_format":        self.video_format,
            "window_x":            self.master.winfo_x(),
            "window_y":            self.master.winfo_y(),
            "window_width":        self.master.winfo_width(),
            "window_height":       self.master.winfo_height(),
            "is_full_screen_mode": self.is_full_screen_mode.get(),
        }
        try:
            with open("settings.json", "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    #  НОВОЕ ОКНО «О ПРОГРАММЕ» (добавлено)
    # ──────────────────────────────────────────────────────────────────────────
    def show_about_window(self):
        about = tk.Toplevel(self.master)
        about.withdraw()
        about.overrideredirect(True)
        about.attributes('-topmost', True)
        about.configure(bg=BG)

        sw = about.winfo_screenwidth()
        sh = about.winfo_screenheight()
        w, h = 540, 460
        x = (sw - w) // 2
        y = (sh - h) // 2
        about.geometry(f"{w}x{h}+{x}+{y}")
        about.deiconify()

        # Псевдо-заголовок (точно как в рамке захвата)
        def start_drag(event):
            about._drag_x = event.x
            about._drag_y = event.y

        def do_drag(event):
            nx = about.winfo_x() + event.x - about._drag_x
            ny = about.winfo_y() + event.y - about._drag_y
            about.geometry(f"+{nx}+{ny}")

        tb = tk.Frame(about, bg=REC_TITLEBAR, height=TITLEBAR_H)
        tb.pack(fill=tk.X)
        tb.bind("<ButtonPress-1>", start_drag)
        tb.bind("<B1-Motion>", do_drag)

        close_btn = tk.Button(
            tb, text="✕", fg=REC_TITLE_FG, bg=REC_TITLEBAR,
            activebackground=REC_CLOSE_HOV, activeforeground="white",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0,
            padx=8, pady=0, cursor="hand2",
            command=about.destroy
        )
        close_btn.pack(side=tk.RIGHT, fill=tk.Y)

        title_lbl = tk.Label(
            tb, text="MyBandycam — О программе", fg=REC_TITLE_FG, bg=REC_TITLEBAR,
            font=("Segoe UI", 8, "bold"), anchor="w", padx=6
        )
        title_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        title_lbl.bind("<ButtonPress-1>", start_drag)
        title_lbl.bind("<B1-Motion>", do_drag)

        # Контент
        content = tk.Frame(about, bg=BG, padx=25, pady=20)
        content.pack(fill=tk.BOTH, expand=True)

        def open_url(url):
            def handler(e=None):
                webbrowser.open(url)
            return handler

        # Профессиональное оформление с разными стилями
        tk.Label(content, text="Программа MyBandycam v.1.0.0",
                 font=("Segoe UI", 14, "bold"), bg=BG, fg=ACCENT,
                 anchor="w", justify=tk.LEFT).pack(anchor="w", pady=(0, 12))

        tk.Label(content, text="1. Программа позволяет делать скриншоты экрана,\n"
                               "   запись видео в двух форматах:\n"
                               "   .mp4, .wmv",
                 font=("Segoe UI", 9), bg=BG, fg=FG,
                 anchor="w", justify=tk.LEFT).pack(anchor="w", pady=3)

        tk.Label(content, text="2. Позволяет менять FPS записи.",
                 font=("Segoe UI", 9), bg=BG, fg=FG,
                 anchor="w", justify=tk.LEFT).pack(anchor="w", pady=3)

        tk.Label(content, text="3. Работает в полноэкранном режиме (Full)",
                 font=("Segoe UI", 9), bg=BG, fg=FG,
                 anchor="w", justify=tk.LEFT).pack(anchor="w", pady=3)

        tk.Label(content, text="4. Работает в режиме окна захвата.",
                 font=("Segoe UI", 9), bg=BG, fg=FG,
                 anchor="w", justify=tk.LEFT).pack(anchor="w", pady=3)

        # GitHub (кликабельная ссылка)
        gh_frame = tk.Frame(content, bg=BG)
        gh_frame.pack(anchor="w", pady=4)
        tk.Label(gh_frame, text="   * GitHub проекта: ", 
                 font=("Segoe UI", 9), bg=BG, fg=FG).pack(side=tk.LEFT)
        link1 = tk.Label(gh_frame, text="https://github.com/pavekscb/mybandicam",
                         font=("Segoe UI", 9, "underline"), bg=BG, fg=ACCENT2, cursor="hand2")
        link1.pack(side=tk.LEFT)
        link1.bind("<Button-1>", open_url("https://github.com/pavekscb/mybandicam"))

        # Releases (кликабельная ссылка)
        rel_frame = tk.Frame(content, bg=BG)
        rel_frame.pack(anchor="w", pady=4)
        tk.Label(rel_frame, text="   * Готовый EXE файл для Windows (10) можно скачать в разделе ", 
                 font=("Segoe UI", 9), bg=BG, fg=FG).pack(side=tk.LEFT)
        link2 = tk.Label(rel_frame, text="https://github.com/pavekscb/mybandicam/releases",
                         font=("Segoe UI", 9, "underline"), bg=BG, fg=ACCENT2, cursor="hand2")
        link2.pack(side=tk.LEFT)
        link2.bind("<Button-1>", open_url("https://github.com/pavekscb/mybandicam/releases"))

        tk.Label(content, text="5. Что бы изменить папку сохранения файлов нажмите правую кнопку мышки на папку.",
                 font=("Segoe UI", 9), bg=BG, fg=FG,
                 anchor="w", justify=tk.LEFT).pack(anchor="w", pady=3)

    def on_closing(self):
        if self.is_full_screen_mode.get():
            self.record_width  = 742
            self.record_height = 340
        self.stop_recording()
        self.save_settings()
        self.master.destroy()


# ─── Запуск ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = ScreenRecorder(root)
    root.mainloop()
