import json
import os

data_folder = "data"
activities_file = None

for file in os.listdir(data_folder):
    if file.startswith("activities_") and file.endswith(".json"):
        activities_file = os.path.join(data_folder, file)
        break

if not activities_file:
    print("No se encontró archivo de activities.")
    exit()

print(f"Leyendo archivo: {activities_file}")

with open(activities_file, "r", encoding="utf-8") as f:
    activities = json.load(f)

if not activities:
    print("No hay actividades en el archivo.")
    exit()

activity = activities[0]

activity_type = activity.get("activityType", {}).get("typeKey")
distance_km = activity.get("distance", 0) / 1000
moving_time_min = activity.get("movingDuration", 0) / 60
elapsed_time_min = activity.get("elapsedDuration", 0) / 60
elevation = activity.get("elevationGain", 0)
calories = activity.get("calories", 0)

avg_hr = activity.get("averageHR")
max_hr = activity.get("maxHR")

avg_power = activity.get("avgPower")
max_power = activity.get("maxPower")
np_power = activity.get("normPower")

avg_cadence = activity.get("averageBikingCadenceInRevPerMinute")
max_cadence = activity.get("maxBikingCadenceInRevPerMinute")

tss = activity.get("trainingStressScore")
intensity = activity.get("intensityFactor")
vo2max = activity.get("vO2MaxValue")
grit = activity.get("grit")
aerobic_te = activity.get("aerobicTrainingEffect")
anaerobic_te = activity.get("anaerobicTrainingEffect")

print("\n============================")
print("REPORTE DEL ENTRENAMIENTO")
print("============================")

print(f"Nombre: {activity.get('activityName')}")
print(f"Tipo de actividad: {activity_type}")
print(f"Distancia: {distance_km:.2f} km")
print(f"Tiempo moviéndose: {moving_time_min:.1f} min")
print(f"Tiempo transcurrido: {elapsed_time_min:.1f} min")
print(f"Elevación ganada: {elevation:.0f} m")
print(f"Calorías: {calories:.0f}")

print("\nFrecuencia cardíaca")
print("-------------------")
print(f"Promedio: {avg_hr} bpm")
print(f"Máxima: {max_hr} bpm")

print("\nPotencia")
print("-------------------")
print(f"Promedio: {avg_power} W")
print(f"Máxima: {max_power} W")
print(f"Potencia normalizada: {np_power} W")

print("\nCadencia")
print("-------------------")
print(f"Promedio: {avg_cadence} rpm")
print(f"Máxima: {max_cadence} rpm")

print("\nCarga de entrenamiento")
print("-------------------")
print(f"TSS: {tss}")
print(f"Intensity Factor: {intensity}")
print(f"VO2max: {vo2max}")
print(f"Grit: {grit}")
print(f"Aerobic TE: {aerobic_te}")
print(f"Anaerobic TE: {anaerobic_te}")

print("\n============================")
print("INTERPRETACIÓN")
print("============================")

if intensity is not None:
    if intensity > 0.9:
        print("Entrenamiento MUY intenso.")
    elif intensity > 0.75:
        print("Entrenamiento fuerte.")
    else:
        print("Entrenamiento moderado.")

if tss is not None:
    if tss > 180:
        print("Carga fisiológica muy alta, requiere recuperación seria.")
    elif tss > 100:
        print("Carga de entrenamiento alta.")
    else:
        print("Carga de entrenamiento moderada.")

if np_power is not None and avg_power is not None:
    variability = np_power / avg_power if avg_power > 0 else 0
    print(f"Factor de variabilidad NP/AP: {variability:.2f}")
    if variability > 1.2:
        print("El esfuerzo fue muy variable, típico de MTB/XC/trail técnico.")

if avg_hr is not None and max_hr is not None and max_hr >= 180:
    print("Hubo picos cardiovasculares altos.")

if aerobic_te is not None and aerobic_te >= 4.0:
    print("La sesión sí empujó fuerte el estímulo aeróbico.")