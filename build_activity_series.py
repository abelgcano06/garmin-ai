import json
import os
import csv

DATA_FOLDER = "data"

# Métricas que sí queremos para análisis serio
TARGET_METRICS = {
    "directTimestamp": "timestamp",
    "sumElapsedDuration": "elapsed_s",
    "sumDistance": "distance_m",
    "directElevation": "elevation_m",
    "directSpeed": "speed_mps",
    "directBikeCadence": "cadence_rpm",
    "directHeartRate": "heart_rate_bpm",
    "directPower": "power_w",
    "directRespirationRate": "respiration_brpm",
    "directVerticalSpeed": "vertical_speed_mps",
    "directGrit": "grit",
    "directAvailableStamina": "available_stamina",
    "directPotentialStamina": "potential_stamina",
    "directPerformanceCondition": "performance_condition",
}


def find_activity_details_file(data_folder: str) -> str | None:
    for file in os.listdir(data_folder):
        if file.startswith("activity_details_") and file.endswith(".json"):
            return os.path.join(data_folder, file)
    return None


def build_metric_index_map(metric_descriptors: list[dict]) -> dict[str, int]:
    index_map = {}
    for i, metric in enumerate(metric_descriptors):
        key = metric.get("key")
        if key:
            index_map[key] = i
    return index_map


def safe_get(metrics: list, index: int | None):
    if index is None:
        return None
    if index < len(metrics):
        return metrics[index]
    return None


def main():
    details_file = find_activity_details_file(DATA_FOLDER)

    if not details_file:
        print("No se encontró archivo activity_details en la carpeta data.")
        return

    print(f"Leyendo archivo: {details_file}")

    with open(details_file, "r", encoding="utf-8") as f:
        details = json.load(f)

    metric_descriptors = details.get("metricDescriptors", [])
    activity_metrics = details.get("activityDetailMetrics", [])

    if not metric_descriptors:
        print("El archivo no trae metricDescriptors.")
        return

    if not activity_metrics:
        print("El archivo no trae activityDetailMetrics.")
        return

    metric_index_map = build_metric_index_map(metric_descriptors)

    print("\nMétricas objetivo encontradas:")
    for garmin_key, output_name in TARGET_METRICS.items():
        if garmin_key in metric_index_map:
            print(f"  OK  {garmin_key} -> {output_name} (índice {metric_index_map[garmin_key]})")
        else:
            print(f"  --  {garmin_key} -> {output_name} (no encontrada)")

    rows = []

    for row in activity_metrics:
        metrics = row.get("metrics", [])
        clean_row = {}

        for garmin_key, output_name in TARGET_METRICS.items():
            idx = metric_index_map.get(garmin_key)
            clean_row[output_name] = safe_get(metrics, idx)

        rows.append(clean_row)

    output_file = os.path.join(DATA_FOLDER, "activity_series_clean.csv")

    fieldnames = list(TARGET_METRICS.values())

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nCSV limpio generado: {output_file}")
    print(f"Total de filas: {len(rows)}")

    print("\nPrimeras 5 filas:")
    for r in rows[:5]:
        print(r)


if __name__ == "__main__":
    main()