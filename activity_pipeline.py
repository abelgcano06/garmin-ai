import csv
import json
import os
from datetime import datetime
from activity_analyzer import analyze_activity

from app_context import (
    get_current_user_id,
    get_activity_dir,
    get_activity_details_path,
    get_activity_series_path,
    get_activity_analysis_path,
    get_user_profile_path,
)


def download_activity_details(client, activity_id, user_id=None):
    user_id = user_id or get_current_user_id()

    print("\nDescargando activity details...")

    details = client.get_activity_details(activity_id)

    path = get_activity_details_path(activity_id, user_id)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(details, f, indent=2)

    print(f"Detalles guardados en: {path}")

    return path, details


def build_metric_index_map(metric_descriptors):
    index_map = {}
    for i, metric in enumerate(metric_descriptors):
        key = metric.get("key")
        if key:
            index_map[key] = i
    return index_map


def safe_get(metrics, index):
    if index is None:
        return None
    if index < len(metrics):
        return metrics[index]
    return None


def build_activity_series_csv(details, activity_id, user_id=None):
    user_id = user_id or get_current_user_id()

    metric_descriptors = details.get("metricDescriptors", [])
    activity_metrics = details.get("activityDetailMetrics", [])

    if not metric_descriptors or not activity_metrics:
        raise ValueError("El archivo activity_details no trae metricDescriptors o activityDetailMetrics.")

    target_metrics = {
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

    metric_index_map = build_metric_index_map(metric_descriptors)

    rows = []
    for row in activity_metrics:
        metrics = row.get("metrics", [])
        clean_row = {}

        for garmin_key, output_name in target_metrics.items():
            idx = metric_index_map.get(garmin_key)
            clean_row[output_name] = safe_get(metrics, idx)

        rows.append(clean_row)

    output_file = get_activity_series_path(activity_id, user_id)

    fieldnames = list(target_metrics.values())

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Serie limpia generada: {output_file}")
    print(f"Total de filas: {len(rows)}")

    return output_file


def basic_activity_analysis(activity):
    name = activity.get("activityName", "Sin nombre")
    activity_type = activity.get("activityType", {}).get("typeKey", "unknown")

    distance_km = (activity.get("distance", 0) or 0) / 1000
    moving_min = (activity.get("movingDuration", 0) or 0) / 60
    elevation = activity.get("elevationGain", 0) or 0

    avg_hr = activity.get("averageHR")
    avg_power = activity.get("avgPower")

    avg_speed = distance_km / (moving_min / 60) if moving_min else 0

    summary = {
        "name": name,
        "type": activity_type,
        "distance_km": round(distance_km, 2),
        "moving_minutes": round(moving_min, 1),
        "elevation_m": round(elevation),
        "avg_speed_kmh": round(avg_speed, 2),
        "avg_hr": avg_hr,
        "avg_power": avg_power,
    }

    return summary


def save_analysis_json(activity_id, analysis_result, user_id=None):
    user_id = user_id or get_current_user_id()

    path = get_activity_analysis_path(activity_id, user_id)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, indent=2, ensure_ascii=False)

    print(f"Análisis final guardado en: {path}")

    return path


def load_user_profile(user_id):
    path = get_user_profile_path(user_id)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_activity_pipeline(client, activity, user_id=None):
    user_id = user_id or get_current_user_id()

    print("\n===================================")
    print("INICIANDO PIPELINE DE ACTIVIDAD")
    print("===================================")

    activity_id = activity["activityId"]

    get_activity_dir(activity_id, user_id)

    # Cargar perfil del usuario para FTP y MAX_HR reales
    # ftp_apex = calculado por Apex (preferido); ftp = manual del usuario (fallback)
    profile = load_user_profile(user_id)
    ftp = float(profile.get("ftp_apex") or profile.get("ftp") or 230.0)
    max_hr = float(profile.get("max_hr") or 185.0)
    print(f"[perfil] FTP={ftp}W (apex={profile.get('ftp_apex')}, manual={profile.get('ftp')})  MAX_HR={max_hr}bpm")

    details_path, details = download_activity_details(client, activity_id, user_id)
    series_path = build_activity_series_csv(details, activity_id, user_id)

    summary = basic_activity_analysis(activity)

    print("\n==============================")
    print("ANÁLISIS BÁSICO")
    print("==============================")
    for k, v in summary.items():
        print(f"{k}: {v}")

    analysis_result = analyze_activity(activity, series_path, ftp=ftp, max_hr=max_hr)

    analysis_json_path = save_analysis_json(activity_id, analysis_result, user_id)

    result = {
        "summary": summary,
        "details_file": details_path,
        "series_file": series_path,
        "analysis_file": analysis_json_path,
        "analysis_time": datetime.now().isoformat(),
        "analysis_result": analysis_result,
    }

    return result