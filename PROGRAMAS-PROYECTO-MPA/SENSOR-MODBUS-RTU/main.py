import serial.tools.list_ports
from pymodbus.client import ModbusSerialClient
import time

DIRECCION_SENSOR = 20
BAUDRATE         = 9600

def listar_puertos():
    puertos = list(serial.tools.list_ports.comports())
    if not puertos:
        print("No se encontraron puertos COM disponibles.")
        return []
    print("\n📡 Puertos COM disponibles:")
    for i, p in enumerate(puertos):
        print(f"  [{i}] {p.device} — {p.description}")
    return puertos

def seleccionar_puerto(puertos):
    while True:
        try:
            seleccion = int(input("\n Selecciona el número del puerto: "))
            if 0 <= seleccion < len(puertos):
                return puertos[seleccion].device
            else:
                print("⚠️  Número fuera de rango.")
        except ValueError:
            print("⚠️  Ingresa un número válido.")

def leer_sensor(cliente, direccion):
    try:
        resultado = cliente.read_input_registers(
            address=0x0001,
            count=2,
            device_id=direccion    # ← parámetro correcto en 3.12
        )
        if resultado.isError():
            return None, None

        raw_temp = resultado.registers[0]
        raw_hum  = resultado.registers[1]

        if raw_temp > 32767:
            raw_temp -= 65536

        return raw_temp / 10.0, raw_hum / 10.0

    except Exception as e:
        print(f"❌ Excepción: {e}")
        return None, None

def main():
    print("=" * 55)
    print("   MPA — Sensor XY-MD02  |  Modbus RTU  |  pymodbus 3.12")
    print(f"   Slave: {DIRECCION_SENSOR}  |  Baudrate: {BAUDRATE}")
    print("=" * 55)

    puertos = listar_puertos()
    if not puertos:
        return

    puerto = seleccionar_puerto(puertos)
    print(f"\n✅ Puerto: {puerto}")

    cliente = ModbusSerialClient(
        port=puerto,
        baudrate=BAUDRATE,
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=1,
        framer="rtu"
    )

    conectado = cliente.connect()
    print(f"   connect() retornó: {conectado}")

    if not conectado:
        print("❌ No se pudo abrir el puerto.")
        return

    # ── DIAGNÓSTICO: probar dirección 20 ──
    print(f"\n🔍 Probando slave {DIRECCION_SENSOR}...")
    temp, hum = leer_sensor(cliente, DIRECCION_SENSOR)

    if temp is not None:
        print(f"✅ ¡Sensor OK!  Temperatura: {temp}°C  |  Humedad: {hum}%RH\n")
    else:
        print("⚠️  No respondió en dirección 20. Escaneando 1-30...\n")
        encontrado = False
        for addr in range(1, 31):
            t, h = leer_sensor(cliente, addr)
            if t is not None:
                print(f"✅ ¡Sensor encontrado en dirección {addr}!")
                print(f"   Temperatura: {t}°C  |  Humedad: {h}%RH")
                encontrado = True
                break
            time.sleep(0.15)

        if not encontrado:
            print("❌ No se encontró sensor en dirección 1-30.")
            print("   Verifica: cableado A(+)/B(-), alimentación y baudrate.")
        cliente.close()
        return

    # ── LECTURA CONTINUA ──
    print("📊 Lectura continua cada 2s  (Ctrl+C para detener)\n")
    print(f"{'Tiempo':<12} {'Temp (°C)':<15} {'Humedad (%RH)':<15}")
    print("-" * 42)

    try:
        while True:
            temp, hum = leer_sensor(cliente, DIRECCION_SENSOR)
            if temp is not None:
                ts = time.strftime("%H:%M:%S")
                print(f"{ts:<12} {temp:<15.1f} {hum:<15.1f}")
            else:
                print("⚠️  Sin lectura, reintentando...")
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n🛑 Detenido por el usuario.")

    finally:
        cliente.close()
        print("🔌 Conexión cerrada.")

if __name__ == "__main__":
    main()