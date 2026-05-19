import json
import os

from sleep_engine_v1 import build_sleep_series, compute_analysis, build_findings, extract_notable_events
from build_sleep_brief import build_sleep_brief
from sleep_history_engine import run_sleep_history_engine
from sleep_brief_ai import generate_sleep_ai_brief
from sleep_charts_generator import generate_sleep_night_charts, generate_sleep_history_charts

from app_context import (
    get_current_user_id,
    get_user_root,
    get_sleep_dir,
    get_sleep_history_dir,
    get_sleep_raw_path,
    get_sleep_series_path,
    get_sleep_analysis_path,
    get_sleep_findings_path,
    get_sleep_brief_path,
    get_sleep_events_path,
    get_sleep_trends_path,
    get_sleep_patterns_path,
    get_sleep_longitudinal_brief_path,
    get_sleep_day_dir,
)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_call(name, fn, verbose=True):
    try:
        data = fn()
        if verbose:
            print(f"[OK] {name}")
        return {"ok": True, "data": data}
    except Exception as e:
        if verbose:
            print(f"[ERROR] {name}: {e}")
        return {"ok": False, "error": str(e)}


def build_sleep_raw_dump(client, date_str, user_id=None, verbose=True):
    user_id = user_id or get_current_user_id()

    return {
        "meta": {
            "date": date_str,
            "user_id": user_id
        },
        "calls": {
            "get_stats": safe_call("get_stats", lambda: client.get_stats(date_str), verbose=verbose),
            "get_sleep_data": safe_call("get_sleep_data", lambda: client.get_sleep_data(date_str), verbose=verbose),
        }
    }

def print_ai_result(ai_brief):
    hero = ai_brief.get("hero", {})
    systems = ai_brief.get("systems", [])
    today = ai_brief.get("today", {})
    pattern = ai_brief.get("pattern", {})
    deep_analysis = ai_brief.get("deep_analysis", {})

    print("\n==========================")
    print("SLEEP HERO")
    print("==========================\n")
    print(f"SLEEP SCORE: {hero.get('score', '')}/100")
    print(f"STATUS: {hero.get('status', '')}\n")
    print(f"{hero.get('headline', '')}\n")

    if systems:
        print("==========================")
        print("CÓMO AMANECIERON TUS SISTEMAS")
        print("==========================\n")

        for system in systems:
            print(f"{system.get('name', '')}")
            print(f"Score: {system.get('score', '')}/10")
            print(f"Estado: {system.get('status', '')}")
            print(f"{system.get('message', '')}\n")

    print("==========================")
    print("HOY")
    print("==========================\n")
    print(f"Rendimiento: {today.get('performance', '')}\n")
    print(f"Acción: {today.get('action', '')}\n")

    print("==========================")
    print("TU PATRÓN")
    print("==========================\n")
    print(f"{pattern.get('message', '')}\n")

    print("==========================")
    print("DEEP ANALYSIS")
    print("==========================\n")

    print(f"Headline: {deep_analysis.get('headline', '')}\n")
    print(f"Tipo de noche: {deep_analysis.get('night_type_interpretation', '')}\n")
    print(f"Insight principal: {deep_analysis.get('main_insight', '')}\n")
    print(f"Qué pasó: {deep_analysis.get('what_happened', '')}\n")
    print(f"Qué significa en ti: {deep_analysis.get('what_it_means_in_you', '')}\n")
    print(f"Probables drivers: {deep_analysis.get('likely_drivers', '')}\n")
    print(f"Impacto en rendimiento: {deep_analysis.get('performance_outlook', '')}\n")
    print(f"Entrenamiento: {deep_analysis.get('training_guidance', '')}\n")
    print(f"Recovery: {deep_analysis.get('recovery_focus', '')}\n")
    print(f"Seguimiento: {deep_analysis.get('follow_up_priority', '')}\n")

    takeaways = deep_analysis.get("key_takeaways", [])
    if takeaways:
        print("KEY TAKEAWAYS:")
        for item in takeaways:
            print(f"- {item}")

def run_sleep_full_flow(
    client,
    date_str,
    user_id=None,
    run_history=True,
    run_ai=True,
    run_charts=True,
    verbose=True
):
    user_id = user_id or get_current_user_id()

    if verbose:
        print("\n===================================")
        print(f"INICIANDO SLEEP FULL FLOW: {date_str}")
        print("===================================")

    # 1) RAW — reutilizar si ya fue descargado (sync interrumpido o re-proceso)
    raw_path = get_sleep_raw_path(date_str, user_id)
    if os.path.exists(raw_path):
        import json as _json
        with open(raw_path, encoding="utf-8") as _f:
            raw_dump = _json.load(_f)
        if verbose:
            print(f"[CACHE] sleep_raw.json reutilizado para {date_str}")
    else:
        raw_dump = build_sleep_raw_dump(client, date_str, user_id=user_id, verbose=verbose)
        save_json(raw_path, raw_dump)

    sleep_ok = raw_dump["calls"]["get_sleep_data"]["ok"]
    stats_ok = raw_dump["calls"]["get_stats"]["ok"]

    if not sleep_ok or not stats_ok:
        if verbose:
            print("\n[ERROR] No se pudo bajar toda la data necesaria.")
            print("Revisa sleep_raw.json.")
        return None

    # 2) SERIES
    series = build_sleep_series(raw_dump)
    save_json(get_sleep_series_path(date_str, user_id), series)
    if verbose:
        print("[OK] sleep_series.json")

    # 2b) NOTABLE EVENTS (temporal signals with timestamps)
    notable_events = extract_notable_events(series)
    save_json(get_sleep_events_path(date_str, user_id), notable_events)
    if verbose:
        print(f"[OK] sleep_events.json ({len(notable_events)} eventos)")

    # 3) ANALYSIS
    analysis = compute_analysis(raw_dump, series, user_dir=get_user_root(user_id))
    save_json(get_sleep_analysis_path(date_str, user_id), analysis)
    if verbose:
        print("[OK] sleep_analysis.json")

    # 4) FINDINGS
    findings = build_findings(analysis)
    save_json(get_sleep_findings_path(date_str, user_id), findings)
    if verbose:
        print("[OK] sleep_findings.json")

    # 5) BRIEF INTERNO
    brief = build_sleep_brief(analysis, findings)
    save_json(get_sleep_brief_path(date_str, user_id), brief)
    if verbose:
        print("[OK] sleep_brief.json")

    # 6) CHARTS DE LA NOCHE
    sleep_day_dir = get_sleep_day_dir(date_str, user_id)
    night_chart_files = []
    if run_charts:
        night_chart_files = generate_sleep_night_charts(sleep_day_dir)
        if verbose:
            print(f"[OK] charts noche generadas: {len(night_chart_files)}")

    # 7) HISTORY + BASLINES + TRENDS + PATTERNS + BOTTLENECKS + CLUSTERS
    history_chart_files = []

    if run_history:
        base_sleep_dir = get_sleep_dir(user_id)
        out_history_dir = get_sleep_history_dir(user_id)
        run_sleep_history_engine(base_sleep_dir, out_history_dir)

        if verbose:
            print("[OK] sleep_history / baselines / trends / anomalies / bottlenecks / patterns")

        # 8) CHARTS LONGITUDINALES
        if run_charts:
            history_chart_files = generate_sleep_history_charts(out_history_dir)
            if verbose:
                print(f"[OK] charts history generadas: {len(history_chart_files)}")

    # 9) AI BRIEF
    analysis_path = get_sleep_analysis_path(date_str, user_id)
    findings_path = get_sleep_findings_path(date_str, user_id)
    brief_path = get_sleep_brief_path(date_str, user_id)
    events_path = get_sleep_events_path(date_str, user_id)
    longitudinal_brief_path = get_sleep_longitudinal_brief_path(user_id)
    trends_path = get_sleep_trends_path(user_id)
    patterns_path = get_sleep_patterns_path(user_id)

    brief_ai = None
    brief_ai_path = None
    ai_ok = False

    if run_ai:
        if verbose:
            print("[INFO] Generando Sleep AI Brief...")

        ai_result = generate_sleep_ai_brief(
            analysis_path=analysis_path,
            findings_path=findings_path,
            brief_path=brief_path,
            events_path=events_path,
            longitudinal_brief_path=longitudinal_brief_path,
            trends_path=trends_path,
            patterns_path=patterns_path,
            user_dir=get_user_root(user_id),
        )

        if ai_result:
            brief_ai, brief_ai_path = ai_result
            ai_ok = True

            if verbose:
                print("[OK] sleep_brief_ai.json")
                if brief_ai_path:
                    print(f"[INFO] Archivo IA guardado en: {brief_ai_path}")
                print_ai_result(brief_ai)
        else:
            if verbose:
                print("[WARNING] No se pudo generar sleep_brief_ai.json")

    # Dual write a PostgreSQL
    try:
        from db import ensure_user, upsert_sleep
        from app_context import get_current_garmin_email
        email = get_current_garmin_email()
        if email:
            db_user_id = ensure_user(email)
            upsert_sleep(db_user_id, date_str, analysis, brief, brief_ai)
            if verbose:
                print("[DB] sleep_daily actualizado en PostgreSQL")
    except Exception as db_err:
        if verbose:
            print(f"[DB] Warning: no se pudo escribir en PostgreSQL: {db_err}")

    result = {
        "user_id": user_id,
        "date": date_str,
        "analysis": analysis,
        "findings": findings,
        "brief": brief,
        "brief_ai": brief_ai,
        "ai_ok": ai_ok,
        "night_chart_files": night_chart_files,
        "history_chart_files": history_chart_files,
        "sleep_raw_file": get_sleep_raw_path(date_str, user_id),
        "sleep_series_file": get_sleep_series_path(date_str, user_id),
        "sleep_analysis_file": get_sleep_analysis_path(date_str, user_id),
        "sleep_findings_file": get_sleep_findings_path(date_str, user_id),
        "sleep_brief_file": get_sleep_brief_path(date_str, user_id),
        "sleep_brief_ai_file": brief_ai_path,
        "sleep_history_file": os.path.join(get_sleep_history_dir(user_id), "sleep_history.json"),
        "sleep_trends_file": get_sleep_trends_path(user_id),
        "sleep_patterns_file": get_sleep_patterns_path(user_id),
        "sleep_longitudinal_brief_file": get_sleep_longitudinal_brief_path(user_id),
    }

    if verbose:
        print("\n===================================")
        print("SLEEP FULL FLOW TERMINADO")
        print("===================================")
        print(f"Usuario: {user_id}")
        print(f"Fecha: {date_str}")
        print(f"Overall recovery score: {analysis['recovery_summary']['overall_recovery_score']}")
        print(f"Primary limiter: {findings.get('limiters', {}).get('primary_limiter', '')}")
        print(f"IA generada: {'SÍ' if ai_ok else 'NO'}")
        print(f"Charts noche: {len(night_chart_files)}")
        print(f"Charts history: {len(history_chart_files)}")
        print("===================================\n")

    return result