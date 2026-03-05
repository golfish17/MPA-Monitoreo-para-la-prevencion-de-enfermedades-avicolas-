import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports
from pymodbus.client import ModbusSerialClient
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import time
import csv
import os
import threading
from collections import deque
import datetime

# ── CONFIGURACIÓN ──────────────────────────────────────
DIRECCION_SENSOR = 20
BAUDRATE         = 9600
MAX_BUFFER       = 10       # líneas en el buffer visual
MAX_GRAFICA      = 60       # puntos en la gráfica
INTERVALO_MS     = 2000     # ms entre lecturas

# ── COLORES Y FUENTES ──────────────────────────────────
COLOR_BG         = "#0D1117"
COLOR_PANEL      = "#161B22"
COLOR_BORDE      = "#21262D"
COLOR_ACENTO     = "#00E5A0"
COLOR_TEMP       = "#FF6B6B"
COLOR_HUM        = "#4FC3F7"
COLOR_TEXTO      = "#E6EDF3"
COLOR_SUBTEXTO   = "#8B949E"
FUENTE_TITULO    = ("Consolas", 13, "bold")
FUENTE_VALOR     = ("Consolas", 36, "bold")
FUENTE_UNIDAD    = ("Consolas", 13)
FUENTE_BUFFER    = ("Consolas", 9)
FUENTE_BTN       = ("Consolas", 10, "bold")

# ═══════════════════════════════════════════════════════
# SPLASH SCREEN
# ═══════════════════════════════════════════════════════
class SplashScreen:
    def __init__(self, root, callback):
        self.root = root
        self.callback = callback

        self.root.overrideredirect(True)
        self.root.configure(bg=COLOR_BG)

        ancho, alto = 480, 380
        x = (self.root.winfo_screenwidth()  - ancho) // 2
        y = (self.root.winfo_screenheight() - alto)  // 2
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")

        # Fondo
        frame = tk.Frame(self.root, bg=COLOR_BG)
        frame.pack(expand=True, fill="both")

        # Logo
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "RECURSOS-DATASHET-INFO\LOGOMPA.png")
            img = Image.open(logo_path).convert("RGBA").resize((180, 180), Image.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
            tk.Label(frame, image=self.logo_img, bg=COLOR_BG).pack(pady=(40, 10))
        except Exception:
            tk.Label(frame, text="🐔", font=("Consolas", 60), bg=COLOR_BG).pack(pady=(40, 10))

        tk.Label(frame, text="MPA", font=("Consolas", 32, "bold"),
                 bg=COLOR_BG, fg=COLOR_ACENTO).pack()

        tk.Label(frame, text="Sistema de Monitoreo Avícola",
                 font=("Consolas", 11), bg=COLOR_BG, fg=COLOR_SUBTEXTO).pack(pady=(4, 20))

        # Barra de progreso
        self.progress = ttk.Progressbar(frame, length=300, mode="determinate")
        self.progress.pack(pady=10)

        self.lbl_status = tk.Label(frame, text="Iniciando...",
                                   font=("Consolas", 9), bg=COLOR_BG, fg=COLOR_SUBTEXTO)
        self.lbl_status.pack()

        # Estilo barra
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TProgressbar", troughcolor=COLOR_BORDE,
                        background=COLOR_ACENTO, thickness=6)

        self.root.after(100, self.animar)

    def animar(self, paso=0):
        mensajes = [
            "Iniciando sistema...",
            "Cargando módulos...",
            "Buscando sensores...",
            "Preparando HMI...",
            "¡Listo!"
        ]
        if paso <= 100:
            self.progress["value"] = paso
            idx = min(paso // 25, len(mensajes) - 1)
            self.lbl_status.config(text=mensajes[idx])
            self.root.after(30, self.animar, paso + 2)
        else:
            self.root.after(400, self.callback)


# ═══════════════════════════════════════════════════════
# VENTANA DE SELECCIÓN DE PUERTO
# ═══════════════════════════════════════════════════════
class VentanaPuerto:
    def __init__(self, root, callback):
        self.root = root
        self.callback = callback

        self.root.title("MPA — Seleccionar Puerto")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        ancho, alto = 420, 280
        x = (self.root.winfo_screenwidth()  - ancho) // 2
        y = (self.root.winfo_screenheight() - alto)  // 2
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")

        tk.Label(self.root, text="📡  Seleccionar Puerto COM",
                 font=FUENTE_TITULO, bg=COLOR_BG, fg=COLOR_ACENTO).pack(pady=(30, 10))

        tk.Label(self.root, text="Adaptador USB-RS485 detectado:",
                 font=FUENTE_BUFFER, bg=COLOR_BG, fg=COLOR_SUBTEXTO).pack()

        # Lista de puertos
        self.puertos = list(serial.tools.list_ports.comports())
        nombres = [f"{p.device}  —  {p.description}" for p in self.puertos]

        self.combo = ttk.Combobox(self.root, values=nombres, state="readonly",
                                  width=45, font=("Consolas", 9))
        if nombres:
            self.combo.current(0)
        self.combo.pack(pady=12)

        # Estilo
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TCombobox", fieldbackground=COLOR_PANEL,
                        background=COLOR_PANEL, foreground=COLOR_TEXTO)

        self.lbl_info = tk.Label(self.root, text="",
                                 font=("Consolas", 9), bg=COLOR_BG, fg="#FF6B6B")
        self.lbl_info.pack()

        tk.Button(self.root, text="  CONECTAR  ", font=FUENTE_BTN,
                  bg=COLOR_ACENTO, fg=COLOR_BG, relief="flat",
                  cursor="hand2", command=self.conectar).pack(pady=16)

        tk.Button(self.root, text="Actualizar puertos", font=("Consolas", 8),
                  bg=COLOR_PANEL, fg=COLOR_SUBTEXTO, relief="flat",
                  cursor="hand2", command=self.actualizar).pack()

    def actualizar(self):
        self.puertos = list(serial.tools.list_ports.comports())
        nombres = [f"{p.device}  —  {p.description}" for p in self.puertos]
        self.combo["values"] = nombres
        if nombres:
            self.combo.current(0)

    def conectar(self):
        if not self.puertos:
            self.lbl_info.config(text="❌ No hay puertos disponibles.")
            return
        idx = self.combo.current()
        puerto = self.puertos[idx].device
        self.lbl_info.config(text=f"Conectando a {puerto}...", fg=COLOR_ACENTO)
        self.root.after(100, lambda: self.callback(puerto))


# ═══════════════════════════════════════════════════════
# HMI PRINCIPAL
# ═══════════════════════════════════════════════════════
class HMIPrincipal:
    def __init__(self, root, puerto):
        self.root = root
        self.puerto = puerto
        self.cliente = None
        self.corriendo = False

        # Datos
        self.buffer_temp = deque(maxlen=MAX_GRAFICA)
        self.buffer_hum  = deque(maxlen=MAX_GRAFICA)
        self.buffer_time = deque(maxlen=MAX_GRAFICA)
        self.log_buffer  = []
        self.datos_csv   = []

        self.root.title("MPA — Monitor de Ambiente")
        self.root.configure(bg=COLOR_BG)
        self.root.state("zoomed")  # maximizado

        self.construir_ui()
        self.conectar_sensor()

    # ── UI ─────────────────────────────────────────────
    def construir_ui(self):
        # ── HEADER ──
        header = tk.Frame(self.root, bg=COLOR_BG, height=60)
        header.pack(fill="x", padx=20, pady=(15, 5))

        try:
            logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
            img = Image.open(logo_path).convert("RGBA").resize((45, 45), Image.LANCZOS)
            self.logo_small = ImageTk.PhotoImage(img)
            tk.Label(header, image=self.logo_small, bg=COLOR_BG).pack(side="left", padx=(0, 10))
        except:
            pass

        tk.Label(header, text="MPA — Sistema de Monitoreo Avícola",
                 font=("Consolas", 16, "bold"), bg=COLOR_BG, fg=COLOR_ACENTO).pack(side="left")

        self.lbl_reloj = tk.Label(header, text="", font=("Consolas", 12),
                                   bg=COLOR_BG, fg=COLOR_SUBTEXTO)
        self.lbl_reloj.pack(side="right")
        self.actualizar_reloj()

        self.lbl_estado = tk.Label(header, text="⬤  Conectando...",
                                    font=("Consolas", 10), bg=COLOR_BG, fg="#FFB347")
        self.lbl_estado.pack(side="right", padx=20)

        # ── SEPARADOR ──
        tk.Frame(self.root, bg=COLOR_BORDE, height=1).pack(fill="x", padx=20)

        # ── TRIPTICO ──
        triptico = tk.Frame(self.root, bg=COLOR_BG)
        triptico.pack(fill="both", expand=True, padx=20, pady=10)

        triptico.columnconfigure(0, weight=1)
        triptico.columnconfigure(1, weight=1)
        triptico.columnconfigure(2, weight=1)
        triptico.rowconfigure(0, weight=1)

        # Panel 1 — Temperatura
        self.panel_temp = self.crear_panel(triptico, 0, "🌡️  TEMPERATURA AMBIENTE",
                                            COLOR_TEMP, "°C")
        # Panel 2 — Amoniaco (placeholder)
        self.panel_amoniaco = self.crear_panel(triptico, 1, "💨  AMONIACO",
                                               "#FFB347", "PPM")
        # Panel 3 — Humedad
        self.panel_hum = self.crear_panel(triptico, 2, "💧  HUMEDAD RELATIVA",
                                           COLOR_HUM, "%RH")

        # ── GRÁFICA ──
        frame_graf = tk.Frame(self.root, bg=COLOR_PANEL, bd=0)
        frame_graf.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(frame_graf, text="📈  Temperatura en Tiempo Real",
                 font=("Consolas", 10, "bold"), bg=COLOR_PANEL,
                 fg=COLOR_ACENTO).pack(anchor="w", padx=10, pady=(8, 0))

        self.fig, self.ax = plt.subplots(figsize=(12, 2.2), facecolor=COLOR_PANEL)
        self.ax.set_facecolor(COLOR_BG)
        self.ax.tick_params(colors=COLOR_SUBTEXTO, labelsize=8)
        self.ax.spines[:].set_color(COLOR_BORDE)
        self.linea_temp, = self.ax.plot([], [], color=COLOR_TEMP, linewidth=2, label="Temp °C")
        self.linea_hum,  = self.ax.plot([], [], color=COLOR_HUM,  linewidth=1.5,
                                         linestyle="--", label="Hum %RH")
        self.ax.legend(facecolor=COLOR_PANEL, edgecolor=COLOR_BORDE,
                       labelcolor=COLOR_TEXTO, fontsize=8)
        self.ax.set_ylabel("Valor", color=COLOR_SUBTEXTO, fontsize=8)
        plt.tight_layout(pad=0.5)

        self.canvas_graf = FigureCanvasTkAgg(self.fig, master=frame_graf)
        self.canvas_graf.get_tk_widget().pack(fill="x", padx=10, pady=(0, 8))

        # ── FOOTER / BOTÓN CSV ──
        footer = tk.Frame(self.root, bg=COLOR_BG)
        footer.pack(fill="x", padx=20, pady=(0, 12))

        tk.Label(footer, text=f"Puerto: {self.puerto}  |  Slave: {DIRECCION_SENSOR}  |  {BAUDRATE} baud",
                 font=("Consolas", 8), bg=COLOR_BG, fg=COLOR_SUBTEXTO).pack(side="left")

        tk.Button(footer, text="💾  EXPORTAR CSV", font=FUENTE_BTN,
                  bg="#238636", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self.exportar_csv).pack(side="right")

        self.lbl_csv = tk.Label(footer, text="", font=("Consolas", 8),
                                 bg=COLOR_BG, fg=COLOR_ACENTO)
        self.lbl_csv.pack(side="right", padx=10)

    def crear_panel(self, parent, col, titulo, color, unidad):
        """Crea un panel del tríptico y retorna referencias a sus widgets."""
        frame = tk.Frame(parent, bg=COLOR_PANEL, bd=0,
                         highlightbackground=COLOR_BORDE, highlightthickness=1)
        frame.grid(row=0, column=col, sticky="nsew",
                   padx=(0 if col == 0 else 8, 0), pady=0)

        tk.Label(frame, text=titulo, font=("Consolas", 10, "bold"),
                 bg=COLOR_PANEL, fg=color).pack(anchor="w", padx=14, pady=(14, 0))

        tk.Frame(frame, bg=color, height=2).pack(fill="x", padx=14, pady=(4, 0))

        # Valor grande
        lbl_valor = tk.Label(frame, text="--.-", font=FUENTE_VALOR,
                              bg=COLOR_PANEL, fg=color)
        lbl_valor.pack(pady=(10, 0))

        tk.Label(frame, text=unidad, font=FUENTE_UNIDAD,
                 bg=COLOR_PANEL, fg=COLOR_SUBTEXTO).pack()

        # Buffer (últimas lecturas)
        tk.Label(frame, text="— Últimas lecturas —", font=("Consolas", 8),
                 bg=COLOR_PANEL, fg=COLOR_SUBTEXTO).pack(pady=(12, 2))

        txt_buffer = tk.Text(frame, height=MAX_BUFFER, width=22,
                              font=FUENTE_BUFFER, bg=COLOR_BG,
                              fg=COLOR_TEXTO, bd=0, relief="flat",
                              state="disabled")
        txt_buffer.pack(padx=14, pady=(0, 14), fill="both", expand=True)

        return {"valor": lbl_valor, "buffer": txt_buffer}

    # ── RELOJ ──────────────────────────────────────────
    def actualizar_reloj(self):
        self.lbl_reloj.config(text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self.actualizar_reloj)

    # ── CONEXIÓN SENSOR ────────────────────────────────
    def conectar_sensor(self):
        self.cliente = ModbusSerialClient(
            port=self.puerto,
            baudrate=BAUDRATE,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1,
            framer="rtu"
        )
        if self.cliente.connect():
            self.lbl_estado.config(text="⬤  Conectado", fg=COLOR_ACENTO)
            self.corriendo = True
            threading.Thread(target=self.loop_lectura, daemon=True).start()
        else:
            self.lbl_estado.config(text="⬤  Error de conexión", fg="#FF6B6B")

    # ── LOOP DE LECTURA (hilo separado) ────────────────
    def loop_lectura(self):
        while self.corriendo:
            try:
                res = self.cliente.read_input_registers(
                    address=0x0001, count=2, device_id=DIRECCION_SENSOR
                )
                if not res.isError():
                    raw_t = res.registers[0]
                    raw_h = res.registers[1]
                    if raw_t > 32767:
                        raw_t -= 65536
                    temp = raw_t / 10.0
                    hum  = raw_h / 10.0
                    ts   = datetime.datetime.now()
                    self.root.after(0, self.actualizar_ui, temp, hum, ts)
            except Exception:
                pass
            time.sleep(INTERVALO_MS / 1000)

    # ── ACTUALIZAR UI ──────────────────────────────────
    def actualizar_ui(self, temp, hum, ts):
        ts_str = ts.strftime("%H:%M:%S")

        # Valores grandes
        self.panel_temp["valor"].config(text=f"{temp:.1f}")
        self.panel_hum["valor"].config(text=f"{hum:.1f}")
        self.panel_amoniaco["valor"].config(text="--")   # placeholder

        # Buffer texto
        self.agregar_buffer(self.panel_temp["buffer"],    f"{ts_str}   {temp:.1f} °C")
        self.agregar_buffer(self.panel_hum["buffer"],     f"{ts_str}   {hum:.1f} %RH")
        self.agregar_buffer(self.panel_amoniaco["buffer"],f"{ts_str}   -- PPM")

        # Datos para gráfica y CSV
        self.buffer_temp.append(temp)
        self.buffer_hum.append(hum)
        self.buffer_time.append(ts_str)
        self.datos_csv.append([ts.strftime("%Y-%m-%d %H:%M:%S"), temp, hum, "--"])

        # Actualizar gráfica
        x = list(range(len(self.buffer_temp)))
        self.linea_temp.set_data(x, list(self.buffer_temp))
        self.linea_hum.set_data(x, list(self.buffer_hum))
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas_graf.draw()

    def agregar_buffer(self, widget, texto):
        widget.config(state="normal")
        widget.insert("end", texto + "\n")
        lineas = int(widget.index("end-1c").split(".")[0])
        if lineas > MAX_BUFFER:
            widget.delete("1.0", "2.0")
        widget.see("end")
        widget.config(state="disabled")

    # ── EXPORTAR CSV ───────────────────────────────────
    def exportar_csv(self):
        if not self.datos_csv:
            messagebox.showwarning("Sin datos", "Aún no hay datos para exportar.")
            return
        nombre = f"datos_mpa_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        ruta   = os.path.join(os.path.dirname(__file__), nombre)
        with open(ruta, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Timestamp", "Temperatura (°C)", "Humedad (%RH)", "Amoniaco (PPM)"])
            w.writerows(self.datos_csv)
        self.lbl_csv.config(text=f"✅ Guardado: {nombre}")
        messagebox.showinfo("CSV Exportado", f"Archivo guardado:\n{ruta}")


# ═══════════════════════════════════════════════════════
# FLUJO PRINCIPAL
# ═══════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    root.withdraw()

    def abrir_seleccion_puerto():
        root.destroy()
        root2 = tk.Tk()
        VentanaPuerto(root2, lambda puerto: abrir_hmi(root2, puerto))
        root2.mainloop()

    def abrir_hmi(ventana_puerto, puerto):
        ventana_puerto.destroy()
        root3 = tk.Tk()
        HMIPrincipal(root3, puerto)
        root3.mainloop()

    splash_win = tk.Toplevel(root)
    SplashScreen(splash_win, abrir_seleccion_puerto)
    root.mainloop()

if __name__ == "__main__":
    main()