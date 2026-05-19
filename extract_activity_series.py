import json
import os

data_folder = "data"
details_file = None

for file in os.listdir(data_folder):
    if file.startswith("activity_details_") and file.endswith(".json"):
        details_file = os.path.join(data_folder, file)
        break

if not details_file:
    print("No se encontró archivo activity_details.")
    exit()

print(f"Leyendo archivo: {details_file}")

with open(details_file, "r", encoding="utf-8") as f:
    details = json.load(f)

metric_descriptors = details.get("metricDescriptors", [])
activity_metrics = details.get("activityDetailMetrics", [])

if not metric_descriptors or not activity_metrics:
    print("No hay metricDescriptors o activityDetailMetrics.")
    exit()

print("\nMétricas detectadas:")
for i, metric in enumerate(metric_descriptors):
    key = metric.get("key", "sin_nombre")
    unit = metric.get("unit", {}).get("key", "")
    print(f"{i}: {key} ({unit})")

print(f"\nTotal de registros de serie temporal: {len(activity_metrics)}")