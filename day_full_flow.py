import json
import os

from day_engine_v1 import build_day_series, compute_day_analysis, build_findings, extract_notable_events_day
from build_day_brief import build_day_brief
from day_history_engine import run_day_history_engine
from day_brief_ai import generate_day_ai_brief

from app_context import (
    get_current_user_id,
    get_user_root,
    get_day_dir,
    get_day_history_dir,
    get_day_raw_path,
    get_day_series_path,
    get_day_analysis_path,
    get_day_findings_path,
    get_day_brief_path,
    get_day_events_path,
    get_day_trends_path,
    get_day_patterns_path,
    get_day_longitudinal_brief_path,
    get_day_day_dir,
)

# Charts opcionales para que no truene si todavía no has pegado ese archivo
try:
    from day_charts_generator import generate_day_charts, generate_day_history_charts
except Exception:
    def generate_day_charts(day_day_dir):
        return []

    def generate_day_history_charts(day_history_dir):
        return []


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

def build_day_raw_dump(client, date_str, user_id=None, verbose=True):
    user_id = user_id or get_current_user_id()

    return {
        "meta": {
            "date": date_str,
            "user_id": user_id
        },
        "calls": {
            "get_stats": safe_call("get_stats", lambda: client.get_stats(date_str), verbose=verbose),
            "get_heart_rates": safe_call("get_heart_rates", lambda: client.get_heart_rates(date_str), verbose=verbose),
            "get_stress_data": safe_call("get_stress_data", lambda: client.get_stress_data(date_str), verbose=verbose),
            "get_body_battery": safe_call("get_body_battery", lambda: client.get_body_battery(date_str, date_str), verbose=verbose),
            "get_respiration_data": safe_call("get_respiration_data", lambda: client.get_respiration_data(date_str), verbose=verbose),
            "get_hrv_data": safe_call("get_hrv_data", lambda: client.get_hrv_data(date_str), verbose=verbose),
        }
    }

def print_ai_result(ai_brief):
    hero = ai_brief.get("hero", {})
    systems = ai_brief.get("systems", [])
    today = ai_brief.get("today", {})
    pattern = ai_brief.get("pattern", {})
    correlations = ai_brief.get("correlations", [])
    deep_analysis = ai_brief.get("deep_analysis", {})

    print("\n==========================")
    print("DAY AI BRIEF")
    print("==========================\n")

    print(f"Score: {hero.get('score', '')}/100")
    print(f"Status: {hero.get('status', '')}")
    print(f"Headline: {hero.get('headline', '')}\n")

    if systems:
        print("SISTEMAS HOY:\n")
        for s in systems:
            print(f"{s.get('name','')} — {s.get('score','')}/10 [{s.get('status','')}]")
            print(f"  {s.get('message','')}\n")

    print(f"Rendimiento: {today.get('performance', '')}")
    print(f"Acción: {today.get('action', '')}\n")
    print(f"Patrón: {pattern.get('message', '')}\n")

    if correlations:
        print("CORRELACIONES:")
        for c in correlations:
            print(f"  {' ↔ '.join(c.get('systems',[]))} — {c.get('insight','')}\n")

    print("==========================")
    print("DEEP ANALYSIS")
    print("==========================\n")

    print(f"Headline: {deep_analysis.get('headline', '')}\n")
    print(f"Tipo de día: {deep_analysis.get('day_type_interpretation', '')}\n")
    print(f"Limitante principal: {deep_analysis.get('primary_limiter', '')}\n")
    print(f"Limitante secundario: {deep_analysis.get('secondary_limiter', '')}\n")
    print(f"Insight principal: {deep_analysis.get('main_insight', '')}\n")
    print(f"Qué está pasando: {deep_analysis.get('what_is_happening', '')}\n")
    print(f"Qué significa en ti: {deep_analysis.get('what_it_means_in_you', '')}\n")
    print(f"Probables drivers: {deep_analysis.get('likely_drivers', '')}\n")
    print(f"Resumen fisiológico: {deep_analysis.get('physiology_summary', '')}\n")
    print(f"Impacto en rendimiento: {deep_analysis.get('performance_outlook', '')}\n")
    print(f"Qué hacer con entrenamiento: {deep_analysis.get('training_guidance', '')}\n")
    print(f"Foco de recuperación: {deep_analysis.get('recovery_focus', '')}\n")
    print(f"Seguimiento: {deep_analysis.get('follow_up_priority', '')}\n")

    takeaways = deep_analysis.get("key_takeaways", [])
    if takeaways:
        print("KEY TAKEAWAYS:")
        for item in takeaways:
            print(f"- {item}")


def run_day_full_flow(
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
        print(f"INICIANDO DAY FULL FLOW: {date_str}")
        print("===================================")

    # 1) RAW
    raw_dump = build_day_raw_dump(client, date_str, user_id=user_id, verbose=verbose)
    save_json(get_day_raw_path(date_str, user_id), raw_dump)

    stats_ok = raw_dump["calls"]["get_stats"]["ok"]

    if not stats_ok:
        if verbose:
            print("\n[ERROR] No se pudo bajar toda la data necesaria.")
            print("Revisa day_raw.json.")
        return None

    # 2) SERIES
    series = build_day_series(raw_dump)
    save_json(get_day_series_path(date_str, user_id), series)
    if verbose:
        print("[OK] day_series.json")

    # 2b) NOTABLE EVENTS (intraday signals with timestamps)
    notable_events = extract_notable_events_day(series)
    save_json(get_day_events_path(date_str, user_id), notable_events)
    if verbose:
        print(f"[OK] day_events.json ({len(notable_events)} eventos)")

    # 3) ANALYSIS
    analysis = compute_day_analysis(raw_dump, series, user_dir=get_user_root(user_id))
    save_json(get_day_analysis_path(date_str, user_id), analysis)
    if verbose:
        print("[OK] day_analysis.json")

    # 4) FINDINGS
    # Cargar baselines para findings personalizados
    from day_engine_v1 import load_personal_baselines
    _baselines = load_personal_baselines(get_user_root(user_id))
    findings = build_findings(analysis, baselines=_baselines)
    save_json(get_day_findings_path(date_str, user_id), findings)
    if verbose:
        print("[OK] day_findings.json")

    # 5) BRIEF INTERNO
    brief = build_day_brief(analysis, findings)
    save_json(get_day_brief_path(date_str, user_id), brief)
    if verbose:
        print("[OK] day_brief.json")

    # 6) CHARTS DEL DÍA
    day_chart_files = []
    if run_charts:
        try:
            day_chart_files = generate_day_charts(get_day_day_dir(date_str, user_id))
            if verbose:
                print(f"[OK] Charts día: {len(day_chart_files)}")
        except Exception as e:
            if verbose:
                print(f"[WARNING] No se pudieron generar charts del día: {e}")

    # 7) HISTORY
    history_chart_files = []
    if run_history:
        try:
            run_day_history_engine(
                base_day_dir=get_day_dir(user_id),
                out_history_dir=get_day_history_dir(user_id)
            )
            if verbose:
                print("[OK] day_history_engine")

            if run_charts:
                try:
                    history_chart_files = generate_day_history_charts(get_day_history_dir(user_id))
                    if verbose:
                        print(f"[OK] Charts history: {len(history_chart_files)}")
                except Exception as e:
                    if verbose:
                        print(f"[WARNING] No se pudieron generar charts de history: {e}")

        except Exception as e:
            if verbose:
                print(f"[WARNING] No se pudo correr day_history_engine: {e}")

    # 8) AI BRIEF
    ai_ok = False
    brief_ai = {}
    brief_ai_path = None

    if run_ai:
        ai_result = generate_day_ai_brief(
            analysis_path=get_day_analysis_path(date_str, user_id),
            findings_path=get_day_findings_path(date_str, user_id),
            brief_path=get_day_brief_path(date_str, user_id),
            events_path=get_day_events_path(date_str, user_id),
            longitudinal_brief_path=get_day_longitudinal_brief_path(user_id),
            trends_path=get_day_trends_path(user_id),
            patterns_path=get_day_patterns_path(user_id),
            user_dir=get_user_root(user_id),
        )

        if ai_result:
            brief_ai, brief_ai_path = ai_result
            ai_ok = True

            if verbose:
                print("[OK] day_brief_ai.json")
                if brief_ai_path:
                    print(f"[INFO] Archivo IA guardado en: {brief_ai_path}")
                print_ai_result(brief_ai)
        else:
            if verbose:
                print("[WARNING] No se pudo generar day_brief_ai.json")

    # Dual write a PostgreSQL
    try:
        from db import ensure_user, upsert_day
        from app_context import get_current_garmin_email
        email = get_current_garmin_email()
        if email:
            db_user_id = ensure_user(email)
            upsert_day(db_user_id, date_str, analysis, brief_ai)
            if verbose:
                print("[DB] day_daily actualizado en PostgreSQL")
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
        "day_chart_files": day_chart_files,
        "history_chart_files": history_chart_files,
        "day_raw_file": get_day_raw_path(date_str, user_id),
        "day_series_file": get_day_series_path(date_str, user_id),
        "day_analysis_file": get_day_analysis_path(date_str, user_id),
        "day_findings_file": get_day_findings_path(date_str, user_id),
        "day_brief_file": get_day_brief_path(date_str, user_id),
        "day_brief_ai_file": brief_ai_path,
        "day_history_file": os.path.join(get_day_history_dir(user_id), "day_history.json"),
        "day_trends_file": get_day_trends_path(user_id),
        "day_patterns_file": get_day_patterns_path(user_id),
        "day_longitudinal_brief_file": get_day_longitudinal_brief_path(user_id),
    }

    if verbose:
        print("\n===================================")
        print("DAY FULL FLOW TERMINADO")
        print("===================================")
        print(f"Usuario: {user_id}")
        print(f"Fecha: {date_str}")
        print(f"Overall day state score: {analysis['recovery_summary']['overall_day_state_score']}")
        print(f"Primary limiter: {findings.get('limiters', {}).get('primary_limiter', '')}")
        print(f"IA generada: {'SÍ' if ai_ok else 'NO'}")
        print(f"Charts día: {len(day_chart_files)}")
        print(f"Charts history: {len(history_chart_files)}")
        print("===================================\n")

    return result


def main():
    from garmin_auth import login_garmin

    print("===================================")
    print("DAY FULL FLOW")
    print("===================================")

    email = input("Correo Garmin: ").strip()
    password = input("Contraseña Garmin: ").strip()
    date_str = input("Fecha a analizar (YYYY-MM-DD): ").strip()

    client = login_garmin(email, password)
    if not client:
        print("No se pudo iniciar sesión en Garmin.")
        return

    result = run_day_full_flow(client, date_str=date_str, verbose=True)

    if not result:
        print("No se pudo completar el flujo.")


if __name__ == "__main__":
    main()