from garminconnect import Garmin
from datetime import date, timedelta
import getpass
import json
import os

email = input("Escribe tu correo de Garmin: ")
password = getpass.getpass("Escribe tu contraseña de Garmin: ")

print("Conectando con Garmin...")

client = Garmin(email, password)
client.login()

# Ayer
yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"\nConexión exitosa.")
print(f"Fecha consultada: {yesterday}")

# Crear carpeta data si no existe
os.makedirs("data", exist_ok=True)

# 1) Stats de ayer
stats = client.get_stats(yesterday)
with open(f"data/stats_{yesterday}.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)

print(f"✔ Stats guardados: data/stats_{yesterday}.json")

# 2) Heart rates de ayer
heart_rates = client.get_heart_rates(yesterday)
with open(f"data/heart_rates_{yesterday}.json", "w", encoding="utf-8") as f:
    json.dump(heart_rates, f, indent=2, ensure_ascii=False)

print(f"✔ Heart rates guardados: data/heart_rates_{yesterday}.json")

# 3) Actividades de ayer
activities = client.get_activities_by_date(yesterday, yesterday)
with open(f"data/activities_{yesterday}.json", "w", encoding="utf-8") as f:
    json.dump(activities, f, indent=2, ensure_ascii=False)

print(f"✔ Actividades guardadas: data/activities_{yesterday}.json")

# 4) Si hubo actividades, guardar detalle de la primera
if activities and len(activities) > 0:
    first_activity = activities[0]
    activity_id = first_activity.get("activityId")

    print(f"\nPrimera actividad encontrada:")
    print(f"  Nombre: {first_activity.get('activityName')}")
    print(f"  Tipo: {first_activity.get('activityType', {}).get('typeKey')}")
    print(f"  ID: {activity_id}")

    if activity_id:
        activity_details = client.get_activity_details(activity_id)
        with open(f"data/activity_details_{activity_id}.json", "w", encoding="utf-8") as f:
            json.dump(activity_details, f, indent=2, ensure_ascii=False)

        print(f"✔ Detalle guardado: data/activity_details_{activity_id}.json")
else:
    print("\nNo se encontraron actividades para ayer.")