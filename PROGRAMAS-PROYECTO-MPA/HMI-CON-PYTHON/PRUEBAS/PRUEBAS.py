"""
╔══════════════════════════════════════════════════════╗
║         MPA - HMI Dashboard v5                       ║
║         Cámara al centro, datos alrededor            ║
╚══════════════════════════════════════════════════════╝
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports
from pymodbus.client import ModbusSerialClient
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import time, csv, os, threading, datetime
from collections import deque
import cv2
import numpy as np

# ── CONFIGURACIÓN ──────────────────────────────────────
DIRECCION_SENSOR = 20
BAUDRATE         = 9600
MAX_GRAFICA      = 50
INTERVALO_MS     = 2000
CAMARA_INDEX     = 1
CAMARA_BACKEND   = cv2.CAP_DSHOW

# ── COLORES ────────────────────────────────────────────
C_BG     = "#0D1117"
C_PANEL  = "#161B22"
C_BORDE  = "#21262D"
C_ACENTO = "#00E5A0"
C_TEMP   = "#FF6B6B"
C_HUM    = "#4FC3F7"
C_PPM    = "#FFB347"
C_TERMO  = "#FF4ECD"
C_TXT    = "#E6EDF3"
C_SUB    = "#8B949E"
C_CSV    = "#238636"


# ═══════════════════════════════════════════════════════
# SPLASH
# ═══════════════════════════════════════════════════════
class SplashScreen:
    def __init__(self, root, callback):
        self.root = root
        self.callback = callback
        root.overrideredirect(True)
        root.configure(bg=C_BG)
        w, h = 460, 360
        x = (root.winfo_screenwidth()  - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
        frame = tk.Frame(root, bg=C_BG)
        frame.pack(expand=True, fill="both")
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
            img = Image.open(path).convert("RGBA").resize((160, 160), Image.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
            tk.Label(frame, image=self.logo_img, bg=C_BG).pack(pady=(28, 6))
        except:
            tk.Label(frame, text="MPA", font=("Consolas", 48, "bold"),
                     bg=C_BG, fg=C_ACENTO).pack(pady=(40, 8))
        tk.Label(frame, text="Sistema de Monitoreo Avícola",
                 font=("Consolas", 11), bg=C_BG, fg=C_SUB).pack()
        self.progress = ttk.Progressbar(frame, length=280, mode="determinate")
        self.progress.pack(pady=18)
        self.lbl = tk.Label(frame, text="Iniciando...",
                            font=("Consolas", 9), bg=C_BG, fg=C_SUB)
        self.lbl.pack()
        s = ttk.Style()
        s.theme_use("default")
        s.configure("TProgressbar", troughcolor=C_BORDE,
                    background=C_ACENTO, thickness=5)
        root.after(100, self._animar)

    def _animar(self, v=0):
        msgs = ["Iniciando sistema...", "Cargando módulos...",
                "Buscando sensores...", "Preparando HMI...", "¡Listo!"]
        if v <= 100:
            self.progress["value"] = v
            self.lbl.config(text=msgs[min(v // 25, 4)])
            self.root.after(25, self._animar, v + 2)
        else:
            self.root.after(300, self.callback)


# ═══════════════════════════════════════════════════════
# SELECCIÓN DE PUERTO
# ═══════════════════════════════════════════════════════
class VentanaPuerto:
    def __init__(self, root, callback):
        self.root = root
        self.callback = callback
        root.title("MPA — Conectar Sensor")
        root.configure(bg=C_BG)
        root.resizable(False, False)
        w, h = 440, 260
        x = (root.winfo_screenwidth()  - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
        tk.Label(root, text="📡  Puerto COM — Sensor Temp/Humedad",
                 font=("Consolas", 12, "bold"), bg=C_BG, fg=C_ACENTO).pack(pady=(28, 8))
        self.puertos = list(serial.tools.list_ports.comports())
        nombres = [f"{p.device}  —  {p.description}" for p in self.puertos]
        self.combo = ttk.Combobox(root, values=nombres, state="readonly",
                                  width=44, font=("Consolas", 9))
        if nombres:
            self.combo.current(0)
        self.combo.pack(pady=8)
        self.lbl_err = tk.Label(root, text="", font=("Consolas", 9),
                                bg=C_BG, fg=C_TEMP)
        self.lbl_err.pack()
        tk.Button(root, text="  CONECTAR  ", font=("Consolas", 10, "bold"),
                  bg=C_ACENTO, fg=C_BG, relief="flat", cursor="hand2",
                  padx=14, pady=7, command=self._conectar).pack(pady=14)
        tk.Button(root, text="Actualizar puertos", font=("Consolas", 8),
                  bg=C_PANEL, fg=C_SUB, relief="flat",
                  cursor="hand2", command=self._actualizar).pack()

    def _actualizar(self):
        self.puertos = list(serial.tools.list_ports.comports())
        nombres = [f"{p.device}  —  {p.description}" for p in self.puertos]
        self.combo["values"] = nombres
        if nombres:
            self.combo.current(0)

    def _conectar(self):
        if not self.puertos:
            self.lbl_err.config(text="❌ No hay puertos disponibles.")
            return
        puerto = self.puertos[self.combo.current()].device
        self.lbl_err.config(text=f"Conectando a {puerto}...", fg=C_ACENTO)
        self.root.after(100, lambda: self.callback(puerto))


# ═══════════════════════════════════════════════════════
# DASHBOARD PRINCIPAL
# ═══════════════════════════════════════════════════════
class HMIPrincipal:
    def __init__(self, root, puerto):
        self.root      = root
        self.puerto    = puerto
        self.cliente   = None
        self.corriendo = False

        self.buf_temp  = deque(maxlen=MAX_GRAFICA)
        self.buf_hum   = deque(maxlen=MAX_GRAFICA)
        self.buf_termo = deque(maxlen=MAX_GRAFICA)
        self.buf_ppm   = deque(maxlen=MAX_GRAFICA)
        self.datos_csv = []

        root.title("MPA — Dashboard de Monitoreo")
        root.configure(bg=C_BG)
        root.state("zoomed")

        self._build_ui()
        self._conectar_sensor()
        self._actualizar_reloj()

    # ── BUILD UI ───────────────────────────────────────
    def _build_ui(self):
        # HEADER
        hdr = tk.Frame(self.root, bg=C_BG)
        hdr.pack(fill="x", padx=14, pady=(10, 6))

        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
            img = Image.open(path).convert("RGBA").resize((38, 38), Image.LANCZOS)
            self._logo_hdr = ImageTk.PhotoImage(img)
            tk.Label(hdr, image=self._logo_hdr, bg=C_BG).pack(side="left", padx=(0, 8))
        except:
            pass

        tk.Label(hdr, text="MPA — Sistema de Monitoreo Avícola",
                 font=("Consolas", 14, "bold"), bg=C_BG, fg=C_ACENTO).pack(side="left")

        self.lbl_estado = tk.Label(hdr, text="⬤  Conectando...",
                                    font=("Consolas", 9), bg=C_BG, fg=C_PPM)
        self.lbl_estado.pack(side="right", padx=(10, 0))
        self.lbl_reloj = tk.Label(hdr, text="", font=("Consolas", 10),
                                   bg=C_BG, fg=C_SUB)
        self.lbl_reloj.pack(side="right")

        tk.Frame(self.root, bg=C_BORDE, height=1).pack(fill="x", padx=14, pady=(0, 6))

        # ── BODY: layout dashboard ──
        body = tk.Frame(self.root, bg=C_BG)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        body.columnconfigure(0, weight=1)   # columna izquierda
        body.columnconfigure(1, weight=3)   # cámara — más ancha
        body.columnconfigure(2, weight=1)   # columna derecha
        body.rowconfigure(0, weight=3)      # fila principal
        body.rowconfigure(1, weight=1)      # fila gráficas

        # ── COL IZQUIERDA ──────────────────────────────
        left = tk.Frame(body, bg=C_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        left.rowconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        self._card_valor(left, 0, "🌡️ TEMPERATURA", C_TEMP, "°C",
                         "lbl_temp")
        self._card_valor(left, 1, "💧 HUMEDAD", C_HUM, "%RH",
                         "lbl_hum")
        self._card_valor(left, 2, "💨 AMONIACO", C_PPM, "PPM",
                         "lbl_ppm", placeholder="Sin sensor")

        # ── CÁMARA CENTRAL ─────────────────────────────
        cam_outer = tk.Frame(body, bg=C_PANEL,
                             highlightbackground=C_TERMO, highlightthickness=2)
        cam_outer.grid(row=0, column=1, sticky="nsew", padx=6, pady=(0, 6))

        hdr_cam = tk.Frame(cam_outer, bg=C_PANEL)
        hdr_cam.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(hdr_cam, text="📷  CÁMARA TÉRMICA — UTi260B",
                 font=("Consolas", 10, "bold"), bg=C_PANEL,
                 fg=C_TERMO).pack(side="left")
        self.lbl_fps = tk.Label(hdr_cam, text="-- FPS",
                                 font=("Consolas", 8), bg=C_PANEL, fg=C_SUB)
        self.lbl_fps.pack(side="right")

        tk.Frame(cam_outer, bg=C_TERMO, height=2).pack(fill="x", padx=10, pady=(0, 6))

        self.canvas_cam = tk.Label(cam_outer, bg="#050505",
                                    text="Iniciando cámara...",
                                    font=("Consolas", 11), fg=C_SUB)
        self.canvas_cam.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # ── COL DERECHA ────────────────────────────────
        right = tk.Frame(body, bg=C_BG)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0), pady=(0, 6))
        right.rowconfigure(0, weight=2)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        # Panel pollos
        pollos_frame = tk.Frame(right, bg=C_PANEL,
                                highlightbackground=C_TERMO, highlightthickness=1)
        pollos_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        tk.Label(pollos_frame, text="🐔  POLLOS",
                 font=("Consolas", 10, "bold"), bg=C_PANEL,
                 fg=C_TERMO).pack(pady=(10, 2))
        tk.Frame(pollos_frame, bg=C_TERMO, height=2).pack(fill="x", padx=10)

        self.lbl_n_pollos = tk.Label(pollos_frame, text="--",
                                      font=("Consolas", 42, "bold"),
                                      bg=C_PANEL, fg=C_TERMO)
        self.lbl_n_pollos.pack(pady=(4, 0))
        tk.Label(pollos_frame, text="detectados",
                 font=("Consolas", 8), bg=C_PANEL, fg=C_SUB).pack()

        self.buf_txt_cam = tk.Text(pollos_frame, height=5,
                                    font=("Consolas", 8), bg=C_BG,
                                    fg=C_TXT, bd=0, state="disabled")
        self.buf_txt_cam.pack(fill="both", expand=True,
                               padx=10, pady=(6, 10))

        # Botón CSV
        csv_frame = tk.Frame(right, bg=C_PANEL,
                             highlightbackground=C_BORDE, highlightthickness=1)
        csv_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 6))

        tk.Button(csv_frame, text="💾  GUARDAR CSV",
                  font=("Consolas", 9, "bold"),
                  bg=C_CSV, fg="white", relief="flat", cursor="hand2",
                  padx=10, pady=8, command=self._exportar_csv).pack(
                  fill="x", padx=10, pady=(10, 4))
        self.lbl_csv = tk.Label(csv_frame, text="",
                                 font=("Consolas", 7), bg=C_PANEL,
                                 fg=C_ACENTO, wraplength=160)
        self.lbl_csv.pack(pady=(0, 8))

        # Info conexión
        info_frame = tk.Frame(right, bg=C_PANEL,
                              highlightbackground=C_BORDE, highlightthickness=1)
        info_frame.grid(row=2, column=0, sticky="nsew")

        tk.Label(info_frame,
                 text=f"Puerto: {self.puerto}\nSlave: {DIRECCION_SENSOR}\n{BAUDRATE} baud",
                 font=("Consolas", 8), bg=C_PANEL, fg=C_SUB,
                 justify="center").pack(pady=10)

        self.lbl_n_reg = tk.Label(info_frame, text="Registros: 0",
                                   font=("Consolas", 8), bg=C_PANEL, fg=C_SUB)
        self.lbl_n_reg.pack(pady=(0, 8))

        # ── FILA INFERIOR — GRÁFICAS ───────────────────
        graf_row = tk.Frame(body, bg=C_BG)
        graf_row.grid(row=1, column=0, columnspan=3,
                      sticky="nsew", pady=(0, 0))
        graf_row.columnconfigure(0, weight=2)
        graf_row.columnconfigure(1, weight=1)
        graf_row.columnconfigure(2, weight=1)
        graf_row.rowconfigure(0, weight=1)

        self._build_graf_ambiente(graf_row)
        self._build_graf_termo(graf_row)
        self._build_graf_ppm(graf_row)

    # ── CARD VALOR ─────────────────────────────────────
    def _card_valor(self, parent, row, titulo, color, unidad,
                    attr_name, placeholder=""):
        card = tk.Frame(parent, bg=C_PANEL,
                        highlightbackground=color, highlightthickness=2)
        card.grid(row=row, column=0, sticky="nsew",
                  pady=(0 if row == 0 else 6, 0))

        tk.Label(card, text=titulo, font=("Consolas", 9, "bold"),
                 bg=C_PANEL, fg=color).pack(pady=(10, 2))
        tk.Frame(card, bg=color, height=2).pack(fill="x", padx=10)

        lbl = tk.Label(card, text="--.-" if not placeholder else "--",
                       font=("Consolas", 38, "bold"),
                       bg=C_PANEL, fg=color)
        lbl.pack(pady=(4, 0))
        setattr(self, attr_name, lbl)

        tk.Label(card, text=unidad, font=("Consolas", 10),
                 bg=C_PANEL, fg=C_SUB).pack()
        if placeholder:
            tk.Label(card, text=placeholder, font=("Consolas", 7),
                     bg=C_PANEL, fg=C_SUB).pack(pady=(0, 6))

    # ── GRÁFICA AMBIENTE (Temp + Hum doble eje) ────────
    def _build_graf_ambiente(self, parent):
        f = tk.Frame(parent, bg=C_PANEL,
                     highlightbackground=C_BORDE, highlightthickness=1)
        f.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        tk.Label(f, text="📈 Temp & Humedad",
                 font=("Consolas", 8, "bold"), bg=C_PANEL,
                 fg=C_ACENTO).pack(anchor="w", padx=8, pady=(5, 2))

        self.fig_amb, self.ax_t = plt.subplots(figsize=(6, 1.8),
                                                facecolor=C_PANEL)
        self.fig_amb.subplots_adjust(left=0.08, right=0.92,
                                      top=0.85, bottom=0.2)
        self.ax_t.set_facecolor(C_BG)
        self.ax_t.tick_params(colors=C_TEMP, labelsize=7)
        self.ax_t.set_ylabel("°C", color=C_TEMP, fontsize=7)
        for sp in self.ax_t.spines.values():
            sp.set_color(C_BORDE)

        self.ax_h = self.ax_t.twinx()
        self.ax_h.tick_params(colors=C_HUM, labelsize=7)
        self.ax_h.set_ylabel("%RH", color=C_HUM, fontsize=7)
        self.ax_h.spines["right"].set_color(C_HUM)
        for sp in ["top", "bottom", "left"]:
            self.ax_h.spines[sp].set_color(C_BORDE)

        self.line_t, = self.ax_t.plot([], [], color=C_TEMP, linewidth=1.8)
        self.line_h, = self.ax_h.plot([], [], color=C_HUM,
                                       linewidth=1.8, linestyle="--")

        self.canvas_amb = FigureCanvasTkAgg(self.fig_amb, master=f)
        self.canvas_amb.get_tk_widget().pack(fill="both", expand=True,
                                              padx=6, pady=(0, 6))

    # ── GRÁFICA TÉRMICA ────────────────────────────────
    def _build_graf_termo(self, parent):
        f = tk.Frame(parent, bg=C_PANEL,
                     highlightbackground=C_BORDE, highlightthickness=1)
        f.grid(row=0, column=1, sticky="nsew", padx=5)

        tk.Label(f, text="🌡️ Temp. Pollos",
                 font=("Consolas", 8, "bold"), bg=C_PANEL,
                 fg=C_TERMO).pack(anchor="w", padx=8, pady=(5, 2))

        self.fig_termo, self.ax_termo = plt.subplots(figsize=(3, 1.8),
                                                      facecolor=C_PANEL)
        self.fig_termo.subplots_adjust(left=0.14, right=0.97,
                                        top=0.85, bottom=0.2)
        self.ax_termo.set_facecolor(C_BG)
        self.ax_termo.tick_params(colors=C_TERMO, labelsize=7)
        self.ax_termo.set_ylabel("°C", color=C_TERMO, fontsize=7)
        for sp in self.ax_termo.spines.values():
            sp.set_color(C_BORDE)

        self.line_termo, = self.ax_termo.plot([], [], color=C_TERMO,
                                               linewidth=1.8)

        self.canvas_termo = FigureCanvasTkAgg(self.fig_termo, master=f)
        self.canvas_termo.get_tk_widget().pack(fill="both", expand=True,
                                                padx=6, pady=(0, 6))

    # ── GRÁFICA PPM ────────────────────────────────────
    def _build_graf_ppm(self, parent):
        f = tk.Frame(parent, bg=C_PANEL,
                     highlightbackground=C_BORDE, highlightthickness=1)
        f.grid(row=0, column=2, sticky="nsew", padx=(5, 0))

        tk.Label(f, text="💨 Amoniaco PPM",
                 font=("Consolas", 8, "bold"), bg=C_PANEL,
                 fg=C_PPM).pack(anchor="w", padx=8, pady=(5, 2))

        self.fig_ppm, self.ax_ppm = plt.subplots(figsize=(3, 1.8),
                                                   facecolor=C_PANEL)
        self.fig_ppm.subplots_adjust(left=0.14, right=0.97,
                                      top=0.85, bottom=0.2)
        self.ax_ppm.set_facecolor(C_BG)
        self.ax_ppm.tick_params(colors=C_PPM, labelsize=7)
        self.ax_ppm.set_ylabel("PPM", color=C_PPM, fontsize=7)
        for sp in self.ax_ppm.spines.values():
            sp.set_color(C_BORDE)

        self.line_ppm, = self.ax_ppm.plot([], [], color=C_PPM, linewidth=1.8)

        self.canvas_ppm = FigureCanvasTkAgg(self.fig_ppm, master=f)
        self.canvas_ppm.get_tk_widget().pack(fill="both", expand=True,
                                              padx=6, pady=(0, 6))

    # ── RELOJ ──────────────────────────────────────────
    def _actualizar_reloj(self):
        self.lbl_reloj.config(
            text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._actualizar_reloj)

    # ── CONEXIÓN SENSOR ────────────────────────────────
    def _conectar_sensor(self):
        self.cliente = ModbusSerialClient(
            port=self.puerto, baudrate=BAUDRATE,
            bytesize=8, parity='N', stopbits=1,
            timeout=1, framer="rtu"
        )
        if self.cliente.connect():
            self.lbl_estado.config(text="⬤  Conectado", fg=C_ACENTO)
            self.corriendo = True
            threading.Thread(target=self._loop_sensor,  daemon=True).start()
            threading.Thread(target=self._loop_camara,  daemon=True).start()
        else:
            self.lbl_estado.config(text="⬤  Error sensor", fg=C_TEMP)
            self.corriendo = True
            threading.Thread(target=self._loop_camara,  daemon=True).start()

    # ── LOOP SENSOR ────────────────────────────────────
    def _loop_sensor(self):
        while self.corriendo:
            temp, hum = None, None
            try:
                res = self.cliente.read_input_registers(
                    address=0x0001, count=2, device_id=DIRECCION_SENSOR)
                if not res.isError():
                    raw_t = res.registers[0]
                    raw_h = res.registers[1]
                    if raw_t > 32767:
                        raw_t -= 65536
                    temp = raw_t / 10.0
                    hum  = raw_h / 10.0
            except Exception:
                pass
            ts = datetime.datetime.now()
            self.root.after(0, self._actualizar_datos, temp, hum, ts)
            time.sleep(INTERVALO_MS / 1000)

    # ── LOOP CÁMARA ────────────────────────────────────
    def _loop_camara(self):
        cap = cv2.VideoCapture(CAMARA_INDEX, CAMARA_BACKEND)
        if not cap.isOpened():
            self.root.after(0, lambda: self.canvas_cam.config(
                text="❌ Cámara no disponible", fg=C_TEMP))
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        t_prev = time.time()
        while self.corriendo:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            try:
                # FPS
                now  = time.time()
                fps  = 1.0 / max(now - t_prev, 0.001)
                t_prev = now

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                w = self.canvas_cam.winfo_width()
                h = self.canvas_cam.winfo_height()
                if w > 10 and h > 10:
                    frame_rgb = cv2.resize(frame_rgb, (w, h),
                                           interpolation=cv2.INTER_LINEAR)
                img_tk = ImageTk.PhotoImage(Image.fromarray(frame_rgb))
                self.root.after(0, self._mostrar_frame, img_tk, fps)
            except Exception:
                pass
            time.sleep(1 / 25)

        cap.release()

    def _mostrar_frame(self, img_tk, fps):
        try:
            self.canvas_cam.config(image=img_tk, text="")
            self.canvas_cam._img = img_tk
            self.lbl_fps.config(text=f"{fps:.1f} FPS")
        except Exception:
            pass

    # ── ACTUALIZAR DATOS ───────────────────────────────
    def _actualizar_datos(self, temp, hum, ts):
        ts_str = ts.strftime("%H:%M:%S")

        try:
            if temp is not None:
                self.lbl_temp.config(text=f"{temp:.1f}", fg=C_TEMP)
                self.buf_temp.append(temp)
            else:
                self.lbl_temp.config(text="ERR", fg="#444")
        except Exception:
            pass

        try:
            if hum is not None:
                self.lbl_hum.config(text=f"{hum:.1f}", fg=C_HUM)
                self.buf_hum.append(hum)
            else:
                self.lbl_hum.config(text="ERR", fg="#444")
        except Exception:
            pass

        try:
            if temp is not None:
                self.datos_csv.append([
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    f"{temp:.1f}", f"{hum:.1f}" if hum else "--", "--"
                ])
                self.lbl_n_reg.config(text=f"Registros: {len(self.datos_csv)}")
        except Exception:
            pass

        self._graf_ambiente()
        self._graf_termo()
        self._graf_ppm()

    # ── GRÁFICAS UPDATE ────────────────────────────────
    def _graf_ambiente(self):
        try:
            dt = list(self.buf_temp)
            dh = list(self.buf_hum)
            if len(dt) >= 2:
                self.line_t.set_data(range(len(dt)), dt)
                self.ax_t.relim(); self.ax_t.autoscale_view()
            if len(dh) >= 2:
                self.line_h.set_data(range(len(dh)), dh)
                self.ax_h.relim(); self.ax_h.autoscale_view()
            if len(dt) >= 2 or len(dh) >= 2:
                self.canvas_amb.draw()
        except Exception:
            pass

    def _graf_termo(self):
        try:
            datos = list(self.buf_termo)
            if len(datos) >= 2:
                self.line_termo.set_data(range(len(datos)), datos)
                self.ax_termo.relim(); self.ax_termo.autoscale_view()
                self.canvas_termo.draw()
        except Exception:
            pass

    def _graf_ppm(self):
        try:
            datos = list(self.buf_ppm)
            if len(datos) >= 2:
                self.line_ppm.set_data(range(len(datos)), datos)
                self.ax_ppm.relim(); self.ax_ppm.autoscale_view()
                self.canvas_ppm.draw()
        except Exception:
            pass

    # ── EXPORTAR CSV ───────────────────────────────────
    def _exportar_csv(self):
        if not self.datos_csv:
            messagebox.showwarning("Sin datos", "Aún no hay datos.")
            return
        nombre = f"datos_mpa_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        ruta   = os.path.join(os.path.dirname(os.path.abspath(__file__)), nombre)
        try:
            with open(ruta, "w", newline="") as file:
                w = csv.writer(file)
                w.writerow(["Timestamp", "Temperatura (°C)",
                             "Humedad (%RH)", "Amoniaco (PPM)"])
                w.writerows(self.datos_csv)
            self.lbl_csv.config(text=f"✅ {nombre}")
            messagebox.showinfo("CSV Exportado", f"Guardado en:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")


# ═══════════════════════════════════════════════════════
# FLUJO PRINCIPAL
# ═══════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    root.withdraw()

    def abrir_puerto():
        root.destroy()
        r2 = tk.Tk()
        VentanaPuerto(r2, lambda p: abrir_hmi(r2, p))
        r2.mainloop()

    def abrir_hmi(rp, puerto):
        rp.destroy()
        r3 = tk.Tk()
        HMIPrincipal(r3, puerto)
        r3.mainloop()

    splash = tk.Toplevel(root)
    SplashScreen(splash, abrir_puerto)
    root.mainloop()

if __name__ == "__main__":
    main()