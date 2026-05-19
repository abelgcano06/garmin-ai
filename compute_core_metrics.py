import csv
import os
from statistics import mean

DATA_FOLDER = "data"
INPUT_FILE = os.path.join(DATA_FOLDER, "activity_series_clean.csv")


def to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_activity_series(filepath):
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean_row = {k: to_float(v) if k != "timestamp" else v for k, v in row.items()}
            rows.append(clean_row)
    return rows


def rolling_average(values, window):
    if len(values) < window:
        return None
    avgs = []
    for i in range(len(values) - window + 1):
        chunk = values[i:i + window]
        if all(v is not None for v in chunk):
            avgs.append(sum(chunk) / window)
    return max(avgs) if avgs else None


def average_of_valid(values):
    valid = [v for v in values if v is not None]
    return mean(valid) if valid else None


def sum_positive_deltas(values):
    total = 0.0
    for i in range(1, len(values)):
        prev_v = values[i - 1]
        curr_v = values[i]
        if prev_v is not None and curr_v is not None:
            delta = curr_v - prev_v
            if delta > 0:
                total += delta
    return total


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"No se encontró el archivo: {INPUT_FILE}")
        return

    rows = read_activity_series(INPUT_FILE)

    if not rows:
        print("No hay datos en el CSV.")
        return

    elapsed = [r["elapsed_s"] for r in rows]
    distance = [r["distance_m"] for r in rows]
    elevation = [r["elevation_m"] for r in rows]
    speed = [r["speed_mps"] for r in rows]
    cadence = [r["cadence_rpm"] for r in rows]
    hr = [r["heart_rate_bpm"] for r in rows]
    power = [r["power_w"] for r in rows]

    # Resumen general
    total_time_s = max([v for v in elapsed if v is not None], default=0)
    total_distance_m = max([v for v in distance if v is not None], default=0)
    avg_speed_mps = average_of_valid(speed)
    avg_speed_kmh = avg_speed_mps * 3.6 if avg_speed_mps is not None else None
    total_ascent_m = sum_positive_deltas(elevation)

    # Potencia
    avg_power = average_of_valid(power)
    max_power = max([v for v in power if v is not None], default=None)
    pedaling_power = [v for v in power if v is not None and v > 0]
    avg_power_when_pedaling = mean(pedaling_power) if pedaling_power else None
    time_with_power_s = len(pedaling_power)

    best_5s = rolling_average(power, 5)
    best_30s = rolling_average(power, 30)
    best_60s = rolling_average(power, 60)
    best_300s = rolling_average(power, 300)
    best_1200s = rolling_average(power, 1200)

    # HR
    avg_hr = average_of_valid(hr)
    max_hr = max([v for v in hr if v is not None], default=None)

    first_half_hr = average_of_valid(hr[: len(hr) // 2])
    second_half_hr = average_of_valid(hr[len(hr) // 2 :])

    first_half_power = average_of_valid(power[: len(power) // 2])
    second_half_power = average_of_valid(power[len(power) // 2 :])

    # Eficiencia aeróbica simple
    aerobic_efficiency = None
    if avg_power is not None and avg_hr is not None and avg_hr > 0:
        aerobic_efficiency = avg_power / avg_hr

    # Desacople básico
    decoupling_pct = None
    if (
        first_half_hr is not None
        and second_half_hr is not None
        and first_half_power is not None
        and second_half_power is not None
        and first_half_hr > 0
        and second_half_hr > 0
    ):
        ratio_1 = first_half_power / first_half_hr
        ratio_2 = second_half_power / second_half_hr
        if ratio_1 > 0:
            decoupling_pct = ((ratio_2 - ratio_1) / ratio_1) * 100

    # Cadencia
    pedaling_cadence = [cadence[i] for i in range(len(cadence))
                        if cadence[i] is not None and power[i] is not None and power[i] > 0]
    avg_cadence_pedaling = mean(pedaling_cadence) if pedaling_cadence else None

    print("\n============================")
    print("CORE METRICS REPORT")
    print("============================")

    print("\nResumen general")
    print("-------------------")
    print(f"Tiempo total: {total_time_s / 60:.1f} min")
    print(f"Distancia total: {total_distance_m / 1000:.2f} km")
    print(f"Velocidad promedio: {avg_speed_kmh:.2f} km/h" if avg_speed_kmh is not None else "Velocidad promedio: n/a")
    print(f"Ascenso acumulado estimado por serie: {total_ascent_m:.0f} m")

    print("\nPotencia")
    print("-------------------")
    print(f"Potencia promedio: {avg_power:.1f} W" if avg_power is not None else "Potencia promedio: n/a")
    print(f"Potencia máxima: {max_power:.1f} W" if max_power is not None else "Potencia máxima: n/a")
    print(f"Potencia promedio pedaleando: {avg_power_when_pedaling:.1f} W" if avg_power_when_pedaling is not None else "Potencia promedio pedaleando: n/a")
    print(f"Tiempo con potencia > 0: {time_with_power_s / 60:.1f} min")

    print("\nMejores esfuerzos")
    print("-------------------")
    print(f"Best 5s: {best_5s:.1f} W" if best_5s is not None else "Best 5s: n/a")
    print(f"Best 30s: {best_30s:.1f} W" if best_30s is not None else "Best 30s: n/a")
    print(f"Best 1min: {best_60s:.1f} W" if best_60s is not None else "Best 1min: n/a")
    print(f"Best 5min: {best_300s:.1f} W" if best_300s is not None else "Best 5min: n/a")
    print(f"Best 20min: {best_1200s:.1f} W" if best_1200s is not None else "Best 20min: n/a")

    print("\nFrecuencia cardiaca")
    print("-------------------")
    print(f"HR promedio: {avg_hr:.1f} bpm" if avg_hr is not None else "HR promedio: n/a")
    print(f"HR máxima: {max_hr:.1f} bpm" if max_hr is not None else "HR máxima: n/a")
    print(f"HR primera mitad: {first_half_hr:.1f} bpm" if first_half_hr is not None else "HR primera mitad: n/a")
    print(f"HR segunda mitad: {second_half_hr:.1f} bpm" if second_half_hr is not None else "HR segunda mitad: n/a")

    print("\nRelación potencia / HR")
    print("-------------------")
    print(f"Eficiencia aeróbica simple (W/bpm): {aerobic_efficiency:.3f}" if aerobic_efficiency is not None else "Eficiencia aeróbica simple: n/a")
    print(f"Desacople básico: {decoupling_pct:.2f}%" if decoupling_pct is not None else "Desacople básico: n/a")

    print("\nCadencia")
    print("-------------------")
    print(f"Cadencia promedio pedaleando: {avg_cadence_pedaling:.1f} rpm" if avg_cadence_pedaling is not None else "Cadencia promedio pedaleando: n/a")

    print("\nInterpretación")
    print("-------------------")

    if decoupling_pct is not None:
        if decoupling_pct < -5:
            print("Hay caída de eficiencia en la segunda mitad: posible fatiga cardiovascular/metabólica.")
        elif decoupling_pct > 5:
            print("La relación potencia/HR mejoró en la segunda mitad.")
        else:
            print("La eficiencia potencia/HR fue bastante estable.")

    if avg_cadence_pedaling is not None and avg_cadence_pedaling < 70:
        print("Cadencia útil relativamente baja, posiblemente estilo de torque/subida/MTB técnico.")

    if best_5s is not None and best_300s is not None:
        ratio = best_5s / best_300s if best_300s > 0 else None
        if ratio is not None:
            if ratio > 2.2:
                print("Perfil con componente explosivo marcada.")
            else:
                print("Perfil más sostenido y menos explosivo.")

    print("\nReporte generado correctamente.")


if __name__ == "__main__":
    main()