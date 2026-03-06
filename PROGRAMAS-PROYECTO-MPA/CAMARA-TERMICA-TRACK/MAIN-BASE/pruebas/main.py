"""
╔══════════════════════════════════════════════════════╗
║     MPA - Tracker YOLOv8 + ByteTrack                 ║
║     Detección robusta + ID persistente               ║
║     Webcam normal → luego térmica                    ║
╚══════════════════════════════════════════════════════╝
"""

import cv2
import csv
import time
import datetime
import winsound
from collections import defaultdict
from ultralytics import YOLO

# ── CONFIGURACIÓN ──────────────────────────────────────
CAMARA_INDEX   = 0
CAMARA_BACKEND = cv2.CAP_DSHOW

MODELO         = "yolov8n.pt"       # nano=rápido, yolov8s.pt=más preciso

# Clases a detectar — COCO dataset
# 0=persona, 14=pájaro, 15=gato, 16=perro, 17=caballo, 88=teddy bear
# Para probar con personas: [0]
# Cuando tengas modelo custom de pollos: cambiar a [0] con tu modelo
CLASES         = [0]                # 0 = persona
NOMBRES_CLASE  = {0: "Persona", 14: "Ave", 15: "Gato"}

CONFIANZA_MIN  = 0.4                # confianza mínima de detección
IOU_THRESHOLD  = 0.5                # umbral IoU para NMS

TEMP_ALERTA    = 33.0               # °C — solo activo con cámara térmica
MAX_TRAYECTORIA = 45                # puntos de trayectoria a guardar

CSV_FILE = f"tracking_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

COLORES_ID = [
    (0,   255, 120),
    (255, 180,   0),
    (0,   200, 255),
    (255,  80, 200),
    (80,  255,  80),
    (255, 120,  80),
    (120,  80, 255),
]


# ═══════════════════════════════════════════════════════
# GESTOR DE TRAYECTORIAS
# ═══════════════════════════════════════════════════════
class GestorTrayectorias:
    def __init__(self):
        self.trayectorias = defaultdict(list)
        self.colores      = {}

    def actualizar(self, track_id, cx, cy):
        self.trayectorias[track_id].append((cx, cy))
        if len(self.trayectorias[track_id]) > MAX_TRAYECTORIA:
            self.trayectorias[track_id].pop(0)
        if track_id not in self.colores:
            self.colores[track_id] = COLORES_ID[(track_id - 1) % len(COLORES_ID)]

    def color(self, track_id):
        return self.colores.get(track_id, COLORES_ID[0])

    def trayectoria(self, track_id):
        return self.trayectorias.get(track_id, [])

    def limpiar_perdidos(self, ids_activos):
        perdidos = [tid for tid in self.trayectorias if tid not in ids_activos]
        for tid in perdidos:
            del self.trayectorias[tid]
            self.colores.pop(tid, None)


# ═══════════════════════════════════════════════════════
# DIBUJAR FRAME
# ═══════════════════════════════════════════════════════
def dibujar(frame, resultados, gestor, fps, n_detectados):
    vis  = frame.copy()
    H, W = vis.shape[:2]
    PANEL = 185

    # Panel lateral
    cv2.rectangle(vis, (W-PANEL, 0), (W, H), (12, 12, 18), -1)
    cv2.line(vis, (W-PANEL, 0), (W-PANEL, H), (40, 40, 50), 1)

    cv2.putText(vis, "MPA TRACKER", (W-PANEL+8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 220, 120), 1)
    cv2.putText(vis, f"FPS: {fps:.1f}", (W-PANEL+8, 38),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (100, 100, 100), 1)
    cv2.putText(vis, f"Detectados: {n_detectados}", (W-PANEL+8, 54),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 220, 120), 1)
    cv2.line(vis, (W-PANEL+4, 62), (W-4, 62), (40, 40, 50), 1)

    y_off = 78

    for det in resultados:
        tid   = det["id"]
        x1,y1,x2,y2 = det["bbox"]
        conf  = det["conf"]
        clase = det["clase"]
        cx,cy = det["centro"]
        color = gestor.color(tid)

        # Trayectoria con desvanecimiento
        tray = gestor.trayectoria(tid)
        for k in range(1, len(tray)):
            alpha  = k / len(tray)
            c_fade = tuple(int(v * alpha) for v in color)
            cv2.line(vis, tray[k-1], tray[k], c_fade, 2)

        # Bounding box
        cv2.rectangle(vis, (x1,y1), (x2,y2), color, 2)

        # Esquinas decorativas
        L = 16
        for px,py,dx,dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
            cv2.line(vis,(px,py),(px+dx*L,py),color,2)
            cv2.line(vis,(px,py),(px,py+dy*L),color,2)

        # Etiqueta
        nombre = NOMBRES_CLASE.get(clase, f"Obj{clase}")
        label  = f"ID {tid}  {nombre}  {conf:.0%}"
        tw     = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)[0][0]
        lx, ly = x1, y1 - 8
        if ly < 18:
            ly = y2 + 18
        cv2.rectangle(vis,(lx-2, ly-16),(lx+tw+4, ly+3), color, -1)
        cv2.putText(vis, label, (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0,0,0), 1, cv2.LINE_AA)

        # Centroide
        cv2.circle(vis, (cx, cy), 5, color, -1)

        # Panel lateral
        cv2.putText(vis, f"ID {tid}: ({cx},{cy})", (W-PANEL+8, y_off),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)
        y_off += 18

    # Info general
    cv2.putText(vis, f"Objetos: {n_detectados}", (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 120), 2)
    cv2.putText(vis, "Q=salir  R=reset  S=captura", (10, H-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 80, 80), 1)
    return vis


# ═══════════════════════════════════════════════════════
# CSV
# ═══════════════════════════════════════════════════════
def init_csv():
    with open(CSV_FILE, "w", newline="") as f:
        csv.writer(f).writerow([
            "Timestamp", "ID", "Clase", "Confianza",
            "Centro_X", "Centro_Y", "X1", "Y1", "X2", "Y2"
        ])
    print(f"CSV: {CSV_FILE}")

def escribir_csv(resultados):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        for det in resultados:
            x1,y1,x2,y2 = det["bbox"]
            w.writerow([
                ts, det["id"],
                NOMBRES_CLASE.get(det["clase"], det["clase"]),
                f"{det['conf']:.3f}",
                det["centro"][0], det["centro"][1],
                x1, y1, x2, y2
            ])


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
def main():
    print("=" * 52)
    print("   MPA — Tracker YOLOv8 + ByteTrack")
    print(f"   Modelo: {MODELO}")
    print(f"   Clases: {[NOMBRES_CLASE.get(c, c) for c in CLASES]}")
    print("   Q=salir  R=reset  S=captura")
    print("=" * 52)

    print("\nCargando modelo YOLO...")
    modelo = YOLO(MODELO)
    print("✅ Modelo listo\n")

    init_csv()

    cap = cv2.VideoCapture(CAMARA_INDEX, CAMARA_BACKEND)
    if not cap.isOpened():
        print(f"ERROR: No se pudo abrir cámara {CAMARA_INDEX}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    gestor      = GestorTrayectorias()
    t_prev      = time.time()
    fps         = 0.0
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        frame_count += 1
        now    = time.time()
        fps    = 0.85*fps + 0.15*(1.0/max(now-t_prev, 0.001))
        t_prev = now

        # Inferencia YOLO + ByteTrack
        results = modelo.track(
            frame,
            persist=True,               # mantiene IDs entre frames
            classes=CLASES,
            conf=CONFIANZA_MIN,
            iou=IOU_THRESHOLD,
            tracker="bytetrack.yaml",   # ByteTrack integrado
            verbose=False
        )

        resultados  = []
        ids_activos = set()

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes  = results[0].boxes
            for i in range(len(boxes)):
                tid  = int(boxes.id[i].item())
                conf = float(boxes.conf[i].item())
                cls  = int(boxes.cls[i].item())
                x1,y1,x2,y2 = map(int, boxes.xyxy[i].tolist())
                cx   = (x1+x2)//2
                cy   = (y1+y2)//2

                gestor.actualizar(tid, cx, cy)
                ids_activos.add(tid)

                resultados.append({
                    "id": tid, "conf": conf, "clase": cls,
                    "bbox": (x1,y1,x2,y2), "centro": (cx,cy)
                })

        gestor.limpiar_perdidos(ids_activos)

        # CSV cada 20 frames
        if resultados and frame_count % 20 == 0:
            escribir_csv(resultados)

        # Log consola
        if resultados:
            info = "  |  ".join([f"ID{d['id']}:({d['centro'][0]},{d['centro'][1]})"
                                  for d in resultados])
            print(f"\r{info}     ", end="", flush=True)

        vis = dibujar(frame, resultados, gestor, fps, len(resultados))
        cv2.imshow("MPA — YOLOv8 + ByteTrack  |  Q=salir", vis)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            gestor = GestorTrayectorias()
            print("\n🔄 IDs reseteados")
        elif key == ord('s'):
            nombre = f"captura_{datetime.datetime.now().strftime('%H%M%S')}.png"
            cv2.imwrite(nombre, vis)
            print(f"\n📸 Captura: {nombre}")

    if resultados:
        escribir_csv(resultados)

    cap.release()
    cv2.destroyAllWindows()
    print(f"\n\n✅ CSV guardado: {CSV_FILE}")

if __name__ == "__main__":
    main()