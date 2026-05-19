"""
generate_activity_brief.py
==========================
Genera activity_brief.json para una actividad específica usando solo los
archivos JSON ya existentes en disco — no necesita cliente Garmin.

Uso:
    python generate_activity_brief.py --activity_id 22530043901

Imprime JSON a stdout:
    { "ok": true, "brief_file": "...", "activity_id": "..." }
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
    get_activity_analysis_path,
    get_activity_findings_path,
)
from activity_brief_ai import (
    build_prompt,
    call_ai,
    parse_json_response,
    save_brief_json,
    build_previous_activities_summary,
    build_motor_score,
    build_motor_score_label,
    normalize_quick_output,
    fill_quick_fallbacks,
)
from trend_analyzer import analyze_trends
from limiter_detector import detect_limiter
from history_engine import load_history
from athlete_context import get_athlete_context_for_section


def _load(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--activity_id", required=True, help="ID de la actividad")
    args = parser.parse_args()
    activity_id = str(args.activity_id)

    # ── Usuario activo ────────────────────────────────────────────────────────
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

    # ── Verificar que el analysis existe ─────────────────────────────────────
    analysis_path = get_activity_analysis_path(activity_id, user_id)
    if not os.path.exists(analysis_path):
        print(json.dumps({"ok": False, "error": f"activity_analysis.json no encontrado: {analysis_path}"}))
        sys.exit(1)

    # ── Verificar si ya existe el brief (caché) ───────────────────────────────
    brief_path = os.path.join(os.path.dirname(analysis_path), "activity_brief.json")
    if os.path.exists(brief_path):
        brief = _load(brief_path)
        print(json.dumps({"ok": True, "cached": True, "brief_file": brief_path, "activity_id": activity_id, "brief": brief}))
        sys.exit(0)

    # ── Cargar todos los inputs ───────────────────────────────────────────────
    analysis  = _load(analysis_path)
    findings  = _load(get_activity_findings_path(activity_id, user_id))
    series_insights = _load(os.path.join(os.path.dirname(analysis_path), "series_insights.json"))

    # Notable events (may not exist for older activities)
    events_raw = _load(os.path.join(os.path.dirname(analysis_path), "activity_events.json"))
    notable_events = events_raw if isinstance(events_raw, list) else []

    # Limiter y tendencias (calculados de historial local, sin Garmin)
    limiter      = detect_limiter(analysis)
    history      = load_history(user_id=user_id)
    trend_report = analyze_trends(history)

    # Contexto del atleta
    athlete_context = get_athlete_context_for_section(user_dir, "activity")

    # Últimas 4 actividades previas para comparación
    previous_analyses = []
    index_path = os.path.join(user_dir, "activity_index.json")
    if os.path.exists(index_path):
        idx_raw  = _load(index_path)
        idx_acts = idx_raw.get("activities", idx_raw) if isinstance(idx_raw, dict) else idx_raw
        prev_acts = [a for a in idx_acts if str(a.get("activity_id", "")) != activity_id][-4:]
        for prev in reversed(prev_acts):
            af = prev.get("analysis_file", "")
            full = af if os.path.isabs(af) else os.path.join(BASE_DIR, af)
            if os.path.exists(full):
                previous_analyses.append(_load(full))

    prev_summary = build_previous_activities_summary(previous_analyses)

    # Baseline y perfil para el plan de 3 días
    athlete_baseline = _load(os.path.join(user_dir, "performance_intelligence", "athlete_baseline.json"))
    profile          = _load(os.path.join(user_dir, "profile.json"))

    # ── Llamar a Claude ───────────────────────────────────────────────────────
    findings_payload = {"findings": findings.get("findings", [])} if isinstance(findings, dict) else {"findings": []}

    prompt = build_prompt(
        analysis,
        findings_payload,
        limiter=limiter,
        trends=trend_report,
        athlete_context=athlete_context,
        previous_activities=prev_summary,
        athlete_baseline=athlete_baseline,
        profile=profile,
        series_insights=series_insights,
        notable_events=notable_events,
    )

    motor_score = build_motor_score(analysis)
    motor_label = build_motor_score_label(motor_score)

    try:
        raw_text = call_ai(prompt)
        brief    = parse_json_response(raw_text)
        brief    = normalize_quick_output(brief, motor_score, motor_label)
    except Exception as e:
        brief = fill_quick_fallbacks(analysis, findings_payload)

    # ── Guardar en disco (caché permanente) ───────────────────────────────────
    saved_path = save_brief_json(analysis_path, brief)

    # Actualizar brief_file en activity_index.json
    try:
        idx_raw  = _load(index_path)
        idx_acts = idx_raw.get("activities", idx_raw) if isinstance(idx_raw, dict) else idx_raw
        updated  = False
        for act in idx_acts:
            if str(act.get("activity_id", "")) == activity_id:
                act["brief_file"] = saved_path
                updated = True
                break
        if updated:
            if isinstance(idx_raw, dict):
                idx_raw["activities"] = idx_acts
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(idx_raw, f, indent=2, ensure_ascii=False)
            else:
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(idx_acts, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # no-fatal — el brief ya está guardado

    print(json.dumps({"ok": True, "cached": False, "brief_file": saved_path, "activity_id": activity_id, "brief": brief}))


if __name__ == "__main__":
    main()
