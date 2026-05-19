from garminconnect import Garmin
import json
import os
from datetime import datetime

def safe_call(name, fn):
    try:
        result = fn()
        print(f"[OK] {name}")
        return result
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        return {"error": str(e)}

def main():
    email = input("Correo Garmin: ").strip()
    password = input("Contraseña Garmin: ").strip()
    date_str = input("Fecha (YYYY-MM-DD): ").strip()

    # Validar fecha
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print("Fecha inválida. Usa formato YYYY-MM-DD.")
        return

    print("\nIniciando sesión en Garmin...")
    client = Garmin(email, password)
    client.login()
    print("[OK] Login exitoso\n")

    # Crear carpeta data si no existe
    os.makedirs("data", exist_ok=True)

    # Jalar varios bloques útiles para entender qué devuelve Garmin
    output = {
        "date": date_str,
        "stats": safe_call("get_stats", lambda: client.get_stats(date_str)),
        "sleep_data": safe_call("get_sleep_data", lambda: client.get_sleep_data(date_str)),
        "body_battery": safe_call("get_body_battery", lambda: client.get_body_battery(date_str, date_str)),
        "stress_data": safe_call("get_stress_data", lambda: client.get_stress_data(date_str)),
        "resting_heart_rate": safe_call("get_rhr_day", lambda: client.get_rhr_day(date_str)),
        "hrv_data": safe_call("get_hrv_data", lambda: client.get_hrv_data(date_str)),
    }

    filename = f"data/garmin_day_dump_{date_str}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nArchivo guardado en: {filename}")
    print("\nTambién te recomiendo revisar en consola qué se guardó.")
    print("Si quieres ver solo las llaves principales del archivo, usa luego algo como:")
    print("  python revisar_llaves.py")

if __name__ == "__main__":
    main()