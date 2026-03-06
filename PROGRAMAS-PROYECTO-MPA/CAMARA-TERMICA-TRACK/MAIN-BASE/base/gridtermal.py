import cv2
import numpy as np
import csv
import time

# --- CONFIGURACIÓN ---
# Prueba con 0 si es la única cámara, o 1 si es una externa USB
CAM_INDEX = 1
# En Windows, usar cv2.CAP_DSHOW ayuda a iniciar cámaras USB más rápido
# En Linux/Mac, puedes quitar "+ cv2.CAP_DSHOW"
BACKEND = cv2.CAP_DSHOW 

DELTA_MOTION = 15      # Sensibilidad al movimiento
MIN_AREA = 800         # Ignora ruido pequeño
CSV_FILE = "temperatura_movimiento.csv"

# Inicializar cámara con backend específico
print(f"Intentando abrir cámara en índice {CAM_INDEX}...")
cap = cv2.VideoCapture(CAM_INDEX, BACKEND)

# --- VERIFICACIÓN DE CÁMARA ---
if not cap.isOpened():
    print(f"ERROR: No se pudo abrir la cámara en el índice {CAM_INDEX}.")
    print("Intenta cambiar CAM_INDEX a 0, 1 o 2.")
    exit()

# Configurar resolución (opcional, ayuda a estabilizar UVC)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

prev_gray = None

# Crear CSV
try:
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "area_pixeles", "temp_min", "temp_max", "temp_avg"])
    print(f"Archivo CSV '{CSV_FILE}' creado exitosamente.")
except Exception as e:
    print(f"Error al crear CSV: {e}")

print("Iniciando bucle de captura. Presiona 'ESC' para salir.")

while True:
    ret, frame = cap.read()
    
    # Si falla la lectura de un frame, no rompas inmediatamente, intenta reintentar o avisar
    if not ret:
        print("Error al leer el frame o cámara desconectada.")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Inicializar el primer frame para referencia
    if prev_gray is None:
        prev_gray = gray
        continue

    # ===== DETECCIÓN DE MOVIMIENTO =====
    diff = cv2.absdiff(gray, prev_gray)
    _, motion = cv2.threshold(diff, DELTA_MOTION, 255, cv2.THRESH_BINARY)
    motion = cv2.medianBlur(motion, 7)

    contours, _ = cv2.findContours(motion, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_AREA:
            continue

        # Dibujar contorno
        cv2.drawContours(frame, [cnt], -1, (0, 255, 0), 2)

        # Máscara del objeto en movimiento
        mask = np.zeros_like(gray)
        cv2.drawContours(mask, [cnt], -1, 255, -1)

        # Extraer píxeles dentro del área de movimiento
        pixels = gray[mask == 255]
        
        if len(pixels) > 0:
            # NOTA: En una cámara normal, esto es intensidad de luz (0-255), no temperatura real.
            t_min = float(np.min(pixels))
            t_max = float(np.max(pixels))
            t_avg = float(np.mean(pixels))

        
            try:
                with open(CSV_FILE, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        time.time(),
                        int(area),
                        round(t_min, 2),
                        round(t_max, 2),
                        round(t_avg, 2)
                    ])
            except Exception as e:
                print(f"Error escribiendo en CSV: {e}")

           
            text_info = f"I:{t_avg:.1f} M:{t_max:.1f}"
            cv2.putText(frame, text_info, tuple(cnt[0][0]), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

    # Actualizar frame anterior
    prev_gray = gray.copy()

    cv2.imshow("Deteccion UVC", frame)

    if cv2.waitKey(1) & 0xFF == 27: # ESC para salir
        break

cap.release()
cv2.destroyAllWindows()
print("Programa finalizado.")