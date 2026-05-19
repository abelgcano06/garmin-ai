import json
import os
from datetime import datetime

from app_context import get_activity_history_path, get_current_user_id


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_history(user_id=None):
    user_id = user_id or get_current_user_id()
    history_file = get_activity_history_path(user_id)

    if not os.path.exists(history_file):
        return {"activities": []}

    with open(history_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(history, user_id=None):
    user_id = user_id or get_current_user_id()
    history_file = get_activity_history_path(user_id)

    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def build_history_row(analysis):
    garmin = analysis.get("garmin_summary", {})
    derived = analysis.get("derived_summary", {})
    fatigue = analysis.get("fatigue", {})
    profile = analysis.get("athlete_profile", {})
    climbs = analysis.get("climbs", [])

    top_climb = None
    if climbs:
        top_climb = sorted(climbs, key=lambda x: x.get("climb_score", 0), reverse=True)[0]

    vo2_count = sum(1 for e in analysis.get("efforts", []) if e.get("type") == "VO2")
    sprint_count = sum(1 for e in analysis.get("efforts", []) if e.get("type") == "SPRINT")
    threshold_count = sum(1 for e in analysis.get("efforts", []) if e.get("type") == "THRESHOLD")

    metabolic = analysis.get("metabolic_index", {})

    row = {
        "activity_id": garmin.get("activity_id"),
        "date": garmin.get("start_date") or datetime.now().strftime("%Y-%m-%d"),
        "name": garmin.get("name"),
        "type": garmin.get("type"),
        "distance_km": garmin.get("distance_km"),
        "moving_minutes": garmin.get("moving_minutes"),
        "elapsed_minutes": garmin.get("elapsed_minutes"),
        "elevation_m": garmin.get("elevation_m"),
        "avg_hr": garmin.get("avg_hr"),
        "max_hr": garmin.get("max_hr"),
        "avg_power": garmin.get("avg_power"),
        "max_power": garmin.get("max_power"),
        "garmin_np": garmin.get("garmin_np"),
        "garmin_tss": garmin.get("garmin_tss"),
        "garmin_if": garmin.get("garmin_if"),
        "vo2max": garmin.get("vo2max"),
        "aerobic_te": garmin.get("aerobic_te"),
        "anaerobic_te": garmin.get("anaerobic_te"),
        "grit": garmin.get("grit"),

        "estimated_np": derived.get("estimated_np"),
        "vi": derived.get("vi"),
        "estimated_if": derived.get("estimated_if"),
        "energy_kj": derived.get("energy_kj"),
        "aerobic_efficiency": derived.get("aerobic_efficiency"),
        "ride_classification": derived.get("ride_classification"),

        "fatigue_onset_min": fatigue.get("fatigue_onset_min"),
        "power_drop_pct": fatigue.get("power_drop_pct"),
        "efficiency_drop_pct": fatigue.get("efficiency_drop_pct"),
        "climb_repeatability_pct": fatigue.get("climb_repeatability_pct"),

        "primary_type": profile.get("primary_type"),
        "secondary_type": profile.get("secondary_type"),
        "competition_style": profile.get("competition_style"),
        "strengths": profile.get("strengths"),
        "limiters": profile.get("limiters"),
        "development_focus": profile.get("development_focus"),
        "confidence": profile.get("confidence"),

        "avg_msi": metabolic.get("avg_msi"),
        "max_msi": metabolic.get("max_msi"),
        "high_msi_pct": metabolic.get("high_msi_pct"),
        "valid_msi_samples": metabolic.get("valid_msi_samples"),

        "climb_count": len(climbs),
        "top_climb_power": top_climb.get("avg_power") if top_climb else None,
        "top_climb_duration_min": top_climb.get("duration_min") if top_climb else None,
        "top_climb_gain_m": top_climb.get("elevation_gain_m") if top_climb else None,
        "top_climb_grade_pct": top_climb.get("avg_grade_pct") if top_climb else None,
        "top_climb_score": top_climb.get("climb_score") if top_climb else None,

        "vo2_count": vo2_count,
        "sprint_count": sprint_count,
        "threshold_count": threshold_count,
    }

    return row


def upsert_history_row(history, row):
    activities = history.get("activities", [])

    existing_idx = None
    for i, item in enumerate(activities):
        if item.get("activity_id") == row.get("activity_id"):
            existing_idx = i
            break

    if existing_idx is not None:
        activities[existing_idx] = row
    else:
        activities.append(row)

    history["activities"] = activities
    return history


def main():
    analysis_path = input("Ruta del archivo activity_analysis.json: ").strip()
    user_id = input("user_id (Enter para usar actual): ").strip() or None

    if not os.path.exists(analysis_path):
        print("No se encontró el archivo.")
        return

    analysis = load_json(analysis_path)
    history = load_history(user_id=user_id)

    row = build_history_row(analysis)
    history = upsert_history_row(history, row)
    save_history(history, user_id=user_id)

    history_file = get_activity_history_path(user_id)

    print("\n==========================")
    print("HISTORIAL ACTUALIZADO")
    print("==========================")
    print(f"Actividad guardada: {row.get('name')}")
    print(f"ID: {row.get('activity_id')}")
    print(f"Tipo: {row.get('type')}")
    print(f"Archivo: {history_file}")
    print(f"Total actividades en historial: {len(history.get('activities', []))}")


if __name__ == "__main__":
    main()