from garminconnect import Garmin
import json
import os
import inspect
from datetime import datetime
from typing import Any


def safe_json(value: Any):
    """
    Convierte objetos no serializables a algo seguro para guardar en JSON.
    """
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): safe_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [safe_json(v) for v in value]
        return str(value)


def safe_call(name, fn):
    """
    Ejecuta una llamada y nunca rompe todo el script si falla.
    """
    try:
        result = fn()
        print(f"[OK] {name}")
        return {
            "ok": True,
            "data": safe_json(result)
        }
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        return {
            "ok": False,
            "error": str(e)
        }


def summarize_structure(obj, depth=0, max_depth=3):
    """
    Genera un resumen liviano de la estructura de un objeto JSON:
    tipos, llaves y tamaños.
    """
    if depth > max_depth:
        return "MAX_DEPTH_REACHED"

    if isinstance(obj, dict):
        return {
            "_type": "dict",
            "_keys": list(obj.keys()),
            "_children": {
                str(k): summarize_structure(v, depth + 1, max_depth)
                for k, v in obj.items()
            }
        }

    if isinstance(obj, list):
        preview = obj[:3]
        return {
            "_type": "list",
            "_len": len(obj),
            "_sample": [summarize_structure(v, depth + 1, max_depth) for v in preview]
        }

    return type(obj).__name__


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def list_client_methods(client):
    methods = []
    for name in dir(client):
        if name.startswith("_"):
            continue
        attr = getattr(client, name)
        if callable(attr):
            try:
                sig = str(inspect.signature(attr))
            except Exception:
                sig = "(signature_unavailable)"
            methods.append({
                "name": name,
                "signature": sig
            })
    return sorted(methods, key=lambda x: x["name"].lower())


def main():
    print("=== Garmin Raw Explorer ===")
    email = input("Correo Garmin: ").strip()
    password = input("Contraseña Garmin: ").strip()
    date_str = input("Fecha objetivo (YYYY-MM-DD): ").strip()

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print("Fecha inválida. Usa YYYY-MM-DD.")
        return

    output_dir = os.path.join("data", f"garmin_raw_explorer_{date_str}")
    os.makedirs(output_dir, exist_ok=True)

    print("\nIniciando sesión...")
    client = Garmin(email, password)
    client.login()
    print("[OK] Login exitoso")

    # 1) Guardar lista de métodos disponibles reales en tu instalación
    methods = list_client_methods(client)
    save_json(os.path.join(output_dir, "available_methods.json"), methods)
    print(f"[OK] available_methods.json guardado con {len(methods)} métodos")

    # 2) Probar endpoints comunes para saber qué raw data puedes obtener
    #    Ojo: algunos nombres pueden no existir en tu versión.
    common_calls = {
        # Resumen diario
        "get_stats": lambda: client.get_stats(date_str),

        # Sueño
        "get_sleep_data": lambda: client.get_sleep_data(date_str),

        # Body Battery
        "get_body_battery": lambda: client.get_body_battery(date_str, date_str),

        # Estrés
        "get_stress_data": lambda: client.get_stress_data(date_str),

        # FC reposo
        "get_rhr_day": lambda: client.get_rhr_day(date_str),

        # HRV
        "get_hrv_data": lambda: client.get_hrv_data(date_str),

        # Heart rate series
        "get_heart_rates": lambda: client.get_heart_rates(date_str),

        # Actividades del día / cercanas
        "get_activities_by_date": lambda: client.get_activities_by_date(date_str, date_str),

        # Hydration / respiración / health snapshots si existen
        "get_respiration_data": lambda: client.get_respiration_data(date_str),
        "get_spo2_data": lambda: client.get_spo2_data(date_str),
        "get_body_composition": lambda: client.get_body_composition(date_str),
        "get_steps_data": lambda: client.get_steps_data(date_str),
        "get_intensity_minutes_data": lambda: client.get_intensity_minutes_data(date_str),
        "get_floors_data": lambda: client.get_floors_data(date_str),
        "get_calories_data": lambda: client.get_calories_data(date_str),
    }

    raw_dump = {
        "meta": {
            "date": date_str,
            "output_dir": output_dir
        },
        "calls": {}
    }

    for call_name, call_fn in common_calls.items():
        if hasattr(client, call_name):
            raw_dump["calls"][call_name] = safe_call(call_name, call_fn)
        else:
            print(f"[SKIP] {call_name}: método no existe en tu versión")
            raw_dump["calls"][call_name] = {
                "ok": False,
                "error": "method_not_available_in_this_library_version"
            }

    # 3) Guardar dump completo
    raw_path = os.path.join(output_dir, "raw_dump.json")
    save_json(raw_path, raw_dump)
    print(f"[OK] raw_dump.json guardado")

    # 4) Guardar resumen de estructura
    structure_summary = {
        "meta": raw_dump["meta"],
        "calls": {}
    }

    for name, payload in raw_dump["calls"].items():
        if payload.get("ok"):
            structure_summary["calls"][name] = {
                "ok": True,
                "structure": summarize_structure(payload.get("data"))
            }
        else:
            structure_summary["calls"][name] = {
                "ok": False,
                "error": payload.get("error")
            }

    structure_path = os.path.join(output_dir, "structure_summary.json")
    save_json(structure_path, structure_summary)
    print(f"[OK] structure_summary.json guardado")

    # 5) Guardar archivo de métodos en txt legible también
    methods_txt_path = os.path.join(output_dir, "available_methods.txt")
    with open(methods_txt_path, "w", encoding="utf-8") as f:
        for m in methods:
            f.write(f"{m['name']}{m['signature']}\n")
    print(f"[OK] available_methods.txt guardado")

    print("\n=== TERMINADO ===")
    print("Archivos generados:")
    print(f" - {os.path.join(output_dir, 'available_methods.json')}")
    print(f" - {os.path.join(output_dir, 'available_methods.txt')}")
    print(f" - {os.path.join(output_dir, 'raw_dump.json')}")
    print(f" - {os.path.join(output_dir, 'structure_summary.json')}")
    print("\nMándame idealmente estos dos:")
    print("1) raw_dump.json")
    print("2) structure_summary.json")


if __name__ == "__main__":
    main()