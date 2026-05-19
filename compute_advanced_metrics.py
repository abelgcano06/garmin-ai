import csv
import os
from statistics import mean

DATA_FOLDER = "data"
INPUT_FILE = os.path.join(DATA_FOLDER, "activity_series_clean.csv")

# Ajustables
FTP = 230.0
MAX_HR = 185.0


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
                "cadence": to_float(r["cadence_rpm"]),
                "elevation": to_float(r["elevation_m"]),
                "speed": to_float(r["speed_mps"]),
            })
    return rows


def average(values):
    valid = [v for v in values if v is not None]
    return mean(valid) if valid else None


def max_valid(values):
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def compute_np(power_values):
    """
    Aproximación clásica:
    1) rolling average de 30 s
    2) elevar a la cuarta
    3) promedio
    4) raíz cuarta
    """
    valid = [p if p is not None else 0 for p in power_values]

    if len(valid) < 30:
        return None

    rolling_30 = []
    for i in range(len(valid) - 30 + 1):
        chunk = valid[i:i + 30]
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

        t0 = rows[i - 1]["time"]
        t1 = rows[i]["time"]

        if t0 is None or t1 is None:
            deltas.append(0)
        else:
            dt = t1 - t0
            deltas.append(dt if dt >= 0 else 0)

    return deltas


def total_positive_ascent(elevations):
    total = 0.0
    for i in range(1, len(elevations)):
        e0 = elevations[i - 1]
        e1 = elevations[i]
        if e0 is not None and e1 is not None:
            d = e1 - e0
            if d > 0:
                total += d
    return total


def power_zone(power, ftp):
    if power is None:
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
    if hr is None:
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
        zone = zone_fn(row[value_key], ref_value)
        dt = deltas[i]

        if zone is None or dt <= 0:
            continue

        zone_times[zone] = zone_times.get(zone, 0) + dt

    return zone_times


def print_zone_table(title, zone_times):
    print(f"\n{title}")
    print("-------------------")

    if not zone_times:
        print("Sin datos")
        return

    total = sum(zone_times.values())

    for zone in sorted(zone_times.keys()):
        seconds = zone_times[zone]
        minutes = seconds / 60
        pct = (seconds / total * 100) if total > 0 else 0
        print(f"{zone}: {minutes:.1f} min ({pct:.1f}%)")


def clean_moving_rows(rows):
    """
    Filtra tiempo útil básico:
    - potencia > 0 o cadencia > 0 o velocidad > 0.5 m/s
    """
    filtered = []

    for r in rows:
        p = r["power"] if r["power"] is not None else 0
        c = r["cadence"] if r["cadence"] is not None else 0
        s = r["speed"] if r["speed"] is not None else 0

        if p > 0 or c > 0 or s > 0.5:
            filtered.append(r)

    return filtered


def compute_drift(rows):
    """
    Drift simple usando mitades del ride en tiempo útil:
    ratio = avg_power / avg_hr
    """
    if len(rows) < 20:
        return None

    mid = len(rows) // 2
    first = rows[:mid]
    second = rows[mid:]

    p1 = average([r["power"] for r in first if r["power"] is not None and r["power"] > 0])
    h1 = average([r["hr"] for r in first if r["hr"] is not None])
    p2 = average([r["power"] for r in second if r["power"] is not None and r["power"] > 0])
    h2 = average([r["hr"] for r in second if r["hr"] is not None])

    if p1 is None or h1 is None or p2 is None or h2 is None or h1 <= 0 or h2 <= 0:
        return None

    r1 = p1 / h1
    r2 = p2 / h2

    if r1 <= 0:
        return None

    return ((r2 - r1) / r1) * 100


def classify_ride(np_value, avg_power, vi, total_time_h):
    if np_value is None or avg_power is None or vi is None:
        return "No clasificado"

    if vi >= 1.25:
        return "Ride altamente variable, típico de MTB/XC/trail técnico"
    elif vi >= 1.12:
        return "Ride variable con cambios de ritmo moderados"
    elif total_time_h >= 2 and vi < 1.10:
        return "Ride relativamente steady de fondo"
    else:
        return "Ride mixto"


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"No se encontró el archivo: {INPUT_FILE}")
        return

    rows = read_data()

    if not rows:
        print("No hay datos en el archivo.")
        return

    deltas = time_deltas(rows)
    moving_rows = clean_moving_rows(rows)

    moving_deltas = time_deltas(moving_rows)

    powers = [r["power"] for r in rows]
    hrs = [r["hr"] for r in rows]
    elevations = [r["elevation"] for r in rows]
    speeds = [r["speed"] for r in rows]

    moving_powers = [r["power"] for r in moving_rows]
    moving_hrs = [r["hr"] for r in moving_rows]

    total_time_s = rows[-1]["time"] if rows[-1]["time"] is not None else 0
    moving_time_s = sum(moving_deltas)
    coasting_time_s = max(total_time_s - moving_time_s, 0)

    total_distance_m = 0
    distance_values = [to_float(r.get("speed")) for r in rows]  # not used directly, kept safe
    speed_avg = average([s for s in speeds if s is not None])
    total_ascent = total_positive_ascent(elevations)

    avg_power_all = average([p for p in powers if p is not None])
    avg_power_moving = average([p for p in moving_powers if p is not None and p > 0])
    max_power = max_valid(powers)

    avg_hr_all = average(hrs)
    avg_hr_moving = average(moving_hrs)
    max_hr = max_valid(hrs)

    # Energía aproximada: sum(power * dt) / 1000 = kJ
    energy_kj = 0.0
    for i, row in enumerate(rows):
        p = row["power"]
        dt = deltas[i]
        if p is not None and dt > 0:
            energy_kj += (p * dt) / 1000.0

    np_value = compute_np(powers)
    vi = (np_value / avg_power_all) if np_value is not None and avg_power_all and avg_power_all > 0 else None
    intensity_factor = (np_value / FTP) if np_value is not None and FTP > 0 else None

    drift_pct = compute_drift(moving_rows)

    aerobic_efficiency = (
        avg_power_moving / avg_hr_moving
        if avg_power_moving is not None and avg_hr_moving is not None and avg_hr_moving > 0
        else None
    )

    power_zones = accumulate_zone_times(rows, deltas, power_zone, "power", FTP)
    hr_zones = accumulate_zone_times(rows, deltas, hr_zone, "hr", MAX_HR)

    ride_class = classify_ride(
        np_value=np_value,
        avg_power=avg_power_all,
        vi=vi,
        total_time_h=total_time_s / 3600 if total_time_s else 0,
    )

    print("\n==========================")
    print("ADVANCED METRICS REPORT")
    print("==========================")

    print("\nConfiguración")
    print("-------------------")
    print(f"FTP usado: {FTP:.1f} W")
    print(f"HR máxima usada: {MAX_HR:.1f} bpm")

    print("\nSesión")
    print("-------------------")
    print(f"Tiempo total: {total_time_s / 60:.1f} min")
    print(f"Tiempo útil/movimiento: {moving_time_s / 60:.1f} min")
    print(f"Tiempo no útil/coasting: {coasting_time_s / 60:.1f} min")
    print(f"Velocidad promedio: {speed_avg * 3.6:.2f} km/h" if speed_avg is not None else "Velocidad promedio: n/a")
    print(f"Ascenso acumulado estimado: {total_ascent:.0f} m")
    print(f"Energía estimada: {energy_kj:.1f} kJ")

    print("\nPotencia")
    print("-------------------")
    print(f"Potencia promedio total: {avg_power_all:.1f} W" if avg_power_all is not None else "Potencia promedio total: n/a")
    print(f"Potencia promedio útil: {avg_power_moving:.1f} W" if avg_power_moving is not None else "Potencia promedio útil: n/a")
    print(f"Potencia máxima: {max_power:.1f} W" if max_power is not None else "Potencia máxima: n/a")
    print(f"Normalized Power (NP): {np_value:.1f} W" if np_value is not None else "Normalized Power (NP): n/a")
    print(f"Variability Index (VI): {vi:.3f}" if vi is not None else "Variability Index (VI): n/a")
    print(f"Intensity Factor (IF): {intensity_factor:.3f}" if intensity_factor is not None else "Intensity Factor (IF): n/a")

    print("\nFrecuencia cardiaca")
    print("-------------------")
    print(f"HR promedio total: {avg_hr_all:.1f} bpm" if avg_hr_all is not None else "HR promedio total: n/a")
    print(f"HR promedio útil: {avg_hr_moving:.1f} bpm" if avg_hr_moving is not None else "HR promedio útil: n/a")
    print(f"HR máxima: {max_hr:.1f} bpm" if max_hr is not None else "HR máxima: n/a")

    print("\nRelación potencia / cardio")
    print("-------------------")
    print(f"Eficiencia aeróbica simple: {aerobic_efficiency:.3f} W/bpm" if aerobic_efficiency is not None else "Eficiencia aeróbica simple: n/a")
    print(f"Cardiac drift: {drift_pct:.2f}%" if drift_pct is not None else "Cardiac drift: n/a")

    print_zone_table("Zonas de potencia", power_zones)
    print_zone_table("Zonas de HR", hr_zones)

    print("\nClasificación")
    print("-------------------")
    print(ride_class)

    print("\nInterpretación inicial")
    print("-------------------")

    if vi is not None:
        if vi >= 1.25:
            print("Esfuerzo muy estocástico/variable. Muy típico de MTB con cambios de ritmo.")
        elif vi >= 1.12:
            print("Sesión variable, con bastantes cambios de intensidad.")
        else:
            print("Sesión relativamente steady.")

    if intensity_factor is not None:
        if intensity_factor >= 0.95:
            print("La carga relativa fue muy alta respecto al FTP configurado.")
        elif intensity_factor >= 0.85:
            print("Sesión fuerte, cerca de umbral/sweet spot global.")
        else:
            print("Sesión moderada respecto al FTP configurado.")

    if drift_pct is not None:
        if drift_pct < -5:
            print("Se observa caída de eficiencia potencia/HR hacia el final.")
        elif drift_pct > 5:
            print("La relación potencia/HR mejoró en la segunda mitad.")
        else:
            print("La relación potencia/HR fue estable.")

    print("\nReporte avanzado generado correctamente.")


if __name__ == "__main__":
    main()