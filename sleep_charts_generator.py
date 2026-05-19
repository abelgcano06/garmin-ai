import json
import os
from datetime import datetime

import matplotlib.pyplot as plt


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def plot_single_series(x, y, title, ylabel, output_path):
    if not x or not y:
        return None

    plt.figure(figsize=(12, 4))
    plt.plot(x, y)
    plt.title(title)
    plt.xlabel("Tiempo")
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(output_path, dpi=140)
    plt.close()
    return output_path


def plot_multi_series(x, series_map, title, ylabel, output_path):
    valid = False
    plt.figure(figsize=(12, 5))

    for label, y in series_map.items():
        if x and y and len(x) == len(y):
            plt.plot(x, y, label=label)
            valid = True

    if not valid:
        plt.close()
        return None

    plt.title(title)
    plt.xlabel("Tiempo")
    plt.ylabel(ylabel)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=140)
    plt.close()
    return output_path


def generate_sleep_night_charts(sleep_day_dir):
    series_path = os.path.join(sleep_day_dir, "sleep_series.json")
    if not os.path.exists(series_path):
        return []

    series = load_json(series_path)
    charts_dir = ensure_dir(os.path.join(sleep_day_dir, "charts"))
    chart_files = []

    hr = series.get("heart_rate", [])
    if hr:
        x = [parse_ts(p["ts"]) for p in hr]
        y = [p["value"] for p in hr]
        out = plot_single_series(x, y, "Frecuencia cardiaca durante el sueño", "HR", os.path.join(charts_dir, "sleep_hr.png"))
        if out:
            chart_files.append(out)

    stress = series.get("stress", [])
    if stress:
        x = [parse_ts(p["ts"]) for p in stress]
        y = [p["value"] for p in stress]
        out = plot_single_series(x, y, "Estrés nocturno", "Stress", os.path.join(charts_dir, "sleep_stress.png"))
        if out:
            chart_files.append(out)

    bb = series.get("body_battery", [])
    if bb:
        x = [parse_ts(p["ts"]) for p in bb]
        y = [p["value"] for p in bb]
        out = plot_single_series(x, y, "Body Battery durante el sueño", "Body Battery", os.path.join(charts_dir, "sleep_body_battery.png"))
        if out:
            chart_files.append(out)

    respiration = series.get("respiration", [])
    if respiration:
        x = [parse_ts(p["ts"]) for p in respiration]
        y = [p["value"] for p in respiration]
        out = plot_single_series(x, y, "Respiración nocturna", "Respiration", os.path.join(charts_dir, "sleep_respiration.png"))
        if out:
            chart_files.append(out)

    spo2 = series.get("spo2", [])
    if spo2:
        x = [parse_ts(p["ts"]) for p in spo2]
        y = [p["value"] for p in spo2]
        out = plot_single_series(x, y, "SpO2 nocturna", "SpO2", os.path.join(charts_dir, "sleep_spo2.png"))
        if out:
            chart_files.append(out)

    movement = series.get("movement", [])
    if movement:
        x = [parse_ts(p["ts"]) for p in movement]
        y = [p["value"] for p in movement]
        out = plot_single_series(x, y, "Movimiento durante el sueño", "Movement", os.path.join(charts_dir, "sleep_movement.png"))
        if out:
            chart_files.append(out)

    if hr and stress and bb:
        min_len = min(len(hr), len(stress), len(bb))
        x = [parse_ts(hr[i]["ts"]) for i in range(min_len)]

        hr_y = [hr[i]["value"] for i in range(min_len)]
        stress_y = [stress[i]["value"] for i in range(min_len)]
        bb_y = [bb[i]["value"] for i in range(min_len)]

        def normalize(arr):
            if not arr:
                return arr
            lo = min(arr)
            hi = max(arr)
            if hi == lo:
                return [50 for _ in arr]
            return [((v - lo) / (hi - lo)) * 100 for v in arr]

        out = plot_multi_series(
            x,
            {
                "HR_norm": normalize(hr_y),
                "Stress_norm": normalize(stress_y),
                "BodyBattery_norm": normalize(bb_y),
            },
            "Curva combinada de recuperación nocturna",
            "Escala normalizada",
            os.path.join(charts_dir, "sleep_recovery_combined.png")
        )
        if out:
            chart_files.append(out)

    return chart_files


def generate_sleep_history_charts(sleep_history_dir):
    history_path = os.path.join(sleep_history_dir, "sleep_history.json")
    if not os.path.exists(history_path):
        return []

    history = load_json(history_path)
    if not history:
        return []

    charts_dir = ensure_dir(os.path.join(sleep_history_dir, "charts"))
    chart_files = []
    x = [h["calendar_date"] for h in history]

    def plot_history(metric, title, ylabel, filename):
        y = [h.get(metric) for h in history]
        if not y:
            return None

        plt.figure(figsize=(12, 4))
        plt.plot(x, y, marker="o")
        plt.title(title)
        plt.xlabel("Fecha")
        plt.ylabel(ylabel)
        plt.xticks(rotation=45)
        plt.tight_layout()
        out = os.path.join(charts_dir, filename)
        plt.savefig(out, dpi=140)
        plt.close()
        return out

    files_to_make = [
        ("overall_recovery_score", "Tendencia de recuperación global", "Recovery Score", "overall_recovery_trend.png"),
        ("avg_overnight_hrv", "Tendencia de HRV nocturna", "HRV", "hrv_trend.png"),
        ("deep_ratio", "Tendencia de sueño profundo", "Deep Ratio", "deep_ratio_trend.png"),
        ("rem_ratio", "Tendencia de REM", "REM Ratio", "rem_ratio_trend.png"),
        ("min_spo2", "Tendencia de SpO2 mínima", "Min SpO2", "min_spo2_trend.png"),
        ("circadian_alignment_score", "Tendencia de alineación circadiana", "Alignment Score", "circadian_alignment_trend.png"),
        ("recharge_efficiency", "Tendencia de recarga nocturna", "Recharge Efficiency", "recharge_efficiency_trend.png"),
        ("avg_sleep_stress", "Tendencia de estrés nocturno", "Sleep Stress", "sleep_stress_trend.png"),
    ]

    for metric, title, ylabel, filename in files_to_make:
        out = plot_history(metric, title, ylabel, filename)
        if out:
            chart_files.append(out)

    deep = [h.get("deep_ratio") for h in history]
    rem = [h.get("rem_ratio") for h in history]
    if deep and rem:
        plt.figure(figsize=(12, 4))
        plt.plot(x, deep, marker="o", label="Deep Ratio")
        plt.plot(x, rem, marker="o", label="REM Ratio")
        plt.title("Deep vs REM a lo largo del tiempo")
        plt.xlabel("Fecha")
        plt.ylabel("Ratio")
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        out = os.path.join(charts_dir, "deep_vs_rem_trend.png")
        plt.savefig(out, dpi=140)
        plt.close()
        chart_files.append(out)

    return chart_files