"""
ftp_estimator.py
================
Estima el FTP del usuario desde actividades reales sin necesitar test formal.

Tres modelos en orden de prioridad:
  1. Potencia Crítica (CP) — regresión lineal sobre curva de potencia
  2. HR-Potencia Drift     — identifica umbral por decoupling cardíaco
  3. Fallback Simple       — mejor potencia N-min × factor empírico

Fuente de datos:
  - power_profile en activity_analysis.json (ya calculado por activity_analyzer.py)
  - activity_series_clean.csv para modelo HR-drift (series brutas)

Guarda:
  performance_intelligence/ftp_estimate.json

Uso:
    python ftp_estimator.py
    python ftp_estimator.py --user_dir data/users/TU_USER
"""

import json
import os
import csv
import argparse
import math
from datetime import date, datetime
from typing import Optional
import numpy as np


# ─── Constantes ──────────────────────────────────────────────────────────────

# Mapeo nombre → segundos (del power_profile de activity_analysis.json)
DURATION_KEYS = {
    "1min":  60,
    "3min":  180,
    "5min":  300,
    "8min":  480,
    "10min": 600,
    "20min": 1200,
    "30min": 1800,
    "60min": 3600,
}

# Duraciones usadas para regresión CP (mínimo necesario para FTP válido)
CP_DURATIONS = [180, 300, 600, 1200]  # 3min, 5min, 10min, 20min
CP_DURATIONS_OPTIONAL = [1800, 3600]  # 30min, 60min (se usan si están disponibles)

# Factor de corrección CP → FTP (empírico para ciclismo MTB/XC)
CP_CORRECTION = 0.97

# Potencia mínima para considerar "pedaleando"
MIN_PEDALING_POWER = 20.0


# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_json(path: str) -> dict | list | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_mean(vals: list) -> Optional[float]:
    v = [x for x in vals if x is not None and not math.isnan(float(x))]
    return sum(v) / len(v) if v else None


def parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def load_csv_series(csv_path: str) -> list[dict]:
    """Carga la serie temporal de una actividad desde el CSV."""
    if not os.path.exists(csv_path):
        return []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                t = row.get("elapsed_s", "")
                pw = row.get("power_w", "")
                hr = row.get("heart_rate_bpm", "")
                if not t:
                    continue
                try:
                    rows.append({
                        "t": float(t),
                        "power": float(pw) if pw and pw not in ("nan", "") else None,
                        "hr": float(hr) if hr and hr not in ("nan", "") else None,
                    })
                except ValueError:
                    continue
        return rows
    except Exception:
        return []


def iqr_filter(values: list[float], multiplier: float = 1.5) -> list[float]:
    """Elimina outliers con método IQR."""
    if len(values) < 4:
        return values
    arr = sorted(values)
    n = len(arr)
    q1 = arr[n // 4]
    q3 = arr[3 * n // 4]
    iqr = q3 - q1
    lo = q1 - multiplier * iqr
    hi = q3 + multiplier * iqr
    return [v for v in values if lo <= v <= hi]


def r_squared(y_actual: np.ndarray, y_predicted: np.ndarray) -> float:
    """Calcula R² de un ajuste."""
    ss_res = np.sum((y_actual - y_predicted) ** 2)
    ss_tot = np.sum((y_actual - np.mean(y_actual)) ** 2)
    if ss_tot == 0:
        return 1.0
    return float(1 - ss_res / ss_tot)


# ─── Carga de actividades ────────────────────────────────────────────────────

def load_power_activities(user_dir: str) -> list[dict]:
    """
    Carga todas las actividades que tienen potencia real medida.
    Usa power_profile de activity_analysis.json (ya calculado).
    """
    index_path = os.path.join(user_dir, "activity_index.json")
    index_raw = load_json(index_path) or {}
    activities = index_raw.get("activities", []) if isinstance(index_raw, dict) else index_raw

    power_activities = []
    for act in activities:
        analysis_path = act.get("analysis_file", "").replace("\\", "/")
        if not os.path.exists(analysis_path):
            continue
        analysis = load_json(analysis_path)
        if not analysis:
            continue
        gs = analysis.get("garmin_summary", {}) or {}
        avg_power = gs.get("avg_power")
        # Solo actividades con sensor de potencia (avg_power > 0)
        if not avg_power or avg_power <= 0:
            continue
        pp = analysis.get("power_profile", {}) or {}
        if not pp:
            continue
        # Verificar que hay potencias razonables en duraciones largas
        p20 = (pp.get("20min") or {}).get("avg_power", 0) or 0
        if p20 < 50:  # descarta actividades de calidad muy baja
            continue

        act_id = act.get("activity_id")
        csv_path = os.path.join(
            user_dir, "activities", str(act_id), "activity_series_clean.csv"
        ).replace("\\", "/")

        power_activities.append({
            "activity_id": act_id,
            "date": act.get("date", "")[:10],
            "name": act.get("name", ""),
            "moving_minutes": gs.get("moving_minutes", 0),
            "avg_power": avg_power,
            "garmin_np": gs.get("garmin_np"),
            "power_profile": pp,
            "csv_path": csv_path,
        })

    # Ordenar por fecha
    power_activities.sort(key=lambda a: a["date"])
    return power_activities


# ─── MODELO 1: Potencia Crítica (CP) ─────────────────────────────────────────

def extract_power_curve(activities: list[dict]) -> dict[int, float]:
    """
    Consolida la mejor potencia histórica para cada duración
    entre todas las actividades.
    Devuelve {duration_seconds: best_watts}.
    """
    best: dict[int, float] = {}
    for act in activities:
        pp = act["power_profile"]
        for key, dur_s in DURATION_KEYS.items():
            entry = pp.get(key) or {}
            pw = entry.get("avg_power")
            if pw and pw > MIN_PEDALING_POWER:
                if dur_s not in best or pw > best[dur_s]:
                    best[dur_s] = round(pw, 1)
    return best


def fit_critical_power(power_curve: dict[int, float]) -> dict | None:
    """
    Ajuste lineal: W_total = W_prime + CP × T
    donde W_total = avg_power × T

    Solo usa duraciones en CP_DURATIONS (3–20 min) como base,
    añade 30/60 min si están disponibles.
    """
    # Construir puntos de regresión
    use_durations = [d for d in CP_DURATIONS if d in power_curve]
    for d in CP_DURATIONS_OPTIONAL:
        if d in power_curve:
            use_durations.append(d)

    if len(use_durations) < 3:
        return None  # insuficientes puntos para regresión

    X = np.array(use_durations, dtype=float)
    Y = np.array([power_curve[d] * d for d in use_durations], dtype=float)

    # Regresión lineal: Y = W_prime + CP * X
    coeffs = np.polyfit(X, Y, 1)
    cp_watts = float(coeffs[0])
    w_prime = float(coeffs[1])

    # R²
    y_pred = np.polyval(coeffs, X)
    r2 = r_squared(Y, y_pred)

    if cp_watts <= 0:
        return None  # pendiente negativa = datos insuficientes/inconsistentes

    ftp_from_cp = round(cp_watts * CP_CORRECTION, 1)

    return {
        "cp_watts": round(cp_watts, 1),
        "w_prime_joules": round(w_prime, 0),
        "ftp_from_cp": ftp_from_cp,
        "r_squared": round(r2, 4),
        "durations_used": use_durations,
        "n_points": len(use_durations),
    }


def run_cp_model(activities: list[dict]) -> dict:
    """Ejecuta el modelo de Potencia Crítica completo."""
    power_curve = extract_power_curve(activities)
    cp_result = fit_critical_power(power_curve)

    # Formatear curva de potencia con etiquetas legibles
    label_map = {60: "60s", 180: "3min", 300: "5min", 480: "8min",
                 600: "10min", 1200: "20min", 1800: "30min", 3600: "60min"}
    curve_labeled = {
        label_map.get(d, f"{d}s"): round(w, 0)
        for d, w in sorted(power_curve.items())
    }

    # Confianza según número de actividades
    n = len(activities)
    if n >= 10:
        confidence = "high"
        margin = 5
    elif n >= 5:
        confidence = "medium"
        margin = 10
    else:
        confidence = "low"
        margin = 15

    result = {
        "power_curve": curve_labeled,
        "activities_used": n,
        "confidence": confidence,
        "margin_watts": margin,
    }
    if cp_result:
        result.update(cp_result)

    return result


# ─── MODELO 2: HR-Potencia Drift ─────────────────────────────────────────────

def find_stable_segments(rows: list[dict], min_duration_s: float = 240) -> list[dict]:
    """
    Identifica segmentos de esfuerzo estable en la serie temporal.

    Criterios:
    - Duración mínima: 240s (4 min)
    - Potencia media del segmento > 100W
    - Variación de potencia ≤ ±15% de la media (MTB es variable — relajamos a 15%)
    - Sin pausas largas (gaps > 5s se cortan el segmento)
    """
    if len(rows) < 30:
        return []

    segments = []
    # Usar ventana deslizante de 240+ segundos
    n = len(rows)

    i = 0
    while i < n:
        # Buscar el final de un segmento a partir de i
        # Un segmento termina cuando hay una pausa > 5s o potencia < 20W por > 5s
        seg_start = i
        seg_rows = []

        j = i
        while j < n:
            row = rows[j]
            pw = row.get("power")
            t = row.get("t")

            # Cortar por pausa larga
            if j > 0:
                prev_t = rows[j - 1].get("t", 0)
                gap = t - prev_t if t and prev_t else 0
                if gap > 5:
                    break

            # Cortar por potencia cero sostenida (coasting)
            if pw is None or pw < MIN_PEDALING_POWER:
                # Permitir hasta 3 segundos de coasting
                if len(seg_rows) > 0:
                    coasting_count = sum(
                        1 for r in seg_rows[-3:]
                        if (r.get("power") or 0) < MIN_PEDALING_POWER
                    )
                    if coasting_count >= 2:
                        break
                j += 1
                continue

            seg_rows.append(row)
            j += 1

        # Evaluar el segmento
        if len(seg_rows) < 10:
            i = j + 1
            continue

        # Duración del segmento (usar elapsed_s)
        t_start = seg_rows[0].get("t", 0)
        t_end = seg_rows[-1].get("t", 0)
        duration_s = t_end - t_start

        if duration_s < min_duration_s:
            i = j + 1
            continue

        # Potencia y HR del segmento
        powers = [r["power"] for r in seg_rows if r.get("power") and r["power"] > MIN_PEDALING_POWER]
        hrs = [r["hr"] for r in seg_rows if r.get("hr") and r["hr"] > 40]

        if not powers or len(hrs) < 10:
            i = j + 1
            continue

        power_avg = sum(powers) / len(powers)

        if power_avg < 100:
            i = j + 1
            continue

        # Variabilidad de potencia (relajada para MTB)
        power_std = (sum((p - power_avg) ** 2 for p in powers) / len(powers)) ** 0.5
        cv = power_std / power_avg if power_avg > 0 else 1.0

        if cv > 0.50:  # >50% CV es demasiado variable para HR drift
            i = j + 1
            continue

        # HR promedio primeros y últimos 2 minutos
        window_s = min(120, duration_s * 0.3)  # adaptativo si el segmento es corto
        hrs_first = [
            r["hr"] for r in seg_rows
            if r.get("hr") and r["hr"] > 40 and r["t"] - t_start <= window_s
        ]
        hrs_last = [
            r["hr"] for r in seg_rows
            if r.get("hr") and r["hr"] > 40 and t_end - r["t"] <= window_s
        ]

        if not hrs_first or not hrs_last or len(hrs_first) < 3 or len(hrs_last) < 3:
            i = j + 1
            continue

        hr_first = sum(hrs_first) / len(hrs_first)
        hr_last = sum(hrs_last) / len(hrs_last)
        cardiac_drift = (hr_last - hr_first) / hr_first

        # Clasificar por drift
        if cardiac_drift < 0.03:
            zone = "sub_threshold"
        elif cardiac_drift <= 0.06:
            zone = "threshold"
        else:
            zone = "supra_threshold"

        segments.append({
            "t_start": round(t_start, 1),
            "t_end": round(t_end, 1),
            "duration_s": round(duration_s, 1),
            "power_avg": round(power_avg, 1),
            "hr_first": round(hr_first, 1),
            "hr_last": round(hr_last, 1),
            "cardiac_drift": round(cardiac_drift, 4),
            "power_cv": round(cv, 3),
            "zone": zone,
        })

        i = j + 1

    return segments


def estimate_ftp_from_hr_drift(segments: list[dict]) -> dict:
    """
    Estima FTP a partir de la zona de umbral en los segmentos.

    - Segmentos 'threshold': promedio ponderado por duración
    - Si no hay threshold: interpolar entre sub y supra
    """
    threshold_segs = [s for s in segments if s["zone"] == "threshold"]
    sub_segs = [s for s in segments if s["zone"] == "sub_threshold"]
    supra_segs = [s for s in segments if s["zone"] == "supra_threshold"]

    ftp_hr = None
    method = "none"

    if threshold_segs:
        # Promedio ponderado por duración
        total_dur = sum(s["duration_s"] for s in threshold_segs)
        ftp_hr = sum(s["power_avg"] * s["duration_s"] for s in threshold_segs) / total_dur
        method = "threshold_weighted_mean"

    elif sub_segs and supra_segs:
        # Interpolar: tomar el más alto de sub y el más bajo de supra
        max_sub = max(sub_segs, key=lambda s: s["power_avg"])
        min_supra = min(supra_segs, key=lambda s: s["power_avg"])
        # Umbral estimado a mitad del gap
        ftp_hr = (max_sub["power_avg"] + min_supra["power_avg"]) / 2
        method = "interpolated_sub_supra"

    elif sub_segs:
        # Solo sub-threshold: FTP estimado como máximo sub * 1.08
        max_sub = max(sub_segs, key=lambda s: s["power_avg"])
        ftp_hr = max_sub["power_avg"] * 1.08
        method = "upper_bound_from_sub_threshold"

    avg_drift = None
    if threshold_segs:
        avg_drift = sum(s["cardiac_drift"] for s in threshold_segs) / len(threshold_segs)

    return {
        "ftp_from_hr_drift": round(ftp_hr, 1) if ftp_hr else None,
        "method": method,
        "segments_analyzed": len(segments),
        "threshold_segments": len(threshold_segs),
        "sub_threshold_segments": len(sub_segs),
        "supra_threshold_segments": len(supra_segs),
        "avg_drift_at_threshold": round(avg_drift, 4) if avg_drift else None,
    }


def run_hr_drift_model(activities: list[dict]) -> dict:
    """Ejecuta el modelo HR-drift sobre todas las actividades con potencia."""
    all_segments = []

    for act in activities:
        csv_path = act.get("csv_path", "")
        if not csv_path or not os.path.exists(csv_path):
            continue
        rows = load_csv_series(csv_path)
        if not rows:
            continue
        segs = find_stable_segments(rows)
        all_segments.extend(segs)

    return estimate_ftp_from_hr_drift(all_segments)


# ─── MODELO 3: Fallback Simple ───────────────────────────────────────────────

def run_fallback_model(power_curve: dict[int, float]) -> dict:
    """
    Fallback: mejor potencia en ventana × factor.
    Usa la curva de potencia ya calculada.
    """
    ftp = None
    source = None

    if 1200 in power_curve and power_curve[1200] > 0:
        ftp = round(power_curve[1200] * 0.95, 1)
        source = "best_20min × 0.95"
    elif 3600 in power_curve and power_curve[3600] > 0:
        ftp = round(power_curve[3600] * 1.0, 1)
        source = "best_60min × 1.0"
    elif 600 in power_curve and power_curve[600] > 0:
        ftp = round(power_curve[600] * 0.85, 1)
        source = "best_10min × 0.85"
    elif 300 in power_curve and power_curve[300] > 0:
        ftp = round(power_curve[300] * 0.75, 1)
        source = "best_5min × 0.75"

    return {
        "ftp_from_fallback": ftp,
        "source": source,
    }


# ─── Consenso ────────────────────────────────────────────────────────────────

def build_consensus(cp_model: dict, hr_model: dict, fallback: dict) -> dict:
    """Combina las estimaciones de los tres modelos en un consenso."""
    estimates = {}

    cp_ftp = cp_model.get("ftp_from_cp")
    hr_ftp = hr_model.get("ftp_from_hr_drift")
    fb_ftp = fallback.get("ftp_from_fallback")

    if cp_ftp and cp_ftp > 0:
        estimates["cp"] = cp_ftp
    if hr_ftp and hr_ftp > 0:
        estimates["hr_drift"] = hr_ftp
    if fb_ftp and fb_ftp > 0:
        estimates["fallback"] = fb_ftp

    if not estimates:
        return {"final_estimate": None, "agreement": "insufficient_data"}

    # Pesos por modelo: CP > HR-drift > fallback
    weights = {"cp": 0.55, "hr_drift": 0.30, "fallback": 0.15}

    total_weight = sum(weights[k] for k in estimates)
    final = sum(estimates[k] * weights[k] for k in estimates) / total_weight
    final = round(final, 1)

    # Acuerdo entre modelos
    vals = list(estimates.values())
    if len(vals) >= 2:
        max_diff = max(vals) - min(vals)
        diff_pct = (max_diff / final) * 100 if final > 0 else 100
        if diff_pct < 5:
            agreement = "high"
        elif diff_pct < 10:
            agreement = "moderate"
        else:
            agreement = "low"
    else:
        agreement = "single_model"

    result = {
        "final_estimate": final,
        "agreement": agreement,
        "models_used": list(estimates.keys()),
    }
    if "cp" in estimates:
        result["cp_estimate"] = estimates["cp"]
    if "hr_drift" in estimates:
        result["hr_estimate"] = estimates["hr_drift"]
    if len(estimates) >= 2:
        result["difference_watts"] = round(max(estimates.values()) - min(estimates.values()), 1)

    return result


# ─── Motor principal ──────────────────────────────────────────────────────────

def estimate_ftp(user_dir: str) -> dict:
    """
    Motor principal. Carga las actividades, corre los tres modelos
    y guarda ftp_estimate.json.
    """
    # Cargar actividades con potencia
    activities = load_power_activities(user_dir)
    n_power = len(activities)

    if n_power == 0:
        print("  [FTP Estimator] Sin actividades con sensor de potencia.")
        return {}

    # ── Modelo 1: CP ──
    cp_model = run_cp_model(activities)
    power_curve = extract_power_curve(activities)

    # ── Modelo 2: HR Drift ──
    hr_model = run_hr_drift_model(activities)

    # ── Modelo 3: Fallback ──
    fallback = run_fallback_model(power_curve)

    # ── Consenso ──
    consensus = build_consensus(cp_model, hr_model, fallback)
    ftp_final = consensus.get("final_estimate")

    # Confianza global
    n_acts = cp_model.get("activities_used", 0)
    cp_confidence = cp_model.get("confidence", "low")
    r2 = cp_model.get("r_squared", 0)
    model_agreement = consensus.get("agreement", "low")

    if cp_confidence == "high" and r2 > 0.90 and model_agreement in ("high", "moderate"):
        overall_confidence = "high"
        margin = 5
    elif cp_confidence in ("medium", "high") and r2 > 0.80:
        overall_confidence = "medium"
        margin = 10
    else:
        overall_confidence = "low"
        margin = 15

    # W/kg si hay peso en el perfil
    profile = load_json(os.path.join(user_dir, "profile.json")) or {}
    weight_kg = profile.get("weight_kg") or profile.get("weight")
    ftp_wkg = round(ftp_final / weight_kg, 2) if ftp_final and weight_kg else None

    # Comparación con FTP declarado en perfil
    declared_ftp = profile.get("ftp")
    notes = []
    if declared_ftp and ftp_final:
        diff = abs(ftp_final - declared_ftp)
        if diff > 20:
            direction = "mayor" if ftp_final > declared_ftp else "menor"
            notes.append(
                f"Estimación es {round(diff)}W {direction} que tu FTP declarado ({declared_ftp}W). "
                "Considera actualizar tu perfil."
            )
    if n_acts < 5:
        notes.append(
            "Estimación basada en pocas actividades. Aumenta a 5+ sesiones con potenciómetro para mayor precisión."
        )
    notes.append(
        "Estimación basada en esfuerzos naturales en MTB. Para mayor precisión, hacer test de 20min en llano."
    )

    # Método usado en texto legible
    methods_used = consensus.get("models_used", [])
    method_labels = {"cp": "potencia_critica", "hr_drift": "hr_drift", "fallback": "fallback_simple"}
    method_str = " + ".join(method_labels.get(m, m) for m in methods_used)

    # Fechas
    today_str = date.today().isoformat()
    # Próxima actualización: 15 días o 5 actividades nuevas
    next_update = "en 15 días o después de 5 actividades nuevas con potenciómetro"

    result = {
        "ftp_estimated": ftp_final,
        "ftp_confidence": overall_confidence,
        "ftp_margin_watts": margin,
        "ftp_range": [
            round(ftp_final - margin, 0) if ftp_final else None,
            round(ftp_final + margin, 0) if ftp_final else None,
        ],
        "ftp_wkg": ftp_wkg,
        "method_used": method_str,

        "critical_power_model": {
            "cp_watts": cp_model.get("cp_watts"),
            "w_prime_joules": cp_model.get("w_prime_joules"),
            "ftp_from_cp": cp_model.get("ftp_from_cp"),
            "activities_used": n_acts,
            "power_curve": cp_model.get("power_curve", {}),
            "r_squared": cp_model.get("r_squared"),
            "durations_used_s": cp_model.get("durations_used"),
        },

        "hr_drift_model": {
            "ftp_from_hr_drift": hr_model.get("ftp_from_hr_drift"),
            "method": hr_model.get("method"),
            "segments_analyzed": hr_model.get("segments_analyzed", 0),
            "threshold_segments": hr_model.get("threshold_segments", 0),
            "avg_drift_at_threshold": hr_model.get("avg_drift_at_threshold"),
        },

        "fallback_model": {
            "ftp_from_fallback": fallback.get("ftp_from_fallback"),
            "source": fallback.get("source"),
        },

        "consensus": consensus,

        "confidence_factors": {
            "activities_with_power": n_acts,
            "total_segments_analyzed": hr_model.get("segments_analyzed", 0),
            "power_curve_r_squared": cp_model.get("r_squared"),
            "model_agreement": model_agreement,
            "cp_confidence": cp_confidence,
        },

        "notes": " | ".join(notes) if notes else None,
        "generated_at": today_str,
        "next_update": next_update,
    }

    # Guardar
    output_path = os.path.join(
        user_dir, "performance_intelligence", "ftp_estimate.json"
    ).replace("\\", "/")
    save_json(output_path, result)

    # ── Resumen en consola ──
    curve = cp_model.get("power_curve", {})
    curve_str = "  ".join(f"{k}={v:.0f}W" for k, v in list(curve.items())[:5])
    cp_w = cp_model.get("cp_watts", "N/D")
    hr_w = hr_model.get("ftp_from_hr_drift", "N/D")
    r2_str = f"{r2:.3f}" if r2 else "N/D"

    margin_str = f"+/-{margin}W"
    range_str = f"[{ftp_final - margin:.0f}-{ftp_final + margin:.0f}W]" if ftp_final else ""

    print(f"\n{'='*60}")
    print(f"FTP ESTIMADO: {ftp_final or 'N/D'}W {margin_str} {range_str}")
    if ftp_wkg:
        print(f"W/kg:         {ftp_wkg}")
    print(f"Confianza:    {overall_confidence}")
    print(f"Metodo:       {method_str}")
    print(f"CP model:     {cp_w}W (R2={r2_str}) -> FTP={cp_model.get('ftp_from_cp','N/D')}W")
    print(f"HR-drift:     {hr_w}W ({hr_model.get('threshold_segments',0)} segmentos umbral)")
    print(f"Actividades:  {n_acts} con potenciometro")
    if curve_str:
        print(f"Curva:        {curve_str}")
    print(f"Guardado en:  {output_path}")
    print(f"{'='*60}\n")

    # Always update athlete_baseline.json when called programmatically
    baseline_path = os.path.join(user_dir, "performance_intelligence", "athlete_baseline.json")
    if os.path.exists(baseline_path):
        update_baseline_with_ftp(user_dir, result)

    return result


# ─── Integración con profile_intelligence ────────────────────────────────────

def update_baseline_with_ftp(user_dir: str, ftp_result: dict) -> None:
    """
    Actualiza athlete_baseline.json con la sección ftp_model.
    """
    baseline_path = os.path.join(
        user_dir, "performance_intelligence", "athlete_baseline.json"
    ).replace("\\", "/")

    baseline = load_json(baseline_path)
    if not baseline or not isinstance(baseline, dict):
        return

    baseline["ftp_model"] = {
        "ftp_estimated": ftp_result.get("ftp_estimated"),
        "ftp_confidence": ftp_result.get("ftp_confidence"),
        "ftp_margin_watts": ftp_result.get("ftp_margin_watts"),
        "ftp_wkg": ftp_result.get("ftp_wkg"),
        "method_used": ftp_result.get("method_used"),
        "cp_watts": ftp_result.get("critical_power_model", {}).get("cp_watts"),
        "w_prime_joules": ftp_result.get("critical_power_model", {}).get("w_prime_joules"),
        "r_squared": ftp_result.get("critical_power_model", {}).get("r_squared"),
        "updated_at": ftp_result.get("generated_at"),
    }

    # Actualizar también athlete_context_string con el FTP estimado
    ftp_val = ftp_result.get("ftp_estimated")
    margin = ftp_result.get("ftp_margin_watts", 10)
    confidence = ftp_result.get("ftp_confidence", "media")
    method = ftp_result.get("method_used", "")
    if ftp_val:
        ftp_ctx = f"FTP estimado: {ftp_val}W +/-{margin}W (confianza {confidence}, metodo: {method})"
        old_ctx = baseline.get("athlete_context_string", "")
        # Reemplazar o añadir la sección FTP
        if "FTP" in old_ctx:
            import re
            old_ctx = re.sub(r"FTP[^\.]*\.", ftp_ctx + ".", old_ctx, count=1)
        else:
            old_ctx = old_ctx.rstrip(".") + f". {ftp_ctx}."
        baseline["athlete_context_string"] = old_ctx

    save_json(baseline_path, baseline)
    print(f"  [baseline] Actualizado con ftp_model -> {baseline_path}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FTP Estimator — motor de potencia crítica + HR drift")
    parser.add_argument("--user_dir", type=str, default=None)
    parser.add_argument("--email", type=str, default=None)
    parser.add_argument("--update_baseline", action="store_true", default=True,
                        help="Actualizar athlete_baseline.json con los resultados (default: True)")
    args = parser.parse_args()

    if args.user_dir:
        user_dir = args.user_dir
    elif args.email:
        clean = args.email.strip().lower().replace("@", "_at_").replace(".", "_")
        user_dir = os.path.join("data", "users", clean)
    else:
        user_dir = os.path.join("data", "users", "abelgcanofuentes_at_hotmail_com")

    if not os.path.exists(user_dir):
        print(f"ERROR: Directorio no encontrado: {user_dir}")
        exit(1)

    print(f"Estimando FTP para: {user_dir}")
    result = estimate_ftp(user_dir)

    if result and args.update_baseline:
        update_baseline_with_ftp(user_dir, result)
