import json
import os
from datetime import date, timedelta

from activity_full_flow import run_activity_full_flow
from activity_ai_chat import run_activity_ai_chat
from app_context import get_current_user_id, get_recent_activities_path


def get_recent_activities(client, days_back=7):
    """
    Obtiene actividades recientes de los últimos N días, incluyendo hoy.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back - 1)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    print(f"\nBuscando actividades del {start_str} al {end_str}...")

    activities = client.get_activities_by_date(start_str, end_str)
    return activities


def save_activities_json(activities, user_id=None):
    """
    Guarda actividades recientes dentro de la carpeta del usuario actual.
    """
    user_id = user_id or get_current_user_id()
    path = get_recent_activities_path(user_id)

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(activities, f, indent=2, ensure_ascii=False)

    return path


def print_activity_list(activities):
    if not activities:
        print("\nNo se encontraron actividades recientes.")
        return

    print("\n==============================")
    print("ACTIVIDADES RECIENTES")
    print("==============================")

    for i, act in enumerate(activities, start=1):
        name = act.get("activityName", "Sin nombre")
        activity_type = act.get("activityType", {}).get("typeKey", "unknown")
        distance_km = (act.get("distance", 0) or 0) / 1000
        moving_min = (act.get("movingDuration", 0) or 0) / 60
        date_str = act.get("startTimeLocal", "Sin fecha")

        print(
            f"{i}. {name} | {activity_type} | "
            f"{distance_km:.2f} km | {moving_min:.1f} min | {date_str}"
        )


def select_activity(activities):
    if not activities:
        return None

    while True:
        choice = input("\nElige el número de actividad (o 0 para cancelar): ").strip()

        if choice == "0":
            return None

        if not choice.isdigit():
            print("Pon un número válido.")
            continue

        idx = int(choice) - 1

        if 0 <= idx < len(activities):
            return activities[idx]

        print("Número fuera de rango.")


def show_activity_summary(activity):
    print("\n==============================")
    print("RESUMEN DE ACTIVIDAD")
    print("==============================")

    name = activity.get("activityName", "Sin nombre")
    activity_type = activity.get("activityType", {}).get("typeKey", "unknown")
    distance_km = (activity.get("distance", 0) or 0) / 1000
    moving_min = (activity.get("movingDuration", 0) or 0) / 60
    elapsed_min = (activity.get("elapsedDuration", 0) or 0) / 60
    elevation = activity.get("elevationGain", 0) or 0
    calories = activity.get("calories", 0) or 0
    avg_hr = activity.get("averageHR")
    max_hr = activity.get("maxHR")
    avg_power = activity.get("avgPower")
    max_power = activity.get("maxPower")
    np_power = activity.get("normPower")

    print(f"Nombre: {name}")
    print(f"Tipo: {activity_type}")
    print(f"Distancia: {distance_km:.2f} km")
    print(f"Tiempo moviéndose: {moving_min:.1f} min")
    print(f"Tiempo total: {elapsed_min:.1f} min")
    print(f"Elevación: {elevation:.0f} m")
    print(f"Calorías: {calories:.0f}")
    print(f"HR promedio: {avg_hr}")
    print(f"HR máxima: {max_hr}")
    print(f"Potencia promedio: {avg_power}")
    print(f"Potencia máxima: {max_power}")
    print(f"Potencia normalizada: {np_power}")


def print_performance_scores(scores):
    if not scores:
        return

    print("\n==========================")
    print("PERFORMANCE SCORES")
    print("==========================")

    ordered_keys = [
        "repeatability_score",
        "metabolic_cost_score",
        "efficiency_score",
        "pacing_score",
        "muscular_load_score",
        "overall_score",
    ]

    labels = {
        "repeatability_score": "Repeatability Score",
        "metabolic_cost_score": "Metabolic Cost Score",
        "efficiency_score": "Efficiency Score",
        "pacing_score": "Pacing Control Score",
        "muscular_load_score": "Muscular Load Score",
        "overall_score": "Overall Performance Score",
    }

    for key in ordered_keys:
        block = scores.get(key, {})
        score = block.get("score")
        reason = block.get("reason")
        print(f"\n{labels[key]}: {score}/100")
        print(f"Por qué: {reason}")


def print_brief(brief):
    meta = brief.get("meta", {})
    p1 = brief.get("phase_1_quick_insight", {})
    p2 = brief.get("phase_2_deep_analysis", {})
    tg = brief.get("training_guidance", {})
    cx = brief.get("contextual_layer", {})

    print("\n==========================")
    print("ACTIVITY BRIEF IA")
    print("==========================\n")

    print(f"Actividad: {meta.get('activity_name', '')}")
    print(f"ID: {meta.get('activity_id', '')}")
    print(f"Deporte: {meta.get('sport', '')}\n")

    print("----------- FASE 1: QUICK INSIGHT -----------\n")
    print(f"Headline: {p1.get('headline', '')}\n")

    overall = p1.get("overall_score", {})
    print(f"Overall Score: {overall.get('score', '')}/100")
    print(f"Label: {overall.get('label', '')}")
    print(f"Por qué: {overall.get('explanation', '')}\n")

    print("Scores:")
    for item in p1.get("scores", []):
        print(f"- {item.get('name', '')}: {item.get('score', '')}/100")
        print(f"  {item.get('explanation', '')}")

    print(f"\nVeredicto: {p1.get('verdict', '')}\n")
    print(f"Qué pasó: {p1.get('what_happened', '')}\n")
    print(f"Insight clave: {p1.get('key_insight', '')}\n")
    print(f"Identidad del atleta: {p1.get('athlete_identity', '')}\n")
    print(f"Impacto en rendimiento: {p1.get('performance_impact', '')}\n")
    print(f"Próxima decisión: {p1.get('next_decision', '')}\n")

    print("----------- FASE 2: DEEP ANALYSIS -----------\n")
    print(f"Interpretación de sesión: {p2.get('session_interpretation', '')}\n")

    pa = p2.get("physiological_analysis", {})
    print("Physiological Analysis:")
    print(f"- Tipo de fatiga: {pa.get('fatigue_type', '')}")
    print(f"- Limitante principal: {pa.get('main_limitation', '')}")
    print(f"- Limitante secundaria: {pa.get('secondary_limitation', '')}")
    print(f"- Comportamiento del costo: {pa.get('cost_behavior', '')}")
    print(f"- Comportamiento de eficiencia: {pa.get('efficiency_behavior', '')}\n")

    ppa = p2.get("power_profile_analysis", {})
    print("Power Profile Analysis:")
    print(f"- Short efforts: {ppa.get('short_efforts', '')}")
    print(f"- Threshold behavior: {ppa.get('threshold_behavior', '')}")
    print(f"- Fatigue response: {ppa.get('fatigue_response', '')}\n")

    ca = p2.get("climb_analysis", {})
    best = ca.get("best_climb", {})
    print("Climb Analysis:")
    print(f"- Mejor subida: {best.get('duration_min', '')} min | {best.get('avg_power', '')} W")
    print(f"- Insight: {best.get('insight', '')}")
    print(f"- Repeatability drop: {ca.get('repeatability_drop_pct', '')}")
    print(f"- Cadence behavior: {ca.get('cadence_behavior', '')}")
    print(f"- Interpretación: {ca.get('interpretation', '')}\n")

    ea = p2.get("efficiency_analysis", {})
    print("Efficiency Analysis:")
    print(f"- Efficiency drop: {ea.get('efficiency_drop_pct', '')}")
    print(f"- HR-power relation: {ea.get('hr_power_relation', '')}")
    print(f"- Interpretación: {ea.get('interpretation', '')}\n")

    ma = p2.get("metabolic_analysis", {})
    print("Metabolic Analysis:")
    print(f"- Avg MSI: {ma.get('avg_msi', '')}")
    print(f"- High MSI %: {ma.get('high_msi_pct', '')}")
    print(f"- Interpretación: {ma.get('interpretation', '')}\n")

    pac = p2.get("pacing_analysis", {})
    print("Pacing Analysis:")
    print(f"- VI: {pac.get('vi', '')}")
    print(f"- Ride type: {pac.get('ride_type', '')}")
    print(f"- Impacto: {pac.get('impact', '')}\n")

    mech = p2.get("mechanical_analysis", {})
    print("Mechanical Analysis:")
    print(f"- Cadencia: {mech.get('cadence', '')}")
    print(f"- Torque effect: {mech.get('torque_effect', '')}")
    print(f"- Muscle load: {mech.get('muscle_load', '')}\n")

    print("Findings Summary:")
    for item in p2.get("findings_summary", []):
        print(f"- {item}")

    print(f"\nMedical Interpretation: {p2.get('medical_interpretation', '')}\n")

    print("----------- TRAINING GUIDANCE -----------\n")
    print(f"Primary focus: {tg.get('primary_focus', '')}\n")

    sr = tg.get("session_recommendation", {})
    print("Session Recommendation:")
    print(f"- Tipo: {sr.get('type', '')}")
    print(f"- Descripción: {sr.get('description', '')}")
    print(f"- Recuperación: {sr.get('recovery', '')}")
    print(f"- Cadencia objetivo: {sr.get('cadence_target', '')}")
    print(f"- Goal: {sr.get('goal', '')}\n")

    print("Technical Adjustments:")
    for item in tg.get("technical_adjustments", []):
        print(f"- {item}")

    print(f"\nRecovery advice: {tg.get('recovery_advice', '')}\n")

    print("----------- CONTEXTUAL LAYER -----------\n")
    print(f"Athlete type: {cx.get('athlete_type', '')}")
    print(f"Pattern detected: {cx.get('pattern_detected', '')}")

    print("Long-term focus:")
    for item in cx.get("long_term_focus", []):
        print(f"- {item}")


def print_limiter(limiter):
    print("\n==========================")
    print("LIMITER DETECTOR")
    print("==========================")
    print(f"Limitante principal: {limiter.get('primary_limiter')}")
    print(f"Limitante secundaria: {limiter.get('secondary_limiter')}")
    print(f"Confianza: {limiter.get('confidence')}")
    print(f"Regla activada: {limiter.get('rule_triggered')}")
    print(f"Explicación: {limiter.get('explanation')}")
    print(f"Foco de entrenamiento: {limiter.get('training_focus')}")

    print("\nEVIDENCIA:")
    for k, v in limiter.get("evidence", {}).items():
        print(f"- {k}: {v}")

    why_not = limiter.get("why_not_others", [])
    if why_not:
        print("\nPOR QUÉ NO OTRAS:")
        for item in why_not:
            print(f"- {item}")


def print_trends(trends):
    print("\n==========================")
    print("TREND ANALYZER")
    print("==========================")

    if trends.get("error"):
        print(trends["error"])
        return

    print(f"Sesiones recientes: {trends.get('recent_count')}")
    print(f"Sesiones previas: {trends.get('previous_count')}")

    for t in trends.get("trends", []):
        print(
            f"- {t.get('label')}: "
            f"previo={t.get('previous_avg')} | "
            f"reciente={t.get('recent_avg')} | "
            f"tendencia={t.get('direction')} | "
            f"cambio={t.get('pct_change')}%"
        )


def print_chart_files(chart_files):
    if not chart_files:
        return

    print("\n==========================")
    print("CHARTS GENERADAS")
    print("==========================")
    for path in chart_files:
        print(f"- {path}")


def ask_open_chat():
    while True:
        choice = input("\n¿Quieres abrir Activity AI Chat para esta actividad? (s/n): ").strip().lower()

        if choice in ("s", "n"):
            return choice == "s"

        print("Responde con 's' o 'n'.")


def activity_module(client):
    user_id = get_current_user_id()

    print("\n===================================")
    print("MÓDULO DE ACTIVIDAD")
    print("===================================")
    print(f"Usuario actual: {user_id}")

    activities = get_recent_activities(client, days_back=7)

    save_path = save_activities_json(activities, user_id=user_id)
    print(f"\nActividades guardadas en: {save_path}")

    print_activity_list(activities)

    selected = select_activity(activities)

    if not selected:
        print("\nSelección cancelada.\n")
        return

    show_activity_summary(selected)

    flow_result = run_activity_full_flow(client, selected, user_id=user_id)

    pipeline_result = flow_result["pipeline_result"]
    brief = flow_result["brief"]
    limiter = flow_result.get("limiter", {})
    trends = flow_result.get("trends", {})
    chart_files = flow_result.get("chart_files", [])
    performance_scores = pipeline_result["analysis_result"].get("performance_scores", {})

    print("\n==============================")
    print("ANÁLISIS PREMIUM GENERADO")
    print("==============================")
    print(f"Archivo de details: {pipeline_result['details_file']}")
    print(f"Archivo de serie limpia: {pipeline_result['series_file']}")
    print(f"Archivo de análisis final: {pipeline_result['analysis_file']}")
    print(f"Archivo de findings: {flow_result['findings_file']}")
    print(f"Archivo de brief IA: {flow_result['brief_file']}")
    print(f"Archivo de historial: {flow_result['history_file']}")
    print(f"Archivo de index: {flow_result.get('activity_index_file')}")
    print(f"Hora de análisis: {pipeline_result['analysis_time']}")
    print(f"Usuario actual: {flow_result.get('user_id', user_id)}")

    print_chart_files(chart_files)
    print_performance_scores(performance_scores)
    print_brief(brief)
    print_limiter(limiter)
    print_trends(trends)

    if ask_open_chat():
        run_activity_ai_chat(
            analysis_path=pipeline_result["analysis_file"],
            findings_path=flow_result.get("findings_file"),
            brief_path=flow_result.get("brief_file"),
            limiter=limiter,
            trends=trends,
        )