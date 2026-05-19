import json
import os
from datetime import datetime

from app_context import get_current_user_id, get_user_root


def get_activity_index_path(user_id=None):
    user_id = user_id or get_current_user_id()
    return os.path.join(get_user_root(user_id), "activity_index.json")


def load_activity_index(user_id=None):
    path = get_activity_index_path(user_id)

    if not os.path.exists(path):
        return {"activities": []}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_activity_index(index_data, user_id=None):
    path = get_activity_index_path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    return path


def build_activity_index_row(
    activity,
    analysis_result,
    findings_file,
    brief_file,
    chart_files,
    limiter,
):
    garmin = analysis_result.get("garmin_summary", {})
    derived = analysis_result.get("derived_summary", {})

    row = {
        "activity_id": activity.get("activityId"),
        "indexed_at": datetime.now().isoformat(),
        "date": activity.get("startTimeLocal"),
        "name": activity.get("activityName"),
        "type": activity.get("activityType", {}).get("typeKey"),
        "distance_km": garmin.get("distance_km"),
        "moving_minutes": garmin.get("moving_minutes"),
        "elevation_m": garmin.get("elevation_m"),
        "avg_hr": garmin.get("avg_hr"),
        "avg_power": garmin.get("avg_power"),
        "garmin_np": garmin.get("garmin_np"),
        "estimated_np": derived.get("estimated_np"),
        "vi": derived.get("vi"),
        "ride_classification": derived.get("ride_classification"),
        "primary_limiter": limiter.get("primary_limiter") if limiter else None,
        "secondary_limiter": limiter.get("secondary_limiter") if limiter else None,
        "analysis_file": os.path.join(os.path.dirname(brief_file or findings_file or ""), "activity_analysis.json"),
        "findings_file": findings_file,
        "brief_file": brief_file,
        "chart_files": chart_files or [],
    }

    return row


def upsert_activity_index_row(index_data, row):
    activities = index_data.get("activities", [])

    existing_idx = None
    for i, item in enumerate(activities):
        if item.get("activity_id") == row.get("activity_id"):
            existing_idx = i
            break

    if existing_idx is not None:
        activities[existing_idx] = row
    else:
        activities.append(row)

    # orden descendente por fecha si existe
    activities.sort(
        key=lambda x: x.get("date") or "",
        reverse=True
    )

    index_data["activities"] = activities
    return index_data


def update_activity_index(
    activity,
    analysis_result,
    findings_file,
    brief_file,
    chart_files,
    limiter,
    user_id=None,
):
    index_data = load_activity_index(user_id)

    row = build_activity_index_row(
        activity=activity,
        analysis_result=analysis_result,
        findings_file=findings_file,
        brief_file=brief_file,
        chart_files=chart_files,
        limiter=limiter,
    )

    index_data = upsert_activity_index_row(index_data, row)
    index_path = save_activity_index(index_data, user_id)

    return index_path, row


def main():
    print("Este módulo está pensado para ser llamado desde activity_full_flow.py")


if __name__ == "__main__":
    main()