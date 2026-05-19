import csv
import os
from statistics import mean

DATA_FOLDER = "data"
INPUT_FILE = os.path.join(DATA_FOLDER, "activity_series_clean.csv")

# Duraciones objetivo en segundos
DURATIONS = [1, 5, 10, 30, 60, 180, 300, 480, 600, 1200, 1800, 3600]


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
                "time": to_float(r["elapsed_s"]),
                "power": to_float(r["power_w"]),
                "hr": to_float(r["heart_rate_bpm"]),
            })
    return rows


def format_duration(seconds):
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    return f"{minutes}min"


def best_window_by_real_time(rows, duration_s):
    best = None
    n = len(rows)

    for i in range(n):
        start_time = rows[i]["time"]
        if start_time is None:
            continue

        power_vals = []
        hr_vals = []

        for j in range(i, n):
            current_time = rows[j]["time"]
            if current_time is None:
                continue

            elapsed = current_time - start_time

            p = rows[j]["power"]
            h = rows[j]["hr"]

            if p is not None:
                power_vals.append(p)
            if h is not None:
                hr_vals.append(h)

            if elapsed >= duration_s:
                if not power_vals:
                    break

                avg_power = sum(power_vals) / len(power_vals)
                avg_hr = mean(hr_vals) if hr_vals else None

                candidate = {
                    "start_idx": i,
                    "end_idx": j,
                    "avg_power": avg_power,
                    "avg_hr": avg_hr,
                    "real_duration_s": elapsed,
                }

                if best is None or candidate["avg_power"] > best["avg_power"]:
                    best = candidate

                break

    return best


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"No se encontró el archivo: {INPUT_FILE}")
        return

    rows = read_data()

    if not rows:
        print("No hay datos en el archivo.")
        return

    print("\n==========================")
    print("POWER PROFILE V2")
    print("==========================")

    results = []

    for d in DURATIONS:
        result = best_window_by_real_time(rows, d)

        if result is None:
            print(f"{format_duration(d):>6} | n/a")
            continue

        start_time = rows[result["start_idx"]]["time"]
        end_time = rows[result["end_idx"]]["time"]

        start_min = start_time / 60 if start_time is not None else None
        end_min = end_time / 60 if end_time is not None else None

        results.append({
            "duration_s": d,
            "label": format_duration(d),
            "avg_power": result["avg_power"],
            "avg_hr": result["avg_hr"],
            "start_min": start_min,
            "end_min": end_min,
            "real_duration_s": result["real_duration_s"],
        })

        hr_text = f"{result['avg_hr']:.0f} bpm" if result["avg_hr"] is not None else "n/a"

        print(
            f"{format_duration(d):>6} | "
            f"{result['avg_power']:.1f} W | "
            f"HR {hr_text} | "
            f"{start_min:.1f} -> {end_min:.1f} min | "
            f"real {result['real_duration_s']:.0f}s"
        )

    output_file = os.path.join(DATA_FOLDER, "power_profile_v2.csv")
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "duration_s",
            "label",
            "avg_power",
            "avg_hr",
            "start_min",
            "end_min",
            "real_duration_s",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nArchivo guardado: {output_file}")


if __name__ == "__main__":
    main()