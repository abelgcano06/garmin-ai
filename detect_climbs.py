import csv
import os
from statistics import mean

DATA_FOLDER = "data"
INPUT_FILE = os.path.join(DATA_FOLDER, "activity_series_clean.csv")

# Reglas base de detección
MIN_CLIMB_GAIN_M = 20.0
MIN_CLIMB_DURATION_S = 90.0
MIN_CLIMB_DISTANCE_M = 300.0
MIN_GRADE_PCT = 2.0


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


def max_valid(values):
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def classify_climb(duration_s, gain_m, grade_pct):
    if duration_s < 180 and gain_m < 40:
        return "short_punchy"
    elif duration_s < 600 and grade_pct >= 5:
        return "medium_steep"
    elif duration_s >= 600:
        return "long_sustained"
    else:
        return "rolling_climb"


def compute_climb_score(gain_m, avg_power, avg_hr, grade_pct):
    score = 0.0
    score += gain_m * 1.0
    score += (avg_power or 0) * 0.25
    score += (avg_hr or 0) * 0.10
    score += grade_pct * 5.0
    return round(score, 1)


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
    vam = (gain_m / duration_s) * 3600 if duration_s > 0 else 0

    powers = [r["power_w"] for r in segment]
    hrs = [r["heart_rate_bpm"] for r in segment]
    cads = [r["cadence_rpm"] for r in segment]

    avg_power = average(powers)
    max_power = max_valid(powers)
    avg_hr = average(hrs)
    max_hr = max_valid(hrs)
    avg_cadence = average(cads)

    climb_type = classify_climb(duration_s, gain_m, avg_grade_pct)
    climb_score = compute_climb_score(gain_m, avg_power, avg_hr, avg_grade_pct)

    return {
        "start_min": round(start_time / 60, 2),
        "end_min": round(end_time / 60, 2),
        "duration_min": round(duration_s / 60, 2),
        "distance_m": round(distance_m, 1),
        "elevation_gain_m": round(gain_m, 1),
        "avg_grade_pct": round(avg_grade_pct, 2),
        "avg_power": round(avg_power, 1) if avg_power is not None else None,
        "max_power": round(max_power, 1) if max_power is not None else None,
        "avg_hr": round(avg_hr, 1) if avg_hr is not None else None,
        "max_hr": round(max_hr, 1) if max_hr is not None else None,
        "avg_cadence": round(avg_cadence, 1) if avg_cadence is not None else None,
        "vam": round(vam, 1),
        "climb_type": climb_type,
        "climb_score": climb_score,
    }


def detect_climbs(rows):
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

        local_grade = (elev_delta / dist_delta * 100) if dist_delta > 0 else 0

        climbing_now = elev_delta > 0 and local_grade >= 0.5

        if climbing_now and not in_climb:
            in_climb = True
            start_idx = i - 1

        elif not climbing_now and in_climb:
            end_idx = i - 1
            climb = summarize_climb(rows, start_idx, end_idx)

            if climb:
                if (
                    climb["elevation_gain_m"] >= MIN_CLIMB_GAIN_M
                    and climb["duration_min"] * 60 >= MIN_CLIMB_DURATION_S
                    and climb["distance_m"] >= MIN_CLIMB_DISTANCE_M
                    and climb["avg_grade_pct"] >= MIN_GRADE_PCT
                ):
                    climbs.append(climb)

            in_climb = False
            start_idx = None

    if in_climb and start_idx is not None:
        end_idx = len(rows) - 1
        climb = summarize_climb(rows, start_idx, end_idx)
        if climb:
            if (
                climb["elevation_gain_m"] >= MIN_CLIMB_GAIN_M
                and climb["duration_min"] * 60 >= MIN_CLIMB_DURATION_S
                and climb["distance_m"] >= MIN_CLIMB_DISTANCE_M
                and climb["avg_grade_pct"] >= MIN_GRADE_PCT
            ):
                climbs.append(climb)

    return climbs


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"No se encontró el archivo: {INPUT_FILE}")
        return

    rows = read_data()

    if not rows:
        print("No hay datos en el archivo.")
        return

    climbs = detect_climbs(rows)

    print("\n==========================")
    print("DETECTED CLIMBS")
    print("==========================")

    if not climbs:
        print("No se detectaron subidas con las reglas actuales.")
        return

    for i, climb in enumerate(climbs, start=1):
        print(f"\nClimb #{i}")
        for k, v in climb.items():
            print(f"{k}: {v}")

    print(f"\nTotal climbs detected: {len(climbs)}")


if __name__ == "__main__":
    main()