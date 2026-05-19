import csv
import os
from statistics import mean

DATA_FOLDER = "data"
INPUT_FILE = os.path.join(DATA_FOLDER, "activity_series_clean.csv")


def to_float(v):
    try:
        return float(v)
    except:
        return None


def read_data():
    rows = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "elapsed_s": to_float(r.get("elapsed_s")),
                "distance_m": to_float(r.get("distance_m")),
                "elevation_m": to_float(r.get("elevation_m")),
                "power_w": to_float(r.get("power_w")),
                "heart_rate_bpm": to_float(r.get("heart_rate_bpm")),
                "cadence_rpm": to_float(r.get("cadence_rpm")),
                "speed_mps": to_float(r.get("speed_mps")),
            })
    return rows


def average(values):
    valid = [v for v in values if v is not None]
    return mean(valid) if valid else None


def rolling_time_windows(rows, window_s=300):
    """
    Construye ventanas por tiempo real.
    """
    windows = []
    n = len(rows)

    for i in range(n):
        start_t = rows[i]["elapsed_s"]
        if start_t is None:
            continue

        segment = []
        for j in range(i, n):
            t = rows[j]["elapsed_s"]
            if t is None:
                continue

            segment.append(rows[j])

            if t - start_t >= window_s:
                powers = [r["power_w"] for r in segment if r["power_w"] is not None and r["power_w"] > 0]
                hrs = [r["heart_rate_bpm"] for r in segment if r["heart_rate_bpm"] is not None]

                if powers:
                    avg_power = average(powers)
                    avg_hr = average(hrs)
                    efficiency = (avg_power / avg_hr) if avg_hr and avg_hr > 0 else None

                    windows.append({
                        "start_min": round(start_t / 60, 2),
                        "end_min": round(t / 60, 2),
                        "avg_power": round(avg_power, 1) if avg_power is not None else None,
                        "avg_hr": round(avg_hr, 1) if avg_hr is not None else None,
                        "efficiency": round(efficiency, 4) if efficiency is not None else None,
                    })
                break

    return windows


def detect_climbs_local(rows,
                        min_gain_m=20.0,
                        min_duration_s=90.0,
                        min_distance_m=300.0,
                        min_grade_pct=2.0):
    climbs = []
    in_climb = False
    start_idx = None

    for i in range(1, len(rows)):
        prev_row = rows[i - 1]
        curr_row = rows[i]

        prev_elev = prev_row["elevation_m"]
        curr_elev = curr_row["elevation_m"]
        prev_dist = prev_row["distance_m"]
        curr_dist = curr_row["distance_m"]

        if None in [prev_elev, curr_elev, prev_dist, curr_dist]:
            continue

        elev_delta = curr_elev - prev_elev
        dist_delta = curr_dist - prev_dist
        local_grade = (elev_delta / dist_delta * 100) if dist_delta and dist_delta > 0 else 0

        climbing_now = elev_delta > 0 and local_grade >= 0.5

        if climbing_now and not in_climb:
            in_climb = True
            start_idx = i - 1

        elif not climbing_now and in_climb:
            end_idx = i - 1
            climb = summarize_climb(rows, start_idx, end_idx)
            if climb:
                if (
                    climb["elevation_gain_m"] >= min_gain_m
                    and climb["duration_s"] >= min_duration_s
                    and climb["distance_m"] >= min_distance_m
                    and climb["avg_grade_pct"] >= min_grade_pct
                ):
                    climbs.append(climb)

            in_climb = False
            start_idx = None

    if in_climb and start_idx is not None:
        end_idx = len(rows) - 1
        climb = summarize_climb(rows, start_idx, end_idx)
        if climb:
            if (
                climb["elevation_gain_m"] >= min_gain_m
                and climb["duration_s"] >= min_duration_s
                and climb["distance_m"] >= min_distance_m
                and climb["avg_grade_pct"] >= min_grade_pct
            ):
                climbs.append(climb)

    return climbs


def summarize_climb(rows, start_idx, end_idx):
    segment = rows[start_idx:end_idx + 1]

    start_time = segment[0]["elapsed_s"]
    end_time = segment[-1]["elapsed_s"]

    start_dist = segment[0]["distance_m"]
    end_dist = segment[-1]["distance_m"]

    start_elev = segment[0]["elevation_m"]
    end_elev = segment[-1]["elevation_m"]

    if None in [start_time, end_time, start_dist, end_dist, start_elev, end_elev]:
        return None

    duration_s = end_time - start_time
    distance_m = end_dist - start_dist
    gain_m = end_elev - start_elev

    if duration_s <= 0 or distance_m <= 0 or gain_m <= 0:
        return None

    avg_grade_pct = (gain_m / distance_m) * 100 if distance_m > 0 else 0

    powers = [r["power_w"] for r in segment if r["power_w"] is not None]
    hrs = [r["heart_rate_bpm"] for r in segment if r["heart_rate_bpm"] is not None]

    avg_power = average(powers)
    avg_hr = average(hrs)
    efficiency = (avg_power / avg_hr) if avg_power is not None and avg_hr and avg_hr > 0 else None

    return {
        "start_min": round(start_time / 60, 2),
        "end_min": round(end_time / 60, 2),
        "duration_s": round(duration_s, 1),
        "distance_m": round(distance_m, 1),
        "elevation_gain_m": round(gain_m, 1),
        "avg_grade_pct": round(avg_grade_pct, 2),
        "avg_power": round(avg_power, 1) if avg_power is not None else None,
        "avg_hr": round(avg_hr, 1) if avg_hr is not None else None,
        "efficiency": round(efficiency, 4) if efficiency is not None else None,
    }


def compute_power_drop(rows):
    half = len(rows) // 2

    first = [r["power_w"] for r in rows[:half] if r["power_w"] is not None and r["power_w"] > 0]
    second = [r["power_w"] for r in rows[half:] if r["power_w"] is not None and r["power_w"] > 0]

    p1 = average(first)
    p2 = average(second)

    if p1 is None or p2 is None or p1 <= 0:
        return None

    return round(((p2 - p1) / p1) * 100, 2)


def compute_efficiency_drop(rows):
    # Only use pedaling segments to avoid descents masking real degradation
    pedaling = [r for r in rows if r.get("power_w") is not None and r["power_w"] > 50]
    if len(pedaling) < 10:
        return None

    half = len(pedaling) // 2

    p1 = average([r["power_w"] for r in pedaling[:half] if r["power_w"] is not None and r["power_w"] > 0])
    h1 = average([r["heart_rate_bpm"] for r in pedaling[:half] if r["heart_rate_bpm"] is not None])

    p2 = average([r["power_w"] for r in pedaling[half:] if r["power_w"] is not None and r["power_w"] > 0])
    h2 = average([r["heart_rate_bpm"] for r in pedaling[half:] if r["heart_rate_bpm"] is not None])

    if p1 is None or h1 is None or p2 is None or h2 is None or h1 <= 0 or h2 <= 0:
        return None

    e1 = p1 / h1
    e2 = p2 / h2

    if e1 <= 0:
        return None

    return round(((e2 - e1) / e1) * 100, 2)


def compute_climb_repeatability(climbs):
    """
    Compara primera mitad de subidas vs segunda mitad de subidas.
    """
    if len(climbs) < 4:
        return None

    mid = len(climbs) // 2
    first = climbs[:mid]
    second = climbs[mid:]

    p1 = average([c["avg_power"] for c in first if c["avg_power"] is not None])
    p2 = average([c["avg_power"] for c in second if c["avg_power"] is not None])

    if p1 is None or p2 is None or p1 <= 0:
        return None

    return round(((p2 - p1) / p1) * 100, 2)


def detect_fatigue_onset(windows, drop_threshold_pct=-8.0, consecutive_hits=3):
    """
    Detecta onset cuando la eficiencia cae de forma sostenida
    respecto al mejor valor previo.
    """
    valid = [w for w in windows if w["efficiency"] is not None]
    if len(valid) < 8:
        return None

    best_so_far = valid[0]["efficiency"]
    hits = 0

    for w in valid[1:]:
        eff = w["efficiency"]
        if eff is None or best_so_far <= 0:
            continue

        drop_pct = ((eff - best_so_far) / best_so_far) * 100

        if drop_pct <= drop_threshold_pct:
            hits += 1
            if hits >= consecutive_hits:
                return w["start_min"]
        else:
            hits = 0
            if eff > best_so_far:
                best_so_far = eff

    return None


def build_fatigue_report(rows):
    windows = rolling_time_windows(rows, window_s=300)
    climbs = detect_climbs_local(rows)

    power_drop_pct = compute_power_drop(rows)
    efficiency_drop_pct = compute_efficiency_drop(rows)
    climb_repeatability_pct = compute_climb_repeatability(climbs)
    fatigue_onset_min = detect_fatigue_onset(windows)

    return {
        "fatigue_onset_min": fatigue_onset_min,
        "power_drop_pct": power_drop_pct,
        "efficiency_drop_pct": efficiency_drop_pct,
        "climb_repeatability_pct": climb_repeatability_pct,
        "window_count": len(windows),
        "climb_count": len(climbs),
    }


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"No se encontró el archivo: {INPUT_FILE}")
        return

    rows = read_data()
    if not rows:
        print("No hay datos.")
        return

    report = build_fatigue_report(rows)

    print("\n==========================")
    print("FATIGUE ANALYSIS V2")
    print("==========================")
    for k, v in report.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()