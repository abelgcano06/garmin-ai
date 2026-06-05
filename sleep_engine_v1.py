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


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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


def ts_ms_to_iso(ts_ms):
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def duration_seconds(start_iso, end_iso):
    s = parse_iso(start_iso)
    e = parse_iso(end_iso)
    if s is None or e is None:
        return 0
    return int((e - s).total_seconds())


def safe_get(dct, *keys, default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def normalize_ts(ts):
    if ts is None:
        return ""
    if isinstance(ts, (int, float)):
        return ts_ms_to_iso(int(ts))
    if isinstance(ts, str):
        dt = parse_iso(ts)
        if dt:
            return dt.isoformat()
        return ts
    return str(ts)


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


def split_thirds(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return [], [], []
    n = len(vals)
    a = max(1, n // 3)
    b = max(a + 1, (2 * n) // 3)
    return vals[:a], vals[a:b], vals[b:]


def split_halves(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return [], []
    mid = max(1, len(vals) // 2)
    return vals[:mid], vals[mid:]


# =========================
# Flexible extraction
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
            if k in item and item[k] is not None:
                ts = item[k]
                break

        value = None
        for k in value_keys:
            if k in item and item[k] is not None:
                value = item[k]
                break

        if ts is not None and value is not None:
            try:
                out.append({
                    "ts": normalize_ts(ts),
                    "value": float(value)
                })
            except Exception:
                pass

    return out


def infer_sleep_levels_from_dto(dto):
    start_gmt = normalize_ts(dto.get("sleepStartTimestampGMT"))
    end_gmt = normalize_ts(dto.get("sleepEndTimestampGMT"))

    if not start_gmt or not end_gmt:
        return []

    start_dt = parse_iso(start_gmt)
    end_dt = parse_iso(end_gmt)
    if not start_dt or not end_dt:
        return []

    total = int((end_dt - start_dt).total_seconds())
    if total <= 0:
        return []

    deep_sec = int(dto.get("deepSleepSeconds", 0) or 0)
    light_sec = int(dto.get("lightSleepSeconds", 0) or 0)
    rem_sec = int(dto.get("remSleepSeconds", 0) or 0)
    awake_sec = int(dto.get("awakeSleepSeconds", 0) or 0)

    cursor = start_dt
    levels = []

    def push(stage, secs):
        nonlocal cursor, levels
        if secs <= 0:
            return
        end = cursor.timestamp() + secs
        end_dt_local = datetime.fromtimestamp(end, tz=timezone.utc)
        levels.append({
            "stage": stage,
            "start_ts": cursor.isoformat(),
            "end_ts": end_dt_local.isoformat(),
            "duration_seconds": int(secs)
        })
        cursor = end_dt_local

    # Aproximación fisiológica base:
    # first half favorece deep, later half favorece rem.
    # No es la verdad absoluta, pero sirve para sacar placement y densities.
    first_half_budget = total // 2

    deep_first = min(deep_sec, int(deep_sec * 0.75))
    rem_late = min(rem_sec, int(rem_sec * 0.75))
    deep_rest = max(0, deep_sec - deep_first)
    rem_rest = max(0, rem_sec - rem_late)

    # Orden simple de arquitectura aproximada
    push("light", min(light_sec, max(0, first_half_budget // 3)))
    light_sec -= min(light_sec, max(0, first_half_budget // 3))

    push("deep", deep_first)
    push("light", min(light_sec, max(0, first_half_budget // 3)))
    light_sec -= min(light_sec, max(0, first_half_budget // 3))

    push("rem", rem_rest)
    push("awake", min(awake_sec, awake_sec // 2 if awake_sec > 1 else awake_sec))
    awake_sec -= min(awake_sec, awake_sec // 2 if awake_sec > 1 else awake_sec)

    push("light", max(0, light_sec // 2))
    light_sec -= max(0, light_sec // 2)
    push("deep", deep_rest)
    push("light", light_sec)
    push("rem", rem_late)
    push("awake", awake_sec)

    if levels:
        levels[-1]["end_ts"] = end_dt.isoformat()
        levels[-1]["duration_seconds"] = max(
            0,
            duration_seconds(levels[-1]["start_ts"], levels[-1]["end_ts"])
        )

    return levels


# =========================
# Build sleep series
# =========================

def build_sleep_series(raw_dump):
    sleep_data = safe_get(raw_dump, "calls", "get_sleep_data", "data", default={}) or {}
    dto = sleep_data.get("dailySleepDTO", {}) or {}

    series = {
        "calendar_date": dto.get("calendarDate", ""),
        "sleep_start_gmt": normalize_ts(dto.get("sleepStartTimestampGMT")),
        "sleep_end_gmt": normalize_ts(dto.get("sleepEndTimestampGMT")),
        "sleep_start_local": normalize_ts(dto.get("sleepStartTimestampLocal")),
        "sleep_end_local": normalize_ts(dto.get("sleepEndTimestampLocal")),
        "series_meta": {
            "source": "garmin",
            "timezone": "",
            "sampling_notes": {
                "heart_rate": "from sleepHeartRate if available",
                "hrv": "from hrvData if available",
                "stress": "from sleepStress if available",
                "body_battery": "from sleepBodyBattery if available",
                "respiration": "from wellnessEpochRespirationDataDTOList if available",
                "spo2": "from wellnessEpochSPO2DataDTOList if available",
                "movement": "from sleepMovement if available"
            }
        },
        "heart_rate": extract_numeric_series(
            sleep_data.get("sleepHeartRate", []),
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampGmt", "ts", "time"],
            value_keys=["value", "heartRate", "hr", "beatsPerMinute", "avgHeartRate"]
        ),
        "hrv": extract_numeric_series(
            sleep_data.get("hrvData", []),
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampGmt", "ts", "time"],
            value_keys=["value", "hrv", "rmssd", "overnightHrv", "avgHrv"]
        ),
        "stress": extract_numeric_series(
            sleep_data.get("sleepStress", []),
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampGmt", "ts", "time"],
            value_keys=["value", "stressLevel", "stress", "avgStress"]
        ),
        "body_battery": extract_numeric_series(
            sleep_data.get("sleepBodyBattery", []),
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampGmt", "ts", "time"],
            value_keys=["value", "bodyBattery", "battery", "bodyBatteryValue"]
        ),
        "respiration": extract_numeric_series(
            sleep_data.get("wellnessEpochRespirationDataDTOList", []),
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampGmt", "ts", "time"],
            value_keys=["value", "respirationValue", "respiration", "breathsPerMinute"]
        ),
        "spo2": extract_numeric_series(
            sleep_data.get("wellnessEpochSPO2DataDTOList", []),
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampGmt", "ts", "time"],
            value_keys=["value", "spo2", "spo2Value", "oxygenSaturation"]
        ),
        "movement": extract_numeric_series(
            sleep_data.get("sleepMovement", []),
            ts_keys=["startGMT", "startTimeGMT", "calendarDate", "timestampGMT", "timestampGmt", "ts", "time"],
            value_keys=["activityLevel", "value", "movement"]
        ),
        "sleep_levels": []
    }

    raw_levels = sleep_data.get("sleepLevels", [])
    if isinstance(raw_levels, list) and raw_levels:
        for item in raw_levels:
            if not isinstance(item, dict):
                continue
            stage = item.get("stage") or item.get("sleepLevel") or item.get("type") or ""
            start_ts = normalize_ts(
                item.get("startGMT") or item.get("startTimeGMT") or item.get("startTs") or item.get("start")
            )
            end_ts = normalize_ts(
                item.get("endGMT") or item.get("endTimeGMT") or item.get("endTs") or item.get("end")
            )
            dur = item.get("durationSeconds")
            if dur is None and start_ts and end_ts:
                dur = duration_seconds(start_ts, end_ts)
            series["sleep_levels"].append({
                "stage": str(stage),
                "start_ts": start_ts,
                "end_ts": end_ts,
                "duration_seconds": int(dur or 0)
            })
    else:
        series["sleep_levels"] = infer_sleep_levels_from_dto(dto)

    return series


# =========================
# Scoring helpers
# =========================

def score_sleep_efficiency(se):
    return clamp((se - 0.70) / 0.25 * 100.0, 0.0, 100.0)


def score_rem_ratio(rem_ratio):
    if rem_ratio <= 0:
        return 0.0
    if 0.20 <= rem_ratio <= 0.30:
        return 100.0
    if rem_ratio < 0.20:
        return clamp(rem_ratio / 0.20 * 100.0)
    return clamp((0.40 - rem_ratio) / 0.10 * 100.0)


def score_deep_ratio(deep_ratio):
    if deep_ratio <= 0:
        return 0.0
    if 0.16 <= deep_ratio <= 0.25:
        return 100.0
    if deep_ratio < 0.16:
        return clamp(deep_ratio / 0.16 * 100.0)
    return clamp((0.35 - deep_ratio) / 0.10 * 100.0)


def score_fragmentation(frag_index):
    return clamp(100.0 - frag_index * 100.0, 0.0, 100.0)


def score_hr_stability(hr_std):
    return clamp(100.0 - hr_std * 8.0, 0.0, 100.0)


def score_stress(avg_sleep_stress):
    return clamp(100.0 - avg_sleep_stress * 3.0, 0.0, 100.0)


def score_respiratory_stability(resp_std):
    return clamp(100.0 - resp_std * 12.0, 0.0, 100.0)


def score_oxygen(avg_spo2, min_spo2, baselines=None):
    if baselines and isinstance(baselines.get("min_spo2_p25"), (int, float)):
        threshold = baselines["min_spo2_p25"]
    else:
        threshold = 85.0
    score = 0.6 * clamp((avg_spo2 - 90) / 8 * 100.0) + 0.4 * clamp((min_spo2 - threshold) / 10 * 100.0)
    return clamp(score, 0.0, 100.0)


def score_recharge(body_battery_change, sleep_hours, body_battery_end=None):
    # Primary (70%): nivel al despertar — ¿en qué estado terminó la batería?
    # Secondary (30%): velocidad de recarga — ¿qué tan eficiente fue la carga?
    if body_battery_end is not None and body_battery_end > 0:
        wake_score = clamp(float(body_battery_end), 0.0, 100.0)
        if sleep_hours > 0:
            rate_score = clamp((body_battery_change / sleep_hours) / 10.0 * 100.0, 0.0, 100.0)
        else:
            rate_score = 50.0
        return round(0.7 * wake_score + 0.3 * rate_score, 2)
    # Fallback si no hay dato de nivel final
    if sleep_hours <= 0:
        return 0.0
    eff = body_battery_change / sleep_hours
    return clamp(eff / 8.0 * 100.0, 0.0, 100.0)


def score_circadian_alignment(status):
    mapping = {
        "ALIGNED": 100.0,
        "GOOD": 90.0,
        "SLIGHTLY_OFF": 75.0,
        "BEHIND": 55.0,
        "AHEAD": 55.0,
        "NOT_ALIGNED": 40.0
    }
    return mapping.get(str(status).upper(), 60.0)


def score_hrv_status(hrv_status):
    mapping = {
        "BALANCED": 100.0,
        "NORMAL": 90.0,
        "LOW": 55.0,
        "UNBALANCED": 40.0,
        "POOR": 30.0
    }
    return mapping.get(str(hrv_status).upper(), 65.0)


# =========================
# Advanced metrics
# =========================

def compute_stage_metrics(sleep_levels, total_sleep_seconds):
    if not sleep_levels:
        return {
            "stage_transition_count": 0,
            "architecture_stability_score": 60.0,
            "early_window_deep_ratio": 0.0,
            "late_window_rem_ratio": 0.0,
            "deep_distribution_score": 50.0,
            "rem_distribution_score": 50.0,
        }

    transitions = 0
    prev = None
    for lvl in sleep_levels:
        stage = str(lvl.get("stage", "")).lower()
        if prev is not None and stage != prev:
            transitions += 1
        prev = stage

    start_ts = parse_iso(sleep_levels[0]["start_ts"])
    end_ts = parse_iso(sleep_levels[-1]["end_ts"])
    if not start_ts or not end_ts:
        return {
            "stage_transition_count": transitions,
            "architecture_stability_score": clamp(100 - transitions * 5, 0, 100),
            "early_window_deep_ratio": 0.0,
            "late_window_rem_ratio": 0.0,
            "deep_distribution_score": 50.0,
            "rem_distribution_score": 50.0,
        }

    total_window = max(1, int((end_ts - start_ts).total_seconds()))
    early_cut = int(total_window * 0.50)
    late_start = int(total_window * 0.50)

    deep_total = 0
    deep_early = 0
    rem_total = 0
    rem_late = 0

    for lvl in sleep_levels:
        stage = str(lvl.get("stage", "")).lower()
        s = parse_iso(lvl["start_ts"])
        e = parse_iso(lvl["end_ts"])
        if not s or not e:
            continue

        rel_s = int((s - start_ts).total_seconds())
        rel_e = int((e - start_ts).total_seconds())
        dur = max(0, rel_e - rel_s)

        if stage == "deep":
            deep_total += dur
            overlap_early = max(0, min(rel_e, early_cut) - max(rel_s, 0))
            deep_early += overlap_early

        if stage == "rem":
            rem_total += dur
            overlap_late = max(0, min(rel_e, total_window) - max(rel_s, late_start))
            rem_late += overlap_late

    early_window_deep_ratio = pct(deep_early, deep_total)
    late_window_rem_ratio = pct(rem_late, rem_total)

    architecture_stability_score = clamp(100.0 - transitions * 4.5, 0.0, 100.0)
    deep_distribution_score = clamp(early_window_deep_ratio * 100.0, 0.0, 100.0)
    rem_distribution_score = clamp(late_window_rem_ratio * 100.0, 0.0, 100.0)

    return {
        "stage_transition_count": transitions,
        "architecture_stability_score": round(architecture_stability_score, 2),
        "early_window_deep_ratio": round(early_window_deep_ratio, 4),
        "late_window_rem_ratio": round(late_window_rem_ratio, 4),
        "deep_distribution_score": round(deep_distribution_score, 2),
        "rem_distribution_score": round(rem_distribution_score, 2),
    }


def count_spikes(values, threshold_std=1.0):
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 5:
        return 0
    m = mean(vals)
    s = stddev(vals)
    if s == 0:
        return 0
    return sum(1 for v in vals if v > m + threshold_std * s)


def count_spo2_drops(spo2_values, drop_threshold=3.0):
    vals = [v for v in spo2_values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return 0, 0.0
    drops = []
    for i in range(1, len(vals)):
        delta = vals[i - 1] - vals[i]
        if delta >= drop_threshold:
            drops.append(delta)
    return len(drops), mean(drops) if drops else 0.0


def compute_segmented_recharge(bb_values):
    vals = [v for v in bb_values if isinstance(v, (int, float))]
    if len(vals) < 4:
        return {
            "bb_gain_first_half": 0.0,
            "bb_gain_second_half": 0.0,
            "bb_recharge_slope_first_half": 0.0,
            "bb_recharge_slope_second_half": 0.0,
            "body_battery_recharge_velocity": 0.0
        }

    first, second = split_halves(vals)

    gain_first = (first[-1] - first[0]) if len(first) >= 2 else 0.0
    gain_second = (second[-1] - second[0]) if len(second) >= 2 else 0.0
    slope_first = linear_slope(first)
    slope_second = linear_slope(second)
    velocity = linear_slope(vals)

    return {
        "bb_gain_first_half": round(gain_first, 2),
        "bb_gain_second_half": round(gain_second, 2),
        "bb_recharge_slope_first_half": round(slope_first, 4),
        "bb_recharge_slope_second_half": round(slope_second, 4),
        "body_battery_recharge_velocity": round(velocity, 4)
    }


def compute_autonomic_shape(hr_values, stress_values, hrv_values):
    hr_first, hr_mid, hr_last = split_thirds(hr_values)
    stress_first, stress_mid, stress_last = split_thirds(stress_values)
    hrv_first, hrv_second = split_halves(hrv_values)

    hr_first_avg = mean(hr_first)
    hr_last_avg = mean(hr_last)
    hr_drop_pct = pct((hr_first_avg - hr_last_avg), hr_first_avg) if hr_first_avg > 0 else 0.0

    stress_first_avg = mean(stress_first)
    stress_last_avg = mean(stress_last)

    hrv_first_avg = mean(hrv_first)
    hrv_second_avg = mean(hrv_second)

    return {
        "hr_first_third_avg": round(hr_first_avg, 2),
        "hr_last_third_avg": round(hr_last_avg, 2),
        "hr_overnight_drop_pct": round(hr_drop_pct, 4),
        "stress_first_third_avg": round(stress_first_avg, 2),
        "stress_last_third_avg": round(stress_last_avg, 2),
        "hrv_first_half": round(hrv_first_avg, 2),
        "hrv_second_half": round(hrv_second_avg, 2),
    }


# =========================
# Analysis
# =========================

def load_sleep_baselines(user_dir):
    """
    Carga los baselines personales de sueño desde sleep_history/sleep_baselines.json.
    Retorna None si no existen o hay menos de 7 noches de historia.
    """
    baselines_path = os.path.join(user_dir, "sleep_history", "sleep_baselines.json")
    if not os.path.exists(baselines_path):
        return None
    try:
        data = load_json(baselines_path)
        if data.get("window_days", 0) < 7:
            return None
        metrics = data.get("metrics", {})
        result = {}
        for k, v in metrics.items():
            if isinstance(v.get("mean"), (int, float)):
                result[k] = v["mean"]
            if isinstance(v.get("p25"), (int, float)):
                result[f"{k}_p25"] = v["p25"]
        return result
    except Exception:
        return None


def compute_analysis(raw_dump, series, user_dir=None, baselines=None):
    if baselines is None and user_dir:
        baselines = load_sleep_baselines(user_dir)

    sleep_data = safe_get(raw_dump, "calls", "get_sleep_data", "data", default={}) or {}
    stats = safe_get(raw_dump, "calls", "get_stats", "data", default={}) or {}
    dto = sleep_data.get("dailySleepDTO", {}) or {}

    sleep_start_gmt = series["sleep_start_gmt"]
    sleep_end_gmt = series["sleep_end_gmt"]

    sleep_time_seconds = int(dto.get("sleepTimeSeconds", 0) or 0)
    time_in_bed_seconds = duration_seconds(sleep_start_gmt, sleep_end_gmt)
    sleep_efficiency = (sleep_time_seconds / time_in_bed_seconds) if time_in_bed_seconds > 0 else 0.0

    deep_sleep_seconds = int(dto.get("deepSleepSeconds", 0) or 0)
    light_sleep_seconds = int(dto.get("lightSleepSeconds", 0) or 0)
    rem_sleep_seconds = int(dto.get("remSleepSeconds", 0) or 0)
    awake_sleep_seconds = int(dto.get("awakeSleepSeconds", 0) or 0)
    awake_count = int(dto.get("awakeCount", 0) or 0)

    total_sleep = max(sleep_time_seconds, 1)
    deep_ratio = deep_sleep_seconds / total_sleep
    light_ratio = light_sleep_seconds / total_sleep
    rem_ratio = rem_sleep_seconds / total_sleep
    awake_ratio = awake_sleep_seconds / total_sleep

    movement_values = [x["value"] for x in series["movement"]]
    hr_values = [x["value"] for x in series["heart_rate"]]
    hrv_values = [x["value"] for x in series["hrv"]]
    stress_values = [x["value"] for x in series["stress"]]
    respiration_values = [x["value"] for x in series["respiration"]]
    spo2_values = [x["value"] for x in series["spo2"]]
    bb_values = [x["value"] for x in series["body_battery"]]

    movement_index = mean(movement_values)
    restlessness_score = 100.0 - clamp(movement_index * 15.0, 0.0, 100.0)
    fragmentation_index = min(1.0, awake_count * 0.15 + movement_index / 10.0)

    avg_sleep_hr = float(dto.get("avgHeartRate", mean(hr_values)) or 0.0)
    resting_hr = float(safe_get(stats, "restingHeartRate", default=sleep_data.get("restingHeartRate", 0)) or 0.0)
    min_sleep_hr = min(hr_values) if hr_values else 0.0
    max_sleep_hr = max(hr_values) if hr_values else 0.0
    hr_drop = max(resting_hr - min_sleep_hr, 0.0)
    hr_stability_index = score_hr_stability(stddev(hr_values))
    hr_recovery_slope = 0.0
    if len(hr_values) >= 6:
        first_chunk = hr_values[: max(3, len(hr_values)//4)]
        last_chunk = hr_values[-max(3, len(hr_values)//4):]
        hr_recovery_slope = mean(first_chunk) - mean(last_chunk)

    avg_overnight_hrv = float(sleep_data.get("avgOvernightHrv", mean(hrv_values)) or 0.0)
    hrv_status = str(sleep_data.get("hrvStatus", "") or "")
    hrv_recovery_score = score_hrv_status(hrv_status)

    if len(hrv_values) >= 6:
        first_hrv = hrv_values[: max(3, len(hrv_values)//4)]
        last_hrv = hrv_values[-max(3, len(hrv_values)//4):]
        hrv_ramp = mean(last_hrv) - mean(first_hrv)
        hrv_ramp_score = clamp(50.0 + hrv_ramp * 5.0, 0.0, 100.0)
    else:
        hrv_ramp_score = hrv_recovery_score

    avg_sleep_stress = float(dto.get("avgSleepStress", mean(stress_values)) or 0.0)
    stress_load_score = score_stress(avg_sleep_stress)
    stress_stability_index = clamp(100.0 - stddev(stress_values) * 4.0, 0.0, 100.0)
    # Alto = sistema simpático activo (estrés alto + FC inestable)
    sympathetic_activation_score = clamp(
        0.6 * (100.0 - stress_load_score) + 0.4 * (100.0 - hr_stability_index),
        0.0, 100.0
    )

    avg_respiration = float(dto.get("averageRespirationValue", mean(respiration_values)) or 0.0)
    min_respiration = float(dto.get("lowestRespirationValue", min(respiration_values) if respiration_values else 0.0) or 0.0)
    max_respiration = float(dto.get("highestRespirationValue", max(respiration_values) if respiration_values else 0.0) or 0.0)
    respiration_variability = stddev(respiration_values)
    respiratory_stability_score = score_respiratory_stability(respiration_variability)
    breathing_disruption_severity = str(dto.get("breathingDisruptionSeverity", "") or "")

    avg_spo2 = float(dto.get("averageSpO2Value", mean(spo2_values)) or 0.0)
    min_spo2 = float(dto.get("lowestSpO2Value", min(spo2_values) if spo2_values else 0.0) or 0.0)
    max_spo2 = float(dto.get("highestSpO2Value", max(spo2_values) if spo2_values else 0.0) or 0.0)
    oxygen_stability_score = score_oxygen(avg_spo2, min_spo2, baselines=baselines)
    oxygen_risk_flag = bool(min_spo2 > 0 and min_spo2 < 88)

    body_battery_start = bb_values[0] if bb_values else float(safe_get(stats, "bodyBatteryDuringSleep", default=0) or 0.0)
    body_battery_end = bb_values[-1] if bb_values else float(safe_get(stats, "bodyBatteryAtWakeTime", default=0) or 0.0)
    body_battery_change = float(sleep_data.get("bodyBatteryChange", body_battery_end - body_battery_start) or 0.0)
    sleep_hours = sleep_time_seconds / 3600.0 if sleep_time_seconds else 0.0
    recharge_efficiency = score_recharge(body_battery_change, sleep_hours, body_battery_end=body_battery_end)

    sleep_need = dto.get("sleepNeed", {}) or {}
    baseline_minutes = int(sleep_need.get("baseline", 0) or 0)
    actual_minutes = int(sleep_need.get("actual", 0) or 0)
    sleep_need_gap_minutes = actual_minutes - int(sleep_time_seconds / 60)
    training_feedback_raw = str(sleep_need.get("trainingFeedback", "") or "")

    alignment = dto.get("sleepAlignment", {}) or {}
    sleep_alignment_status = str(alignment.get("status", "") or "")
    sleep_midpoint_minutes = float(alignment.get("lastSleepMidpointMins", 0) or 0.0)
    optimal_midpoint_minutes = float(alignment.get("optimalSleepWindowMidpointMins", 0) or 0.0)
    circadian_alignment_score = score_circadian_alignment(sleep_alignment_status)

    # V2 metrics
    stage_metrics = compute_stage_metrics(series.get("sleep_levels", []), sleep_time_seconds)
    autonomic_shape = compute_autonomic_shape(hr_values, stress_values, hrv_values)
    segmented_recharge = compute_segmented_recharge(bb_values)

    movement_spike_count = count_spikes(movement_values, threshold_std=1.0)
    stress_spike_count = count_spikes(stress_values, threshold_std=1.0)
    micro_arousal_score = clamp(
        awake_count * 10 + movement_spike_count * 3 + stress_spike_count * 2,
        0.0, 100.0
    )
    overnight_instability_score = clamp(
        0.35 * (fragmentation_index * 100.0) +
        0.25 * min(movement_spike_count * 5, 100) +
        0.20 * min(stress_spike_count * 5, 100) +
        0.20 * (100 - stage_metrics["architecture_stability_score"]),
        0.0, 100.0
    )

    spo2_drop_count, spo2_drop_depth_avg = count_spo2_drops(spo2_values, drop_threshold=3.0)
    respiratory_irregularity_score = clamp(
        0.60 * (100 - respiratory_stability_score) +
        0.40 * min(spo2_drop_count * 10, 100),
        0.0, 100.0
    )
    oxygen_recovery_after_drop_score = clamp(
        100.0 - min(spo2_drop_depth_avg * 20.0, 100.0),
        0.0, 100.0
    )

    autonomic_recovery_curve_score = clamp(
        0.22 * hrv_recovery_score +
        0.14 * hrv_ramp_score +
        0.14 * hr_stability_index +
        0.14 * stress_load_score +
        0.12 * recharge_efficiency +
        0.12 * clamp(autonomic_shape["hr_overnight_drop_pct"] * 100, 0, 100) +
        0.12 * clamp(100 - (autonomic_shape["stress_last_third_avg"] * 3), 0, 100),
        0.0, 100.0
    )

    physical_recovery_score = clamp(
        0.18 * score_sleep_efficiency(sleep_efficiency) +
        0.18 * score_deep_ratio(deep_ratio) +
        0.12 * stage_metrics["deep_distribution_score"] +
        0.18 * respiratory_stability_score +
        0.12 * oxygen_stability_score +
        0.22 * recharge_efficiency,
        0.0, 100.0
    )

    neural_recovery_score = clamp(
        0.24 * score_rem_ratio(rem_ratio) +
        0.14 * stage_metrics["rem_distribution_score"] +
        0.18 * hrv_recovery_score +
        0.12 * hrv_ramp_score +
        0.12 * stress_load_score +
        0.20 * circadian_alignment_score,
        0.0, 100.0
    )

    architecture_balance_score = clamp(
        0.25 * score_deep_ratio(deep_ratio) +
        0.25 * score_rem_ratio(rem_ratio) +
        0.20 * score_fragmentation(fragmentation_index) +
        0.15 * stage_metrics["deep_distribution_score"] +
        0.15 * stage_metrics["rem_distribution_score"],
        0.0, 100.0
    )

    overall_recovery_score = clamp(
        0.20 * physical_recovery_score +
        0.22 * neural_recovery_score +
        0.26 * autonomic_recovery_curve_score +
        0.12 * score_sleep_efficiency(sleep_efficiency) +
        0.10 * architecture_balance_score +
        0.10 * recharge_efficiency,
        0.0, 100.0
    )

    # Penalización por carga de entrenamiento alta acumulada
    if "HIGH" in training_feedback_raw.upper():
        overall_recovery_score = clamp(overall_recovery_score - 5.0, 0.0, 100.0)

    return {
        "calendar_date": dto.get("calendarDate", ""),

        "sleep_window": {
            "sleep_start_gmt": sleep_start_gmt,
            "sleep_end_gmt": sleep_end_gmt,
            "sleep_start_local": series["sleep_start_local"],
            "sleep_end_local": series["sleep_end_local"],
            "sleep_time_seconds": sleep_time_seconds,
            "time_in_bed_seconds": time_in_bed_seconds,
            "sleep_efficiency": round(sleep_efficiency, 4)
        },

        "sleep_architecture": {
            "deep_sleep_seconds": deep_sleep_seconds,
            "light_sleep_seconds": light_sleep_seconds,
            "rem_sleep_seconds": rem_sleep_seconds,
            "awake_sleep_seconds": awake_sleep_seconds,
            "deep_ratio": round(deep_ratio, 4),
            "light_ratio": round(light_ratio, 4),
            "rem_ratio": round(rem_ratio, 4),
            "awake_ratio": round(awake_ratio, 4),
            "awake_count": awake_count,
            "fragmentation_index": round(fragmentation_index, 4),
            "movement_index": round(movement_index, 4),
            "restlessness_score": round(restlessness_score, 2),
            "architecture_balance_score": round(architecture_balance_score, 2),
            "stage_transition_count": stage_metrics["stage_transition_count"],
            "architecture_stability_score": stage_metrics["architecture_stability_score"],
            "early_window_deep_ratio": stage_metrics["early_window_deep_ratio"],
            "late_window_rem_ratio": stage_metrics["late_window_rem_ratio"],
            "deep_distribution_score": stage_metrics["deep_distribution_score"],
            "rem_distribution_score": stage_metrics["rem_distribution_score"],
        },

        "cardiac_recovery": {
            "avg_sleep_hr": round(avg_sleep_hr, 2),
            "resting_hr": round(resting_hr, 2),
            "min_sleep_hr": round(min_sleep_hr, 2),
            "max_sleep_hr": round(max_sleep_hr, 2),
            "hr_drop": round(hr_drop, 2),
            "hr_stability_index": round(hr_stability_index, 2),
            "hr_recovery_slope": round(hr_recovery_slope, 2),
            "hr_first_third_avg": autonomic_shape["hr_first_third_avg"],
            "hr_last_third_avg": autonomic_shape["hr_last_third_avg"],
            "hr_overnight_drop_pct": autonomic_shape["hr_overnight_drop_pct"],
        },

        "autonomic_recovery": {
            "avg_overnight_hrv": round(avg_overnight_hrv, 2),
            "hrv_status": hrv_status,
            "hrv_recovery_score": round(hrv_recovery_score, 2),
            "hrv_ramp_score": round(hrv_ramp_score, 2),
            "autonomic_recovery_curve_score": round(autonomic_recovery_curve_score, 2),
            "sympathetic_activation_score": round(sympathetic_activation_score, 2),
            "stress_first_third_avg": autonomic_shape["stress_first_third_avg"],
            "stress_last_third_avg": autonomic_shape["stress_last_third_avg"],
            "hrv_first_half": autonomic_shape["hrv_first_half"],
            "hrv_second_half": autonomic_shape["hrv_second_half"],
        },

        "stress_recovery": {
            "avg_sleep_stress": round(avg_sleep_stress, 2),
            "stress_load_score": round(stress_load_score, 2),
            "stress_stability_index": round(stress_stability_index, 2),
            "stress_spike_count": int(stress_spike_count),
        },

        "respiratory_recovery": {
            "avg_respiration": round(avg_respiration, 2),
            "min_respiration": round(min_respiration, 2),
            "max_respiration": round(max_respiration, 2),
            "respiration_variability": round(respiration_variability, 2),
            "respiratory_stability_score": round(respiratory_stability_score, 2),
            "breathing_disruption_severity": breathing_disruption_severity,
            "respiratory_irregularity_score": round(respiratory_irregularity_score, 2),
        },

        "oxygenation": {
            "avg_spo2": round(avg_spo2, 2),
            "min_spo2": round(min_spo2, 2),
            "max_spo2": round(max_spo2, 2),
            "oxygen_stability_score": round(oxygen_stability_score, 2),
            "oxygen_risk_flag": oxygen_risk_flag,
            "spo2_drop_count": int(spo2_drop_count),
            "spo2_drop_depth_avg": round(spo2_drop_depth_avg, 2),
            "oxygen_recovery_after_drop_score": round(oxygen_recovery_after_drop_score, 2),
        },

        "energy_recharge": {
            "body_battery_start": round(body_battery_start, 2),
            "body_battery_end": round(body_battery_end, 2),
            "body_battery_change": round(body_battery_change, 2),
            "recharge_efficiency": round(recharge_efficiency, 2),
            "bb_gain_first_half": segmented_recharge["bb_gain_first_half"],
            "bb_gain_second_half": segmented_recharge["bb_gain_second_half"],
            "bb_recharge_slope_first_half": segmented_recharge["bb_recharge_slope_first_half"],
            "bb_recharge_slope_second_half": segmented_recharge["bb_recharge_slope_second_half"],
            "body_battery_recharge_velocity": segmented_recharge["body_battery_recharge_velocity"],
        },

        "sleep_need": {
            "baseline_minutes": baseline_minutes,
            "actual_minutes": actual_minutes,
            "sleep_need_gap_minutes": sleep_need_gap_minutes,
            "feedback": str(sleep_need.get("feedback", "") or ""),
            "training_feedback": str(sleep_need.get("trainingFeedback", "") or ""),
            "sleep_history_adjustment": str(sleep_need.get("sleepHistoryAdjustment", "") or ""),
            "hrv_adjustment": str(sleep_need.get("hrvAdjustment", "") or "")
        },

        "circadian_alignment": {
            "sleep_alignment_status": sleep_alignment_status,
            "sleep_midpoint_minutes": round(sleep_midpoint_minutes, 2),
            "optimal_midpoint_minutes": round(optimal_midpoint_minutes, 2),
            "circadian_alignment_score": round(circadian_alignment_score, 2)
        },

        "instability_markers": {
            "movement_spike_count": int(movement_spike_count),
            "micro_arousal_score": round(micro_arousal_score, 2),
            "overnight_instability_score": round(overnight_instability_score, 2),
        },

        "recovery_summary": {
            "physical_recovery_score": round(physical_recovery_score, 2),
            "neural_recovery_score": round(neural_recovery_score, 2),
            "overall_recovery_score": round(overall_recovery_score, 2)
        }
    }


# =========================
# Findings V2
# =========================

def build_findings(analysis):
    findings = []

    sw = analysis["sleep_window"]
    arch = analysis["sleep_architecture"]
    cardio = analysis["cardiac_recovery"]
    auto = analysis["autonomic_recovery"]
    stress = analysis["stress_recovery"]
    resp = analysis["respiratory_recovery"]
    oxy = analysis["oxygenation"]
    energy = analysis["energy_recharge"]
    need = analysis["sleep_need"]
    circ = analysis["circadian_alignment"]
    instab = analysis["instability_markers"]
    summary = analysis["recovery_summary"]

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

    if sw["sleep_time_seconds"] < 6 * 3600:
        add("short_sleep", "high", 0.9, "duration",
            "Short sleep duration",
            "Total sleep time was below 6 hours, which may impair recovery.",
            "sleep_time_seconds", sw["sleep_time_seconds"], 21600)

    if arch["deep_ratio"] < 0.16:
        add("low_deep_sleep", "medium", 0.82, "architecture",
            "Low deep sleep",
            "Deep sleep proportion was below preferred range for physical restoration.",
            "deep_ratio", arch["deep_ratio"], 0.16)

    if arch["rem_ratio"] < 0.20:
        add("low_rem_sleep", "medium", 0.86, "architecture",
            "Low REM sleep",
            "REM proportion was below target, which may reduce neural and cognitive recovery.",
            "rem_ratio", arch["rem_ratio"], 0.20)

    if arch["late_window_rem_ratio"] < 0.55 and arch["rem_ratio"] < 0.20:
        add("compressed_late_rem", "medium", 0.78, "architecture",
            "Late-night REM compression",
            "REM was not only low, but also underrepresented in the late portion of the night.",
            "late_window_rem_ratio", arch["late_window_rem_ratio"], 0.55)

    if arch["early_window_deep_ratio"] < 0.55 and arch["deep_ratio"] < 0.18:
        add("weak_early_deep_distribution", "medium", 0.74, "architecture",
            "Weak early deep sleep distribution",
            "Deep sleep was not strongly concentrated in the early night as expected.",
            "early_window_deep_ratio", arch["early_window_deep_ratio"], 0.55)

    if arch["fragmentation_index"] > 0.30:
        add("fragmented_sleep", "medium", 0.8, "architecture",
            "Fragmented sleep",
            "Sleep showed signs of fragmentation through awakenings and/or movement instability.",
            "fragmentation_index", arch["fragmentation_index"], 0.30)

    if instab["micro_arousal_score"] > 35:
        add("micro_arousal_pattern", "medium", 0.76, "instability",
            "Micro-arousal pattern",
            "The night showed repeated instability signals consistent with micro-arousal-like disruption.",
            "micro_arousal_score", instab["micro_arousal_score"], 35)

    if stress["avg_sleep_stress"] > 20:
        add("high_nocturnal_stress", "medium", 0.84, "stress",
            "High nocturnal stress",
            "Average sleep stress was elevated, suggesting incomplete overnight downregulation.",
            "avg_sleep_stress", stress["avg_sleep_stress"], 20)

    if auto["autonomic_recovery_curve_score"] < 55:
        add("low_autonomic_recovery", "high", 0.88, "autonomic",
            "Low autonomic recovery",
            "Autonomic recovery curve suggests incomplete overnight nervous system recovery.",
            "autonomic_recovery_curve_score", auto["autonomic_recovery_curve_score"], 55)

    if cardio["hr_overnight_drop_pct"] < 0.03:
        add("poor_hr_downshift", "medium", 0.74, "autonomic",
            "Poor overnight HR downshift",
            "Heart rate did not fall much across the night, which may indicate incomplete physiological downregulation.",
            "hr_overnight_drop_pct", cardio["hr_overnight_drop_pct"], 0.03)

    if energy["recharge_efficiency"] < 55:
        add("poor_recharge_efficiency", "medium", 0.8, "energy",
            "Poor overnight recharge efficiency",
            "Body Battery recharge relative to sleep duration was lower than expected.",
            "recharge_efficiency", energy["recharge_efficiency"], 55)

    if resp["respiratory_stability_score"] < 60:
        add("respiratory_instability", "medium", 0.76, "respiration",
            "Respiratory instability",
            "Respiration variability suggests inconsistent breathing stability during sleep.",
            "respiratory_stability_score", resp["respiratory_stability_score"], 60)

    if oxy["spo2_drop_count"] >= 2:
        add("repeated_oxygen_drops", "high", 0.8, "oxygenation",
            "Repeated oxygen drops",
            "Multiple overnight oxygen drops were detected.",
            "spo2_drop_count", oxy["spo2_drop_count"], 2)

    if oxy["oxygen_risk_flag"]:
        add("oxygen_risk_flag", "high", 0.8, "oxygenation",
            "Low oxygen nadir",
            "Minimum overnight SpO2 fell into a range that deserves follow-up if recurrent.",
            "min_spo2", oxy["min_spo2"], 88)

    if circ["circadian_alignment_score"] < 60:
        add("circadian_misalignment", "medium", 0.78, "circadian",
            "Circadian misalignment",
            "Sleep timing appears misaligned with the preferred or optimal window.",
            "circadian_alignment_score", circ["circadian_alignment_score"], 60)

    if need["sleep_need_gap_minutes"] > 60:
        add("recovery_opportunity_loss", "medium", 0.75, "quantity",
            "Recovery opportunity loss",
            "Sleep duration fell meaningfully short of current sleep need.",
            "sleep_need_gap_minutes", need["sleep_need_gap_minutes"], 60)

    # limiter candidates
    limiter_candidates = [
        ("circadian_misalignment", 100 - circ["circadian_alignment_score"]),
        ("autonomic_fatigue", 100 - auto["autonomic_recovery_curve_score"]),
        ("poor_neural_recovery", 100 - summary["neural_recovery_score"]),
        ("respiratory_instability", 100 - resp["respiratory_stability_score"] if oxy["spo2_drop_count"] >= 1 or oxy["oxygen_risk_flag"] else 0),
        ("sleep_quantity_deficit", max(0, need["sleep_need_gap_minutes"])),
        ("sleep_continuity_instability", instab["overnight_instability_score"]),
    ]

    limiter_candidates.sort(key=lambda x: x[1], reverse=True)
    primary_limiter = limiter_candidates[0][0] if limiter_candidates else ""
    secondary_limiter = limiter_candidates[1][0] if len(limiter_candidates) > 1 else ""
    limiter_conf = clamp(limiter_candidates[0][1] if limiter_candidates else 0.0, 0.0, 100.0) / 100.0

    flags = {
        "possible_autonomic_strain": auto["autonomic_recovery_curve_score"] < 55 or cardio["hr_overnight_drop_pct"] < 0.03,
        "possible_respiratory_instability": resp["respiratory_stability_score"] < 60 or oxy["spo2_drop_count"] >= 2,
        "possible_oxygenation_issue": oxy["oxygen_risk_flag"],
        "possible_circadian_misalignment": circ["circadian_alignment_score"] < 60,
        "possible_short_sleep_recovery_gap": sw["sleep_time_seconds"] < 6 * 3600 or need["sleep_need_gap_minutes"] > 60
    }

    return {
        "calendar_date": analysis["calendar_date"],
        "findings": findings,
        "limiters": {
            "primary_limiter": primary_limiter,
            "secondary_limiter": secondary_limiter,
            "confidence": round(limiter_conf, 2),
            "training_impact": "moderate" if summary["overall_recovery_score"] >= 55 else "high",
            "recovery_impact": "moderate" if summary["overall_recovery_score"] >= 55 else "high",
            "recommended_focus": primary_limiter
        },
        "flags": flags
    }


# =========================
# Notable Events Extractor
# =========================

def _parse_ts(ts_str):
    """Parse ISO timestamp to datetime, return None on failure."""
    if not ts_str:
        return None
    try:
        s = ts_str[:19].replace("T", " ")
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _fmt_hhmm(ts_str):
    dt = _parse_ts(ts_str)
    if not dt:
        return ts_str[:16] if ts_str else "??"
    return dt.strftime("%H:%M")


def _ev_unpack(p):
    """Desempaca un punto de serie — acepta dict {ts, value} o list/tuple [ts, val]."""
    if isinstance(p, dict):
        return p.get("ts"), p.get("value")
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return p[0], p[1]
    return None, None


def extract_notable_events(series: dict) -> list:
    """
    Scan raw time-series data and extract the most physiologically
    significant nocturnal events with their timestamp and duration.

    Returns a list of up to 6 events, sorted by severity (high first).
    Each event:
      {
        "time":        "02:47",
        "signal":      "SpO2 | HRV | Estrés | Frecuencia cardíaca",
        "event":       "bajó a 91%",
        "duration_min": 18,      # null if point event
        "severity":    "high | medium",
        "system":      "Respiración | Sistema nervioso | Estrés"
      }
    """
    events = []

    # ── SpO2 drops ────────────────────────────────────────────────────────────
    spo2_series = series.get("spo2", [])
    i = 0
    while i < len(spo2_series):
        ts, val = _ev_unpack(spo2_series[i])
        if val is not None and float(val) < 93:
            nadir = float(val)
            nadir_ts = ts
            j = i
            while j < len(spo2_series):
                p_ts, v = _ev_unpack(spo2_series[j])
                if v is None or float(v) >= 94:
                    break
                if float(v) < nadir:
                    nadir = float(v)
                    nadir_ts = p_ts or ts
                j += 1
            duration_min = max(1, (j - i) * 2)
            severity = "high" if nadir < 88 else "medium"
            events.append({
                "time": _fmt_hhmm(nadir_ts or ts),
                "signal": "SpO₂",
                "event": f"bajó a {int(nadir)}%",
                "duration_min": duration_min,
                "severity": severity,
                "system": "Respiración"
            })
            i = j
        else:
            i += 1

    # ── HRV sharp drops ───────────────────────────────────────────────────────
    hrv_series = series.get("hrv", [])
    for idx in range(2, len(hrv_series)):
        _, prev_v = _ev_unpack(hrv_series[idx - 2])
        cur_ts, cur_v = _ev_unpack(hrv_series[idx])
        if prev_v and cur_v:
            drop = float(prev_v) - float(cur_v)
            if drop >= 12:
                events.append({
                    "time": _fmt_hhmm(cur_ts),
                    "signal": "HRV",
                    "event": f"caída de {int(drop)} ms",
                    "duration_min": None,
                    "severity": "medium",
                    "system": "Sistema nervioso"
                })

    # ── Stress spikes during sleep ────────────────────────────────────────────
    stress_series = series.get("stress", [])
    in_spike = False
    spike_start_ts = None
    spike_peak = 0
    for pair in stress_series:
        ts, val = _ev_unpack(pair)
        if val is None:
            continue
        fval = float(val)
        if fval > 40 and not in_spike:
            in_spike = True
            spike_start_ts = ts
            spike_peak = fval
        elif fval > 40 and in_spike:
            spike_peak = max(spike_peak, fval)
        elif fval <= 30 and in_spike:
            in_spike = False
            events.append({
                "time": _fmt_hhmm(spike_start_ts),
                "signal": "Estrés",
                "event": f"pico a {int(spike_peak)}",
                "duration_min": None,
                "severity": "high" if spike_peak > 55 else "medium",
                "system": "Sistema nervioso"
            })
            spike_peak = 0

    # ── HR nocturnal spike (possible arousal) ─────────────────────────────────
    hr_series = series.get("heart_rate", [])
    window = 5
    for idx in range(window, len(hr_series) - window):
        cur_ts, cur_v = _ev_unpack(hr_series[idx])
        if cur_v is None:
            continue
        neighbors = []
        for k in range(idx - window, idx + window + 1):
            if k == idx:
                continue
            _, nv = _ev_unpack(hr_series[k])
            if nv is not None:
                neighbors.append(float(nv))
        if not neighbors:
            continue
        local_mean = sum(neighbors) / len(neighbors)
        if float(cur_v) - local_mean >= 14:
            events.append({
                "time": _fmt_hhmm(cur_ts),
                "signal": "Frecuencia cardíaca",
                "event": f"pico a {int(float(cur_v))} bpm (+{int(float(cur_v) - local_mean)} sobre media local)",
                "duration_min": None,
                "severity": "medium",
                "system": "Sistema nervioso"
            })

    # ── Deduplicate events too close in time (< 8 min apart, same signal) ────
    def _to_minutes(hhmm):
        try:
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return -999

    seen = []
    deduped = []
    for ev in events:
        key = ev["signal"]
        t = _to_minutes(ev["time"])
        too_close = any(abs(t - _to_minutes(s["time"])) < 8 and s["signal"] == key for s in seen)
        if not too_close:
            deduped.append(ev)
            seen.append(ev)

    # ── Sort: high first, then by time ────────────────────────────────────────
    severity_rank = {"high": 0, "medium": 1}
    deduped.sort(key=lambda e: (severity_rank.get(e["severity"], 2), _to_minutes(e["time"])))

    return deduped[:6]