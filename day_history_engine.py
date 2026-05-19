"""
day_history_engine.py — Motor de historial del día
===================================================
Mejoras vs versión anterior:
  1. Filtro de calidad — días sin datos reales no entran al historial
  2. Agrega training_load (ATL/CTL/TSB) al historial
  3. Baselines calculados solo con días válidos
  4. cognitive_load eliminado de métricas (redundante con nervous_system)
  5. Anomalías ahora comparan contra basal personal, no umbral fijo
"""

import json
import os
from glob import glob
from statistics import mean, median


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_mean(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(mean(vals), 4) if vals else 0.0


def safe_median(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(median(vals), 4) if vals else 0.0


def pct_diff(value, baseline):
    if baseline in (0, None):
        return 0.0
    return round(((value - baseline) / baseline) * 100.0, 2)


def trend_label(recent_avg, older_avg, positive_is_good=True, tolerance=3.0):
    diff = recent_avg - older_avg
    if abs(diff) <= tolerance:
        return "stable"
    if positive_is_good:
        return "improving" if diff > 0 else "worsening"
    return "improving" if diff < 0 else "worsening"


# =========================
# Load day files
# =========================

def load_day_days(base_day_dir):
    analysis_files = sorted(glob(os.path.join(base_day_dir, "*", "day_analysis.json")))
    findings_files = sorted(glob(os.path.join(base_day_dir, "*", "day_findings.json")))
    brief_files    = sorted(glob(os.path.join(base_day_dir, "*", "day_brief.json")))

    days = {}

    for path in analysis_files:
        date_str = os.path.basename(os.path.dirname(path))
        days.setdefault(date_str, {})
        days[date_str]["analysis"] = load_json(path)

    for path in findings_files:
        date_str = os.path.basename(os.path.dirname(path))
        days.setdefault(date_str, {})
        days[date_str]["findings"] = load_json(path)

    for path in brief_files:
        date_str = os.path.basename(os.path.dirname(path))
        days.setdefault(date_str, {})
        days[date_str]["brief"] = load_json(path)

    ordered = []
    for date_str in sorted(days.keys()):
        row = {"calendar_date": date_str}
        row.update(days[date_str])
        ordered.append(row)

    return ordered


def _is_day_valid(analysis):
    """
    Verifica si el día tiene datos reales suficientes para entrar al historial.
    Usa el campo data_validity si existe (motor nuevo),
    o hace la validación manual si es un análisis del motor viejo.
    """
    # Motor nuevo — tiene data_validity
    validity = analysis.get("data_validity")
    if isinstance(validity, dict):
        return validity.get("is_valid", True)

    # Motor viejo — validación manual por puntos de serie
    timeline = analysis.get("timeline_summary", {})
    hr_points = timeline.get("hr_points", 0)
    stress_points = timeline.get("stress_points", 0)
    bb_points = timeline.get("body_battery_points", 0)

    # Si todo es 0, es un día sin reloj puesto
    if hr_points == 0 and stress_points == 0 and bb_points == 0:
        return False

    # Si el overall score es exactamente 100 con 0 puntos — día falso
    overall = analysis.get("recovery_summary", {}).get("overall_day_state_score", 0)
    if overall >= 99.9 and hr_points == 0:
        return False

    return True


# =========================
# History
# =========================

def build_day_history(days):
    history = []
    skipped = 0

    for d in days:
        analysis = d.get("analysis", {})
        findings = d.get("findings", {})
        brief    = d.get("brief", {})

        if not analysis:
            continue

        # MEJORA 1: Filtro de calidad
        if not _is_day_valid(analysis):
            skipped += 1
            continue

        training_load = analysis.get("training_load", {})

        history.append({
            "calendar_date": d["calendar_date"],

            "overall_day_state_score": analysis["recovery_summary"]["overall_day_state_score"],
            "system_strain_score":     analysis["recovery_summary"]["system_strain_score"],
            "day_capacity_score":      analysis["recovery_summary"]["day_capacity_score"],

            "nervous_system_load_score": analysis["nervous_system_load"]["nervous_system_load_score"],
            "avg_day_hr":                analysis["nervous_system_load"]["avg_hr"],
            "hr_variability":            analysis["nervous_system_load"]["hr_variability"],
            "avg_hrv":                   analysis["nervous_system_load"]["avg_hrv"],

            "energy_dynamics_score": analysis["energy_dynamics"]["energy_dynamics_score"],
            "body_battery_change":   analysis["energy_dynamics"]["body_battery_change"],
            "body_battery_slope":    analysis["energy_dynamics"]["body_battery_slope"],
            "recharge_events":       analysis["energy_dynamics"]["recharge_events"],
            "crash_events":          analysis["energy_dynamics"]["crash_events"],

            "physical_load_score":  analysis["physical_load"]["physical_load_score"],
            "steps":                analysis["physical_load"]["steps"],
            "intensity_minutes":    analysis["physical_load"]["intensity_minutes"],
            "active_calories":      analysis["physical_load"]["active_calories"],
            "max_hr":               analysis["physical_load"]["max_hr"],

            "stress_behavior_score": analysis["stress_behavior"]["stress_behavior_score"],
            "avg_stress":            analysis["stress_behavior"]["avg_stress"],
            "max_stress":            analysis["stress_behavior"]["max_stress"],
            "high_stress_count":     analysis["stress_behavior"]["high_stress_count"],
            "stress_spike_count":    analysis["stress_behavior"]["stress_spike_count"],
            "high_stress_ratio":     analysis["stress_behavior"]["high_stress_ratio"],

            "recovery_response_score": analysis["recovery_response"]["recovery_response_score"],
            "has_real_recovery_data":  analysis["recovery_response"].get("has_real_recovery_data", True),
            "downshift_count":         analysis["recovery_response"]["downshift_count"],
            "downshift_ratio":         analysis["recovery_response"]["downshift_ratio"],

            "respiratory_behavior_score": analysis["respiratory_behavior"]["respiratory_behavior_score"],
            "avg_respiration":            analysis["respiratory_behavior"]["avg_respiration"],
            "respiration_variability":    analysis["respiratory_behavior"]["respiration_variability"],

            # MEJORA 2: Training load
            "atl":       training_load.get("atl"),
            "ctl":       training_load.get("ctl"),
            "tsb":       training_load.get("tsb"),
            "tsb_label": training_load.get("tsb_label"),

            "primary_limiter":   findings.get("limiters", {}).get("primary_limiter", ""),
            "secondary_limiter": findings.get("limiters", {}).get("secondary_limiter", ""),
            "headline":          brief.get("headline", ""),
            "data_valid":        True,
        })

    if skipped > 0:
        print(f"  [day_history] {skipped} días sin datos reales excluidos del historial")

    return history


def build_day_baselines(history):
    if not history:
        return {}

    # MEJORA 3: cognitive_load eliminado, training_load agregado
    metrics = [
        "overall_day_state_score",
        "system_strain_score",
        "day_capacity_score",
        "nervous_system_load_score",
        "avg_day_hr",
        "hr_variability",
        "avg_hrv",
        "energy_dynamics_score",
        "body_battery_change",
        "body_battery_slope",
        "recharge_events",
        "crash_events",
        "physical_load_score",
        "steps",
        "intensity_minutes",
        "active_calories",
        "max_hr",
        "stress_behavior_score",
        "avg_stress",
        "max_stress",
        "high_stress_count",
        "stress_spike_count",
        "high_stress_ratio",
        "recovery_response_score",
        "downshift_count",
        "downshift_ratio",
        "respiratory_behavior_score",
        "avg_respiration",
        "respiration_variability",
        "atl",
        "ctl",
        "tsb",
    ]

    baseline = {
        "window_days": len(history),
        "metrics": {}
    }

    for metric in metrics:
        vals = [x.get(metric) for x in history if isinstance(x.get(metric), (int, float))]
        if vals:
            baseline["metrics"][metric] = {
                "mean":   safe_mean(vals),
                "median": safe_median(vals),
                "min":    round(min(vals), 4),
                "max":    round(max(vals), 4),
                "n":      len(vals),
            }

    return baseline


def build_day_trends(history):
    if not history:
        return {}

    recent   = history[-3:] if len(history) >= 3 else history
    baseline = history[-7:] if len(history) >= 7 else history
    older    = history[-14:-7] if len(history) >= 14 else history[:-len(recent)] if len(history) > len(recent) else history

    metrics = {
        "overall_day_state_score":    {"positive_is_good": True},
        "system_strain_score":        {"positive_is_good": False},
        "day_capacity_score":         {"positive_is_good": True},
        "nervous_system_load_score":  {"positive_is_good": False},
        "energy_dynamics_score":      {"positive_is_good": True},
        "body_battery_change":        {"positive_is_good": True},
        "crash_events":               {"positive_is_good": False},
        "physical_load_score":        {"positive_is_good": False},
        "stress_behavior_score":      {"positive_is_good": False},
        "avg_stress":                 {"positive_is_good": False},
        "high_stress_ratio":          {"positive_is_good": False},
        "recovery_response_score":    {"positive_is_good": True},
        "respiratory_behavior_score": {"positive_is_good": True},
        "tsb":                        {"positive_is_good": True},
        "ctl":                        {"positive_is_good": True},
    }

    trends = {}
    for metric, cfg in metrics.items():
        recent_avg   = safe_mean([x.get(metric) for x in recent])
        baseline_avg = safe_mean([x.get(metric) for x in baseline])
        older_avg    = safe_mean([x.get(metric) for x in older])
        trends[metric] = {
            "recent_avg":       recent_avg,
            "baseline_avg":     baseline_avg,
            "older_avg":        older_avg,
            "trend_vs_baseline": trend_label(recent_avg, baseline_avg, positive_is_good=cfg["positive_is_good"]),
            "trend_vs_older":    trend_label(recent_avg, older_avg, positive_is_good=cfg["positive_is_good"]),
        }

    return trends


def build_day_anomalies(history, baselines):
    if not history or not baselines:
        return {"anomalies": []}

    baseline_metrics = baselines.get("metrics", {})
    anomalies = []

    checks = [
        ("overall_day_state_score",    "low_day_state_anomaly",         -12, True),
        ("day_capacity_score",         "low_day_capacity_anomaly",       -12, True),
        ("energy_dynamics_score",      "low_energy_stability_anomaly",   -15, True),
        ("recovery_response_score",    "low_recovery_response_anomaly",  -18, True),
        ("respiratory_behavior_score", "low_respiratory_stability_anomaly", -18, True),
        ("system_strain_score",        "high_system_strain_anomaly",      15, False),
        ("nervous_system_load_score",  "high_nervous_load_anomaly",       15, False),
        ("physical_load_score",        "high_physical_load_anomaly",      15, False),
        ("stress_behavior_score",      "high_stress_behavior_anomaly",    15, False),
        ("avg_stress",                 "high_avg_stress_anomaly",         25, False),
        ("high_stress_ratio",          "high_stress_ratio_anomaly",       20, False),
        ("crash_events",               "high_energy_crash_anomaly",       20, False),
    ]

    for row in history:
        row_anomalies = []
        for metric, code, threshold, lower_is_bad_relative in checks:
            value    = row.get(metric)
            baseline = baseline_metrics.get(metric, {}).get("median")
            if not isinstance(value, (int, float)) or not isinstance(baseline, (int, float)):
                continue
            diff = pct_diff(value, baseline)
            if lower_is_bad_relative:
                if diff <= threshold:
                    row_anomalies.append({
                        "code": code,
                        "metric": metric,
                        "value": round(value, 4),
                        "baseline_median": round(baseline, 4),
                        "pct_diff_vs_baseline": diff,
                    })
            else:
                if diff >= threshold:
                    row_anomalies.append({
                        "code": code,
                        "metric": metric,
                        "value": round(value, 4),
                        "baseline_median": round(baseline, 4),
                        "pct_diff_vs_baseline": diff,
                    })
        anomalies.append({
            "calendar_date": row["calendar_date"],
            "anomalies": row_anomalies,
        })

    return {"anomalies": anomalies}


def classify_day_bottleneck(row, baselines=None):
    scores = {
        "stress_bottleneck":          0,
        "nervous_system_bottleneck":  0,
        "energy_bottleneck":          0,
        "physical_bottleneck":        0,
        "recovery_bottleneck":        0,
        "respiratory_bottleneck":     0,
    }

    # Umbrales personalizados si hay baselines
    stress_threshold   = baselines["metrics"].get("stress_behavior_score", {}).get("mean", 70) * 1.3 if baselines else 70
    nervous_threshold  = baselines["metrics"].get("nervous_system_load_score", {}).get("mean", 75) * 1.2 if baselines else 75
    recovery_threshold = baselines["metrics"].get("recovery_response_score", {}).get("mean", 50) * 0.6 if baselines else 35

    if row.get("stress_behavior_score", 0) >= stress_threshold:
        scores["stress_bottleneck"] += 2
    if row.get("nervous_system_load_score", 0) >= nervous_threshold:
        scores["nervous_system_bottleneck"] += 2
    if row.get("energy_dynamics_score", 100) <= 40 or row.get("body_battery_change", 0) <= -35:
        scores["energy_bottleneck"] += 2
    if row.get("physical_load_score", 0) >= 72:
        scores["physical_bottleneck"] += 2
    if row.get("has_real_recovery_data", True) and row.get("recovery_response_score", 100) <= recovery_threshold:
        scores["recovery_bottleneck"] += 2
    if row.get("respiratory_behavior_score", 100) <= 45:
        scores["respiratory_bottleneck"] += 2

    dominant = max(scores, key=scores.get)
    if scores[dominant] == 0:
        dominant = "none"

    return {"scores": scores, "dominant_bottleneck": dominant}


def build_day_bottlenecks(history, baselines=None):
    per_day   = []
    aggregate = {
        "stress_bottleneck": 0, "nervous_system_bottleneck": 0,
        "energy_bottleneck": 0, "physical_bottleneck": 0,
        "recovery_bottleneck": 0, "respiratory_bottleneck": 0,
    }

    for row in history:
        item = classify_day_bottleneck(row, baselines=baselines)
        per_day.append({
            "calendar_date":      row["calendar_date"],
            "dominant_bottleneck": item["dominant_bottleneck"],
            "scores":              item["scores"],
        })
        dom = item["dominant_bottleneck"]
        if dom in aggregate:
            aggregate[dom] += 1

    dominant_bottleneck = max(aggregate, key=aggregate.get) if aggregate else ""
    if aggregate.get(dominant_bottleneck, 0) == 0:
        dominant_bottleneck = ""

    return {
        "per_day": per_day,
        "aggregate": {"counts": aggregate, "dominant_bottleneck": dominant_bottleneck},
    }


def build_day_patterns(history, trends, bottlenecks=None, anomalies=None):
    recurrent_patterns = []
    limiter_counts     = {}

    high_stress_days  = 0
    energy_crash_days = 0
    low_recovery_days = 0
    high_nervous_days = 0
    high_physical_days = 0

    for h in history:
        limiter = h.get("primary_limiter", "")
        if limiter:
            limiter_counts[limiter] = limiter_counts.get(limiter, 0) + 1

        if h.get("stress_behavior_score", 0) >= 70 or h.get("high_stress_ratio", 0) >= 0.30:
            high_stress_days += 1
        if h.get("energy_dynamics_score", 100) <= 40 or h.get("body_battery_change", 0) <= -35:
            energy_crash_days += 1
        if h.get("has_real_recovery_data", True) and h.get("recovery_response_score", 100) <= 35:
            low_recovery_days += 1
        if h.get("nervous_system_load_score", 0) >= 75:
            high_nervous_days += 1
        if h.get("physical_load_score", 0) >= 72:
            high_physical_days += 1

    n       = len(history)
    trigger = max(2, n // 3)

    if high_stress_days >= trigger:
        recurrent_patterns.append({
            "code": "chronic_high_day_stress", "count": high_stress_days,
            "severity": "high" if high_stress_days >= 4 else "moderate",
            "description": "Multiple days showed sustained high daytime stress."
        })
    if energy_crash_days >= trigger:
        recurrent_patterns.append({
            "code": "recurrent_energy_crash_pattern", "count": energy_crash_days,
            "severity": "moderate",
            "description": "Energy reserves repeatedly dropped too fast across the day."
        })
    if low_recovery_days >= trigger:
        recurrent_patterns.append({
            "code": "recurrent_low_intraday_recovery", "count": low_recovery_days,
            "severity": "moderate",
            "description": "The body repeatedly struggled to downshift during the day."
        })
    if high_nervous_days >= trigger:
        recurrent_patterns.append({
            "code": "chronic_nervous_system_strain", "count": high_nervous_days,
            "severity": "moderate",
            "description": "Nervous system load was repeatedly high."
        })
    if high_physical_days >= trigger:
        recurrent_patterns.append({
            "code": "chronic_high_physical_load", "count": high_physical_days,
            "severity": "moderate",
            "description": "Physical demand was repeatedly high across several days."
        })

    return {
        "recurrent_patterns": recurrent_patterns,
        "limiter_counts":     limiter_counts,
        "dominant_bottleneck": bottlenecks.get("aggregate", {}).get("dominant_bottleneck", "") if bottlenecks else "",
    }


def build_day_longitudinal_brief(history, trends, patterns, baselines=None, anomalies=None, bottlenecks=None):
    if not history:
        return {
            "headline": "No day history available.",
            "summary": "Not enough processed days to detect patterns.",
            "dominant_pattern": "", "main_risk": "", "coaching_focus": "", "trajectory": "unknown"
        }

    recurrent_patterns   = patterns.get("recurrent_patterns", [])
    dominant_bottleneck  = patterns.get("dominant_bottleneck", "")
    trajectory           = trends.get("overall_day_state_score", {}).get("trend_vs_baseline", "stable")

    dominant_pattern = (
        recurrent_patterns[0]["description"] if recurrent_patterns
        else f"The dominant bottleneck across days is {dominant_bottleneck.replace('_', ' ')}." if dominant_bottleneck
        else "No single dominant daytime pattern stands out yet."
    )

    risk_map = {
        "stress_bottleneck":         ("Stress is repeatedly shaping the body state of the day.", "Reduce sustained stress exposure and create intentional downshift blocks."),
        "energy_bottleneck":         ("Energy reserves are being depleted too aggressively across days.", "Improve pacing, reduce unnecessary output, and protect recovery windows."),
        "recovery_bottleneck":       ("The body is repeatedly failing to recover during the day.", "Insert real pauses and avoid staying loaded continuously."),
        "nervous_system_bottleneck": ("The nervous system is carrying repeated strain.", "Lower total system load and improve nervous system downregulation."),
        "physical_bottleneck":       ("Physical demand is repeatedly high enough to accumulate fatigue.", "Manage physical load better across the week."),
        "respiratory_bottleneck":    ("Breathing stability deserves follow-up if the pattern continues.", "Track whether respiratory irregularity repeats alongside fatigue or stress."),
    }

    main_risk, coaching_focus = risk_map.get(
        dominant_bottleneck,
        ("The day profile is mixed, without a single dominant repeated risk.", "Keep collecting days to identify the true dominant pattern.")
    )

    headline = {
        "improving": "Daytime physiology is trending in a better direction.",
        "worsening": "Daytime physiology is trending in a more strained direction.",
    }.get(trajectory, "Daytime physiology looks relatively stable.")

    return {
        "headline":         headline,
        "summary":          f"Across {len(history)} processed days, the current trajectory is {trajectory}. {dominant_pattern}",
        "dominant_pattern": dominant_pattern,
        "main_risk":        main_risk,
        "coaching_focus":   coaching_focus,
        "trajectory":       trajectory,
    }


# =========================
# Orchestrator
# =========================

def run_day_history_engine(base_day_dir, out_history_dir):
    days      = load_day_days(base_day_dir)
    history   = build_day_history(days)
    baselines = build_day_baselines(history)
    trends    = build_day_trends(history)
    anomalies = build_day_anomalies(history, baselines)
    bottlenecks = build_day_bottlenecks(history, baselines=baselines)
    patterns  = build_day_patterns(history, trends, bottlenecks=bottlenecks, anomalies=anomalies)
    longitudinal_brief = build_day_longitudinal_brief(
        history, trends, patterns,
        baselines=baselines, anomalies=anomalies, bottlenecks=bottlenecks
    )

    save_json(os.path.join(out_history_dir, "day_history.json"),          history)
    save_json(os.path.join(out_history_dir, "day_baselines.json"),         baselines)
    save_json(os.path.join(out_history_dir, "day_trends.json"),            trends)
    save_json(os.path.join(out_history_dir, "day_anomalies.json"),         anomalies)
    save_json(os.path.join(out_history_dir, "day_bottlenecks.json"),       bottlenecks)
    save_json(os.path.join(out_history_dir, "day_patterns.json"),          patterns)
    save_json(os.path.join(out_history_dir, "day_longitudinal_brief.json"), longitudinal_brief)

    return {
        "history": history, "baselines": baselines, "trends": trends,
        "anomalies": anomalies, "bottlenecks": bottlenecks,
        "patterns": patterns, "longitudinal_brief": longitudinal_brief,
    }


def main():
    base_day_dir    = input("Ruta base de días procesados: ").strip()
    out_history_dir = input("Ruta salida day_history: ").strip()
    result = run_day_history_engine(base_day_dir, out_history_dir)
    print(f"\nDAY HISTORY ENGINE COMPLETADO — {len(result['history'])} días válidos")


if __name__ == "__main__":
    main()