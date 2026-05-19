"""
test_workout_upload.py
======================
Prueba si la sesión de Garmin actual tiene acceso de escritura
al endpoint workout-service/workout.

Uso:
    python test_workout_upload.py
"""

import json
import os
import sys
import getpass

from garminconnect import Garmin

WORKOUT_PAYLOAD = {
    "workoutName": "Test Apex",
    "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "workoutSegments": [{
        "segmentOrder": 1,
        "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
        "workoutSteps": [{
            "type": "ExecutableStepDTO",
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "endCondition": {
                "conditionTypeId": 2,
                "conditionTypeKey": "time",
                "conditionValue": 1800
            },
            "endConditionValue": 1800,
            "targetType": {
                "workoutTargetTypeId": 1,
                "workoutTargetTypeKey": "no.target"
            }
        }]
    }]
}


def get_credentials():
    session_path = os.path.join(os.path.dirname(__file__), "garmin_session.json")
    email = None
    if os.path.exists(session_path):
        with open(session_path, encoding="utf-8") as f:
            email = json.load(f).get("email")
        print(f"Email detectado: {email}")
    else:
        email = input("Correo Garmin: ").strip()

    password = getpass.getpass(f"Contraseña para {email}: ")
    return email, password


def main():
    print("=" * 50)
    print("TEST — upload_workout a Garmin Connect")
    print("=" * 50)

    email, password = get_credentials()

    print("\nIniciando sesión...")
    client = Garmin(email, password)
    client.login()
    print("[OK] Login exitoso\n")

    print("Intentando POST a /workout-service/workout ...")
    try:
        result = client.upload_workout(WORKOUT_PAYLOAD)
        print(f"\n✓ HTTP 200/201 — Acceso de escritura CONFIRMADO")
        print(f"Workout creado. Respuesta:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        err = str(e)
        print(f"\n✗ Error: {err}")
        # Try to get response body for debugging
        if hasattr(e, "response") and e.response is not None:
            print(f"HTTP {e.response.status_code}")
            try:
                print("Body:", e.response.json())
            except Exception:
                print("Body (text):", e.response.text[:500])
        if "401" in err:
            print("→ HTTP 401: No autenticado. Problema de sesión.")
        elif "403" in err:
            print("→ HTTP 403: Autenticado pero sin permiso de escritura en esta cuenta.")
        elif "404" in err:
            print("→ HTTP 404: Endpoint no encontrado o URL incorrecta.")
        elif "500" in err:
            print("→ HTTP 500: Servidor rechaza el payload — formato JSON incorrecto.")


if __name__ == "__main__":
    main()
