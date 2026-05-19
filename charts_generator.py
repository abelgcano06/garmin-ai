import os
import pandas as pd
import matplotlib.pyplot as plt

from app_context import get_activity_charts_dir, get_current_user_id


def generate_charts(series_file, activity_id, user_id=None):
    user_id = user_id or get_current_user_id()

    if not os.path.exists(series_file):
        print(f"No se encontró el archivo de serie: {series_file}")
        return []

    df = pd.read_csv(series_file)

    charts_folder = get_activity_charts_dir(activity_id, user_id=user_id)
    os.makedirs(charts_folder, exist_ok=True)

    chart_files = []

    # Validación mínima de columnas reales del proyecto
    required_cols = ["elapsed_s", "power_w", "heart_rate_bpm"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        print(f"No se pudieron generar charts. Faltan columnas: {missing}")
        print(f"Columnas disponibles: {list(df.columns)}")
        return []

    # Convertir tiempo a minutos
    df["time_min"] = df["elapsed_s"] / 60.0

    # 1) POWER VS TIME
    plt.figure(figsize=(10, 4))
    plt.plot(df["time_min"], df["power_w"])
    plt.title("Power vs Time")
    plt.xlabel("Tiempo (min)")
    plt.ylabel("Potencia (W)")
    plt.tight_layout()
    power_time_path = os.path.join(charts_folder, "power_time.png")
    plt.savefig(power_time_path)
    chart_files.append(power_time_path)
    plt.close()

    # 2) HR VS POWER
    valid_hr_power = df.dropna(subset=["power_w", "heart_rate_bpm"])
    if not valid_hr_power.empty:
        plt.figure(figsize=(6, 6))
        plt.scatter(valid_hr_power["power_w"], valid_hr_power["heart_rate_bpm"], s=5)
        plt.title("HR vs Power")
        plt.xlabel("Potencia (W)")
        plt.ylabel("Frecuencia cardiaca (bpm)")
        plt.tight_layout()
        hr_power_path = os.path.join(charts_folder, "hr_power.png")
        plt.savefig(hr_power_path)
        chart_files.append(hr_power_path)
        plt.close()

    # 3) CADENCE VS TIME
    if "cadence_rpm" in df.columns:
        valid_cad = df.dropna(subset=["cadence_rpm"])
        if not valid_cad.empty:
            plt.figure(figsize=(10, 4))
            plt.plot(valid_cad["time_min"], valid_cad["cadence_rpm"])
            plt.title("Cadence vs Time")
            plt.xlabel("Tiempo (min)")
            plt.ylabel("Cadencia (rpm)")
            plt.tight_layout()
            cadence_time_path = os.path.join(charts_folder, "cadence_time.png")
            plt.savefig(cadence_time_path)
            chart_files.append(cadence_time_path)
            plt.close()

    # 4) ELEVATION VS TIME
    if "elevation_m" in df.columns:
        valid_elev = df.dropna(subset=["elevation_m"])
        if not valid_elev.empty:
            plt.figure(figsize=(10, 4))
            plt.plot(valid_elev["time_min"], valid_elev["elevation_m"])
            plt.title("Elevation vs Time")
            plt.xlabel("Tiempo (min)")
            plt.ylabel("Elevación (m)")
            plt.tight_layout()
            elevation_time_path = os.path.join(charts_folder, "elevation_time.png")
            plt.savefig(elevation_time_path)
            chart_files.append(elevation_time_path)
            plt.close()

    # 5) FATIGUE CURVE SIMPLE
    if "power_w" in df.columns:
        valid_power = df.dropna(subset=["power_w"]).copy()
        if not valid_power.empty:
            valid_power["block_10min"] = (valid_power["time_min"] // 10).astype(int)
            fatigue_df = valid_power.groupby("block_10min", as_index=False)["power_w"].mean()

            plt.figure(figsize=(8, 4))
            plt.plot(fatigue_df["block_10min"] * 10, fatigue_df["power_w"], marker="o")
            plt.title("Fatigue Curve (avg power por bloque de 10 min)")
            plt.xlabel("Tiempo (min)")
            plt.ylabel("Potencia media (W)")
            plt.tight_layout()
            fatigue_curve_path = os.path.join(charts_folder, "fatigue_curve.png")
            plt.savefig(fatigue_curve_path)
            chart_files.append(fatigue_curve_path)
            plt.close()

    print(f"Charts generadas en: {charts_folder}")
    return chart_files