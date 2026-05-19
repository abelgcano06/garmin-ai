"""
series_insights_engine.py
=========================
Extrae correlaciones de la serie temporal (CSV) de una actividad.
Produce series_insights.json con ~8 insights estructurados que describen
lo que pasó en la actividad en términos de dinámica temporal:
desacople cardíaco, depleción de stamina, fatiga de cadencia por ascenso, etc.

Uso:
    python series_insights_engine.py \\
        --csv data/users/USER/activities/ID/activity_series_clean.csv \\
        --analysis data/users/USER/activities/ID/activity_analysis.json
"""

import csv
import json
import os
import argparse
from datetime import datetime
from statistics import mean


# ─── CSV loader ───────────────────────────────────────────────────────────────

def _load_csv(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = {}
            for k, v in row.items():
                try:
                    parsed[k] = float(v) if v.strip() != "" else None
                except (ValueError, AttributeError):
                    parsed[k] = None
            rows.append(parsed)
    return rows


def _safe(rows: list[dict], col: str, filt=None) -> list[float]:
    """Extrae columna filtrando nulos y aplicando filtro opcional."""
    out = []
    for r in rows:
        v = r.get(col)
        if v is not None and v != 0:
            if filt is None or filt(r):
                out.append(v)
    return out


# ─── 1. Desacople cardíaco ─────────────────────────────────────────────────

def _compute_cardiac_decoupling(rows: list[dict]) -> dict | None:
    valid = [r for r in rows if (r.get("power_w") or 0) > 50 and (r.get("heart_rate_bpm") or 0) > 0]
    if len(valid) < 20:
        return None

    mid = len(valid) // 2
    h1 = valid[:mid]
    h2 = valid[mid:]

    p1 = mean(r["power_w"] for r in h1)
    p2 = mean(r["power_w"] for r in h2)
    hr1 = mean(r["heart_rate_bpm"] for r in h1)
    hr2 = mean(r["heart_rate_bpm"] for r in h2)

    if p1 == 0 or hr1 == 0:
        return None

    power_ratio = p2 / p1
    hr_ratio = hr2 / hr1
    decoupling_ratio = hr_ratio / power_ratio if power_ratio > 0 else 1.0

    decoupled = decoupling_ratio > 1.05
    severity = "none"
    if decoupling_ratio > 1.12:
        severity = "high"
    elif decoupling_ratio > 1.06:
        severity = "moderate"
    elif decoupling_ratio > 1.02:
        severity = "low"

    power_delta_pct = round((p2 - p1) / p1 * 100, 1)
    hr_delta_pct = round((hr2 - hr1) / hr1 * 100, 1)

    interpretation = (
        f"FC subió {hr_delta_pct:+.1f}% en segunda mitad mientras potencia cambió {power_delta_pct:+.1f}%"
        if decoupled
        else f"FC y potencia se mantuvieron proporcionales — eficiencia cardíaca sostenida"
    )

    return {
        "avg_power_h1": round(p1, 1),
        "avg_hr_h1": round(hr1, 1),
        "avg_power_h2": round(p2, 1),
        "avg_hr_h2": round(hr2, 1),
        "power_delta_pct": power_delta_pct,
        "hr_delta_pct": hr_delta_pct,
        "decoupling_ratio": round(decoupling_ratio, 3),
        "decoupled": decoupled,
        "severity": severity,
        "interpretation": interpretation,
    }


# ─── 2. Depleción de stamina ──────────────────────────────────────────────

def _compute_stamina_depletion(rows: list[dict]) -> dict | None:
    valid = [(r.get("elapsed_s", 0), r["available_stamina"])
             for r in rows if r.get("available_stamina") is not None and r.get("available_stamina") > 0]
    if len(valid) < 10:
        return None

    stamina_start = valid[0][1]
    stamina_end = valid[-1][1]
    total_drop = stamina_start - stamina_end

    # Encuentra la ventana de 5 filas con mayor caída
    biggest_drop = 0
    fastest_start_s = 0
    fastest_end_s = 0
    for i in range(len(valid) - 5):
        drop = valid[i][1] - valid[i + 5][1]
        if drop > biggest_drop:
            biggest_drop = drop
            fastest_start_s = valid[i][0]
            fastest_end_s = valid[i + 5][0]

    return {
        "stamina_start_pct": round(stamina_start, 1),
        "stamina_end_pct": round(stamina_end, 1),
        "total_drop_pct": round(total_drop, 1),
        "fastest_drop_start_min": round(fastest_start_s / 60, 1),
        "fastest_drop_end_min": round(fastest_end_s / 60, 1),
        "fastest_drop_magnitude_pct": round(biggest_drop, 1),
        "interpretation": (
            f"Stamina cayó de {stamina_start:.0f}% a {stamina_end:.0f}% "
            f"— caída más abrupta entre min {fastest_start_s/60:.0f}–{fastest_end_s/60:.0f}"
        ),
    }


# ─── 3. Fatiga de cadencia por ascenso ────────────────────────────────────

def _compute_cadence_fatigue_per_climb(rows: list[dict], climbs: list[dict]) -> list[dict] | None:
    if not climbs:
        return None

    results = []
    for i, climb in enumerate(climbs):
        start_min = climb.get("start_min", 0)
        end_min = start_min + climb.get("duration_min", 0)

        seg = [r for r in rows
               if start_min - 0.5 <= (r.get("elapsed_s", 0) / 60) <= end_min + 0.5
               and (r.get("cadence_rpm") or 0) > 20]

        if len(seg) < 6:
            continue

        n15 = max(1, len(seg) // 6)
        cad_start = mean(r["cadence_rpm"] for r in seg[:n15])
        cad_end = mean(r["cadence_rpm"] for r in seg[-n15:])
        drop = cad_start - cad_end
        drop_pct = drop / cad_start * 100 if cad_start > 0 else 0

        severity = "none"
        if drop_pct > 20:
            severity = "high"
        elif drop_pct > 10:
            severity = "moderate"
        elif drop_pct > 5:
            severity = "low"

        results.append({
            "climb_index": i,
            "climb_type": climb.get("climb_type", ""),
            "avg_grade_pct": climb.get("avg_grade_pct"),
            "vam": climb.get("vam"),
            "cadence_start_rpm": round(cad_start, 1),
            "cadence_end_rpm": round(cad_end, 1),
            "cadence_drop_rpm": round(drop, 1),
            "cadence_drop_pct": round(drop_pct, 1),
            "severity": severity,
        })

    if not results:
        return None
    return results


# ─── 4. Tendencia de condición de rendimiento ────────────────────────────

def _compute_performance_condition_trend(rows: list[dict]) -> dict | None:
    valid = [(r.get("elapsed_s", 0), r["performance_condition"])
             for r in rows
             if r.get("performance_condition") is not None and r["performance_condition"] != 0]
    if len(valid) < 9:
        return None

    n = len(valid)
    t1 = valid[:n // 3]
    t2 = valid[n // 3: 2 * n // 3]
    t3 = valid[2 * n // 3:]

    avg1 = mean(v[1] for v in t1)
    avg2 = mean(v[1] for v in t2)
    avg3 = mean(v[1] for v in t3)

    if avg1 > avg3 + 1:
        direction = "declining"
    elif avg3 > avg1 + 1:
        direction = "improving"
    else:
        direction = "stable"

    return {
        "start_avg": round(avg1, 1),
        "mid_avg": round(avg2, 1),
        "end_avg": round(avg3, 1),
        "trend_direction": direction,
        "interpretation": (
            f"Condición de rendimiento: inicio={avg1:+.1f}, medio={avg2:+.1f}, final={avg3:+.1f} "
            f"— tendencia {direction}"
        ),
    }


# ─── 5. Eficiencia W/bpm por segmentos ────────────────────────────────────

def _compute_wbpm_efficiency_segments(rows: list[dict], n_segments: int = 10) -> dict | None:
    valid = [r for r in rows
             if (r.get("power_w") or 0) > 50 and (r.get("heart_rate_bpm") or 0) > 0]
    if len(valid) < n_segments * 3:
        return None

    seg_size = len(valid) // n_segments
    segments = []
    for i in range(n_segments):
        seg = valid[i * seg_size: (i + 1) * seg_size]
        avg_p = mean(r["power_w"] for r in seg)
        avg_hr = mean(r["heart_rate_bpm"] for r in seg)
        wbpm = avg_p / avg_hr if avg_hr > 0 else 0
        segments.append(round(wbpm, 3))

    h1 = mean(segments[:5])
    h2 = mean(segments[5:])
    det = (h1 - h2) / h1 * 100 if h1 > 0 else 0

    # Segmento donde cruza la caída significativa (>5%)
    threshold_seg = None
    for i in range(1, len(segments)):
        if (segments[0] - segments[i]) / segments[0] * 100 > 5:
            threshold_seg = i
            break

    return {
        "segments": segments,
        "first_half_avg": round(h1, 3),
        "second_half_avg": round(h2, 3),
        "deterioration_pct": round(det, 1),
        "threshold_crossed_at_segment": threshold_seg,
        "interpretation": (
            f"Eficiencia W/bpm: primera mitad {h1:.2f} → segunda mitad {h2:.2f} "
            f"({det:+.1f}%)"
        ),
    }


# ─── 6. Contexto del pico de potencia ─────────────────────────────────────

def _compute_peak_power_context(rows: list[dict]) -> dict | None:
    with_power = [r for r in rows if (r.get("power_w") or 0) > 0]
    if not with_power:
        return None

    peak_row = max(with_power, key=lambda r: r.get("power_w", 0))
    peak_idx = rows.index(peak_row)

    # Ventana ±30 segundos
    window = [r for r in rows
              if abs((r.get("elapsed_s", 0) - peak_row.get("elapsed_s", 0))) <= 30]

    hr_vals = [r["heart_rate_bpm"] for r in window if r.get("heart_rate_bpm")]
    cad_vals = [r["cadence_rpm"] for r in window if r.get("cadence_rpm") and r["cadence_rpm"] > 20]
    elev_vals = [r["elevation_m"] for r in window if r.get("elevation_m")]

    return {
        "power_peak_w": round(peak_row.get("power_w", 0)),
        "elapsed_min_at_peak": round((peak_row.get("elapsed_s", 0)) / 60, 1),
        "hr_at_peak": round(mean(hr_vals)) if hr_vals else None,
        "cadence_at_peak": round(mean(cad_vals)) if cad_vals else None,
        "elevation_at_peak": round(mean(elev_vals)) if elev_vals else None,
        "interpretation": (
            f"Pico {round(peak_row.get('power_w', 0))}W en min {(peak_row.get('elapsed_s', 0))/60:.1f} "
            f"— FC ~{round(mean(hr_vals)) if hr_vals else '?'} bpm, "
            f"cadencia ~{round(mean(cad_vals)) if cad_vals else '?'} rpm"
        ),
    }


# ─── 7. Mejor vs peor ascenso ─────────────────────────────────────────────

def _compute_best_vs_worst_climb(rows: list[dict], climbs: list[dict]) -> dict | None:
    if not climbs or len(climbs) < 2:
        return None

    valid_climbs = [c for c in climbs if c.get("vam") and c.get("vam") > 0]
    if len(valid_climbs) < 2:
        return None

    best = max(valid_climbs, key=lambda c: c.get("vam", 0))
    worst = min(valid_climbs, key=lambda c: c.get("vam", 0))

    power_gap = None
    if best.get("avg_power") and worst.get("avg_power") and worst["avg_power"] > 0:
        power_gap = round((best["avg_power"] - worst["avg_power"]) / worst["avg_power"] * 100, 1)

    vam_gap = round((best["vam"] - worst["vam"]) / worst["vam"] * 100, 1) if worst["vam"] > 0 else None

    return {
        "best_climb_index": climbs.index(best),
        "worst_climb_index": climbs.index(worst),
        "best_vam": round(best["vam"]),
        "worst_vam": round(worst["vam"]),
        "vam_gap_pct": vam_gap,
        "best_avg_power": best.get("avg_power"),
        "worst_avg_power": worst.get("avg_power"),
        "power_gap_pct": power_gap,
        "best_avg_cadence": best.get("avg_cadence"),
        "worst_avg_cadence": worst.get("avg_cadence"),
        "interpretation": (
            f"Mejor ascenso: {round(best['vam'])} m/h (ascenso {climbs.index(best)+1}) "
            f"vs peor: {round(worst['vam'])} m/h (ascenso {climbs.index(worst)+1}) "
            f"— brecha de {vam_gap:+.0f}% en VAM"
        ),
    }


# ─── 8. Degradación segunda mitad ─────────────────────────────────────────

def _compute_second_half_degradation(rows: list[dict]) -> dict | None:
    valid = [r for r in rows if r.get("elapsed_s") is not None]
    if len(valid) < 20:
        return None

    mid = len(valid) // 2
    h1 = valid[:mid]
    h2 = valid[mid:]

    def safe_mean(lst, col, min_val=0):
        vals = [r[col] for r in lst if r.get(col) and r[col] > min_val]
        return mean(vals) if vals else None

    p1 = safe_mean(h1, "power_w", 50)
    p2 = safe_mean(h2, "power_w", 50)
    hr1 = safe_mean(h1, "heart_rate_bpm", 0)
    hr2 = safe_mean(h2, "heart_rate_bpm", 0)
    cad1 = safe_mean(h1, "cadence_rpm", 20)
    cad2 = safe_mean(h2, "cadence_rpm", 20)
    sta1 = safe_mean(h1, "available_stamina", 0)
    sta2 = safe_mean(h2, "available_stamina", 0)

    def delta(a, b):
        if a and b and a > 0:
            return round((b - a) / a * 100, 1)
        return None

    power_delta = delta(p1, p2)
    hr_delta = delta(hr1, hr2)
    cad_delta = delta(cad1, cad2)
    sta_delta = delta(sta1, sta2)

    # Score de degradación (0 = sin degradación, 100 = colapso total)
    score = 0
    if power_delta and power_delta < 0:
        score += min(40, abs(power_delta) * 2)
    if hr_delta and hr_delta > 0:
        score += min(30, hr_delta * 2)
    if cad_delta and cad_delta < 0:
        score += min(30, abs(cad_delta) * 2)

    return {
        "power_delta_pct": power_delta,
        "hr_delta_pct": hr_delta,
        "cadence_delta_pct": cad_delta,
        "stamina_delta_pct": sta_delta,
        "degradation_score": round(score),
        "interpretation": (
            f"Segunda mitad: potencia {power_delta:+.1f}%, FC {hr_delta:+.1f}%, "
            f"cadencia {cad_delta:+.1f}%"
            if all(v is not None for v in [power_delta, hr_delta, cad_delta])
            else "Datos insuficientes para comparar mitades"
        ),
    }


# ─── Motor principal ──────────────────────────────────────────────────────

def run_series_insights(csv_path: str, analysis_path: str) -> dict:
    rows = _load_csv(csv_path)
    if not rows:
        return {"error": "empty_csv", "insights": {}}

    analysis = {}
    if os.path.exists(analysis_path):
        with open(analysis_path, encoding="utf-8") as f:
            analysis = json.load(f)

    climbs = analysis.get("climbs", [])
    garmin = analysis.get("garmin_summary", {})

    insights = {}

    r = _compute_cardiac_decoupling(rows)
    if r: insights["cardiac_decoupling"] = r

    r = _compute_stamina_depletion(rows)
    if r: insights["stamina_depletion"] = r

    r = _compute_cadence_fatigue_per_climb(rows, climbs)
    if r: insights["cadence_fatigue_per_climb"] = r

    r = _compute_performance_condition_trend(rows)
    if r: insights["performance_condition_trend"] = r

    r = _compute_wbpm_efficiency_segments(rows)
    if r: insights["wbpm_efficiency_segments"] = r

    r = _compute_peak_power_context(rows)
    if r: insights["peak_power_context"] = r

    r = _compute_best_vs_worst_climb(rows, climbs)
    if r: insights["best_vs_worst_climb"] = r

    r = _compute_second_half_degradation(rows)
    if r: insights["second_half_degradation"] = r

    return {
        "generated_at": datetime.now().isoformat(),
        "activity_id": garmin.get("activity_id"),
        "total_rows": len(rows),
        "insights": insights,
    }


def save_series_insights(analysis_path: str, insights: dict) -> str:
    folder = os.path.dirname(analysis_path)
    out_path = os.path.join(folder, "series_insights.json")
    os.makedirs(folder, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)
    return out_path


# ─── CLI (backfill) ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Series Insights Engine")
    parser.add_argument("--csv", type=str, help="Ruta al activity_series_clean.csv")
    parser.add_argument("--analysis", type=str, help="Ruta al activity_analysis.json")
    parser.add_argument("--user_dir", type=str, default=None,
                        help="Procesar todas las actividades de un usuario")
    args = parser.parse_args()

    if args.user_dir:
        # Backfill mode: process all activities for a user
        act_dir = os.path.join(args.user_dir, "activities")
        if not os.path.exists(act_dir):
            print(f"No se encontró directorio de actividades: {act_dir}")
        else:
            processed = 0
            for act_id in os.listdir(act_dir):
                act_folder = os.path.join(act_dir, act_id)
                csv_p = os.path.join(act_folder, "activity_series_clean.csv")
                ana_p = os.path.join(act_folder, "activity_analysis.json")
                if os.path.exists(csv_p) and os.path.exists(ana_p):
                    result = run_series_insights(csv_p, ana_p)
                    out = save_series_insights(ana_p, result)
                    n = len(result.get("insights", {}))
                    print(f"  [OK] {act_id} — {n} insights → {out}")
                    processed += 1
            print(f"\nBackfill completo: {processed} actividades procesadas")
    elif args.csv and args.analysis:
        result = run_series_insights(args.csv, args.analysis)
        out = save_series_insights(args.analysis, result)
        print(f"Insights generados: {len(result.get('insights', {}))} → {out}")
        for k, v in result.get("insights", {}).items():
            interp = v.get("interpretation", "") if isinstance(v, dict) else ""
            print(f"  {k}: {interp}")
    else:
        print("Usa --csv + --analysis o --user_dir")
