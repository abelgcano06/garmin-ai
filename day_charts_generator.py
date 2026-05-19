import json
import os
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# =========================
# Global chart style
# =========================

plt.rcParams["figure.figsize"] = (14, 6)
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.18
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False
plt.rcParams["axes.titleweight"] = "bold"
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["axes.labelsize"] = 10
plt.rcParams["legend.frameon"] = False


# =========================
# Utils
# =========================

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
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_series(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return []

    vmin = min(vals)
    vmax = max(vals)

    if vmax == vmin:
        return [50.0 if isinstance(v, (int, float)) else None for v in values]

    out = []
    for v in values:
        if not isinstance(v, (int, float)):
            out.append(None)
        else:
            out.append(((v - vmin) / (vmax - vmin)) * 100.0)
    return out


def extract_xy(series):
    x = []
    y = []
    for p in series:
        if not isinstance(p, dict):
            continue
        ts = parse_ts(p.get("ts"))
        value = p.get("value")
        if ts and isinstance(value, (int, float)):
            x.append(ts)
            y.append(float(value))
    return x, y


def save_plot(output_path):
    plt.tight_layout()
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()
    return output_path


def format_time_axis(ax):
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=10))


def compute_esi_from_history_row(row):
    energy = float(row.get("energy_dynamics_score", 0) or 0)
    nervous = float(row.get("nervous_system_load_score", 0) or 0)
    stress = float(row.get("stress_behavior_score", 0) or 0)
    recovery = float(row.get("recovery_response_score", 0) or 0)
    respiratory = float(row.get("respiratory_behavior_score", 0) or 0)

    esi = (
        energy * 0.40 +
        nervous * 0.20 +
        stress * 0.15 +
        recovery * 0.15 +
        respiratory * 0.10
    )
    return round(esi, 1)


# =========================
# Detection helpers
# =========================

def detect_stress_spikes(stress_series, jump_threshold=18):
    spikes = []
    x, y = extract_xy(stress_series)
    for i in range(1, len(y)):
        if (y[i] - y[i - 1]) >= jump_threshold:
            spikes.append((x[i], y[i]))
    return spikes


def detect_stress_downshifts(stress_series, min_drop=15, high_level=55, low_level=35):
    downshifts = []
    x, y = extract_xy(stress_series)
    for i in range(1, len(y)):
        delta = y[i - 1] - y[i]
        if y[i - 1] >= high_level and y[i] <= low_level and delta >= min_drop:
            downshifts.append((x[i], y[i]))
    return downshifts


def detect_bb_crashes(bb_series, drop_threshold=6):
    crashes = []
    x, y = extract_xy(bb_series)
    for i in range(1, len(y)):
        delta = y[i] - y[i - 1]
        if delta <= -drop_threshold:
            crashes.append((x[i], y[i]))
    return crashes


def detect_bb_recharges(bb_series, gain_threshold=4):
    recharges = []
    x, y = extract_xy(bb_series)
    for i in range(1, len(y)):
        delta = y[i] - y[i - 1]
        if delta >= gain_threshold:
            recharges.append((x[i], y[i]))
    return recharges


# =========================
# Visual helpers
# =========================

def add_header(ax, title, subtitle=None):
    ax.set_title(title, loc="left")
    if subtitle:
        ax.text(
            0.0, 1.02, subtitle,
            transform=ax.transAxes,
            fontsize=9,
            alpha=0.8
        )


def annotate_points(ax, points, label_prefix, y_offset=4, max_points=5):
    for i, (x, y) in enumerate(points[:max_points], start=1):
        ax.annotate(
            f"{label_prefix} {i}",
            xy=(x, y),
            xytext=(0, y_offset),
            textcoords="offset points",
            fontsize=8,
            alpha=0.9
        )


def shade_energy_risk(ax, x, y):
    if not x or not y:
        return

    for i in range(1, len(y)):
        if y[i] <= 35:
            ax.axvspan(x[i - 1], x[i], alpha=0.08)


def shade_stress_risk(ax, x, y):
    if not x or not y:
        return

    for i in range(1, len(y)):
        if y[i] >= 70:
            ax.axvspan(x[i - 1], x[i], alpha=0.07)


# =========================
# Day charts
# =========================

def plot_day_state_curve(series, analysis, findings, charts_dir):
    hr = series.get("hr", [])
    stress = series.get("stress", [])
    bb = series.get("body_battery", [])
    respiration = series.get("respiration", [])

    hr_x, hr_y = extract_xy(hr)
    st_x, st_y = extract_xy(stress)
    bb_x, bb_y = extract_xy(bb)
    rp_x, rp_y = extract_xy(respiration)

    if not any([hr_y, st_y, bb_y, rp_y]):
        return None

    overall = analysis.get("recovery_summary", {}).get("overall_day_state_score", 0)
    primary = findings.get("limiters", {}).get("primary_limiter", "unknown")

    fig, ax = plt.subplots()

    if hr_y:
        ax.plot(hr_x, normalize_series(hr_y), linewidth=1.7, label="HR")
    if st_y:
        ax.plot(st_x, normalize_series(st_y), linewidth=1.7, label="Estrés")
    if bb_y:
        ax.plot(bb_x, normalize_series(bb_y), linewidth=2.2, label="Body Battery")
    if rp_y:
        ax.plot(rp_x, normalize_series(rp_y), linewidth=1.5, linestyle="--", label="Respiración")

    add_header(
        ax,
        "Curva integrada del estado del día",
        f"Score global: {overall:.1f} | Limitante principal: {primary}"
    )

    ax.set_xlabel("Hora")
    ax.set_ylabel("Escala normalizada (0–100)")
    ax.set_ylim(0, 105)
    format_time_axis(ax)
    ax.legend(ncol=4, loc="upper right")

    return save_plot(os.path.join(charts_dir, "day_state_curve.png"))


def plot_energy_timeline(series, analysis, charts_dir):
    bb = series.get("body_battery", [])
    x, y = extract_xy(bb)

    if not y:
        return None

    crashes = detect_bb_crashes(bb)
    recharges = detect_bb_recharges(bb)

    energy = analysis.get("energy_dynamics", {})
    start = energy.get("body_battery_start")
    end = energy.get("body_battery_end")
    min_bb = energy.get("body_battery_min")
    max_bb = energy.get("body_battery_max")
    score = energy.get("energy_dynamics_score", 0)

    fig, ax = plt.subplots()

    ax.plot(x, y, linewidth=2.6, label="Body Battery")
    shade_energy_risk(ax, x, y)

    if crashes:
        ax.scatter([p[0] for p in crashes], [p[1] for p in crashes], marker="x", s=70, label="Crash")
        annotate_points(ax, crashes, "Crash", y_offset=6)

    if recharges:
        ax.scatter([p[0] for p in recharges], [p[1] for p in recharges], marker="o", s=45, label="Recarga")
        annotate_points(ax, recharges, "Recarga", y_offset=-12)

    add_header(
        ax,
        "Línea de energía del día",
        f"Inicio: {start} | Fin: {end} | Min: {min_bb} | Max: {max_bb} | Score energía: {score}"
    )

    ax.set_xlabel("Hora")
    ax.set_ylabel("Body Battery")
    format_time_axis(ax)
    ax.legend(loc="upper right")

    return save_plot(os.path.join(charts_dir, "energy_timeline.png"))


def plot_stress_recovery_overlay(series, analysis, charts_dir):
    stress = series.get("stress", [])
    x, y = extract_xy(stress)

    if not y:
        return None

    spikes = detect_stress_spikes(stress)
    downshifts = detect_stress_downshifts(stress)

    recovery = analysis.get("recovery_response", {})
    stress_block = analysis.get("stress_behavior", {})
    score = recovery.get("recovery_response_score", 0)

    fig, ax = plt.subplots()

    ax.plot(x, y, linewidth=2.1, label="Estrés")
    shade_stress_risk(ax, x, y)

    if spikes:
        ax.scatter([p[0] for p in spikes], [p[1] for p in spikes], marker="^", s=60, label="Spike")
        annotate_points(ax, spikes, "Spike", y_offset=6)

    if downshifts:
        ax.scatter([p[0] for p in downshifts], [p[1] for p in downshifts], marker="v", s=60, label="Downshift")
        annotate_points(ax, downshifts, "Down", y_offset=-12)

    add_header(
        ax,
        "Estrés y respuesta de recuperación",
        f"Avg estrés: {stress_block.get('avg_stress', 0)} | Score recovery: {score} | Downshifts: {recovery.get('downshift_count', 0)}"
    )

    ax.set_xlabel("Hora")
    ax.set_ylabel("Estrés")
    format_time_axis(ax)
    ax.legend(loc="upper right")

    return save_plot(os.path.join(charts_dir, "stress_recovery_overlay.png"))


def plot_segment_comparison(series, analysis, charts_dir):
    segments = series.get("segments", {})
    respiratory = analysis.get("respiratory_behavior", {})
    avg_resp = respiratory.get("avg_respiration", 0)

    labels = ["morning", "afternoon", "evening"]
    display_labels = ["Mañana", "Tarde", "Noche"]

    hr_vals = [segments.get(s, {}).get("hr", {}).get("avg", 0) for s in labels]
    stress_vals = [segments.get(s, {}).get("stress", {}).get("avg", 0) for s in labels]
    bb_vals = [segments.get(s, {}).get("body_battery", {}).get("avg", 0) for s in labels]
    resp_vals = [avg_resp, avg_resp, avg_resp]

    x = range(len(labels))
    width = 0.18

    fig, ax = plt.subplots()

    ax.bar([i - 1.5 * width for i in x], hr_vals, width=width, label="HR avg")
    ax.bar([i - 0.5 * width for i in x], stress_vals, width=width, label="Estrés avg")
    ax.bar([i + 0.5 * width for i in x], bb_vals, width=width, label="BB avg")
    ax.bar([i + 1.5 * width for i in x], resp_vals, width=width, label="Resp avg")

    add_header(
        ax,
        "Comparación por segmentos del día",
        "Sirve para detectar en qué bloque del día se rompe el sistema"
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(display_labels)
    ax.set_xlabel("Segmento")
    ax.set_ylabel("Promedio")
    ax.legend(ncol=4, loc="upper right")

    return save_plot(os.path.join(charts_dir, "segment_comparison.png"))


def generate_day_charts(day_day_dir):
    series_path = os.path.join(day_day_dir, "day_series.json")
    analysis_path = os.path.join(day_day_dir, "day_analysis.json")
    findings_path = os.path.join(day_day_dir, "day_findings.json")

    if not os.path.exists(series_path) or not os.path.exists(analysis_path):
        return []

    series = load_json(series_path)
    analysis = load_json(analysis_path)
    findings = load_json(findings_path) if os.path.exists(findings_path) else {}

    charts_dir = ensure_dir(os.path.join(day_day_dir, "charts"))
    chart_files = []

    builders = [
        lambda: plot_day_state_curve(series, analysis, findings, charts_dir),
        lambda: plot_energy_timeline(series, analysis, charts_dir),
        lambda: plot_stress_recovery_overlay(series, analysis, charts_dir),
        lambda: plot_segment_comparison(series, analysis, charts_dir),
    ]

    for fn in builders:
        try:
            out = fn()
            if out:
                chart_files.append(out)
        except Exception:
            pass

    return chart_files


# =========================
# History charts
# =========================

def plot_day_7day_trends(history, charts_dir):
    if not history:
        return None

    recent = history[-7:] if len(history) >= 7 else history
    x = [h["calendar_date"] for h in recent]

    overall = [h.get("overall_day_state_score") for h in recent]
    energy = [h.get("energy_dynamics_score") for h in recent]
    recovery = [h.get("recovery_response_score") for h in recent]
    respiratory = [h.get("respiratory_behavior_score") for h in recent]
    esi = [compute_esi_from_history_row(h) for h in recent]

    fig, ax = plt.subplots()
    ax.plot(x, overall, marker="o", linewidth=2.0, label="Overall")
    ax.plot(x, energy, marker="o", linewidth=2.0, label="Energy")
    ax.plot(x, recovery, marker="o", linewidth=2.0, label="Recovery")
    ax.plot(x, respiratory, marker="o", linewidth=2.0, label="Respiratory")
    ax.plot(x, esi, marker="o", linewidth=2.4, linestyle="--", label="ESI")

    ax.axhline(40, linestyle="--", alpha=0.45)
    ax.axhline(60, linestyle="--", alpha=0.30)

    add_header(
        ax,
        "Tendencias de los últimos 7 días",
        "Incluye score global, energía, recuperación, respiración y ESI"
    )

    ax.set_xlabel("Fecha")
    ax.set_ylabel("Score")
    plt.xticks(rotation=45)
    ax.legend(ncol=5, loc="upper right")

    return save_plot(os.path.join(charts_dir, "day_7day_trends.png"))


def generate_day_history_charts(day_history_dir):
    history_path = os.path.join(day_history_dir, "day_history.json")
    if not os.path.exists(history_path):
        return []

    history = load_json(history_path)
    if not history:
        return []

    charts_dir = ensure_dir(os.path.join(day_history_dir, "charts"))
    chart_files = []

    try:
        out = plot_day_7day_trends(history, charts_dir)
        if out:
            chart_files.append(out)
    except Exception:
        pass

    return chart_files