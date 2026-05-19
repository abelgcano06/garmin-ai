"""
generate_day_brief.py
=====================
Genera day_brief_ai.json para una fecha específica usando solo los
archivos JSON ya existentes en disco — no necesita cliente Garmin.

Uso:
    python generate_day_brief.py --date 2026-04-19

Salida JSON a stdout:
    { "ok": true, "brief_file": "...", "date": "..." }
    { "ok": false, "error": "..." }
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app_context import (
    set_current_garmin_email,
    get_current_user_id,
    get_user_root,
    get_day_analysis_path,
    get_day_findings_path,
    get_day_brief_path,
    get_day_events_path,
    get_day_history_dir,
)
from day_brief_ai import generate_day_ai_brief


def _load(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    args = parser.parse_args()
    date_str = args.date

    session_path = os.path.join(BASE_DIR, "data", "session.json")
    if not os.path.exists(session_path):
        print(json.dumps({"ok": False, "error": "Sin sesión activa"}))
        sys.exit(1)

    session = _load(session_path)
    email = session.get("email", "").strip()
    if not email:
        print(json.dumps({"ok": False, "error": "Email no encontrado en session.json"}))
        sys.exit(1)

    set_current_garmin_email(email)
    user_id = get_current_user_id()
    user_dir = get_user_root(user_id)

    analysis_path = get_day_analysis_path(date_str, user_id)
    if not os.path.exists(analysis_path):
        print(json.dumps({"ok": False, "error": f"day_analysis.json no encontrado: {analysis_path}"}))
        sys.exit(1)

    # Check cache
    history_dir = get_day_history_dir(user_id)
    day_day_dir = os.path.dirname(analysis_path)
    brief_ai_path = os.path.join(day_day_dir, "day_brief_ai.json")
    if os.path.exists(brief_ai_path):
        brief = _load(brief_ai_path)
        print(json.dumps({"ok": True, "cached": True, "brief_file": brief_ai_path, "date": date_str, "brief": brief}))
        sys.exit(0)

    result = generate_day_ai_brief(
        analysis_path=get_day_analysis_path(date_str, user_id),
        findings_path=get_day_findings_path(date_str, user_id),
        brief_path=get_day_brief_path(date_str, user_id),
        events_path=get_day_events_path(date_str, user_id),
        longitudinal_brief_path=os.path.join(history_dir, "day_longitudinal_brief.json"),
        trends_path=os.path.join(history_dir, "day_trends.json"),
        patterns_path=os.path.join(history_dir, "day_patterns.json"),
        user_dir=user_dir,
    )

    if not result:
        print(json.dumps({"ok": False, "error": "Claude no pudo generar el brief"}))
        sys.exit(1)

    brief_ai, saved_path = result
    print(json.dumps({"ok": True, "cached": False, "brief_file": saved_path, "date": date_str, "brief": brief_ai}))


if __name__ == "__main__":
    main()
