from activity_pipeline import run_activity_pipeline
from series_insights_engine import run_series_insights, save_series_insights
from finding_engine import build_findings, save_findings_json
from insight_ranker import rank_findings
from activity_brief_ai import (
    build_prompt, call_ai, parse_json_response, save_brief_json,
    build_previous_activities_summary, build_motor_score, build_motor_score_label,
    normalize_quick_output, fill_quick_fallbacks,
)
from history_engine import load_history, save_history, build_history_row, upsert_history_row
from trend_analyzer import analyze_trends
from limiter_detector import detect_limiter
from charts_generator import generate_charts
from activity_index_engine import update_activity_index
from activity_history_engine import run_activity_history_engine
from app_context import get_current_user_id, get_activity_history_path, get_user_root, get_activity_events_path
from athlete_context import get_athlete_context_for_section
import csv
import json
import os


def extract_notable_events_activity(series_path: str, ftp: float = 230.0, max_hr: float = 185.0) -> list:
    """
    Scan CSV series for physiologically notable events with timestamps.
    Returns up to 6 events: [{time, signal, event, severity}]
    """
    if not os.path.exists(series_path):
        return []

    rows = []
    with open(series_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            def _f(k):
                try:
                    v = r.get(k, "")
                    return float(v) if v and v.strip() != "" else None
                except (ValueError, TypeError):
                    return None
            rows.append({
                "elapsed_s": _f("elapsed_s"),
                "heart_rate_bpm": _f("heart_rate_bpm"),
                "power_w": _f("power_w"),
                "cadence_rpm": _f("cadence_rpm"),
                "available_stamina": _f("available_stamina"),
                "respiration_brpm": _f("respiration_brpm"),
            })

    def fmt_time(elapsed_s):
        if elapsed_s is None:
            return "—"
        total_s = int(elapsed_s)
        h = total_s // 3600
        m = (total_s % 3600) // 60
        s = total_s % 60
        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

    events = []

    # 1. HR spikes: > 20 bpm above 10-sample local mean
    hr_vals = [r.get("heart_rate_bpm") for r in rows if r.get("heart_rate_bpm") is not None]
    if hr_vals:
        global_hr_mean = sum(hr_vals) / len(hr_vals)
        W = 10
        in_spike = False
        for i, row in enumerate(rows):
            hr = row.get("heart_rate_bpm")
            if hr is None:
                continue
            window = [r["heart_rate_bpm"] for r in rows[max(0, i - W):i] if r.get("heart_rate_bpm") is not None]
            local_mean = sum(window) / len(window) if window else global_hr_mean
            if hr > local_mean + 20 and not in_spike:
                in_spike = True
                events.append({
                    "time": fmt_time(row.get("elapsed_s")),
                    "signal": "FC",
                    "event": f"pico {round(hr)} bpm ({round(hr - local_mean):+.0f} vs media local)",
                    "severity": "high" if hr > max_hr * 0.96 else "medium",
                    "_t": row.get("elapsed_s") or 0,
                })
            elif hr <= local_mean + 10:
                in_spike = False

    # 2. Stamina crash: drop >= 20 pts in 30-sample window
    sta_vals = [r.get("available_stamina") for r in rows]
    i = 0
    while i < len(sta_vals) - 30:
        a = sta_vals[i]
        b = sta_vals[i + 30]
        if a is not None and b is not None and a - b >= 20:
            events.append({
                "time": fmt_time(rows[i].get("elapsed_s")),
                "signal": "Stamina",
                "event": f"caída {round(a - b):.0f}% en ~5 min (de {round(a):.0f}% → {round(b):.0f}%)",
                "severity": "high" if a - b >= 30 else "medium",
                "_t": rows[i].get("elapsed_s") or 0,
            })
            i += 30
        else:
            i += 1

    # 3. Cadence crash: < 55 rpm while producing > 50% FTP
    in_cad_drop = False
    for row in rows:
        cad = row.get("cadence_rpm")
        pw = row.get("power_w")
        if cad is not None and pw is not None and cad > 0 and cad < 55 and pw > ftp * 0.5:
            if not in_cad_drop:
                in_cad_drop = True
                events.append({
                    "time": fmt_time(row.get("elapsed_s")),
                    "signal": "Cadencia",
                    "event": f"cadencia {round(cad)} rpm con esfuerzo al {round(pw / ftp * 100):.0f}% FTP",
                    "severity": "medium",
                    "_t": row.get("elapsed_s") or 0,
                })
        else:
            in_cad_drop = False

    # 4. Respiration spike: > 38 brpm
    in_resp_spike = False
    for row in rows:
        resp = row.get("respiration_brpm")
        if resp is not None and resp > 38:
            if not in_resp_spike:
                in_resp_spike = True
                events.append({
                    "time": fmt_time(row.get("elapsed_s")),
                    "signal": "Respiración",
                    "event": f"frecuencia respiratoria {round(resp)} rpm — ventilación límite",
                    "severity": "high" if resp > 45 else "medium",
                    "_t": row.get("elapsed_s") or 0,
                })
        elif resp is not None and resp < 30:
            in_resp_spike = False

    # Deduplicate: remove events < 5 min apart from same signal
    deduped = []
    events.sort(key=lambda e: e.get("_t", 0))
    for ev in events:
        if not deduped:
            deduped.append(ev)
            continue
        last = deduped[-1]
        if ev["signal"] == last["signal"] and ev.get("_t", 0) - last.get("_t", 0) < 300:
            continue
        deduped.append(ev)

    for ev in deduped:
        ev.pop("_t", None)

    return deduped[:6]


def run_activity_full_flow(client, activity, user_id=None, run_ai=True, run_charts=True):
    user_id = user_id or get_current_user_id()

    # 1) Pipeline principal: details + serie limpia + analysis
    pipeline_result = run_activity_pipeline(client, activity, user_id=user_id)

    analysis_result = pipeline_result["analysis_result"]
    analysis_file = pipeline_result["analysis_file"]

    # Filtro de calidad: actividades sin datos reales no se procesan
    if "error" in analysis_result:
        print(f"[SKIP] Actividad sin serie de datos: {analysis_result['error']}")
        return None

    moving_minutes = analysis_result.get("garmin_summary", {}).get("moving_minutes", 0) or 0
    if moving_minutes < 10:
        print(f"[SKIP] Actividad demasiado corta ({moving_minutes:.1f} min), no entra al historial.")
        return None

    # 1.1) Generar gráficas automáticas y guardar lista
    chart_files = []
    if run_charts:
        chart_files = generate_charts(
            pipeline_result["series_file"],
            activity["activityId"],
            user_id=user_id,
        )

    # 1.2) Series insights: correlaciones temporales del CSV
    try:
        series_insights = run_series_insights(
            pipeline_result["series_file"],
            pipeline_result["analysis_file"],
        )
        save_series_insights(pipeline_result["analysis_file"], series_insights)
    except Exception as e:
        print(f"  [series_insights] Error: {e}")
        series_insights = {}

    # 1.3) Notable events: eventos específicos con timestamp del CSV
    try:
        ftp_derived = 230.0
        np_val = analysis_result.get("derived_summary", {}).get("estimated_np")
        if_val = analysis_result.get("derived_summary", {}).get("estimated_if")
        if np_val and if_val and if_val > 0:
            ftp_derived = round(np_val / if_val)
        max_hr_derived = analysis_result.get("garmin_summary", {}).get("max_hr") or 185.0

        notable_events = extract_notable_events_activity(
            pipeline_result["series_file"],
            ftp=ftp_derived,
            max_hr=max_hr_derived,
        )
        events_path = get_activity_events_path(activity["activityId"], user_id)
        with open(events_path, "w", encoding="utf-8") as _f:
            json.dump(notable_events, _f, indent=2, ensure_ascii=False)
        print(f"  [events] {len(notable_events)} eventos notables guardados")
    except Exception as e:
        print(f"  [events] Error: {e}")
        notable_events = []

    # 2) Findings estructurados
    findings = build_findings(analysis_result)

    # 3) Ranking de findings según importancia y perfil del atleta
    athlete_profile = analysis_result.get("athlete_profile", {})
    ranked_findings = rank_findings(findings, athlete_profile)
    findings_payload = {"findings": ranked_findings}

    # Guardar findings
    findings_file = save_findings_json(analysis_file, ranked_findings)

    # 4) History / memoria del atleta
    history = load_history(user_id=user_id)
    row = build_history_row(analysis_result)
    history = upsert_history_row(history, row)
    save_history(history, user_id=user_id)

    # 5) Trend analyzer
    trend_report = analyze_trends(history)

    # 6) Limiter detector
    limiter = detect_limiter(analysis_result)

    # 7) Brief IA enriquecido
    user_dir = get_user_root(user_id)
    athlete_context = get_athlete_context_for_section(user_dir, "activity")

    # Cargar últimas 3 actividades previas para comparación
    previous_analyses = []
    try:
        index_path = os.path.join(user_dir, "activity_index.json")
        if os.path.exists(index_path):
            idx_raw = json.load(open(index_path, encoding="utf-8"))
            idx_acts = idx_raw.get("activities", idx_raw) if isinstance(idx_raw, dict) else idx_raw
            current_id = str(activity.get("activityId", ""))
            prev_acts = [a for a in idx_acts if str(a.get("activity_id", "")) != current_id][-4:]
            for prev in reversed(prev_acts):
                analysis_file_prev = prev.get("analysis_file", "")
                full_path = analysis_file_prev if os.path.isabs(analysis_file_prev) else os.path.join(user_dir, analysis_file_prev)
                if full_path and os.path.exists(full_path):
                    previous_analyses.append(json.load(open(full_path, encoding="utf-8")))
    except Exception as e:
        print(f"  [brief_ai] No se pudo cargar historial previo: {e}")

    prev_summary = build_previous_activities_summary(previous_analyses)

    # Cargar baseline y perfil para el plan de 3 días
    athlete_baseline = json.load(open(os.path.join(user_dir, "performance_intelligence", "athlete_baseline.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(user_dir, "performance_intelligence", "athlete_baseline.json")) else {}
    profile = json.load(open(os.path.join(user_dir, "profile.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(user_dir, "profile.json")) else {}

    prompt = build_prompt(
        analysis_result,
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

    # 7b) AI brief — solo si run_ai=True (no corre en sync automático)
    brief = {}
    brief_file = None
    if run_ai:
        motor_score = build_motor_score(analysis_result)
        motor_label = build_motor_score_label(motor_score)
        try:
            raw_text = call_ai(prompt)
            brief = parse_json_response(raw_text)
            brief = normalize_quick_output(brief, motor_score, motor_label)
            brief_file = save_brief_json(analysis_file, brief)
        except Exception as e:
            print(f"  [brief_ai] ERROR al generar brief IA: {e}")
            brief = fill_quick_fallbacks(analysis_result, findings_payload)
            brief_file = save_brief_json(analysis_file, brief)
            print(f"  [brief_ai] Fallback motor guardado en: {brief_file}")

    # 8) Activity history engine: baselines, tendencias, patrones
    try:
        run_activity_history_engine(user_id=user_id)
    except Exception as e:
        print(f"  [history_engine] ERROR: {e}")

    # 9) Actualizar índice maestro SIEMPRE (aunque no haya brief)
    activity_index_file, activity_index_row = update_activity_index(
        activity=activity,
        analysis_result=analysis_result,
        findings_file=findings_file,
        brief_file=brief_file,
        chart_files=chart_files,
        limiter=limiter,
        user_id=user_id,
    )

    # Dual write a PostgreSQL
    try:
        from db import ensure_user, upsert_activity
        from app_context import get_current_garmin_email
        email = get_current_garmin_email()
        if email:
            db_user_id = ensure_user(email)
            analysis_data = pipeline_result.get("analysis") if pipeline_result else None
            upsert_activity(db_user_id, analysis_data, brief)
            print("[DB] activities actualizado en PostgreSQL")
    except Exception as db_err:
        print(f"[DB] Warning: no se pudo escribir en PostgreSQL: {db_err}")

    return {
        "pipeline_result": pipeline_result,
        "findings": findings_payload,
        "findings_file": findings_file,
        "brief": brief,
        "brief_file": brief_file,
        "history_file": get_activity_history_path(user_id),
        "trends": trend_report,
        "limiter": limiter,
        "chart_files": chart_files,
        "series_insights": series_insights,
        "user_id": user_id,
        "activity_index_file": activity_index_file,
        "activity_index_row": activity_index_row,
    }