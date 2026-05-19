"""
activity_history_engine.py
==========================
Motor de historial de actividades.

Lee todos los activity_analysis.json del usuario y construye:
  - activity_history.json           → lista de sesiones válidas (compatible con history_engine.py)
  - activity_baselines.json         → media, mediana, p25, min, max por métrica
  - activity_trends.json            → tendencias reciente vs baseline vs older
  - activity_anomalies.json         → días anómalos vs baseline personal
  - activity_patterns.json          → patrones recurrentes de riesgo
  - activity_longitudinal_brief.json → resumen longitudinal
"""

import json
import os
from glob import glob
from statistics import mean, median

from app_context import get_current_user_id, get_activities_dir, get_history_dir


# =========================
# Utils
# =========================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_mean(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(mean(vals), 4) if vals else None


def safe_median(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(median(vals), 4) if vals else None


def safe_p25(vals):
    sorted_vals = sorted(v for v in vals if isinstance(v, (int, float)))
    n = len(sorted_vals)
    if n == 0:
        return None
    return round(sorted_vals[max(0, int(n * 0.25) - 1)], 4)


def pct_diff(value, baseline):
    if baseline in (0, None) or value is None:
        return None
    return round(((value - baseline) / abs(baseline)) * 100.0, 2)


def trend_label(recent_avg, older_avg, positive_is_good=True, tolerance_pct=5.0):
    if recent_avg is None or older_avg is None or older_avg == 0:
        return "stable"
    diff_pct = ((recent_avg - older_avg) / abs(older_avg)) * 100
    if abs(diff_pct) <= tolerance_pct:
        return "stable"
    if positive_is_good:
        return "improving" if diff_pct > 0 else "worsening"
    return "improving" if diff_pct < 0 else "worsening"


# =========================
# Carga de datos
# =========================

def load_activity_analyses(base_activities_dir):
    """Carga todos los activity_analysis.json del directorio de actividades."""
    pattern = os.path.join(base_activities_dir, "*", "activity_analysis.json")
    files = sorted(glob(pattern))
    analyses = []
    for path in files:
        try:
            data = load_json(path)
            analyses.append(data)
        except Exception:
            pass
    return analyses


def _is_activity_valid(analysis):
    """Filtra actividades sin datos reales (error en serie o < 10 min de movimiento)."""
    if "error" in analysis:
        return False
    moving_minutes = analysis.get("garmin_summary", {}).get("moving_minutes", 0) or 0
    return moving_minutes >= 10


# =========================
# Historial
# =========================

def build_activity_history(analyses):
    """
    Construye lista flat de sesiones válidas.
    Se guarda en el mismo formato {"activities": [...]} que history_engine.py
    para mantener compatibilidad con trend_analyzer.py.
    """
    history = []
    skipped = 0

    for analysis in analyses:
        if not _is_activity_valid(analysis):
            skipped += 1
            continue

        garmin = analysis.get("garmin_summary", {})
        derived = analysis.get("derived_summary", {})
        fatigue = analysis.get("fatigue", {})
        profile = analysis.get("athlete_profile", {})
        metabolic = analysis.get("metabolic_index", {})
        climbs = analysis.get("climbs", [])
        efforts = analysis.get("efforts", [])

        top_climb = sorted(climbs, key=lambda x: x.get("climb_score", 0), reverse=True)[0] if climbs else {}

        history.append({
            "activity_id":              garmin.get("activity_id"),
            "date":                     garmin.get("start_date", ""),
            "name":                     garmin.get("name", ""),
            "type":                     garmin.get("type", ""),

            # Resumen Garmin
            "distance_km":              garmin.get("distance_km"),
            "moving_minutes":           garmin.get("moving_minutes"),
            "elapsed_minutes":          garmin.get("elapsed_minutes"),
            "elevation_m":              garmin.get("elevation_m"),
            "avg_hr":                   garmin.get("avg_hr"),
            "max_hr":                   garmin.get("max_hr"),
            "avg_power":                garmin.get("avg_power"),
            "max_power":                garmin.get("max_power"),
            "garmin_np":                garmin.get("garmin_np"),
            "garmin_tss":               garmin.get("garmin_tss"),
            "garmin_if":                garmin.get("garmin_if"),
            "aerobic_te":               garmin.get("aerobic_te"),
            "anaerobic_te":             garmin.get("anaerobic_te"),

            # Métricas derivadas
            "estimated_np":             derived.get("estimated_np"),
            "vi":                       derived.get("vi"),
            "estimated_if":             derived.get("estimated_if"),
            "energy_kj":                derived.get("energy_kj"),
            "aerobic_efficiency":       derived.get("aerobic_efficiency"),
            "ride_classification":      derived.get("ride_classification"),

            # Fatiga
            "power_drop_pct":           fatigue.get("power_drop_pct"),
            "efficiency_drop_pct":      fatigue.get("efficiency_drop_pct"),
            "climb_repeatability_pct":  fatigue.get("climb_repeatability_pct"),
            "fatigue_onset_min":        fatigue.get("fatigue_onset_min"),

            # Metabólico
            "avg_msi":                  metabolic.get("avg_msi"),
            "high_msi_pct":             metabolic.get("high_msi_pct"),

            # Subida top
            "top_climb_power":          top_climb.get("avg_power"),
            "top_climb_duration_min":   top_climb.get("duration_min"),
            "top_climb_score":          top_climb.get("climb_score"),
            "top_climb_grade_pct":      top_climb.get("avg_grade_pct"),
            "climb_count":              len(climbs),

            # Esfuerzos
            "vo2_count":                sum(1 for e in efforts if e.get("type") == "VO2"),
            "sprint_count":             sum(1 for e in efforts if e.get("type") == "SPRINT"),
            "threshold_count":          sum(1 for e in efforts if e.get("type") == "THRESHOLD"),

            # Perfil atleta
            "primary_type":             profile.get("primary_type"),
            "secondary_type":           profile.get("secondary_type"),
        })

    if skipped > 0:
        print(f"  [activity_history] {skipped} actividades inválidas excluidas del historial")

    history.sort(key=lambda x: x.get("date") or "")
    return history


# =========================
# Baselines
# =========================

def build_activity_baselines(history):
    if not history:
        return {}

    metrics = [
        "distance_km", "moving_minutes", "elevation_m",
        "avg_hr", "avg_power", "garmin_np", "garmin_tss",
        "estimated_np", "vi", "estimated_if", "energy_kj", "aerobic_efficiency",
        "power_drop_pct", "efficiency_drop_pct", "climb_repeatability_pct", "fatigue_onset_min",
        "avg_msi", "high_msi_pct",
        "top_climb_power", "top_climb_score", "top_climb_grade_pct",
        "climb_count", "vo2_count", "sprint_count", "threshold_count",
    ]

    baseline = {
        "window_count": len(history),
        "metrics": {}
    }

    for metric in metrics:
        vals = [x.get(metric) for x in history if isinstance(x.get(metric), (int, float))]
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        p25 = round(sorted_vals[max(0, int(n * 0.25) - 1)], 4) if n > 0 else None
        baseline["metrics"][metric] = {
            "mean":   safe_mean(vals),
            "median": safe_median(vals),
            "p25":    p25,
            "min":    round(min(vals), 4) if vals else None,
            "max":    round(max(vals), 4) if vals else None,
            "n":      len(vals),
        }

    return baseline


# =========================
# Tendencias
# =========================

def build_activity_trends(history):
    if not history:
        return {}

    recent  = history[-4:]          if len(history) >= 4  else history
    baseline = history[-8:]         if len(history) >= 8  else history
    older   = history[-16:-8]       if len(history) >= 16 else (
              history[:-len(recent)] if len(history) > len(recent) else history)

    metrics = {
        "estimated_np":            {"positive_is_good": True},
        "avg_power":               {"positive_is_good": True},
        "top_climb_power":         {"positive_is_good": True},
        "aerobic_efficiency":      {"positive_is_good": True},
        "garmin_tss":              {"positive_is_good": True},
        "energy_kj":               {"positive_is_good": True},
        "power_drop_pct":          {"positive_is_good": False},
        "efficiency_drop_pct":     {"positive_is_good": False},
        "climb_repeatability_pct": {"positive_is_good": False},
        "avg_msi":                 {"positive_is_good": False},
        "high_msi_pct":            {"positive_is_good": False},
        "vi":                      {"positive_is_good": False},
    }

    trends = {}
    for metric, cfg in metrics.items():
        recent_avg  = safe_mean([x.get(metric) for x in recent])
        baseline_avg = safe_mean([x.get(metric) for x in baseline])
        older_avg   = safe_mean([x.get(metric) for x in older])

        trends[metric] = {
            "recent_avg":        recent_avg,
            "baseline_avg":      baseline_avg,
            "older_avg":         older_avg,
            "trend_vs_baseline": trend_label(recent_avg, baseline_avg, positive_is_good=cfg["positive_is_good"]),
            "trend_vs_older":    trend_label(recent_avg, older_avg,    positive_is_good=cfg["positive_is_good"]),
        }

    return trends


# =========================
# Anomalías
# =========================

def build_activity_anomalies(history, baselines):
    if not history or not baselines:
        return {"anomalies": []}

    baseline_metrics = baselines.get("metrics", {})
    anomalies = []

    checks = [
        ("estimated_np",          "low_np_anomaly",          -15, True),
        ("top_climb_power",       "low_climb_power_anomaly", -15, True),
        ("aerobic_efficiency",    "low_efficiency_anomaly",  -15, True),
        ("power_drop_pct",        "high_power_drop_anomaly",  30, False),
        ("efficiency_drop_pct",   "high_eff_drop_anomaly",    30, False),
        ("avg_msi",               "high_msi_anomaly",         25, False),
        ("high_msi_pct",          "high_msi_pct_anomaly",     40, False),
    ]

    for row in history:
        row_anomalies = []
        for metric, code, threshold, lower_is_bad in checks:
            value    = row.get(metric)
            baseline = baseline_metrics.get(metric, {}).get("median")
            if not isinstance(value, (int, float)) or not isinstance(baseline, (int, float)):
                continue
            diff = pct_diff(value, baseline)
            if diff is None:
                continue
            if lower_is_bad and diff <= threshold:
                row_anomalies.append({"code": code, "metric": metric,
                                      "value": round(value, 4), "baseline_median": round(baseline, 4), "pct_diff": diff})
            elif not lower_is_bad and diff >= threshold:
                row_anomalies.append({"code": code, "metric": metric,
                                      "value": round(value, 4), "baseline_median": round(baseline, 4), "pct_diff": diff})

        anomalies.append({
            "activity_id": row.get("activity_id"),
            "date":        row.get("date"),
            "anomalies":   row_anomalies,
        })

    return {"anomalies": anomalies}


# =========================
# Patrones recurrentes
# =========================

def build_activity_patterns(history):
    if not history:
        return {"recurrent_patterns": [], "risk_counts": {}}

    n = len(history)
    trigger = max(2, n // 3)

    high_power_drop   = sum(1 for h in history if isinstance(h.get("power_drop_pct"), (int, float))
                            and h["power_drop_pct"] <= -6)
    high_eff_drop     = sum(1 for h in history if isinstance(h.get("efficiency_drop_pct"), (int, float))
                            and h["efficiency_drop_pct"] <= -6)
    low_repeatability = sum(1 for h in history if isinstance(h.get("climb_repeatability_pct"), (int, float))
                            and h["climb_repeatability_pct"] <= -6)
    high_msi          = sum(1 for h in history if isinstance(h.get("high_msi_pct"), (int, float))
                            and h["high_msi_pct"] >= 30)
    early_fatigue     = sum(1 for h in history
                            if isinstance(h.get("fatigue_onset_min"), (int, float))
                            and h["fatigue_onset_min"] is not None
                            and h["fatigue_onset_min"] < 30)

    recurrent_patterns = []

    if high_power_drop >= trigger:
        recurrent_patterns.append({
            "code": "chronic_power_durability_issue",
            "count": high_power_drop,
            "severity": "high" if high_power_drop >= trigger * 1.5 else "moderate",
            "description": "La potencia cae de forma importante entre la primera y segunda mitad en múltiples sesiones.",
        })

    if high_eff_drop >= trigger:
        recurrent_patterns.append({
            "code": "chronic_efficiency_drop",
            "count": high_eff_drop,
            "severity": "moderate",
            "description": "La eficiencia potencia/FC se deteriora repetidamente a lo largo de las sesiones.",
        })

    if low_repeatability >= trigger:
        recurrent_patterns.append({
            "code": "chronic_low_climb_repeatability",
            "count": low_repeatability,
            "severity": "high" if low_repeatability >= trigger * 1.5 else "moderate",
            "description": "La capacidad de repetir subidas intensas es repetidamente baja.",
        })

    if high_msi >= trigger:
        recurrent_patterns.append({
            "code": "chronic_high_metabolic_cost",
            "count": high_msi,
            "severity": "moderate",
            "description": "El costo metabólico es elevado en una parte importante del esfuerzo en múltiples sesiones.",
        })

    if early_fatigue >= trigger:
        recurrent_patterns.append({
            "code": "recurrent_early_fatigue_onset",
            "count": early_fatigue,
            "severity": "moderate",
            "description": "La fatiga aparece temprano (< 30 min) en múltiples sesiones.",
        })

    return {
        "recurrent_patterns": recurrent_patterns,
        "risk_counts": {
            "high_power_drop":   high_power_drop,
            "high_eff_drop":     high_eff_drop,
            "low_repeatability": low_repeatability,
            "high_msi":          high_msi,
            "early_fatigue":     early_fatigue,
        },
    }


# =========================
# Brief longitudinal
# =========================

def build_activity_longitudinal_brief(history, trends, patterns, baselines=None):
    if not history:
        return {
            "window_count": 0,
            "performance_trajectory": "no_data",
            "main_strengths": [],
            "main_risks": [],
            "longitudinal_limiter": "",
            "summary": "No hay actividades en el historial.",
        }

    strengths = []
    risks = []

    np_trend         = trends.get("estimated_np", {}).get("trend_vs_baseline")
    climb_trend      = trends.get("top_climb_power", {}).get("trend_vs_baseline")
    eff_trend        = trends.get("aerobic_efficiency", {}).get("trend_vs_baseline")
    msi_trend        = trends.get("avg_msi", {}).get("trend_vs_baseline")
    power_drop_trend = trends.get("power_drop_pct", {}).get("trend_vs_baseline")
    rep_trend        = trends.get("climb_repeatability_pct", {}).get("trend_vs_baseline")

    if np_trend == "improving":
        strengths.append("La potencia normalizada está mejorando en las últimas sesiones.")
    if climb_trend == "improving":
        strengths.append("La potencia en subidas muestra tendencia positiva.")
    if eff_trend in ("improving", "stable"):
        strengths.append("La eficiencia aeróbica se mantiene o mejora.")
    if msi_trend == "improving":
        strengths.append("El costo metabólico está disminuyendo.")
    if rep_trend == "improving":
        strengths.append("La repeatability en subidas está mejorando.")

    for p in patterns["recurrent_patterns"]:
        risks.append(p["description"])

    if power_drop_trend == "worsening":
        risks.append("La caída de potencia entre mitades está empeorando.")

    # Limitador longitudinal dominante
    risk_counts = patterns.get("risk_counts", {})
    longitudinal_limiter = ""
    if risk_counts:
        max_key = max(risk_counts, key=lambda k: risk_counts[k])
        if risk_counts[max_key] > 0:
            longitudinal_limiter = max_key

    # Trayectoria
    if np_trend == "improving" and climb_trend in ("improving", "stable"):
        trajectory = "improving"
    elif np_trend == "worsening" or power_drop_trend == "worsening":
        trajectory = "worsening"
    else:
        trajectory = "stable"

    if not strengths:
        strengths.append("Sin tendencias positivas claras aún.")
    if not risks:
        risks.append("Sin patrones de riesgo recurrentes detectados.")

    summary = (
        f"Analizando {len(history)} sesiones, la trayectoria de rendimiento aparece {trajectory}. "
        f"El limitador longitudinal más frecuente es: {longitudinal_limiter or 'no definido claramente'}."
    )

    return {
        "window_count":           len(history),
        "performance_trajectory": trajectory,
        "main_strengths":         strengths,
        "main_risks":             risks,
        "longitudinal_limiter":   longitudinal_limiter,
        "summary":                summary,
    }


# =========================
# Orquestador principal
# =========================

def run_activity_history_engine(user_id=None):
    user_id = user_id or get_current_user_id()

    base_activities_dir = get_activities_dir(user_id)
    out_dir = get_history_dir(user_id)

    analyses  = load_activity_analyses(base_activities_dir)
    history   = build_activity_history(analyses)
    baselines = build_activity_baselines(history)
    trends    = build_activity_trends(history)
    anomalies = build_activity_anomalies(history, baselines)
    patterns  = build_activity_patterns(history)
    brief     = build_activity_longitudinal_brief(history, trends, patterns, baselines=baselines)

    # Compatible con history_engine.py: {"activities": [...]}
    save_json(os.path.join(out_dir, "activity_history.json"),           {"activities": history})
    save_json(os.path.join(out_dir, "activity_baselines.json"),         baselines)
    save_json(os.path.join(out_dir, "activity_trends.json"),            trends)
    save_json(os.path.join(out_dir, "activity_anomalies.json"),         anomalies)
    save_json(os.path.join(out_dir, "activity_patterns.json"),          patterns)
    save_json(os.path.join(out_dir, "activity_longitudinal_brief.json"), brief)

    print("\n===================================")
    print("ACTIVITY HISTORY ENGINE")
    print("===================================")
    print(f"Sesiones analizadas: {brief['window_count']}")
    print(f"Trayectoria:         {brief['performance_trajectory']}")
    print(f"Limitador:           {brief['longitudinal_limiter']}")
    print(f"Resumen: {brief['summary']}")
    print("===================================\n")

    return {
        "history":   history,
        "baselines": baselines,
        "trends":    trends,
        "anomalies": anomalies,
        "patterns":  patterns,
        "brief":     brief,
    }
