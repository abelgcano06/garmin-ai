"""
day_engine_v1.py — Motor de análisis del día
=============================================
Mejoras vs versión anterior:
  1. Validación de calidad — días sin datos reales se marcan como inválidos
  2. Umbrales personalizados — compara contra tu propio basal histórico
  3. ATL/CTL/TSB — carga aguda, crónica y forma del día desde activity_index
  4. Scores redundantes consolidados — cognitive_load fusionado con nervous_system
  5. HRV diurno corregido — ya no devuelve 50 fijo cuando avg_hrv=0
"""

import json
import math
import os
from datetime import datetime, timezone


# =========================
# Utils
# =========================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def mean(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


def stddev(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return 0.0
    m = mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def pct(part, whole):
    if whole in (0, None):
        return 0.0
    return part / whole


def linear_slope(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    n = len(vals)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = mean(vals)
    num = sum((i - x_mean) * (vals[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def safe_get(dct, *keys, default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def ts_ms_to_iso(ts_ms):
    if ts_ms is None:
        return ""
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def normalize_ts(ts):
    if ts is None:
        return ""
    if isinstance(ts, (int, float)):
        return ts_ms_to_iso(ts)
    if isinstance(ts, str):
        dt = parse_iso(ts)
        if dt:
            return dt.isoformat()
        return ts
    return str(ts)


def split_series_by_window(series):
    morning = []
    afternoon = []
    evening = []
    for item in series:
        if not isinstance(item, dict):
            continue
        ts = parse_iso(item.get("ts"))
        if not ts:
            continue
        hour = ts.hour
        if 5 <= hour < 12:
            morning.append(item)
        elif 12 <= hour < 18:
            afternoon.append(item)
        else:
            evening.append(item)
    return {"morning": morning, "afternoon": afternoon, "evening": evening}


def summarize_segment(series):
    values = [x.get("value") for x in series if isinstance(x.get("value"), (int, float))]
    if not values:
        return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0, "slope": 0.0}
    return {
        "count": len(values),
        "avg": round(mean(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "slope": round(linear_slope(values), 4)
    }


def first_non_none(*values, default=None):
    for v in values:
        if v is not None:
            return v
    return default


# =========================
# Extracción de series (sin cambios)
# =========================

def extract_numeric_series(items, ts_keys, value_keys):
    out = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        ts = None
        for k in ts_keys:
            if item.get(k) is not None:
                ts = item.get(k)
                break
        value = None
        for k in value_keys:
            if item.get(k) is not None:
                value = item.get(k)
                break
        if ts is not None and value is not None:
            try:
                out.append({"ts": normalize_ts(ts), "value": float(value)})
            except Exception:
                pass
    return out


def extract_pair_series(items):
    out = []
    if not isinstance(items, list):
        return out
    for row in items:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            ts = row[0]
            value = row[1]
            if ts is None or value is None:
                continue
            try:
                out.append({"ts": normalize_ts(ts), "value": float(value)})
            except Exception:
                pass
    return out


def extract_map_series(dct):
    out = []
    if not isinstance(dct, dict):
        return out
    for ts, value in dct.items():
        if ts is None or value is None:
            continue
        try:
            out.append({"ts": normalize_ts(ts), "value": float(value)})
        except Exception:
            pass
    return out


def dedupe_series(series):
    dedup = {}
    for item in series:
        ts = item.get("ts")
        value = item.get("value")
        if ts and isinstance(value, (int, float)):
            dedup[ts] = {"ts": ts, "value": float(value)}
    return sorted(dedup.values(), key=lambda x: x["ts"])


def quality_label(series, real_threshold, allow_fallback=False):
    n = len(series)
    if n >= real_threshold:
        return "real_series"
    if n > 0 and allow_fallback:
        return "summary_fallback"
    if n > 0:
        return "partial_series"
    return "missing"


def extract_hr_series(hr_data):
    candidates = []
    if isinstance(hr_data, list):
        pair_series = extract_pair_series(hr_data)
        if pair_series:
            return dedupe_series(pair_series)
        dict_series = extract_numeric_series(
            hr_data,
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampLocal", "ts", "time"],
            value_keys=["value", "heartRate", "hr", "beatsPerMinute"]
        )
        if dict_series:
            return dedupe_series(dict_series)
    if isinstance(hr_data, dict):
        for key in ["heartRateValues", "heartRateValuesArray", "allMetrics", "heartRateDescriptors", "heartRateSamples", "values"]:
            value = hr_data.get(key)
            if isinstance(value, list):
                pair_series = extract_pair_series(value)
                if pair_series:
                    candidates.extend(pair_series)
                else:
                    candidates.extend(extract_numeric_series(
                        value,
                        ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampLocal", "ts", "time"],
                        value_keys=["value", "heartRate", "hr", "beatsPerMinute"]
                    ))
        for key in ["heartRateValues", "heartRateValueMap"]:
            maybe_map = hr_data.get(key)
            if isinstance(maybe_map, dict):
                candidates.extend(extract_map_series(maybe_map))
    return dedupe_series(candidates)


def extract_stress_series(stress_data):
    candidates = []
    if isinstance(stress_data, list):
        pair_series = extract_pair_series(stress_data)
        if pair_series:
            return dedupe_series(pair_series)
        dict_series = extract_numeric_series(
            stress_data,
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampLocal", "ts", "time"],
            value_keys=["value", "stressLevel", "stress"]
        )
        if dict_series:
            return dedupe_series(dict_series)
    if isinstance(stress_data, dict):
        for key in ["stressValues", "stressValuesArray", "allMetrics", "stressDescriptors", "values"]:
            value = stress_data.get(key)
            if isinstance(value, list):
                pair_series = extract_pair_series(value)
                if pair_series:
                    candidates.extend(pair_series)
                else:
                    candidates.extend(extract_numeric_series(
                        value,
                        ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampLocal", "ts", "time"],
                        value_keys=["value", "stressLevel", "stress"]
                    ))
        for key in ["stressValues", "stressValueMap"]:
            maybe_map = stress_data.get(key)
            if isinstance(maybe_map, dict):
                candidates.extend(extract_map_series(maybe_map))
    return dedupe_series(candidates)


def extract_body_battery_series(bb_data):
    candidates = []

    def parse_bb_row(row):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return None
        ts = row[0]
        value = None
        if len(row) >= 2 and isinstance(row[1], (int, float)):
            value = row[1]
        elif len(row) >= 3 and isinstance(row[2], (int, float)):
            value = row[2]
        if ts is None or value is None:
            return None
        try:
            return {"ts": normalize_ts(ts), "value": float(value)}
        except Exception:
            return None

    if isinstance(bb_data, list):
        for item in bb_data:
            if not isinstance(item, dict):
                continue
            arr = item.get("bodyBatteryValuesArray")
            if isinstance(arr, list):
                for row in arr:
                    parsed = parse_bb_row(row)
                    if parsed:
                        candidates.append(parsed)
            for key in ["bodyBatteryValues", "values", "allMetrics"]:
                value = item.get(key)
                if isinstance(value, list):
                    for row in value:
                        parsed = parse_bb_row(row)
                        if parsed:
                            candidates.append(parsed)
                    if not candidates:
                        candidates.extend(extract_numeric_series(
                            value,
                            ts_keys=["calendarDate", "eventStartTimeGmt", "timestampGMT", "timestampLocal", "ts", "time", "startGMT"],
                            value_keys=["bodyBattery", "value", "bodyBatteryValue", "battery", "bodyBatteryLevel"]
                        ))
                elif isinstance(value, dict):
                    candidates.extend(extract_map_series(value))
    elif isinstance(bb_data, dict):
        arr = bb_data.get("bodyBatteryValuesArray")
        if isinstance(arr, list):
            for row in arr:
                parsed = parse_bb_row(row)
                if parsed:
                    candidates.append(parsed)
        for key in ["bodyBatteryValues", "values", "allMetrics"]:
            value = bb_data.get(key)
            if isinstance(value, list):
                for row in value:
                    parsed = parse_bb_row(row)
                    if parsed:
                        candidates.append(parsed)
                if not candidates:
                    candidates.extend(extract_numeric_series(
                        value,
                        ts_keys=["calendarDate", "eventStartTimeGmt", "timestampGMT", "timestampLocal", "ts", "time", "startGMT"],
                        value_keys=["bodyBattery", "value", "bodyBatteryValue", "battery", "bodyBatteryLevel"]
                    ))
            elif isinstance(value, dict):
                candidates.extend(extract_map_series(value))
    return dedupe_series(candidates)


def extract_respiration_series(resp_data):
    candidates = []
    if isinstance(resp_data, list):
        pair_series = extract_pair_series(resp_data)
        if pair_series:
            return dedupe_series(pair_series)
        candidates.extend(extract_numeric_series(
            resp_data,
            ts_keys=["calendarDate", "timestampGMT", "timestampLocal", "ts", "time", "startGMT"],
            value_keys=["respiration", "value", "respirationValue", "breathsPerMinute"]
        ))
        return dedupe_series(candidates)
    if isinstance(resp_data, dict):
        for key in ["respirationValues", "respirationValuesArray", "allMetrics", "values", "respirationValueDescriptors"]:
            value = resp_data.get(key)
            if isinstance(value, list):
                pair_series = extract_pair_series(value)
                if pair_series:
                    candidates.extend(pair_series)
                else:
                    candidates.extend(extract_numeric_series(
                        value,
                        ts_keys=["calendarDate", "timestampGMT", "timestampLocal", "ts", "time", "startGMT"],
                        value_keys=["respiration", "value", "respirationValue", "breathsPerMinute"]
                    ))
            elif isinstance(value, dict):
                candidates.extend(extract_map_series(value))
    return dedupe_series(candidates)


def extract_hrv_series(hrv_data):
    candidates = []
    if isinstance(hrv_data, list):
        pair_series = extract_pair_series(hrv_data)
        if pair_series:
            return dedupe_series(pair_series)
        candidates.extend(extract_numeric_series(
            hrv_data,
            ts_keys=["calendarDate", "timestampGMT", "timestampLocal", "ts", "time", "startGMT"],
            value_keys=["hrv", "value", "rmssd", "avgHrv"]
        ))
        return dedupe_series(candidates)
    if isinstance(hrv_data, dict):
        for key in ["hrvValues", "hrvValuesArray", "allMetrics", "values"]:
            value = hrv_data.get(key)
            if isinstance(value, list):
                pair_series = extract_pair_series(value)
                if pair_series:
                    candidates.extend(pair_series)
                else:
                    candidates.extend(extract_numeric_series(
                        value,
                        ts_keys=["calendarDate", "timestampGMT", "timestampLocal", "ts", "time", "startGMT"],
                        value_keys=["hrv", "value", "rmssd", "avgHrv"]
                    ))
            elif isinstance(value, dict):
                candidates.extend(extract_map_series(value))
        for key in ["lastNightAvg", "avgHrv", "weeklyAverage"]:
            val = hrv_data.get(key)
            if isinstance(val, (int, float)):
                candidates.append({
                    "ts": normalize_ts(hrv_data.get("calendarDate") or hrv_data.get("timestampGMT") or ""),
                    "value": float(val)
                })
                break
    return dedupe_series(candidates)


def build_summary_fallback_series(stats_data, date_str):
    hr = []
    stress = []
    bb = []
    respiration = []
    start_ts = normalize_ts(stats_data.get("wellnessStartTimeGmt") or f"{date_str}T08:00:00")
    mid_ts = normalize_ts(f"{date_str}T12:00:00")
    end_ts = normalize_ts(stats_data.get("wellnessEndTimeGmt") or f"{date_str}T23:59:00")
    avg_stress = stats_data.get("averageStressLevel")
    if isinstance(avg_stress, (int, float)):
        stress.append({"ts": mid_ts, "value": float(avg_stress)})
    min_avg_hr = stats_data.get("minAvgHeartRate")
    max_avg_hr = stats_data.get("maxAvgHeartRate")
    if isinstance(min_avg_hr, (int, float)):
        hr.append({"ts": start_ts, "value": float(min_avg_hr)})
    if isinstance(max_avg_hr, (int, float)):
        hr.append({"ts": end_ts, "value": float(max_avg_hr)})
    bb_wake = stats_data.get("bodyBatteryAtWakeTime")
    bb_low = stats_data.get("bodyBatteryLowestValue")
    bb_recent = stats_data.get("bodyBatteryMostRecentValue")
    if isinstance(bb_wake, (int, float)):
        bb.append({"ts": start_ts, "value": float(bb_wake)})
    if isinstance(bb_low, (int, float)):
        bb.append({"ts": mid_ts, "value": float(bb_low)})
    if isinstance(bb_recent, (int, float)):
        bb.append({"ts": end_ts, "value": float(bb_recent)})
    avg_resp = stats_data.get("avgWakingRespirationValue")
    low_resp = stats_data.get("lowestRespirationValue")
    high_resp = stats_data.get("highestRespirationValue")
    if isinstance(low_resp, (int, float)):
        respiration.append({"ts": start_ts, "value": float(low_resp)})
    if isinstance(avg_resp, (int, float)):
        respiration.append({"ts": mid_ts, "value": float(avg_resp)})
    if isinstance(high_resp, (int, float)):
        respiration.append({"ts": end_ts, "value": float(high_resp)})
    return {
        "hr": dedupe_series(hr),
        "stress": dedupe_series(stress),
        "body_battery": dedupe_series(bb),
        "respiration": dedupe_series(respiration),
    }


# =========================
# ATL / CTL / TSB
# =========================

def compute_atl_ctl_tsb(user_dir, calendar_date):
    """
    Calcula carga aguda (ATL), crónica (CTL) y forma del día (TSB)
    leyendo el activity_index.json del usuario.

    ATL = fatiga de los últimos 7 días (decay 0.87/día)
    CTL = forma de los últimos 42 días (decay 0.97/día)
    TSB = CTL - ATL  (positivo = fresco, negativo = fatigado)
    """
    index_path = os.path.join(user_dir, "activity_index.json")
    if not os.path.exists(index_path):
        return {"atl": None, "ctl": None, "tsb": None, "source": "no_activity_index"}

    try:
        index = load_json(index_path)
        activities = index.get("activities", [])
    except Exception:
        return {"atl": None, "ctl": None, "tsb": None, "source": "load_error"}

    # Filtrar actividades con TSS válido y fecha anterior al día objetivo
    tss_by_date = {}
    for act in activities:
        act_date = (act.get("date") or "")[:10]
        tss = act.get("garmin_tss") or act.get("tss")
        if act_date and isinstance(tss, (int, float)) and act_date < calendar_date:
            # Suma TSS si hay varias actividades el mismo día
            tss_by_date[act_date] = tss_by_date.get(act_date, 0) + float(tss)

    if not tss_by_date:
        return {"atl": None, "ctl": None, "tsb": None, "source": "no_tss_data"}

    # Calcular ATL y CTL con decaimiento exponencial
    from datetime import date as date_cls, timedelta
    target = date_cls.fromisoformat(calendar_date)

    atl = 0.0
    ctl = 0.0
    ATL_DECAY = 0.87
    CTL_DECAY = 0.97

    for i in range(1, 43):  # 42 días hacia atrás
        d = (target - timedelta(days=i)).isoformat()
        tss = tss_by_date.get(d, 0.0)
        weight_atl = ATL_DECAY ** i
        weight_ctl = CTL_DECAY ** i
        atl += tss * weight_atl
        ctl += tss * weight_ctl

    # Normalizar sobre los mismos 42 días acumulados (ATL tiene más peso en primeros 7)
    atl_norm = sum(ATL_DECAY ** i for i in range(1, 43))
    ctl_norm = sum(CTL_DECAY ** i for i in range(1, 43))
    atl = atl / atl_norm if atl_norm > 0 else 0.0
    ctl = ctl / ctl_norm if ctl_norm > 0 else 0.0
    tsb = ctl - atl

    # TSB > 10 = fresco, -10 a 10 = neutro, < -10 = fatigado
    if tsb > 10:
        tsb_label = "fresh"
    elif tsb >= -10:
        tsb_label = "neutral"
    elif tsb >= -25:
        tsb_label = "fatigued"
    else:
        tsb_label = "very_fatigued"

    return {
        "atl": round(atl, 2),
        "ctl": round(ctl, 2),
        "tsb": round(tsb, 2),
        "tsb_label": tsb_label,
        "source": "activity_index",
        "days_with_tss": len(tss_by_date),
    }


# =========================
# Build day series
# =========================

def build_day_series(raw_dump):
    stats_data = safe_get(raw_dump, "calls", "get_stats", "data", default={}) or {}
    hr_data = safe_get(raw_dump, "calls", "get_heart_rates", "data", default={})
    stress_data = safe_get(raw_dump, "calls", "get_stress_data", "data", default={})
    bb_data = safe_get(raw_dump, "calls", "get_body_battery", "data", default={})
    resp_data = safe_get(raw_dump, "calls", "get_respiration_data", "data", default={})
    hrv_data = safe_get(raw_dump, "calls", "get_hrv_data", "data", default={})

    calendar_date = str(first_non_none(
        stats_data.get("calendarDate"),
        safe_get(raw_dump, "meta", "date"),
        default=""
    ))

    hr_series_real = extract_hr_series(hr_data)
    stress_series_real = extract_stress_series(stress_data)
    body_battery_series_real = extract_body_battery_series(bb_data)
    respiration_series_real = extract_respiration_series(resp_data)
    hrv_series_real = extract_hrv_series(hrv_data)

    fallback = build_summary_fallback_series(stats_data, calendar_date)

    hr_series = hr_series_real if hr_series_real else fallback["hr"]
    stress_series = stress_series_real if stress_series_real else fallback["stress"]
    body_battery_series = body_battery_series_real if body_battery_series_real else fallback["body_battery"]
    respiration_series = respiration_series_real if respiration_series_real else fallback["respiration"]
    hrv_series = hrv_series_real

    timeline = sorted(list({
        x["ts"]
        for x in (hr_series + stress_series + body_battery_series + respiration_series + hrv_series)
        if x.get("ts")
    }))

    steps = first_non_none(stats_data.get("totalSteps"), stats_data.get("steps"), default=0)
    intensity_minutes = (
        float(first_non_none(stats_data.get("moderateIntensityMinutes"), 0, default=0) or 0) +
        float(first_non_none(stats_data.get("vigorousIntensityMinutes"), 0, default=0) or 0)
    )
    active_calories = float(first_non_none(
        stats_data.get("activeKilocalories"),
        stats_data.get("wellnessActiveKilocalories"),
        default=0
    ) or 0)

    hr_segments = split_series_by_window(hr_series)
    stress_segments = split_series_by_window(stress_series)
    bb_segments = split_series_by_window(body_battery_series)

    bb_quality = "real_series" if len(body_battery_series_real) >= 3 else (
        "summary_fallback" if len(body_battery_series) > 0 else "missing"
    )

    data_quality = {
        "hr": quality_label(hr_series_real, real_threshold=50, allow_fallback=bool(hr_series)),
        "stress": quality_label(stress_series_real, real_threshold=50, allow_fallback=bool(stress_series)),
        "body_battery": bb_quality,
        "respiration": quality_label(respiration_series_real, real_threshold=50, allow_fallback=bool(respiration_series)),
        "hrv": quality_label(hrv_series_real, real_threshold=10, allow_fallback=bool(hrv_series)),
    }

    return {
        "calendar_date": calendar_date,
        "series_meta": {
            "source": "garmin",
            "data_quality": data_quality,
            "source_debug": {
                "get_heart_rates_type": type(hr_data).__name__,
                "get_stress_data_type": type(stress_data).__name__,
                "get_body_battery_type": type(bb_data).__name__,
                "get_respiration_data_type": type(resp_data).__name__,
                "get_hrv_data_type": type(hrv_data).__name__,
            }
        },
        "timeline": timeline,
        "hr": hr_series,
        "stress": stress_series,
        "body_battery": body_battery_series,
        "respiration": respiration_series,
        "hrv": hrv_series,
        "steps": int(steps or 0),
        "intensity_minutes": float(intensity_minutes or 0),
        "active_calories": float(active_calories or 0),
        "segments": {
            "morning": {
                "hr": summarize_segment(hr_segments["morning"]),
                "stress": summarize_segment(stress_segments["morning"]),
                "body_battery": summarize_segment(bb_segments["morning"]),
            },
            "afternoon": {
                "hr": summarize_segment(hr_segments["afternoon"]),
                "stress": summarize_segment(stress_segments["afternoon"]),
                "body_battery": summarize_segment(bb_segments["afternoon"]),
            },
            "evening": {
                "hr": summarize_segment(hr_segments["evening"]),
                "stress": summarize_segment(stress_segments["evening"]),
                "body_battery": summarize_segment(bb_segments["evening"]),
            }
        }
    }


# =========================
# MEJORA 1: Validación de calidad del día
# =========================

def validate_day_quality(series):
    """
    Retorna True si el día tiene datos reales suficientes para análisis.
    Días sin reloj puesto o sin datos reales se marcan como inválidos
    y no deben entrar al historial ni a las correlaciones.
    """
    quality = safe_get(series, "series_meta", "data_quality", default={}) or {}
    hr_points = len(series.get("hr", []))
    stress_points = len(series.get("stress", []))
    bb_points = len(series.get("body_battery", []))

    # Necesita al menos HR o stress con datos reales
    has_real_hr = quality.get("hr") == "real_series" and hr_points >= 20
    has_real_stress = quality.get("stress") == "real_series" and stress_points >= 20
    has_real_bb = quality.get("body_battery") == "real_series" and bb_points >= 3

    has_minimum_data = has_real_hr or has_real_stress or has_real_bb

    return {
        "is_valid": has_minimum_data,
        "has_real_hr": has_real_hr,
        "has_real_stress": has_real_stress,
        "has_real_bb": has_real_bb,
        "hr_points": hr_points,
        "stress_points": stress_points,
        "bb_points": bb_points,
    }


# =========================
# MEJORA 2: Scoring personalizado con baselines
# =========================

def load_personal_baselines(user_dir):
    """
    Carga los baselines personales del usuario desde day_history.
    Si no existen, retorna None y el motor usa umbrales genéricos.
    """
    baselines_path = os.path.join(user_dir, "day_history", "day_baselines.json")
    if not os.path.exists(baselines_path):
        return None
    try:
        data = load_json(baselines_path)
        metrics = data.get("metrics", {})
        # Solo usar baselines con al menos 7 días de historia
        if data.get("window_days", 0) < 7:
            return None
        return {k: v.get("mean") for k, v in metrics.items() if isinstance(v.get("mean"), (int, float))}
    except Exception:
        return None


def personal_threshold(value, baseline_mean, pct_above=0.20, default_threshold=None):
    """
    Genera un umbral personalizado basado en el basal del usuario.
    pct_above=0.20 significa que el umbral es 20% por encima del basal.
    Si no hay baseline, usa el default_threshold.
    """
    if isinstance(baseline_mean, (int, float)) and baseline_mean > 0:
        return baseline_mean * (1 + pct_above)
    return default_threshold


# =========================
# Scoring functions (mejoradas)
# =========================

def score_nervous_system_load(avg_stress, hr_std, avg_hrv, baselines=None):
    """
    MEJORA: HRV ya no devuelve 50 fijo cuando avg_hrv=0.
    Si no hay HRV real, el componente se estima desde HR_std y stress.
    Si hay baselines personales, compara contra el propio basal del usuario.
    """
    # Componente de estrés — personalizado si hay baseline
    stress_baseline = baselines.get("avg_stress") if baselines else None
    if isinstance(stress_baseline, (int, float)) and stress_baseline > 0:
        # Qué tan alejado está del propio basal (normalizado a 0-100)
        stress_ratio = avg_stress / stress_baseline
        stress_component = clamp(stress_ratio * 40, 0, 100)
    else:
        stress_component = clamp(avg_stress * 1.15, 0, 100)

    # Componente de variabilidad HR
    hr_component = clamp(hr_std * 7.5, 0, 100)

    # Componente HRV — CORREGIDO
    if avg_hrv > 5:
        # HRV real disponible — menor HRV = mayor carga
        hrv_baseline = baselines.get("avg_hrv") if baselines else None
        if isinstance(hrv_baseline, (int, float)) and hrv_baseline > 5:
            hrv_ratio = hrv_baseline / avg_hrv  # >1 = por debajo del basal
            hrv_component = clamp((hrv_ratio - 1) * 60, 0, 100)
        else:
            hrv_component = clamp(80 - avg_hrv * 0.9, 0, 100)
    else:
        # Sin HRV real — estimamos desde stress y HR_std
        hrv_component = clamp(stress_component * 0.6 + hr_component * 0.4, 0, 100)

    score = stress_component * 0.50 + hr_component * 0.20 + hrv_component * 0.30
    return clamp(score, 0, 100)


def score_energy_dynamics(bb_change, bb_slope, recharge_events, crash_events, bb_points, bb_quality, baselines=None):
    if bb_quality != "real_series" or bb_points < 5:
        base = 55.0
        if bb_change < 0:
            base += bb_change * 0.8
        else:
            base += min(12.0, bb_change * 0.4)
        return clamp(base, 0, 100)

    base = 70.0
    if bb_change < 0:
        base += bb_change * 0.9
    else:
        base += min(15, bb_change * 0.5)

    # Solo penalizar slope negativo (batería drenando rápido)
    # Slope positivo = batería cargando durante el día = buena señal, no penalizar
    if bb_slope < 0:
        base -= abs(bb_slope) * 20
    base += recharge_events * 4.5
    base -= crash_events * 10
    return clamp(base, 0, 100)


def score_cognitive_load(avg_stress, sedentary_seconds, total_seconds, physical_load_score):
    """
    Proxy de carga cognitiva/mental:
    Estrés autonómico ocurriendo mientras no hay actividad física = carga mental probable.
    - Alto estrés + sedentarismo → carga cognitiva alta
    - Alto estrés + mucha actividad física → el estrés es más físico, no mental
    """
    if total_seconds <= 0:
        return 50.0
    sedentary_ratio = clamp(sedentary_seconds / total_seconds, 0.0, 1.0)
    stress_base = clamp(avg_stress * 2.5, 0.0, 100.0)           # avg_stress 0-40 → 0-100
    physical_discount = physical_load_score * 0.3               # si muy activo, menos carga mental
    weighted = (stress_base - physical_discount) * (0.5 + sedentary_ratio * 0.5)
    return clamp(weighted, 0.0, 100.0)


def score_physical_load(steps, intensity_minutes, active_calories, baselines=None):
    """
    MEJORA: Umbrales adaptativos basados en el basal del usuario.
    Un atleta que normalmente hace 10k pasos tiene un umbral diferente
    a alguien que normalmente hace 3k.
    """
    if baselines:
        steps_baseline = baselines.get("steps", 14000)
        intensity_baseline = baselines.get("intensity_minutes", 90)
        calories_baseline = baselines.get("active_calories", 1200)
        # Umbral = 1.5x el basal personal (para que sea "alto" necesitas superar tu propio nivel)
        steps_threshold = max(steps_baseline * 1.5, 5000)
        intensity_threshold = max(intensity_baseline * 1.5, 30)
        calories_threshold = max(calories_baseline * 1.5, 400)
    else:
        steps_threshold = 14000
        intensity_threshold = 90
        calories_threshold = 1200

    score = (
        clamp(steps / steps_threshold * 100, 0, 100) * 0.45 +
        clamp(intensity_minutes / intensity_threshold * 100, 0, 100) * 0.35 +
        clamp(active_calories / calories_threshold * 100, 0, 100) * 0.20
    )
    return clamp(score, 0, 100)


def score_stress_behavior(avg_stress, high_stress_ratio, spike_count, baselines=None):
    """
    MEJORA: Compara avg_stress contra el propio basal del usuario.
    """
    if baselines:
        stress_baseline = baselines.get("avg_stress", 25)
        ratio_baseline = baselines.get("high_stress_ratio", 0.05)
        spike_baseline = baselines.get("stress_spike_count", 40)

        stress_comp = clamp((avg_stress / max(stress_baseline, 1)) * 40, 0, 100)
        ratio_comp = clamp((high_stress_ratio / max(ratio_baseline, 0.01)) * 40, 0, 100)
        spike_comp = clamp((spike_count / max(spike_baseline, 1)) * 30, 0, 100)
    else:
        stress_comp = clamp(avg_stress * 1.0, 0, 100)
        ratio_comp = clamp(high_stress_ratio * 100, 0, 100)
        spike_comp = clamp(spike_count * 8, 0, 100)

    return clamp(stress_comp * 0.50 + ratio_comp * 0.30 + spike_comp * 0.20, 0, 100)


def score_recovery_response(downshift_count, downshift_ratio, max_relief, stress_points, stress_quality, baselines=None):
    if stress_quality != "real_series" or stress_points < 10:
        # MEJORA: Ya no devuelve 50 fijo — devuelve None para que no contamine el historial
        return None

    score = (
        clamp(downshift_count * 12, 0, 100) * 0.35 +
        clamp(downshift_ratio * 100, 0, 100) * 0.40 +
        clamp(max_relief * 1.6, 0, 100) * 0.25
    )
    return clamp(score, 0, 100)


def score_respiratory_behavior(resp_std, resp_range, resp_points, resp_quality):
    if resp_quality != "real_series" or resp_points < 10:
        if resp_points > 0:
            score = 100 - (resp_std * 8.5 + resp_range * 2.0)
            return clamp(score, 0, 100)
        return None  # MEJORA: None en lugar de 50 fijo

    score = 100 - (resp_std * 8.5 + resp_range * 2.0)
    return clamp(score, 0, 100)


# =========================
# Analysis engine
# =========================

def compute_day_analysis(raw_dump, series, user_dir=None, baselines=None):
    """
    user_dir: si se pasa, carga baselines personales y calcula ATL/CTL/TSB.
    baselines: si se pasa directamente, los usa sin cargar del disco.
    """
    stats_data = safe_get(raw_dump, "calls", "get_stats", "data", default={}) or {}
    quality = safe_get(series, "series_meta", "data_quality", default={}) or {}
    calendar_date = series.get("calendar_date", "")

    # Cargar baselines personales si hay user_dir
    if baselines is None and user_dir:
        baselines = load_personal_baselines(user_dir)

    # Validación de calidad
    day_validity = validate_day_quality(series)

    hr_values = [x["value"] for x in series.get("hr", []) if isinstance(x.get("value"), (int, float))]
    stress_values = [x["value"] for x in series.get("stress", []) if isinstance(x.get("value"), (int, float))]
    bb_values = [x["value"] for x in series.get("body_battery", []) if isinstance(x.get("value"), (int, float))]
    resp_values = [x["value"] for x in series.get("respiration", []) if isinstance(x.get("value"), (int, float))]
    hrv_values = [x["value"] for x in series.get("hrv", []) if isinstance(x.get("value"), (int, float))]

    steps = series.get("steps", 0)
    intensity_minutes = series.get("intensity_minutes", 0.0)
    active_calories = series.get("active_calories", 0.0)

    avg_hr = mean(hr_values)
    hr_std = stddev(hr_values)
    max_hr = max(hr_values) if hr_values else float(stats_data.get("maxHeartRate", 0) or 0.0)

    avg_stress = mean(stress_values)
    if avg_stress == 0 and isinstance(stats_data.get("averageStressLevel"), (int, float)):
        avg_stress = float(stats_data.get("averageStressLevel"))

    max_stress = max(stress_values) if stress_values else float(stats_data.get("maxStressLevel", 0) or 0.0)

    high_stress_count = sum(1 for x in stress_values if x >= 70)
    moderate_stress_count = sum(1 for x in stress_values if x >= 50)
    low_stress_count = sum(1 for x in stress_values if x <= 25)

    stress_spike_count = sum(
        1 for i in range(1, len(stress_values))
        if (stress_values[i] - stress_values[i - 1]) >= 18
    )

    high_stress_ratio = pct(high_stress_count, len(stress_values))
    if high_stress_ratio == 0 and isinstance(stats_data.get("highStressPercentage"), (int, float)):
        high_stress_ratio = float(stats_data.get("highStressPercentage")) / 100.0

    avg_hrv = mean(hrv_values)

    # bb_start = al despertar (no medianoche — el primer punto de la serie incluye sueño)
    bb_start = float(stats_data.get("bodyBatteryAtWakeTime", 0) or 0.0) or (bb_values[0] if bb_values else 0.0)
    bb_end = float(stats_data.get("bodyBatteryMostRecentValue", 0) or 0.0) or (bb_values[-1] if bb_values else 0.0)
    bb_change = bb_end - bb_start
    # Slope solo sobre puntos post-despertar (descartar puntos previos al nivel de wake)
    post_wake = [v for v in bb_values if v >= bb_start * 0.85] if bb_start > 0 else bb_values
    bb_slope = linear_slope(post_wake) if len(post_wake) >= 2 else linear_slope(bb_values)
    bb_min = min(bb_values) if bb_values else float(stats_data.get("bodyBatteryLowestValue", 0) or 0.0)
    bb_max = max(bb_values) if bb_values else float(stats_data.get("bodyBatteryHighestValue", 0) or 0.0)

    recharge_events = 0
    crash_events = 0
    max_relief = 0.0
    downshift_count = 0

    bb_quality = quality.get("body_battery", "missing")
    stress_quality = quality.get("stress", "missing")
    resp_quality = quality.get("respiration", "missing")

    if bb_quality == "real_series" and len(bb_values) >= 5:
        for i in range(1, len(bb_values)):
            delta = bb_values[i] - bb_values[i - 1]
            if delta >= 4:
                recharge_events += 1
                if delta > max_relief:
                    max_relief = delta
            if delta <= -6:
                crash_events += 1

    if stress_quality == "real_series" and len(stress_values) >= 10:
        for i in range(1, len(stress_values)):
            delta = stress_values[i - 1] - stress_values[i]
            if stress_values[i - 1] >= 55 and stress_values[i] <= 35 and delta >= 15:
                downshift_count += 1
                if delta > max_relief:
                    max_relief = delta

    _downshift_denom = stress_spike_count + high_stress_count
    downshift_ratio = pct(downshift_count, _downshift_denom) if _downshift_denom > 0 else 0.0

    # Scores con baselines personalizados
    nervous_score = score_nervous_system_load(avg_stress, hr_std, avg_hrv, baselines=baselines)

    energy_score = score_energy_dynamics(
        bb_change=bb_change,
        bb_slope=bb_slope,
        recharge_events=recharge_events,
        crash_events=crash_events,
        bb_points=len(bb_values),
        bb_quality=bb_quality,
        baselines=baselines
    )

    physical_score = score_physical_load(
        steps=steps,
        intensity_minutes=intensity_minutes,
        active_calories=active_calories,
        baselines=baselines
    )

    sedentary_seconds = float(stats_data.get("sedentarySeconds", 0) or 0.0)
    total_day_seconds = float(stats_data.get("durationInMilliseconds", 86400000) or 86400000) / 1000.0
    cognitive_score = score_cognitive_load(
        avg_stress=avg_stress,
        sedentary_seconds=sedentary_seconds,
        total_seconds=total_day_seconds,
        physical_load_score=physical_score,
    )

    stress_score = score_stress_behavior(
        avg_stress=avg_stress,
        high_stress_ratio=high_stress_ratio,
        spike_count=stress_spike_count,
        baselines=baselines
    )

    recovery_score_raw = score_recovery_response(
        downshift_count=downshift_count,
        downshift_ratio=downshift_ratio,
        max_relief=max_relief,
        stress_points=len(stress_values),
        stress_quality=stress_quality,
        baselines=baselines
    )
    # Si no hay datos reales de stress, usamos estimación basada en energy y nervous
    recovery_score = recovery_score_raw if recovery_score_raw is not None else clamp(
        100 - (nervous_score * 0.5 + (100 - energy_score) * 0.5), 0, 100
    )
    has_real_recovery = recovery_score_raw is not None

    if not resp_values and isinstance(stats_data.get("avgWakingRespirationValue"), (int, float)):
        resp_values = [
            float(stats_data.get("lowestRespirationValue", 0) or 0.0),
            float(stats_data.get("avgWakingRespirationValue", 0) or 0.0),
            float(stats_data.get("highestRespirationValue", 0) or 0.0),
        ]

    resp_std = stddev(resp_values)
    resp_range = (max(resp_values) - min(resp_values)) if resp_values else 0.0
    respiratory_score_raw = score_respiratory_behavior(
        resp_std, resp_range,
        resp_points=len(resp_values),
        resp_quality=resp_quality
    )
    respiratory_score = respiratory_score_raw if respiratory_score_raw is not None else 50.0

    # Scores compuestos
    system_strain_score = (
        nervous_score * 0.35 +
        physical_score * 0.20 +
        stress_score * 0.45
    )

    day_capacity_score = (
        energy_score * 0.50 +
        recovery_score * 0.35 +
        respiratory_score * 0.15
    )

    overall_day_state_score = clamp(
        0.55 * day_capacity_score + 0.45 * (100 - system_strain_score),
        0, 100
    )

    # ATL/CTL/TSB
    training_load = {"atl": None, "ctl": None, "tsb": None, "source": "not_computed"}
    if user_dir and calendar_date:
        training_load = compute_atl_ctl_tsb(user_dir, calendar_date)

    return {
        "calendar_date": calendar_date,

        "data_validity": day_validity,

        "timeline_summary": {
            "timeline_points": len(series.get("timeline", [])),
            "hr_points": len(hr_values),
            "stress_points": len(stress_values),
            "body_battery_points": len(bb_values),
            "respiration_points": len(resp_values),
            "hrv_points": len(hrv_values),
        },

        "data_quality": quality,
        "segments": series.get("segments", {}),

        "nervous_system_load": {
            "avg_hr": round(avg_hr, 2),
            "hr_variability": round(hr_std, 2),
            "avg_stress": round(avg_stress, 2),
            "avg_hrv": round(avg_hrv, 2),
            "nervous_system_load_score": round(nervous_score, 2),
        },
        "cognitive_load": {
            "cognitive_load_score": round(cognitive_score, 2),
            "sedentary_ratio": round(clamp(sedentary_seconds / max(total_day_seconds, 1), 0, 1), 3),
        },

        "energy_dynamics": {
            "body_battery_start": round(bb_start, 2),
            "body_battery_end": round(bb_end, 2),
            "body_battery_change": round(bb_change, 2),
            "body_battery_min": round(bb_min, 2),
            "body_battery_max": round(bb_max, 2),
            "body_battery_slope": round(bb_slope, 4),
            "recharge_events": int(recharge_events),
            "crash_events": int(crash_events),
            "energy_dynamics_score": round(energy_score, 2),
        },

        "physical_load": {
            "steps": int(steps),
            "intensity_minutes": round(float(intensity_minutes), 2),
            "active_calories": round(float(active_calories), 2),
            "max_hr": round(max_hr, 2),
            "physical_load_score": round(physical_score, 2),
        },

        "stress_behavior": {
            "avg_stress": round(avg_stress, 2),
            "max_stress": round(max_stress, 2),
            "moderate_stress_count": int(moderate_stress_count),
            "high_stress_count": int(high_stress_count),
            "low_stress_count": int(low_stress_count),
            "stress_spike_count": int(stress_spike_count),
            "high_stress_ratio": round(high_stress_ratio, 4),
            "stress_behavior_score": round(stress_score, 2),
        },

        "recovery_response": {
            "downshift_count": int(downshift_count),
            "downshift_ratio": round(downshift_ratio, 4),
            "max_relief_event": round(max_relief, 2),
            "recovery_response_score": round(recovery_score, 2),
            "has_real_recovery_data": has_real_recovery,
        },

        "respiratory_behavior": {
            "avg_respiration": round(mean(resp_values), 2),
            "respiration_variability": round(resp_std, 2),
            "respiration_range": round(resp_range, 2),
            "respiratory_behavior_score": round(respiratory_score, 2),
        },

        "training_load": training_load,

        "summary_scores": {
            "nervous": round(nervous_score, 2),
            "physical": round(physical_score, 2),
            "stress": round(stress_score, 2),
            "energy": round(energy_score, 2),
            "recovery": round(recovery_score, 2),
            "respiratory": round(respiratory_score, 2),
            "cognitive": round(cognitive_score, 2),
        },

        "recovery_summary": {
            "calendar_date": calendar_date,
            "system_strain_score": round(system_strain_score, 2),
            "day_capacity_score": round(day_capacity_score, 2),
            "overall_day_state_score": round(overall_day_state_score, 2),
        }
    }


# =========================
# Findings engine (mejorado con baselines)
# =========================

def build_findings(analysis, baselines=None):
    findings = []

    nervous = analysis["nervous_system_load"]
    energy = analysis["energy_dynamics"]
    physical = analysis["physical_load"]
    stress = analysis["stress_behavior"]
    recovery = analysis["recovery_response"]
    respiratory = analysis["respiratory_behavior"]
    summary = analysis["recovery_summary"]
    quality = analysis.get("data_quality", {})
    validity = analysis.get("data_validity", {})

    def add(code, severity, confidence, dimension, title, description, metric, value, threshold, context=""):
        findings.append({
            "code": code,
            "severity": severity,
            "confidence": round(confidence, 2),
            "dimension": dimension,
            "title": title,
            "description": description,
            "evidence": {
                "metric": metric,
                "value": round(float(value), 4) if isinstance(value, (int, float)) else value,
                "threshold": threshold,
                "context": context
            }
        })

    # Umbrales adaptativos
    stress_threshold = personal_threshold(
        None,
        baselines.get("avg_stress") if baselines else None,
        pct_above=0.30,
        default_threshold=25
    )
    nervous_threshold = personal_threshold(
        None,
        baselines.get("nervous_system_load_score") if baselines else None,
        pct_above=0.25,
        default_threshold=65
    )
    recovery_threshold = personal_threshold(
        None,
        baselines.get("recovery_response_score") if baselines else None,
        pct_above=-0.30,  # negativo = por debajo del basal
        default_threshold=35
    )

    if nervous["nervous_system_load_score"] >= nervous_threshold:
        add(
            "high_nervous_system_load", "high", 0.88, "nervous_system",
            "High nervous system load",
            "The day shows elevated nervous system strain above your personal baseline.",
            "nervous_system_load_score", nervous["nervous_system_load_score"], nervous_threshold
        )

    if stress["stress_behavior_score"] >= 70:
        add(
            "sustained_high_stress", "high", 0.90, "stress",
            "Sustained high stress",
            "Stress remained elevated above your personal baseline across the day.",
            "stress_behavior_score", stress["stress_behavior_score"], 70
        )

    if stress["avg_stress"] >= stress_threshold:
        add(
            "high_avg_stress_personal", "medium", 0.85, "stress",
            "Stress above personal baseline",
            f"Average stress was {round(stress['avg_stress'], 1)} vs your personal mean of {round(baselines.get('avg_stress', stress_threshold), 1) if baselines else 'N/A'}.",
            "avg_stress", stress["avg_stress"], stress_threshold
        )

    if physical["physical_load_score"] >= 72:
        add(
            "high_physical_load", "medium", 0.84, "physical",
            "High physical load",
            "Movement and activity load exceeded your personal baseline meaningfully.",
            "physical_load_score", physical["physical_load_score"], 72
        )

    if energy["energy_dynamics_score"] <= 40:
        add(
            "energy_crash_pattern", "high", 0.90, "energy",
            "Rapid energy drain",
            "Energy dynamics suggest a fast loss of reserves and poor stability across the day.",
            "energy_dynamics_score", energy["energy_dynamics_score"], 40,
            context=f"body_battery_quality={quality.get('body_battery', 'missing')}"
        )

    if energy["body_battery_change"] <= -35:
        add(
            "deep_energy_depletion", "high", 0.87, "energy",
            "Deep energy depletion",
            "Body Battery dropped sharply across the day.",
            "body_battery_change", energy["body_battery_change"], -35
        )

    if recovery["has_real_recovery_data"] and recovery["recovery_response_score"] <= recovery_threshold:
        add(
            "low_intraday_recovery", "high", 0.88, "recovery",
            "Low intraday recovery",
            "The body showed limited ability to downshift once stress accumulated.",
            "recovery_response_score", recovery["recovery_response_score"], recovery_threshold
        )

    if respiratory["respiratory_behavior_score"] <= 45 and analysis["timeline_summary"]["respiration_points"] > 0:
        add(
            "respiratory_instability_daytime", "medium", 0.74, "respiration",
            "Daytime respiratory instability",
            "Breathing behavior looked irregular — worth monitoring if recurrent.",
            "respiratory_behavior_score", respiratory["respiratory_behavior_score"], 45
        )

    if summary["overall_day_state_score"] <= 45 and validity.get("is_valid", True):
        add(
            "globally_strained_day", "high", 0.89, "summary",
            "Globally strained day",
            "The combined balance of load versus capacity shows the body finished under strain.",
            "overall_day_state_score", summary["overall_day_state_score"], 45
        )

    # Training load findings
    training_load = analysis.get("training_load", {})
    tsb = training_load.get("tsb")
    if isinstance(tsb, (int, float)):
        if tsb < -25:
            add(
                "high_accumulated_fatigue", "high", 0.85, "training_load",
                "High accumulated fatigue (TSB)",
                f"Training Stress Balance is {round(tsb, 1)} — you're carrying significant accumulated fatigue from recent training.",
                "tsb", tsb, -25
            )
        elif tsb < -10:
            add(
                "moderate_accumulated_fatigue", "medium", 0.78, "training_load",
                "Moderate accumulated fatigue (TSB)",
                f"TSB is {round(tsb, 1)} — some fatigue from recent training load.",
                "tsb", tsb, -10
            )

    # Limitante principal
    limiter_candidates = {
        "nervous_system_load": nervous["nervous_system_load_score"],
        "physical_load": physical["physical_load_score"],
        "stress_behavior": stress["stress_behavior_score"],
        "energy_depletion": 100 - energy["energy_dynamics_score"],
        "recovery_failure": 100 - recovery["recovery_response_score"] if recovery["has_real_recovery_data"] else 0.0,
        "respiratory_instability": 100 - respiratory["respiratory_behavior_score"] if analysis["timeline_summary"]["respiration_points"] > 0 else 0.0,
    }

    sorted_limiters = sorted(limiter_candidates.items(), key=lambda x: x[1], reverse=True)
    primary_limiter = sorted_limiters[0][0] if sorted_limiters else ""
    secondary_limiter = sorted_limiters[1][0] if len(sorted_limiters) > 1 else ""

    flags = {
        "high_stress": stress["stress_behavior_score"] >= 70,
        "low_recovery": recovery["has_real_recovery_data"] and recovery["recovery_response_score"] <= recovery_threshold,
        "energy_crash": energy["energy_dynamics_score"] <= 40 or energy["body_battery_change"] <= -35,
        "high_nervous_load": nervous["nervous_system_load_score"] >= nervous_threshold,
        "high_cognitive_load": nervous["nervous_system_load_score"] >= nervous_threshold,
        "high_physical_load": physical["physical_load_score"] >= 72,
        "respiratory_instability": respiratory["respiratory_behavior_score"] <= 45 and analysis["timeline_summary"]["respiration_points"] > 0,
        "high_accumulated_fatigue": isinstance(tsb, (int, float)) and tsb < -10,
        "data_valid": validity.get("is_valid", True),
    }

    return {
        "calendar_date": analysis.get("calendar_date", ""),
        "findings": findings,
        "limiters": {
            "primary_limiter": primary_limiter,
            "secondary_limiter": secondary_limiter
        },
        "flags": flags,
        "baselines_used": baselines is not None,
    }


# =========================
# Notable Events Extractor (intraday)
# =========================

def _parse_ts_day(ts_str):
    if not ts_str:
        return None
    try:
        s = ts_str[:19].replace("T", " ")
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _fmt_hhmm_day(ts_str):
    dt = _parse_ts_day(ts_str)
    if not dt:
        return ts_str[:16] if ts_str else "??"
    return dt.strftime("%H:%M")


def extract_notable_events_day(series: dict) -> list:
    """
    Scan intraday time-series and extract the most physiologically
    significant events with timestamps and duration.

    Signals tracked:
      - Body Battery sharp drops (>= 15 pts in a short window)
      - Stress spikes (> 50 sustained for > 5 samples)
      - HR elevations (> 20 bpm above local mean for that window)
      - Post-activity recovery stall (BB not recovering after load)

    Returns up to 6 events sorted by severity (high first).
    Each event:
      {
        "time":         "14:32",
        "signal":       "Body Battery | Estrés | Frecuencia cardíaca",
        "event":        "caída de 22 pts",
        "duration_min": 18,
        "severity":     "high | medium",
        "system":       "Energía | Estrés | Sistema nervioso"
      }
    """
    events = []

    def _to_min(hhmm):
        try:
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return -999

    # ── Body Battery sharp drops ──────────────────────────────────────────────
    bb_series = series.get("body_battery", [])
    i = 0
    while i < len(bb_series) - 3:
        p0 = bb_series[i]
        v0 = p0[1] if isinstance(p0, (list, tuple)) else None
        ts0 = p0[0] if isinstance(p0, (list, tuple)) else None
        if v0 is None:
            i += 1
            continue
        # look ahead up to 30 samples for a drop
        j = i + 1
        nadir = float(v0)
        nadir_ts = ts0
        while j < min(i + 30, len(bb_series)):
            pj = bb_series[j]
            vj = pj[1] if isinstance(pj, (list, tuple)) else None
            tsj = pj[0] if isinstance(pj, (list, tuple)) else None
            if vj is None:
                j += 1
                continue
            if float(vj) < nadir:
                nadir = float(vj)
                nadir_ts = tsj
            j += 1
        drop = float(v0) - nadir
        if drop >= 15:
            duration_min = (j - i) * 2
            events.append({
                "time": _fmt_hhmm_day(nadir_ts or ts0),
                "signal": "Body Battery",
                "event": f"caída de {int(drop)} pts (hasta {int(nadir)})",
                "duration_min": duration_min,
                "severity": "high" if drop >= 25 else "medium",
                "system": "Energía"
            })
            i = j  # skip ahead past this episode
        else:
            i += 1

    # ── Stress spikes ─────────────────────────────────────────────────────────
    stress_series = series.get("stress", [])
    in_spike = False
    spike_start_ts = None
    spike_peak = 0
    spike_samples = 0
    for pair in stress_series:
        ts, val = (pair[0], pair[1]) if isinstance(pair, (list, tuple)) else (None, None)
        if val is None:
            continue
        fval = float(val)
        if fval > 50 and not in_spike:
            in_spike = True
            spike_start_ts = ts
            spike_peak = fval
            spike_samples = 1
        elif fval > 50 and in_spike:
            spike_peak = max(spike_peak, fval)
            spike_samples += 1
        elif fval <= 35 and in_spike:
            in_spike = False
            if spike_samples >= 3:  # sustained, not a blip
                events.append({
                    "time": _fmt_hhmm_day(spike_start_ts),
                    "signal": "Estrés",
                    "event": f"pico sostenido a {int(spike_peak)} ({spike_samples * 2} min)",
                    "duration_min": spike_samples * 2,
                    "severity": "high" if spike_peak > 65 else "medium",
                    "system": "Estrés"
                })
            spike_peak = 0
            spike_samples = 0

    # ── HR elevations above local mean ────────────────────────────────────────
    hr_series = series.get("heart_rate", [])
    window = 10
    for idx in range(window, len(hr_series) - window):
        cur_p = hr_series[idx]
        cur_v = cur_p[1] if isinstance(cur_p, (list, tuple)) else None
        cur_ts = cur_p[0] if isinstance(cur_p, (list, tuple)) else None
        if cur_v is None:
            continue
        neighbors = [
            float(hr_series[k][1])
            for k in range(idx - window, idx + window + 1)
            if k != idx
            and isinstance(hr_series[k], (list, tuple))
            and hr_series[k][1] is not None
        ]
        if not neighbors:
            continue
        local_mean = sum(neighbors) / len(neighbors)
        if float(cur_v) - local_mean >= 22:
            events.append({
                "time": _fmt_hhmm_day(cur_ts),
                "signal": "Frecuencia cardíaca",
                "event": f"pico a {int(float(cur_v))} bpm (+{int(float(cur_v) - local_mean)} sobre media local)",
                "duration_min": None,
                "severity": "medium",
                "system": "Sistema nervioso"
            })

    # ── Deduplicate events too close in time (< 10 min, same signal) ─────────
    seen = []
    deduped = []
    for ev in events:
        key = ev["signal"]
        t = _to_min(ev["time"])
        too_close = any(
            abs(t - _to_min(s["time"])) < 10 and s["signal"] == key
            for s in seen
        )
        if not too_close:
            deduped.append(ev)
            seen.append(ev)

    severity_rank = {"high": 0, "medium": 1}
    deduped.sort(key=lambda e: (severity_rank.get(e["severity"], 2), _to_min(e["time"])))
    return deduped[:6]


# =========================
# Main
# =========================

def main():
    raw_path = input("Ruta de day_raw.json: ").strip()
    user_dir = input("Ruta del user_dir (opcional, para baselines y ATL/CTL): ").strip() or None

    raw_dump = load_json(raw_path)
    series = build_day_series(raw_dump)
    analysis = compute_day_analysis(raw_dump, series, user_dir=user_dir)
    findings = build_findings(analysis)

    print("\n=== DAY ANALYSIS ===")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
    print("\n=== DAY FINDINGS ===")
    print(json.dumps(findings, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()