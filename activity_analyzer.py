from detect_climbs import detect_climbs
from fatigue_analysis_v2 import build_fatigue_report
from athlete_profile_engine_v2 import build_athlete_profile_v2
from metabolic_index import add_msi_to_rows, summarize_msi
from performance_scores import build_performance_scores

import csv
import os
from statistics import mean

POWER_PROFILE_DURATIONS = [1, 5, 10, 30, 60, 180, 300, 480, 600, 1200, 1800, 3600]

# Umbrales de esfuerzo relativos al FTP del usuario
# SPRINT: 3x FTP, VO2: 1.20x FTP, THRESHOLD: 1.0x FTP
EFFORT_RATIOS = [
    {"type": "SPRINT",    "window": 5,   "ratio": 3.00},
    {"type": "VO2",       "window": 60,  "ratio": 1.20},
    {"type": "THRESHOLD", "window": 600, "ratio": 1.00},
]


def to_float(v):
    try:
        return float(v)
    except Exception:
        return None


def read_activity_series(filepath):
    rows = []
    if not os.path.exists(filepath):
        return rows

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "timestamp": r.get("timestamp"),
                "elapsed_s": to_float(r.get("elapsed_s")),
                "distance_m": to_float(r.get("distance_m")),
                "elevation_m": to_float(r.get("elevation_m")),
                "speed_mps": to_float(r.get("speed_mps")),
                "cadence_rpm": to_float(r.get("cadence_rpm")),
                "heart_rate_bpm": to_float(r.get("heart_rate_bpm")),
                "power_w": to_float(r.get("power_w")),
                "respiration_brpm": to_float(r.get("respiration_brpm")),
                "vertical_speed_mps": to_float(r.get("vertical_speed_mps")),
                "grit": to_float(r.get("grit")),
                "available_stamina": to_float(r.get("available_stamina")),
                "potential_stamina": to_float(r.get("potential_stamina")),
                "performance_condition": to_float(r.get("performance_condition")),
            })
    return rows


def average(values):
    valid = [v for v in values if v is not None]
    return mean(valid) if valid else None


def max_valid(values):
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def min_valid(values):
    valid = [v for v in values if v is not None]
    return min(valid) if valid else None


def sum_positive_deltas(values):
    total = 0.0
    for i in range(1, len(values)):
        a = values[i - 1]
        b = values[i]
        if a is not None and b is not None:
            d = b - a
            if d > 0:
                total += d
    return total


def compute_np(power_values, elapsed_s=None):
    """
    Normalized Power usando ventanas de 30 segundos reales.
    - Si se proveen timestamps (elapsed_s), construye ventanas de exactamente 30s.
    - Los nulos se ignoran (no se convierten a 0) para no inflar el suavizado.
    - Requiere al menos 30 segundos de datos con potencia válida.
    """
    if elapsed_s is not None and len(elapsed_s) == len(power_values):
        # --- Método correcto: rolling 30s basado en tiempo real ---
        # Primero interpolar a 1 sample/segundo para consistencia con Garmin
        t_start = elapsed_s[0] if elapsed_s[0] is not None else 0
        t_end   = elapsed_s[-1] if elapsed_s[-1] is not None else 0
        total_s = int(t_end - t_start)
        if total_s < 30:
            return None

        # Interpolar potencia a grilla de 1s
        from bisect import bisect_left
        valid_pairs = [
            (elapsed_s[i], power_values[i])
            for i in range(len(elapsed_s))
            if elapsed_s[i] is not None and power_values[i] is not None
        ]
        if len(valid_pairs) < 30:
            return None

        ts = [p[0] for p in valid_pairs]
        ps = [p[1] for p in valid_pairs]

        grid = []
        for t in range(int(ts[0]), int(ts[-1]) + 1):
            idx = bisect_left(ts, t)
            if idx == 0:
                grid.append(ps[0])
            elif idx >= len(ts):
                grid.append(ps[-1])
            else:
                # Interpolación lineal entre los dos puntos más cercanos
                t0, t1 = ts[idx - 1], ts[idx]
                p0, p1 = ps[idx - 1], ps[idx]
                frac = (t - t0) / (t1 - t0) if t1 != t0 else 0
                grid.append(p0 + frac * (p1 - p0))

        if len(grid) < 30:
            return None

        rolling_30 = []
        for i in range(len(grid) - 29):
            window = grid[i:i + 30]
            rolling_30.append(sum(window) / 30)

    else:
        # --- Fallback: asume 1 muestra/segundo, ignora nulos ---
        valid = [p for p in power_values if p is not None]
        if len(valid) < 30:
            return None
        # Reconstruir lista completa reemplazando None con interpolación simple
        filled = []
        for p in power_values:
            filled.append(p if p is not None else (filled[-1] if filled else 0))

        rolling_30 = []
        for i in range(len(filled) - 29):
            chunk = filled[i:i + 30]
            rolling_30.append(sum(chunk) / 30)

    if not rolling_30:
        return None

    avg_fourth = sum(x ** 4 for x in rolling_30) / len(rolling_30)
    return avg_fourth ** 0.25


def time_deltas(rows):
    deltas = []
    for i in range(len(rows)):
        if i == 0:
            deltas.append(0)
            continue

        t0 = rows[i - 1]["elapsed_s"]
        t1 = rows[i]["elapsed_s"]

        if t0 is None or t1 is None:
            deltas.append(0)
        else:
            dt = t1 - t0
            deltas.append(dt if dt >= 0 else 0)
    return deltas


def power_zone(power, ftp):
    if power is None or ftp is None or ftp <= 0:
        return None

    ratio = power / ftp

    if ratio < 0.55:
        return "Z1"
    elif ratio < 0.75:
        return "Z2"
    elif ratio < 0.90:
        return "Z3"
    elif ratio < 1.05:
        return "Z4"
    elif ratio < 1.20:
        return "Z5"
    elif ratio < 1.50:
        return "Z6"
    else:
        return "Z7"


def hr_zone(hr, max_hr):
    if hr is None or max_hr is None or max_hr <= 0:
        return None

    ratio = hr / max_hr

    if ratio < 0.60:
        return "Z1"
    elif ratio < 0.70:
        return "Z2"
    elif ratio < 0.80:
        return "Z3"
    elif ratio < 0.90:
        return "Z4"
    else:
        return "Z5"


def accumulate_zone_times(rows, deltas, zone_fn, value_key, ref_value):
    zone_times = {}
    for i, row in enumerate(rows):
        zone = zone_fn(row.get(value_key), ref_value)
        dt = deltas[i]

        if zone is None or dt <= 0:
            continue

        zone_times[zone] = zone_times.get(zone, 0) + dt

    return zone_times


def rolling_avg(series, window):
    avgs = []
    for i in range(len(series) - window + 1):
        chunk = series[i:i + window]
        if all(v is not None for v in chunk):
            avgs.append((i, sum(chunk) / window))
    return avgs


def detect_effort_windows(power, ftp):
    windows = []

    for effort in EFFORT_RATIOS:
        etype = effort["type"]
        window = effort["window"]
        threshold = effort["ratio"] * ftp

        for i, avg_val in rolling_avg(power, window):
            if avg_val > threshold:
                windows.append({
                    "start": i,
                    "end": i + window - 1,
                    "type": etype,
                    "window": window,
                    "trigger_avg_power": avg_val,
                })

    windows.sort(key=lambda x: (x["type"], x["start"]))
    return windows


def group_efforts(windows):
    grouped = []

    if not windows:
        return grouped

    current = windows[0].copy()
    current["trigger_values"] = [windows[0]["trigger_avg_power"]]

    for w in windows[1:]:
        same_type = w["type"] == current["type"]
        overlaps = w["start"] <= current["end"] + 1

        if same_type and overlaps:
            current["end"] = max(current["end"], w["end"])
            current["trigger_values"].append(w["trigger_avg_power"])
        else:
            grouped.append(current)
            current = w.copy()
            current["trigger_values"] = [w["trigger_avg_power"]]

    grouped.append(current)
    return grouped


def summarize_effort(rows, start, end, effort_type, trigger_values):
    segment = rows[start:end + 1]

    power = [r["power_w"] for r in segment if r["power_w"] is not None]
    hr = [r["heart_rate_bpm"] for r in segment if r["heart_rate_bpm"] is not None]
    elev = [r["elevation_m"] for r in segment if r["elevation_m"] is not None]

    start_time = rows[start]["elapsed_s"]
    end_time = rows[end]["elapsed_s"]

    duration_min = None
    if start_time is not None and end_time is not None:
        duration_min = (end_time - start_time) / 60

    elev_gain = 0.0
    for i in range(1, len(elev)):
        delta = elev[i] - elev[i - 1]
        if delta > 0:
            elev_gain += delta

    return {
        "type": effort_type,
        "start_min": round(start_time / 60, 2) if start_time is not None else None,
        "end_min": round(end_time / 60, 2) if end_time is not None else None,
        "duration_min": round(duration_min, 2) if duration_min is not None else None,
        "trigger_avg_power": round(max(trigger_values), 1) if trigger_values else None,
        "avg_power": round(average(power), 1) if power else None,
        "max_power": round(max(power), 1) if power else None,
        "avg_hr": round(average(hr), 1) if hr else None,
        "max_hr": round(max(hr), 1) if hr else None,
        "elevation_gain_m": round(elev_gain, 1),
    }


def build_efforts(rows, ftp):
    power = [r["power_w"] for r in rows]
    windows = detect_effort_windows(power, ftp)
    grouped = group_efforts(windows)

    efforts = []
    for g in grouped:
        efforts.append(
            summarize_effort(
                rows,
                g["start"],
                g["end"],
                g["type"],
                g["trigger_values"],
            )
        )

    return efforts


def best_window_by_real_time(rows, duration_s):
    best = None
    n = len(rows)

    for i in range(n):
        start_time = rows[i]["elapsed_s"]
        if start_time is None:
            continue

        power_vals = []
        hr_vals = []
        last_j = i

        for j in range(i, n):
            current_time = rows[j]["elapsed_s"]
            if current_time is None:
                continue

            elapsed = current_time - start_time
            # Solo incluir muestras dentro del window exacto
            if elapsed > duration_s:
                break

            p = rows[j]["power_w"]
            h = rows[j]["heart_rate_bpm"]
            if p is not None:
                power_vals.append(p)
            if h is not None:
                hr_vals.append(h)
            last_j = j

            if elapsed >= duration_s:
                break

        actual_elapsed = (rows[last_j]["elapsed_s"] or 0) - start_time
        if actual_elapsed < duration_s * 0.9:
            continue  # ventana incompleta (< 90% de la duración pedida)
        if not power_vals:
            continue

        avg_power = sum(power_vals) / len(power_vals)
        avg_hr = mean(hr_vals) if hr_vals else None
        candidate = {
            "start_idx": i,
            "end_idx": last_j,
            "avg_power": avg_power,
            "avg_hr": avg_hr,
            "real_duration_s": actual_elapsed,
        }
        if best is None or candidate["avg_power"] > best["avg_power"]:
            best = candidate

    return best


def format_duration_label(seconds):
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}min"


def build_power_profile(rows):
    result = {}

    for d in POWER_PROFILE_DURATIONS:
        best = best_window_by_real_time(rows, d)

        if best is None:
            result[format_duration_label(d)] = None
            continue

        start_time = rows[best["start_idx"]]["elapsed_s"]
        end_time = rows[best["end_idx"]]["elapsed_s"]

        result[format_duration_label(d)] = {
            "avg_power": round(best["avg_power"], 1),
            "avg_hr": round(best["avg_hr"], 1) if best["avg_hr"] is not None else None,
            "start_min": round(start_time / 60, 2) if start_time is not None else None,
            "end_min": round(end_time / 60, 2) if end_time is not None else None,
            "real_duration_s": round(best["real_duration_s"], 1),
        }

    return result


def build_derived_summary(rows, ftp):
    deltas = time_deltas(rows)

    powers = [r["power_w"] for r in rows]
    hrs = [r["heart_rate_bpm"] for r in rows]
    cadences = [r["cadence_rpm"] for r in rows]
    elevations = [r["elevation_m"] for r in rows]
    speeds = [r["speed_mps"] for r in rows]

    avg_power = average(powers)
    max_power = max_valid(powers)

    avg_hr = average(hrs)
    max_hr = max_valid(hrs)

    avg_speed = average(speeds)
    avg_cadence = average(cadences)

    # Cadencia de pedaleo activo: solo cuando cadencia > 0 y potencia > 30W
    # Excluye bajadas sin pedalear y momentos de recuperación sin esfuerzo
    has_power = any(p is not None and p > 0 for p in powers)
    if has_power:
        active_cad_rows = [r for r in rows if (r.get("cadence_rpm") or 0) > 5 and (r.get("power_w") or 0) > 30]
    else:
        # Sin medidor de potencia: filtrar solo por cadencia > 0
        active_cad_rows = [r for r in rows if (r.get("cadence_rpm") or 0) > 5]
    active_cadences = [r["cadence_rpm"] for r in active_cad_rows if r.get("cadence_rpm") is not None]
    avg_active_cadence = (sum(active_cadences) / len(active_cadences)) if active_cadences else None

    # % de tiempo pedaleando activamente vs tiempo total con datos
    total_rows = len([r for r in rows if r.get("cadence_rpm") is not None])
    pedaling_pct = round(len(active_cad_rows) / total_rows * 100, 1) if total_rows > 0 else None

    total_time_s = rows[-1]["elapsed_s"] if rows and rows[-1]["elapsed_s"] is not None else 0
    total_distance_m = max_valid([r["distance_m"] for r in rows]) or 0
    total_ascent_m = sum_positive_deltas(elevations)

    energy_kj = 0.0
    for i, row in enumerate(rows):
        p = row["power_w"]
        dt = deltas[i]
        if p is not None and dt > 0:
            energy_kj += (p * dt) / 1000.0

    elapsed_times = [r["elapsed_s"] for r in rows]
    np_value = compute_np(powers, elapsed_s=elapsed_times)
    vi = (np_value / avg_power) if np_value is not None and avg_power and avg_power > 0 else None
    intensity_factor = (np_value / ftp) if np_value is not None and ftp > 0 else None

    # TSS = (duration_s × NP × IF) / (FTP × 3600) × 100
    estimated_tss = None
    if np_value is not None and intensity_factor is not None and ftp > 0 and total_time_s:
        estimated_tss = round((total_time_s * np_value * intensity_factor) / (ftp * 3600) * 100, 1)

    # Aerobic efficiency: use only pedaling samples (power > 0) to avoid distortion from coasting/descents
    pedaling_powers = [r["power_w"] for r in rows if r.get("power_w") and r["power_w"] > 10]
    pedaling_hrs = [r["heart_rate_bpm"] for r in rows if r.get("power_w") and r["power_w"] > 10 and r.get("heart_rate_bpm")]
    avg_pedaling_power = (sum(pedaling_powers) / len(pedaling_powers)) if pedaling_powers else None
    avg_pedaling_hr = (sum(pedaling_hrs) / len(pedaling_hrs)) if pedaling_hrs else avg_hr
    aerobic_efficiency = (
        avg_pedaling_power / avg_pedaling_hr
        if avg_pedaling_power is not None and avg_pedaling_hr is not None and avg_pedaling_hr > 0
        else (avg_power / avg_hr if avg_power is not None and avg_hr is not None and avg_hr > 0 else None)
    )

    ride_classification = "No clasificado"
    if vi is not None:
        if vi >= 1.25:
            ride_classification = "Ride altamente variable, típico de MTB/XC/trail técnico"
        elif vi >= 1.12:
            ride_classification = "Ride variable con cambios de ritmo moderados"
        else:
            ride_classification = "Ride relativamente steady"

    return {
        "total_time_min": round(total_time_s / 60, 1) if total_time_s else None,
        "total_distance_km": round(total_distance_m / 1000, 2),
        "estimated_ascent_m": round(total_ascent_m, 1),
        "avg_speed_kmh": round(avg_speed * 3.6, 2) if avg_speed is not None else None,
        "avg_cadence_rpm": round(avg_cadence, 1) if avg_cadence is not None else None,
        "active_cadence_rpm": round(avg_active_cadence, 1) if avg_active_cadence is not None else None,
        "pedaling_pct": pedaling_pct,
        "avg_power": round(avg_power, 1) if avg_power is not None else None,
        "max_power": round(max_power, 1) if max_power is not None else None,
        "avg_hr": round(avg_hr, 1) if avg_hr is not None else None,
        "max_hr": round(max_hr, 1) if max_hr is not None else None,
        "estimated_np": round(np_value, 1) if np_value is not None else None,
        "vi": round(vi, 3) if vi is not None else None,
        "estimated_if": round(intensity_factor, 3) if intensity_factor is not None else None,
        "estimated_tss": estimated_tss,
        "energy_kj": round(energy_kj, 1),
        "aerobic_efficiency": round(aerobic_efficiency, 3) if aerobic_efficiency is not None else None,
        "ride_classification": ride_classification,
    }


def build_zones(rows, ftp, max_hr):
    deltas = time_deltas(rows)

    power_zones = accumulate_zone_times(rows, deltas, power_zone, "power_w", ftp)
    hr_zones = accumulate_zone_times(rows, deltas, hr_zone, "heart_rate_bpm", max_hr)

    def format_zone_table(zone_times):
        total = sum(zone_times.values()) if zone_times else 0
        result = {}

        for zone in sorted(zone_times.keys()):
            sec = zone_times[zone]
            result[zone] = {
                "seconds": round(sec, 1),
                "minutes": round(sec / 60, 2),
                "pct": round((sec / total * 100), 2) if total > 0 else 0,
            }

        return result

    return {
        "power": format_zone_table(power_zones),
        "heart_rate": format_zone_table(hr_zones),
    }


def build_ai_insights_context(garmin_summary, derived_summary, efforts, climbs, athlete_profile, fatigue, metabolic_index):
    findings = []

    ride_class = derived_summary.get("ride_classification")
    if ride_class:
        findings.append(ride_class)

    vi = derived_summary.get("vi")
    if vi is not None and vi >= 1.25:
        findings.append("La actividad fue muy variable y con alta demanda estocástica.")

    np_val = derived_summary.get("estimated_np")
    if np_val is not None:
        findings.append(f"La potencia normalizada estimada fue {np_val} W.")

    if efforts:
        findings.append(f"Se detectaron {len(efforts)} bloques intensos relevantes.")
        top_effort = sorted(
            [e for e in efforts if e.get("avg_power") is not None],
            key=lambda x: x["avg_power"],
            reverse=True,
        )[0]
        findings.append(
            f"El bloque más duro fue de tipo {top_effort['type']} con potencia media de {top_effort['avg_power']} W."
        )

    if climbs:
        findings.append(f"Se detectaron {len(climbs)} subidas relevantes.")
        top_climb = sorted(climbs, key=lambda x: x.get("climb_score", 0), reverse=True)[0]
        findings.append(
            f"La subida más exigente fue una {top_climb['climb_type']} de "
            f"{top_climb['duration_min']} min, {top_climb['elevation_gain_m']} m de ganancia "
            f"y {top_climb['avg_power']} W promedio."
        )

    primary_type = athlete_profile.get("primary_type")
    if primary_type:
        findings.append(f"Perfil preliminar del atleta: {primary_type}.")

    power_drop = fatigue.get("power_drop_pct")
    eff_drop = fatigue.get("efficiency_drop_pct")
    repeatability = fatigue.get("climb_repeatability_pct")

    if power_drop is not None:
        findings.append(f"La potencia útil cayó {power_drop}% entre la primera y segunda mitad.")

    if eff_drop is not None:
        findings.append(f"La eficiencia potencia/HR cayó {eff_drop}% a lo largo de la sesión.")

    if repeatability is not None:
        findings.append(f"La repeatability en subidas cambió {repeatability}% entre el inicio y el final.")

    avg_msi = metabolic_index.get("avg_msi")
    high_msi_pct = metabolic_index.get("high_msi_pct")
    if avg_msi is not None:
        findings.append(f"El costo metabólico promedio estimado (MSI) fue {avg_msi}.")
    if high_msi_pct is not None:
        findings.append(f"El {high_msi_pct}% del tiempo útil estuvo en MSI alto.")

    questions = [
        "¿Qué dice esta actividad sobre mi perfil como ciclista?",
        "¿Dónde estuvo mi bloque más fuerte y qué significa?",
        "¿Mi principal limitante fue potencia, fatiga o pacing?",
        "¿Qué debería entrenar para mejorar este tipo de actividad?",
        "¿Cómo se compara esta actividad con mis patrones esperados?",
        "¿Mi costo metabólico fue alto y por qué?",
    ]

    return {
        "key_findings": findings,
        "questions_user_might_ask": questions,
    }


def build_garmin_summary(activity):
    start_raw = activity.get("startTimeLocal") or activity.get("startTimeGMT") or ""
    start_date = str(start_raw)[:10] if start_raw else ""

    return {
        "activity_id": activity.get("activityId"),
        "name": activity.get("activityName"),
        "type": activity.get("activityType", {}).get("typeKey"),
        "start_date": start_date,
        "distance_km": round(((activity.get("distance", 0) or 0) / 1000), 2),
        "moving_minutes": round(((activity.get("movingDuration", 0) or 0) / 60), 1),
        "elapsed_minutes": round(((activity.get("elapsedDuration", 0) or 0) / 60), 1),
        "elevation_m": round(activity.get("elevationGain", 0) or 0),
        "calories": round(activity.get("calories", 0) or 0),
        "avg_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "avg_power": activity.get("avgPower"),
        "max_power": activity.get("maxPower"),
        "garmin_np": activity.get("normPower"),
        "garmin_tss": activity.get("trainingStressScore"),
        "garmin_if": activity.get("intensityFactor"),
        "vo2max": activity.get("vO2MaxValue"),
        "aerobic_te": activity.get("aerobicTrainingEffect"),
        "anaerobic_te": activity.get("anaerobicTrainingEffect"),
        "grit": activity.get("grit"),
    }


def analyze_activity(activity, series_path, ftp=230.0, max_hr=185.0):
    rows = read_activity_series(series_path)

    if not rows:
        return {
            "error": f"No se encontró la serie de actividad en: {series_path}"
        }

    # Metabolic Strain Index
    rows = add_msi_to_rows(rows, ftp, max_hr)
    metabolic_index = summarize_msi(rows)

    garmin_summary = build_garmin_summary(activity)
    derived_summary = build_derived_summary(rows, ftp)
    power_profile = build_power_profile(rows)
    zones = build_zones(rows, ftp, max_hr)
    efforts = build_efforts(rows, ftp)
    climbs = detect_climbs(rows)
    fatigue = build_fatigue_report(rows)

    if fatigue.get("fatigue_onset_min") is not None and fatigue["fatigue_onset_min"] < 10:
        fatigue["fatigue_onset_min"] = None

    athlete_profile = build_athlete_profile_v2(
        power_profile,
        climbs,
        efforts,
        derived_summary,
        fatigue,
    )

    performance_scores = build_performance_scores({
        "fatigue": fatigue,
        "derived_summary": derived_summary,
        "metabolic_index": metabolic_index,
        "climbs": climbs,
    })

    ai_insights_context = build_ai_insights_context(
        garmin_summary,
        derived_summary,
        efforts,
        climbs,
        athlete_profile,
        fatigue,
        metabolic_index,
    )

    result = {
        "activity_id": activity.get("activityId"),
        "garmin_summary": garmin_summary,
        "derived_summary": derived_summary,
        "power_profile": power_profile,
        "zones": zones,
        "efforts": efforts,
        "climbs": climbs,
        "fatigue": fatigue,
        "athlete_profile": athlete_profile,
        "metabolic_index": metabolic_index,
        "performance_scores": performance_scores,
        "ai_insights_context": ai_insights_context,
    }
    return result


if __name__ == "__main__":
    print("Este archivo está pensado para ser llamado desde el pipeline.")