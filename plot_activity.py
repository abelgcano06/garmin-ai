import csv
import os
import matplotlib.pyplot as plt

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
            rows.append({
                "elapsed_s": to_float(row.get("elapsed_s")),
                "heart_rate_bpm": to_float(row.get("heart_rate_bpm")),
                "power_w": to_float(row.get("power_w")),
                "elevation_m": to_float(row.get("elevation_m")),
            })
    return rows


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"No se encontró el archivo: {INPUT_FILE}")
        return

    rows = read_activity_series(INPUT_FILE)

    time_min = []
    hr = []
    power = []
    elevation = []

    for r in rows:
        if r["elapsed_s"] is not None:
            time_min.append(r["elapsed_s"] / 60)
            hr.append(r["heart_rate_bpm"])
            power.append(r["power_w"])
            elevation.append(r["elevation_m"])

    # Gráfica potencia
    plt.figure(figsize=(14, 4))
    plt.plot(time_min, power)
    plt.xlabel("Tiempo (min)")
    plt.ylabel("Potencia (W)")
    plt.title("Potencia vs Tiempo")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_FOLDER, "plot_power.png"))
    plt.show()

    # Gráfica frecuencia cardiaca
    plt.figure(figsize=(14, 4))
    plt.plot(time_min, hr)
    plt.xlabel("Tiempo (min)")
    plt.ylabel("Frecuencia cardiaca (bpm)")
    plt.title("Frecuencia cardiaca vs Tiempo")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_FOLDER, "plot_hr.png"))
    plt.show()

    # Gráfica elevación
    plt.figure(figsize=(14, 4))
    plt.plot(time_min, elevation)
    plt.xlabel("Tiempo (min)")
    plt.ylabel("Elevación (m)")
    plt.title("Elevación vs Tiempo")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_FOLDER, "plot_elevation.png"))
    plt.show()

    print("\nGráficas guardadas en la carpeta data:")
    print("- plot_power.png")
    print("- plot_hr.png")
    print("- plot_elevation.png")


if __name__ == "__main__":
    main()