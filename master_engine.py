"""
master_engine.py
================
Motor maestro de performance intelligence.

Combina los 3 motores (sueño, día, actividad) para producir:
  1. fusion_daily_records.json   — tabla unificada por fecha
  2. performance_correlations.json — 13 correlaciones con interpretación
  3. dynamic_weights.json        — pesos aprendidos de tus propios datos
  4. readiness_history.json      — readiness score calculado por día
  5. master_brief.json           — brief del día actual con todo integrado

Uso:
    python master_engine.py --user_dir data/users/TU_USER
    python master_engine.py --user_dir data/users/TU_USER --date 2026-03-17
"""

import json
import math
import os
import argparse
from glob import glob
from statistics import mean
from datetime import datetime, date


# =========================================================
# Utils
# =========================================================

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip().strip("\x00")
            if not content:
                return None
            return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_get(dct, *keys, default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def first_number(*values):
    for v in values:
        if isinstance(v, (int, float)):
            return float(v)
    return None


def mean_or_none(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return mean(vals) if vals else None


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def parse_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except Exception:
        return None


def pearson(xs, ys):
    pairs = [
        (a, b) for a, b in zip(xs, ys)
        if isinstance(a, (int, float)) and isinstance(b, (int, float))
    ]
    if len(pairs) < 5:
        return None, len(pairs)

    ax = [p[0] for p in pairs]
    ay = [p[1] for p in pairs]
    mx, my = mean(ax), mean(ay)

    num = sum((a - mx) * (b - my) for a, b in pairs)
    dx = math.sqrt(sum((a - mx) ** 2 for a in ax))
    dy = math.sqrt(sum((b - my) ** 2 for b in ay))

    if dx == 0 or dy == 0:
        return None, len(pairs)

    return num / (dx * dy), len(pairs)


def interpret_r(r):
    if r is None:
        return "insufficient_data"
    ar = abs(r)
    direction = "positive" if r > 0 else "negative"
    if ar >= 0.70:
        strength = "strong"
    elif ar >= 0.45:
        strength = "moderate"
    elif ar >= 0.25:
        strength = "weak"
    else:
        strength = "very_weak"
    return f"{strength}_{direction}"


# =========================================================
# Loaders
# =========================================================

def load_sleep_records(user_dir):
    records = {}
    sleep_dir = os.path.join(user_dir, "sleep")

    for path in glob(os.path.join(sleep_dir, "*", "sleep_analysis.json")):
        date_str = os.path.basename(os.path.dirname(path))
        a = load_json(path)
        if not a:
            continue

        # Validación de calidad: si sleep_time_seconds < 3600 (1 hora)
        # Garmin no registró sueño real ese día — reloj cargando, no puesto, etc.
        sleep_time = safe_get(a, "sleep_window", "sleep_time_seconds") or 0
        if sleep_time < 3600:
            print(f"      [SKIP sueño] {date_str} — sleep_time={sleep_time}s (sin datos reales)")
            continue

        findings_path = os.path.join(os.path.dirname(path), "sleep_findings.json")
        f = load_json(findings_path) or {} if os.path.exists(findings_path) else {}

        records[date_str] = {
            "calendar_date": date_str,
            # Recovery
            "sleep_overall_recovery_score":       safe_get(a, "recovery_summary", "overall_recovery_score"),
            "sleep_physical_recovery_score":      safe_get(a, "recovery_summary", "physical_recovery_score"),
            "sleep_neural_recovery_score":        safe_get(a, "recovery_summary", "neural_recovery_score"),
            # Autonomic
            "sleep_autonomic_recovery_curve_score": safe_get(a, "autonomic_recovery", "autonomic_recovery_curve_score"),
            "sleep_avg_overnight_hrv":            safe_get(a, "autonomic_recovery", "avg_overnight_hrv"),
            "sleep_hrv_recovery_score":           safe_get(a, "autonomic_recovery", "hrv_recovery_score"),
            # Architecture
            "sleep_deep_ratio":                   safe_get(a, "sleep_architecture", "deep_ratio"),
            "sleep_rem_ratio":                    safe_get(a, "sleep_architecture", "rem_ratio"),
            "sleep_fragmentation_index":          safe_get(a, "sleep_architecture", "fragmentation_index"),
            "sleep_architecture_balance_score":   safe_get(a, "sleep_architecture", "architecture_balance_score"),
            # Window
            "sleep_time_seconds":                 safe_get(a, "sleep_window", "sleep_time_seconds"),
            "sleep_efficiency":                   safe_get(a, "sleep_window", "sleep_efficiency"),
            # Stress
            "sleep_avg_sleep_stress":             safe_get(a, "stress_recovery", "avg_sleep_stress"),
            # Oxygenation
            "sleep_min_spo2":                     safe_get(a, "oxygenation", "min_spo2"),
            "sleep_oxygen_risk_flag":             safe_get(a, "oxygenation", "oxygen_risk_flag"),
            # Energy
            "sleep_body_battery_change":          safe_get(a, "energy_recharge", "body_battery_change"),
            "sleep_recharge_efficiency":          safe_get(a, "energy_recharge", "recharge_efficiency"),
            # Circadian
            "sleep_circadian_alignment_score":    safe_get(a, "circadian_alignment", "circadian_alignment_score"),
            # Limiters
            "sleep_primary_limiter":              safe_get(f, "limiters", "primary_limiter"),
            "sleep_secondary_limiter":            safe_get(f, "limiters", "secondary_limiter"),
        }

    return records


def load_day_records(user_dir):
    records = {}
    day_dir = os.path.join(user_dir, "day")

    if not os.path.exists(day_dir):
        return records

    for path in glob(os.path.join(day_dir, "*", "day_analysis.json")):
        date_str = os.path.basename(os.path.dirname(path))
        a = load_json(path)
        if not a:
            continue

        findings_path = os.path.join(os.path.dirname(path), "day_findings.json")
        f = load_json(findings_path) or {} if os.path.exists(findings_path) else {}

        overall = first_number(
            safe_get(a, "recovery_summary", "overall_day_state_score"),
            safe_get(a, "summary_scores", "overall_day_state_score"),
            safe_get(a, "overall_day_state_score"),
            safe_get(a, "integrated_scores", "overall_day_state_score"),
        )

        # Validación de calidad: si el score es exactamente 100 y no hay
        # puntos de HR o stress reales, es un día sin datos reales del reloj
        hr_points = safe_get(a, "timeline_summary", "hr_points") or 0
        stress_points = safe_get(a, "timeline_summary", "stress_points") or 0
        if overall == 100.0 and hr_points == 0 and stress_points == 0:
            print(f"      [SKIP día]   {date_str} — score=100 sin series reales (hr={hr_points}, stress={stress_points})")
            continue

        records[date_str] = {
            "calendar_date": date_str,
            "day_overall_day_state_score":    overall,
            "day_system_strain_score":        first_number(safe_get(a, "recovery_summary", "system_strain_score")),
            "day_capacity_score":             first_number(safe_get(a, "recovery_summary", "day_capacity_score")),
            "day_recovery_response_score":    first_number(
                safe_get(a, "recovery_response", "recovery_response_score"),
                safe_get(a, "recovery_response_score"),
            ),
            "day_energy_dynamics_score":      first_number(
                safe_get(a, "energy_dynamics", "energy_dynamics_score"),
                safe_get(a, "energy_dynamics_score"),
            ),
            "day_avg_stress":                 first_number(
                safe_get(a, "stress_behavior", "avg_stress"),
                safe_get(a, "segments", "morning", "stress", "avg"),
            ),
            "day_nervous_system_load_score":  first_number(
                safe_get(a, "nervous_system_load", "nervous_system_load_score"),
                safe_get(a, "summary_scores", "nervous"),
            ),
            "day_cognitive_load_score":       first_number(
                safe_get(a, "cognitive_load", "cognitive_load_score"),
                safe_get(a, "summary_scores", "cognitive"),
            ),
            "day_body_battery_change":        first_number(
                safe_get(a, "energy_dynamics", "body_battery_change"),
            ),
            "day_primary_limiter":            safe_get(f, "limiters", "primary_limiter"),
            "day_secondary_limiter":          safe_get(f, "limiters", "secondary_limiter"),
        }

    return records


def _extract_activity_date(a):
    for candidate in [
        safe_get(a, "calendar_date"),
        safe_get(a, "activity_date"),
        safe_get(a, "date"),
        safe_get(a, "meta", "date"),
        safe_get(a, "garmin_summary", "calendar_date"),
        safe_get(a, "garmin_summary", "start_time_local"),
        safe_get(a, "garmin_summary", "startTimeLocal"),
    ]:
        d = parse_date(candidate)
        if d:
            return d
    return None


def _extract_activity_metrics(a, findings, brief):
    findings_list = findings.get("findings", []) if findings else []

    power_drop_pct = None
    efficiency_drop_pct = None
    high_msi_pct = None

    for item in findings_list:
        if not isinstance(item, dict):
            continue
        signal = item.get("signal", "")
        evidence = item.get("evidence", {})
        if signal in ("repeatability_low", "power_durability_drop") and power_drop_pct is None:
            power_drop_pct = evidence.get("power_drop_pct")
        if signal == "efficiency_drop_high" and efficiency_drop_pct is None:
            efficiency_drop_pct = evidence.get("efficiency_drop_pct")
        if signal == "low_cadence_metabolic_penalty" and high_msi_pct is None:
            high_msi_pct = evidence.get("high_msi_pct")

    # fallback directo desde analysis
    if power_drop_pct is None:
        power_drop_pct = safe_get(a, "fatigue", "power_drop_pct")
    if efficiency_drop_pct is None:
        efficiency_drop_pct = safe_get(a, "fatigue", "efficiency_drop_pct")
    if high_msi_pct is None:
        high_msi_pct = safe_get(a, "metabolic_index", "high_msi_pct")

    performance_score = first_number(
        safe_get(brief, "phase_1_quick_insight", "overall_score", "score"),
        safe_get(a, "performance_scores", "overall_score", "score"),
        safe_get(a, "overall_score"),
    )

    repeatability_score = first_number(
        safe_get(a, "performance_scores", "repeatability_score", "score"),
        safe_get(brief, "phase_1_quick_insight", "scores", 0, "score"),
    )

    pacing_score = first_number(
        safe_get(a, "performance_scores", "pacing_score", "score"),
    )

    metabolic_cost_score = first_number(
        safe_get(a, "performance_scores", "metabolic_cost_score", "score"),
    )

    tss = first_number(safe_get(a, "garmin_summary", "garmin_tss"))

    return {
        "activity_estimated_np":        first_number(safe_get(a, "derived_summary", "estimated_np"), safe_get(a, "garmin_summary", "garmin_np")),
        "activity_estimated_if":        first_number(safe_get(a, "derived_summary", "estimated_if"), safe_get(a, "garmin_summary", "garmin_if")),
        "activity_vi":                  first_number(safe_get(a, "derived_summary", "vi")),
        "activity_avg_power":           first_number(safe_get(a, "derived_summary", "avg_power"), safe_get(a, "garmin_summary", "avg_power")),
        "activity_tss":                 tss,
        "activity_power_drop_pct":      power_drop_pct,
        "activity_power_drop_loss":     max(0.0, -float(power_drop_pct)) if isinstance(power_drop_pct, (int, float)) else None,
        "activity_efficiency_drop_pct": efficiency_drop_pct,
        "activity_efficiency_drop_loss": max(0.0, -float(efficiency_drop_pct)) if isinstance(efficiency_drop_pct, (int, float)) else None,
        "activity_high_msi_pct":        high_msi_pct,
        "activity_performance_score":   performance_score,
        "activity_repeatability_score": repeatability_score,
        "activity_pacing_score":        pacing_score,
        "activity_metabolic_cost_score": metabolic_cost_score,
    }


def load_activity_records(user_dir):
    activities_dir = os.path.join(user_dir, "activities")
    by_date = {}

    if not os.path.exists(activities_dir):
        return by_date

    # Carga activity_index.json para obtener fecha por activity_id
    # El índice tiene: {"activities": [{"activity_id": 123, "date": "2026-03-18 06:11:00", ...}]}
    index_path = os.path.join(user_dir, "activity_index.json")
    date_by_id = {}
    if os.path.exists(index_path):
        index = load_json(index_path)
        for entry in index.get("activities", []):
            aid = str(entry.get("activity_id", ""))
            date_raw = entry.get("date") or entry.get("startTimeLocal") or entry.get("start_time_local")
            d = parse_date(date_raw)
            if aid and d:
                date_by_id[aid] = d

    for path in glob(os.path.join(activities_dir, "*", "activity_analysis.json")):
        activity_dir = os.path.dirname(path)
        activity_id  = os.path.basename(activity_dir)
        a = load_json(path)
        if not a:
            continue

        findings_path = os.path.join(activity_dir, "activity_findings.json")
        brief_path    = os.path.join(activity_dir, "activity_brief.json")
        findings = load_json(findings_path) or {} if os.path.exists(findings_path) else {}
        brief    = load_json(brief_path)    or {} if os.path.exists(brief_path)    else {}

        # 1) intenta fecha desde el índice (fuente más confiable)
        date_str = date_by_id.get(activity_id)

        # 2) fallback: busca dentro del JSON
        if not date_str:
            date_str = _extract_activity_date(a)

        if not date_str:
            print(f"      [SKIP actividad] {activity_id} — no se pudo determinar la fecha")
            continue

        print(f"      [actividad] {activity_id} → {date_str}")
        metrics = _extract_activity_metrics(a, findings, brief)
        by_date.setdefault(date_str, []).append(metrics)

    if not by_date:
        return {}

    # agrega múltiples actividades del mismo día
    out = {}
    numeric_keys = list(list(by_date.values())[0][0].keys())
    for date_str, rows in by_date.items():
        merged = {"calendar_date": date_str}
        for k in numeric_keys:
            merged[k] = mean_or_none([r.get(k) for r in rows])
        out[date_str] = merged

    return out


# =========================================================
# Fusion
# =========================================================

def build_fusion_records(user_dir):
    sleep_recs    = load_sleep_records(user_dir)
    day_recs      = load_day_records(user_dir)
    activity_recs = load_activity_records(user_dir)

    all_dates = sorted(
        set(sleep_recs.keys()) | set(day_recs.keys()) | set(activity_recs.keys())
    )

    rows = []
    for d in all_dates:
        row = {"calendar_date": d}
        if d in sleep_recs:
            row.update(sleep_recs[d])
        if d in day_recs:
            row.update(day_recs[d])
        if d in activity_recs:
            row.update(activity_recs[d])
        rows.append(row)

    return rows


# =========================================================
# Correlation specs (13 correlaciones)
# =========================================================

CORRELATION_SPECS = [
    # --- Sueño → Actividad ---
    {
        "name": "hrv_vs_durability_loss",
        "x": "sleep_avg_overnight_hrv",
        "y": "activity_power_drop_loss",
        "direction": "negative_is_bad",
        "what_it_says": "HRV nocturna baja → peor capacidad de sostener potencia en el ride.",
    },
    {
        "name": "rem_vs_pacing",
        "x": "sleep_rem_ratio",
        "y": "activity_vi",
        "direction": "negative_is_bad",
        "what_it_says": "Menos REM → peor pacing y más variabilidad de potencia.",
    },
    {
        "name": "autonomic_vs_metabolic_cost",
        "x": "sleep_autonomic_recovery_curve_score",
        "y": "activity_high_msi_pct",
        "direction": "negative_is_bad",
        "what_it_says": "Peor recuperación autonómica → esfuerzo sale más caro metabólicamente.",
    },
    {
        "name": "body_battery_recharge_vs_intensity",
        "x": "sleep_body_battery_change",
        "y": "activity_estimated_if",
        "direction": "positive_is_good",
        "what_it_says": "Más recarga nocturna → mayor tolerancia a intensidad en el ride.",
    },
    {
        "name": "spo2_nadir_vs_durability_loss",
        "x": "sleep_min_spo2",
        "y": "activity_power_drop_loss",
        "direction": "negative_is_bad",
        "what_it_says": "Peor oxigenación nocturna → mayor caída de potencia sostenida.",
    },
    {
        "name": "deep_ratio_vs_repeatability",
        "x": "sleep_deep_ratio",
        "y": "activity_repeatability_score",
        "direction": "positive_is_good",
        "what_it_says": "Más sueño profundo → mejor repeatability en subidas repetidas.",
    },
    {
        "name": "circadian_alignment_vs_pacing",
        "x": "sleep_circadian_alignment_score",
        "y": "activity_pacing_score",
        "direction": "positive_is_good",
        "what_it_says": "Mejor alineación circadiana → mejor dosificación y toma de decisiones.",
    },
    {
        "name": "sleep_quantity_vs_np",
        "x": "sleep_time_seconds",
        "y": "activity_estimated_np",
        "direction": "positive_is_good",
        "what_it_says": "Más horas reales de sueño → mayor output total (NP).",
    },
    # --- Día → Actividad ---
    {
        "name": "day_stress_vs_efficiency_loss",
        "x": "day_avg_stress",
        "y": "activity_efficiency_drop_loss",
        "direction": "negative_is_bad",
        "what_it_says": "Más estrés diurno → peor economía potencia/FC en el ride.",
    },
    {
        "name": "intraday_recovery_vs_durability_loss",
        "x": "day_recovery_response_score",
        "y": "activity_power_drop_loss",
        "direction": "negative_is_bad",
        "what_it_says": "Peor recuperación intradiaria → mayor caída de potencia.",
    },
    {
        "name": "nervous_load_vs_metabolic_cost",
        "x": "day_nervous_system_load_score",
        "y": "activity_metabolic_cost_score",
        "direction": "negative_is_bad",
        "what_it_says": "Mayor carga neural del día → esfuerzo más caro metabólicamente.",
    },
    {
        "name": "day_energy_vs_performance",
        "x": "day_energy_dynamics_score",
        "y": "activity_performance_score",
        "direction": "positive_is_good",
        "what_it_says": "Mejor energía del día → mejor score global de la actividad.",
    },
    # --- Readiness combinado → Performance ---
    {
        "name": "combined_readiness_vs_performance",
        "x": "combined_readiness_score",
        "y": "activity_performance_score",
        "direction": "positive_is_good",
        "what_it_says": "Validación del modelo: qué tan bien predice el readiness tu rendimiento real.",
    },
]


# =========================================================
# Correlaciones
# =========================================================

def compute_correlations(fusion_rows):
    results = []
    for spec in CORRELATION_SPECS:
        xs = [r.get(spec["x"]) for r in fusion_rows]
        ys = [r.get(spec["y"]) for r in fusion_rows]
        r, n = pearson(xs, ys)
        results.append({
            "name": spec["name"],
            "x_metric": spec["x"],
            "y_metric": spec["y"],
            "direction": spec["direction"],
            "n_pairs": n,
            "pearson_r": round(r, 4) if r is not None else None,
            "interpretation": interpret_r(r),
            "what_it_says": spec["what_it_says"],
        })
    return results


# =========================================================
# Pesos dinámicos
# =========================================================

# Métricas que van al readiness score de sueño y cuánto
# impactan la actividad según las correlaciones relevantes
SLEEP_WEIGHT_SOURCES = [
    "hrv_vs_durability_loss",
    "autonomic_vs_metabolic_cost",
    "body_battery_recharge_vs_intensity",
    "spo2_nadir_vs_durability_loss",
    "deep_ratio_vs_repeatability",
    "circadian_alignment_vs_pacing",
    "sleep_quantity_vs_np",
]

DAY_WEIGHT_SOURCES = [
    "day_stress_vs_efficiency_loss",
    "intraday_recovery_vs_durability_loss",
    "nervous_load_vs_metabolic_cost",
    "day_energy_vs_performance",
]


def compute_dynamic_weights(correlations):
    """
    Calcula qué tanto pesa sueño vs día en el combined_readiness_score
    basado en la fuerza absoluta promedio de las correlaciones de cada dominio.
    Si hay datos insuficientes, cae a defaults (0.55 / 0.45).
    """
    corr_by_name = {c["name"]: c for c in correlations}

    def domain_strength(names):
        strengths = []
        for name in names:
            c = corr_by_name.get(name)
            if c and c["pearson_r"] is not None and c["n_pairs"] >= 5:
                strengths.append(abs(c["pearson_r"]))
        return mean(strengths) if strengths else None

    sleep_strength = domain_strength(SLEEP_WEIGHT_SOURCES)
    day_strength   = domain_strength(DAY_WEIGHT_SOURCES)

    if sleep_strength is None and day_strength is None:
        sleep_w, day_w = 0.55, 0.45
        source = "default_insufficient_data"
    elif sleep_strength is None:
        sleep_w, day_w = 0.40, 0.60
        source = "default_no_sleep_corr"
    elif day_strength is None:
        sleep_w, day_w = 0.60, 0.40
        source = "default_no_day_corr"
    else:
        total = sleep_strength + day_strength
        sleep_w = round(sleep_strength / total, 4)
        day_w   = round(day_strength  / total, 4)
        source = "computed_from_correlations"

    return {
        "sleep_weight": sleep_w,
        "day_weight":   day_w,
        "sleep_avg_r":  round(sleep_strength, 4) if sleep_strength else None,
        "day_avg_r":    round(day_strength,   4) if day_strength   else None,
        "source":       source,
        "interpretation": (
            f"Sueño pesa {round(sleep_w*100)}% y día {round(day_w*100)}% "
            f"basado en fuerza media de correlaciones "
            f"(sueño r̄={round(sleep_strength,3) if sleep_strength else 'N/A'}, "
            f"día r̄={round(day_strength,3) if day_strength else 'N/A'})."
        ),
    }


# =========================================================
# Readiness score
# =========================================================

# Penalizaciones por flags críticos (se restan del score base)
SPO2_PENALTY    = 8.0   # si oxygen_risk_flag está activo
HRV_PENALTY     = 6.0   # si hrv_status es UNBALANCED
FRAG_PENALTY    = 4.0   # si fragmentation_index > 0.40


def compute_readiness_score(row, weights):
    """
    Calcula el readiness score de 0–100 para un día específico.
    Combina sueño y día con pesos dinámicos + penalizaciones por flags.
    Si no hay actividad ese día, solo usa sueño+día.
    Si no hay datos de día, solo usa sueño.
    """
    sleep_score = row.get("sleep_overall_recovery_score")
    day_score   = row.get("day_overall_day_state_score")

    # --- Score base combinado ---
    if isinstance(sleep_score, (int, float)) and isinstance(day_score, (int, float)):
        base = weights["sleep_weight"] * float(sleep_score) + weights["day_weight"] * float(day_score)
    elif isinstance(sleep_score, (int, float)):
        base = float(sleep_score)
    elif isinstance(day_score, (int, float)):
        base = float(day_score)
    else:
        return None

    # --- Penalizaciones por flags críticos ---
    penalty = 0.0
    penalty_notes = []

    if row.get("sleep_oxygen_risk_flag") is True:
        penalty += SPO2_PENALTY
        penalty_notes.append(f"spo2_risk (-{SPO2_PENALTY})")

    frag = row.get("sleep_fragmentation_index")
    if isinstance(frag, (int, float)) and frag > 0.40:
        penalty += FRAG_PENALTY
        penalty_notes.append(f"fragmentation ({round(frag,2)}) (-{FRAG_PENALTY})")

    # día: si recovery_response_score es muy bajo (< 10), penaliza
    rrs = row.get("day_recovery_response_score")
    if isinstance(rrs, (int, float)) and rrs < 10:
        p = round((10 - rrs) * 0.5, 1)
        penalty += p
        penalty_notes.append(f"low_intraday_recovery (-{p})")

    final = clamp(base - penalty)

    return {
        "readiness_score":  round(final, 2),
        "base_score":       round(base,  2),
        "penalty_total":    round(penalty, 2),
        "penalty_notes":    penalty_notes,
        "sleep_score_used": sleep_score,
        "day_score_used":   day_score,
        "sleep_weight":     weights["sleep_weight"],
        "day_weight":       weights["day_weight"],
    }


def readiness_label(score):
    if score is None:
        return "no_data"
    if score >= 80:
        return "listo_para_carga_alta"
    if score >= 65:
        return "listo_para_carga_normal"
    if score >= 50:
        return "precaucion_carga_reducida"
    if score >= 35:
        return "recuperacion_activa"
    return "descanso_prioritario"


def readiness_recommendation(score, row):
    label = readiness_label(score)

    recs = {
        "listo_para_carga_alta":     "Día verde. Puedes entrenar con carga alta, intensidad completa y objetivos de rendimiento.",
        "listo_para_carga_normal":   "Día amarillo-verde. Entrena normal. Monitorea si la intensidad se siente más costosa de lo habitual.",
        "precaucion_carga_reducida": "Día amarillo. Reduce volumen o intensidad ~20–30%. Evita bloques VO2 sostenidos.",
        "recuperacion_activa":       "Día naranja. Rodaje suave, movilidad o técnica. No acumules más carga.",
        "descanso_prioritario":      "Día rojo. Descanso completo o actividad muy suave. La carga hoy costará mañana.",
    }

    base_rec = recs.get(label, "")

    # contexto extra por limitantes
    sleep_lim = row.get("sleep_primary_limiter", "")
    day_lim   = row.get("day_primary_limiter", "")

    extras = []
    if sleep_lim == "autonomic_fatigue":
        extras.append("Sistema nervioso en recuperación incompleta — evita picos anaeróbicos.")
    if sleep_lim == "sleep_quantity_deficit":
        extras.append("Déficit de cantidad de sueño — prioriza dormir más esta noche.")
    if "oxygen" in str(sleep_lim):
        extras.append("Alerta de oxigenación nocturna — controla respiración durante el esfuerzo.")
    if day_lim == "recovery_failure":
        extras.append("Recuperación intradiaria limitada — reduce carga si entrenas hoy.")
    if day_lim == "energy_depletion":
        extras.append("Energía diurna baja — recarga antes de salir a rodar.")

    return base_rec + (" " + " ".join(extras) if extras else "")


# =========================================================
# Determinar limitante principal del día
# =========================================================

def compute_primary_limiter(row, readiness):
    if readiness is None:
        return "no_data"

    score = readiness["readiness_score"]

    sleep_lim = row.get("sleep_primary_limiter")
    day_lim   = row.get("day_primary_limiter")
    penalty_notes = readiness.get("penalty_notes", [])

    # Si hay flag crítico de spo2, siempre es el limitante dominante
    if row.get("sleep_oxygen_risk_flag"):
        return "oxygenation_risk"

    # Si el penalty de sueño supera al de día en contribución al score bajo
    sleep_score = row.get("sleep_overall_recovery_score") or 50
    day_score   = row.get("day_overall_day_state_score")  or 50

    if sleep_score < day_score:
        return sleep_lim or "sleep_recovery"
    else:
        return day_lim or "day_state"


# =========================================================
# Brief del día actual
# =========================================================

def build_master_brief(row, readiness, correlations, weights):
    if not row or readiness is None:
        return None

    score = readiness["readiness_score"]
    label = readiness_label(score)
    recommendation = readiness_recommendation(score, row)
    primary_limiter = compute_primary_limiter(row, readiness)

    # Correlaciones fuertes (|r| >= 0.45 con datos suficientes)
    strong_corrs = [
        c for c in correlations
        if c["pearson_r"] is not None
        and abs(c["pearson_r"]) >= 0.45
        and c["n_pairs"] >= 5
    ]

    # Proyección de actividad basada en readiness
    if score >= 80:
        activity_projection = "Condiciones óptimas. Sesiones de calidad alta esperadas."
    elif score >= 65:
        activity_projection = "Rendimiento normal. Ligero riesgo de caída de eficiencia tardía."
    elif score >= 50:
        activity_projection = "Rendimiento por debajo del potencial. Probable caída de potencia en esfuerzos sostenidos."
    else:
        activity_projection = "Rendimiento limitado. Alta probabilidad de degradación de eficiencia y repeatability."

    return {
        "calendar_date":           row.get("calendar_date"),
        "readiness_score":         score,
        "readiness_label":         label,
        "primary_limiter":         primary_limiter,
        "secondary_limiter":       row.get("sleep_secondary_limiter") or row.get("day_secondary_limiter"),
        "recommendation":          recommendation,
        "activity_projection":     activity_projection,
        "penalty_notes":           readiness.get("penalty_notes", []),
        "contributing_scores": {
            "sleep_overall_recovery": row.get("sleep_overall_recovery_score"),
            "sleep_physical":         row.get("sleep_physical_recovery_score"),
            "sleep_neural":           row.get("sleep_neural_recovery_score"),
            "sleep_autonomic_curve":  row.get("sleep_autonomic_recovery_curve_score"),
            "day_overall_state":      row.get("day_overall_day_state_score"),
            "day_recovery_response":  row.get("day_recovery_response_score"),
            "day_energy_dynamics":    row.get("day_energy_dynamics_score"),
        },
        "risk_flags": {
            "oxygen_risk":        row.get("sleep_oxygen_risk_flag", False),
            "low_rem":            isinstance(row.get("sleep_rem_ratio"), (int, float)) and row["sleep_rem_ratio"] < 0.20,
            "low_hrv":            isinstance(row.get("sleep_avg_overnight_hrv"), (int, float)) and row["sleep_avg_overnight_hrv"] < 40,
            "high_day_stress":    isinstance(row.get("day_avg_stress"), (int, float)) and row["day_avg_stress"] > 30,
            "energy_crash":       isinstance(row.get("day_energy_dynamics_score"), (int, float)) and row["day_energy_dynamics_score"] < 25,
            "fragmentation":      isinstance(row.get("sleep_fragmentation_index"), (int, float)) and row["sleep_fragmentation_index"] > 0.40,
        },
        "dynamic_weights": {
            "sleep_weight": weights["sleep_weight"],
            "day_weight":   weights["day_weight"],
            "source":       weights["source"],
        },
        "strong_personal_correlations": [
            {
                "name":         c["name"],
                "r":            c["pearson_r"],
                "what_it_says": c["what_it_says"],
            }
            for c in sorted(strong_corrs, key=lambda x: abs(x["pearson_r"]), reverse=True)[:5]
        ],
    }


# =========================================================
# Master engine principal
# =========================================================

def run_master_engine(user_dir, target_date=None):
    print("\n" + "=" * 50)
    print("MASTER PERFORMANCE INTELLIGENCE ENGINE")
    print("=" * 50)

    output_dir = os.path.join(user_dir, "performance_intelligence")
    os.makedirs(output_dir, exist_ok=True)

    # 1) Fusion
    print("\n[1/5] Construyendo fusion records...")
    fusion_rows = build_fusion_records(user_dir)
    print(f"      {len(fusion_rows)} días fusionados.")
    skipped_sleep = len([r for r in fusion_rows if r.get("sleep_overall_recovery_score") is None])
    skipped_day   = len([r for r in fusion_rows if r.get("day_overall_day_state_score") is None])
    print(f"      (días sin sueño válido excluidos del loader: ver logs de sleep)")
    print(f"      Días sin motor día: {skipped_day} | Días sin motor sueño: {skipped_sleep}")
    save_json(os.path.join(output_dir, "fusion_daily_records.json"), fusion_rows)

    # 2) Correlaciones (necesitan combined_readiness provisional con pesos default)
    print("\n[2/5] Calculando correlaciones (primera pasada con pesos default)...")
    for row in fusion_rows:
        s = row.get("sleep_overall_recovery_score")
        d = row.get("day_overall_day_state_score")
        if isinstance(s, (int, float)) and isinstance(d, (int, float)):
            row["combined_readiness_score"] = round(0.55 * float(s) + 0.45 * float(d), 2)
        elif isinstance(s, (int, float)):
            row["combined_readiness_score"] = round(float(s), 2)
        elif isinstance(d, (int, float)):
            row["combined_readiness_score"] = round(float(d), 2)
        else:
            row["combined_readiness_score"] = None

    correlations = compute_correlations(fusion_rows)

    for c in correlations:
        print(f"      {c['name']}: r={c['pearson_r']} ({c['interpretation']}) [n={c['n_pairs']}]")

    save_json(os.path.join(output_dir, "performance_correlations.json"), {
        "record_count": len(fusion_rows),
        "correlations": correlations,
    })

    # 3) Pesos dinámicos
    print("\n[3/5] Calculando pesos dinámicos...")
    weights = compute_dynamic_weights(correlations)
    print(f"      Sueño: {weights['sleep_weight']} | Día: {weights['day_weight']} ({weights['source']})")
    save_json(os.path.join(output_dir, "dynamic_weights.json"), weights)

    # 4) Readiness history con pesos finales
    print("\n[4/5] Calculando readiness history con pesos dinámicos...")
    readiness_history = []
    for row in fusion_rows:
        r = compute_readiness_score(row, weights)
        if r:
            row["combined_readiness_score"] = r["readiness_score"]
            entry = {
                "calendar_date":   row.get("calendar_date"),
                "readiness_score": r["readiness_score"],
                "readiness_label": readiness_label(r["readiness_score"]),
                "base_score":      r["base_score"],
                "penalty_total":   r["penalty_total"],
                "penalty_notes":   r["penalty_notes"],
                "sleep_score":     r["sleep_score_used"],
                "day_score":       r["day_score_used"],
                "has_activity":    row.get("activity_tss") is not None,
                "activity_performance_score": row.get("activity_performance_score"),
            }
            readiness_history.append(entry)

    save_json(os.path.join(output_dir, "readiness_history.json"), readiness_history)

    # Recomputar correlación final con pesos correctos
    correlations = compute_correlations(fusion_rows)
    save_json(os.path.join(output_dir, "performance_correlations.json"), {
        "record_count": len(fusion_rows),
        "correlations": correlations,
    })

    # 5) Brief del día objetivo
    print("\n[5/5] Generando master brief...")

    if target_date is None:
        target_date = date.today().isoformat()

    # Busca el día objetivo; si no existe, usa el último disponible
    target_row = next((r for r in reversed(fusion_rows) if r.get("calendar_date") == target_date), None)
    if target_row is None:
        target_row = fusion_rows[-1] if fusion_rows else None
        if target_row:
            print(f"      Fecha {target_date} no encontrada. Usando último disponible: {target_row.get('calendar_date')}")

    if target_row:
        readiness = compute_readiness_score(target_row, weights)
        brief = build_master_brief(target_row, readiness, correlations, weights)
        save_json(os.path.join(output_dir, "master_brief.json"), brief)
        _print_brief(brief)
    else:
        print("      No hay datos suficientes para generar el brief.")
        brief = None

    print("\n" + "=" * 50)
    print("MASTER ENGINE TERMINADO")
    print(f"Outputs en: {output_dir}")
    print("=" * 50 + "\n")

    # Guardar en PostgreSQL
    try:
        from db import ensure_user, upsert_intelligence
        from app_context import get_current_garmin_email
        email = get_current_garmin_email()
        db_uid = ensure_user(email)
        if brief:
            upsert_intelligence(db_uid, "master_brief_json", brief)
        upsert_intelligence(db_uid, "readiness_history_json", readiness_history)
        upsert_intelligence(db_uid, "correlations_json", {"record_count": len(fusion_rows), "correlations": correlations})
        upsert_intelligence(db_uid, "dynamic_weights_json", weights)
        print("[DB] user_intelligence actualizado")
    except Exception as e:
        print(f"[DB] Warning master_engine: {e}")

    return {
        "fusion_rows":        fusion_rows,
        "correlations":       correlations,
        "weights":            weights,
        "readiness_history":  readiness_history,
        "master_brief":       brief,
    }


def _print_brief(brief):
    if not brief:
        return
    print(f"\n      Fecha:              {brief['calendar_date']}")
    print(f"      Readiness score:    {brief['readiness_score']}/100")
    print(f"      Label:              {brief['readiness_label']}")
    print(f"      Limitante:          {brief['primary_limiter']}")
    print(f"      Proyección ride:    {brief['activity_projection']}")
    if brief["penalty_notes"]:
        print(f"      Penalizaciones:     {', '.join(brief['penalty_notes'])}")
    print(f"      Recomendación:      {brief['recommendation']}")


# =========================================================
# Función pública para usar desde otros módulos
# =========================================================

def get_master_brief_for_date(user_dir, date_str=None):
    """
    Punto de entrada limpio para llamar desde home_menu.py u otros módulos.
    Retorna el master_brief del día indicado (o el último disponible).
    """
    result = run_master_engine(user_dir, target_date=date_str)
    return result.get("master_brief")


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master Performance Intelligence Engine")
    parser.add_argument(
        "--user_dir",
        type=str,
        default="data/users/TU_USER",
        help="Directorio del usuario (ej: data/users/abelgcanofuentes_at_hotmail_com)"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Fecha objetivo YYYY-MM-DD (default: hoy)"
    )
    args = parser.parse_args()
    run_master_engine(args.user_dir, target_date=args.date)