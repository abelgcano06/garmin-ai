import os
import json
from typing import Optional

BASE_DATA_DIR = "data"
USERS_DIR = os.path.join(BASE_DATA_DIR, "users")

# Contexto vivo de la sesión actual
_CURRENT_GARMIN_EMAIL: Optional[str] = None


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def email_to_user_id(email: str) -> str:
    clean = email.strip().lower()
    clean = clean.replace("@", "_at_")
    clean = clean.replace(".", "_")
    return clean


def set_current_garmin_email(email: str) -> None:
    global _CURRENT_GARMIN_EMAIL
    _CURRENT_GARMIN_EMAIL = email.strip().lower()


def get_current_garmin_email() -> str:
    if not _CURRENT_GARMIN_EMAIL:
        raise ValueError("No hay correo Garmin activo en el contexto actual.")
    return _CURRENT_GARMIN_EMAIL


def get_current_user_id() -> str:
    return email_to_user_id(get_current_garmin_email())


def get_user_root(user_id: str | None = None) -> str:
    user_id = user_id or get_current_user_id()
    return ensure_dir(os.path.join(USERS_DIR, user_id))


def get_user_profile_path(user_id: str | None = None) -> str:
    return os.path.join(get_user_root(user_id), "profile.json")


def get_recent_activities_path(user_id: str | None = None) -> str:
    return os.path.join(get_user_root(user_id), "recent_activities.json")


def get_history_dir(user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_user_root(user_id), "history"))


def get_activity_history_path(user_id: str | None = None) -> str:
    return os.path.join(get_history_dir(user_id), "activity_history.json")


def get_activities_dir(user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_user_root(user_id), "activities"))


def get_activity_dir(activity_id: int | str, user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_activities_dir(user_id), str(activity_id)))


def get_activity_details_path(activity_id: int | str, user_id: str | None = None) -> str:
    return os.path.join(get_activity_dir(activity_id, user_id), "activity_details.json")


def get_activity_series_path(activity_id: int | str, user_id: str | None = None) -> str:
    return os.path.join(get_activity_dir(activity_id, user_id), "activity_series_clean.csv")


def get_activity_analysis_path(activity_id: int | str, user_id: str | None = None) -> str:
    return os.path.join(get_activity_dir(activity_id, user_id), "activity_analysis.json")


def get_activity_findings_path(activity_id: int | str, user_id: str | None = None) -> str:
    return os.path.join(get_activity_dir(activity_id, user_id), "activity_findings.json")


def get_activity_brief_path(activity_id: int | str, user_id: str | None = None) -> str:
    return os.path.join(get_activity_dir(activity_id, user_id), "activity_brief.json")


def get_activity_events_path(activity_id: int | str, user_id: str | None = None) -> str:
    return os.path.join(get_activity_dir(activity_id, user_id), "activity_events.json")


def get_activity_charts_dir(activity_id: int | str, user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_activity_dir(activity_id, user_id), "charts"))


# =========================
# Sleep paths
# =========================

def get_sleep_dir(user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_user_root(user_id), "sleep"))


def get_sleep_day_dir(date_str: str, user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_sleep_dir(user_id), date_str))


def get_sleep_raw_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_sleep_day_dir(date_str, user_id), "sleep_raw.json")


def get_sleep_series_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_sleep_day_dir(date_str, user_id), "sleep_series.json")


def get_sleep_analysis_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_sleep_day_dir(date_str, user_id), "sleep_analysis.json")


def get_sleep_findings_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_sleep_day_dir(date_str, user_id), "sleep_findings.json")


def get_sleep_brief_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_sleep_day_dir(date_str, user_id), "sleep_brief.json")


def get_sleep_events_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_sleep_day_dir(date_str, user_id), "sleep_events.json")


def get_sleep_history_dir(user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_user_root(user_id), "sleep_history"))


def get_sleep_history_path(user_id: str | None = None) -> str:
    return os.path.join(get_sleep_history_dir(user_id), "sleep_history.json")


def get_sleep_trends_path(user_id: str | None = None) -> str:
    return os.path.join(get_sleep_history_dir(user_id), "sleep_trends.json")


def get_sleep_patterns_path(user_id: str | None = None) -> str:
    return os.path.join(get_sleep_history_dir(user_id), "sleep_patterns.json")


def get_sleep_longitudinal_brief_path(user_id: str | None = None) -> str:
    return os.path.join(get_sleep_history_dir(user_id), "sleep_longitudinal_brief.json")


def ensure_current_user_profile(
    garmin_email: str | None = None,
    sport_focus: list[str] | None = None,
    ftp: int | None = None,
    max_hr: int | None = None
) -> None:
    if garmin_email:
        set_current_garmin_email(garmin_email)

    path = get_user_profile_path()
    if os.path.exists(path):
        return

    profile = {
        "user_id": get_current_user_id(),
        "garmin_email": get_current_garmin_email(),
        "sport_focus": sport_focus or ["cycling", "running", "health"],
        "ftp": ftp if ftp is not None else 230,
        "max_hr": max_hr if max_hr is not None else 185
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

        # =========================
# Day paths
# =========================

def get_day_dir(user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_user_root(user_id), "day"))


def get_day_day_dir(date_str: str, user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_day_dir(user_id), date_str))


def get_day_raw_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_day_day_dir(date_str, user_id), "day_raw.json")


def get_day_series_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_day_day_dir(date_str, user_id), "day_series.json")


def get_day_analysis_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_day_day_dir(date_str, user_id), "day_analysis.json")


def get_day_findings_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_day_day_dir(date_str, user_id), "day_findings.json")


def get_day_brief_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_day_day_dir(date_str, user_id), "day_brief.json")


def get_day_events_path(date_str: str, user_id: str | None = None) -> str:
    return os.path.join(get_day_day_dir(date_str, user_id), "day_events.json")


def get_day_history_dir(user_id: str | None = None) -> str:
    return ensure_dir(os.path.join(get_user_root(user_id), "day_history"))


def get_day_history_path(user_id: str | None = None) -> str:
    return os.path.join(get_day_history_dir(user_id), "day_history.json")


def get_day_baselines_path(user_id: str | None = None) -> str:
    return os.path.join(get_day_history_dir(user_id), "day_baselines.json")


def get_day_trends_path(user_id: str | None = None) -> str:
    return os.path.join(get_day_history_dir(user_id), "day_trends.json")


def get_day_patterns_path(user_id: str | None = None) -> str:
    return os.path.join(get_day_history_dir(user_id), "day_patterns.json")


def get_day_longitudinal_brief_path(user_id: str | None = None) -> str:
    return os.path.join(get_day_history_dir(user_id), "day_longitudinal_brief.json")