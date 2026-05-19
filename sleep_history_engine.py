import json
import os
from glob import glob
from statistics import mean, median


def _is_sleep_valid(analysis):
    """
    Filtra noches sin datos reales de sueño.
    Si sleep_time_seconds < 3600, el día no entra al historial.
    """
    sleep_time_seconds = analysis.get("sleep_window", {}).get("sleep_time_seconds", 0)
    return sleep_time_seconds >= 3600


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_mean(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(mean(vals), 4) if vals else 0.0


def safe_median(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(median(vals), 4) if vals else 0.0


def pct_diff(value, baseline):
    if baseline in (0, None):
        return 0.0
    return round(((value - baseline) / baseline) * 100.0, 2)


def trend_label(recent_avg, older_avg, positive_is_good=True, tolerance=3.0):
    diff = recent_avg - older_avg
    if abs(diff) <= tolerance:
        return "stable"
    if positive_is_good:
        return "improving" if diff > 0 else "worsening"
    return "improving" if diff < 0 else "worsening"


def load_sleep_days(base_sleep_dir):
    analysis_files = sorted(glob(os.path.join(base_sleep_dir, "*", "sleep_analysis.json")))
    findings_files = sorted(glob(os.path.join(base_sleep_dir, "*", "sleep_findings.json")))
    brief_files = sorted(glob(os.path.join(base_sleep_dir, "*", "sleep_brief.json")))

    days = {}

    for path in analysis_files:
        date_str = os.path.basename(os.path.dirname(path))
        days.setdefault(date_str, {})
        days[date_str]["analysis"] = load_json(path)

    for path in findings_files:
        date_str = os.path.basename(os.path.dirname(path))
        days.setdefault(date_str, {})
        days[date_str]["findings"] = load_json(path)

    for path in brief_files:
        date_str = os.path.basename(os.path.dirname(path))
        days.setdefault(date_str, {})
        days[date_str]["brief"] = load_json(path)

    ordered = []
    for date_str in sorted(days.keys()):
        row = {"calendar_date": date_str}
        row.update(days[date_str])
        ordered.append(row)

    return ordered


def build_sleep_history(days):
    history = []
    skipped = 0

    for d in days:
        analysis = d.get("analysis", {})
        findings = d.get("findings", {})
        brief = d.get("brief", {})

        if not analysis:
            continue

        # Filtro de calidad: noches con < 1 hora de sueño no entran al historial
        if not _is_sleep_valid(analysis):
            skipped += 1
            continue

        history.append({
            "calendar_date": d["calendar_date"],

            "overall_recovery_score": analysis["recovery_summary"]["overall_recovery_score"],
            "physical_recovery_score": analysis["recovery_summary"]["physical_recovery_score"],
            "neural_recovery_score": analysis["recovery_summary"]["neural_recovery_score"],

            "autonomic_recovery_curve_score": analysis["autonomic_recovery"]["autonomic_recovery_curve_score"],
            "avg_overnight_hrv": analysis["autonomic_recovery"]["avg_overnight_hrv"],
            "hrv_recovery_score": analysis["autonomic_recovery"]["hrv_recovery_score"],
            "hrv_ramp_score": analysis["autonomic_recovery"]["hrv_ramp_score"],
            "hrv_first_half": analysis["autonomic_recovery"].get("hrv_first_half"),
            "hrv_second_half": analysis["autonomic_recovery"].get("hrv_second_half"),

            "sleep_efficiency": analysis["sleep_window"]["sleep_efficiency"],
            "sleep_time_seconds": analysis["sleep_window"]["sleep_time_seconds"],

            "deep_ratio": analysis["sleep_architecture"]["deep_ratio"],
            "rem_ratio": analysis["sleep_architecture"]["rem_ratio"],
            "fragmentation_index": analysis["sleep_architecture"]["fragmentation_index"],
            "movement_index": analysis["sleep_architecture"]["movement_index"],
            "stage_transition_count": analysis["sleep_architecture"].get("stage_transition_count"),
            "architecture_stability_score": analysis["sleep_architecture"].get("architecture_stability_score"),
            "early_window_deep_ratio": analysis["sleep_architecture"].get("early_window_deep_ratio"),
            "late_window_rem_ratio": analysis["sleep_architecture"].get("late_window_rem_ratio"),

            "avg_sleep_stress": analysis["stress_recovery"]["avg_sleep_stress"],
            "stress_load_score": analysis["stress_recovery"]["stress_load_score"],
            "stress_spike_count": analysis["stress_recovery"].get("stress_spike_count"),

            "avg_respiration": analysis["respiratory_recovery"]["avg_respiration"],
            "respiration_variability": analysis["respiratory_recovery"]["respiration_variability"],
            "respiratory_stability_score": analysis["respiratory_recovery"]["respiratory_stability_score"],
            "respiratory_irregularity_score": analysis["respiratory_recovery"].get("respiratory_irregularity_score"),

            "avg_spo2": analysis["oxygenation"]["avg_spo2"],
            "min_spo2": analysis["oxygenation"]["min_spo2"],
            "oxygen_stability_score": analysis["oxygenation"]["oxygen_stability_score"],
            "spo2_drop_count": analysis["oxygenation"].get("spo2_drop_count"),
            "spo2_drop_depth_avg": analysis["oxygenation"].get("spo2_drop_depth_avg"),

            "recharge_efficiency": analysis["energy_recharge"]["recharge_efficiency"],
            "body_battery_change": analysis["energy_recharge"]["body_battery_change"],
            "body_battery_recharge_velocity": analysis["energy_recharge"].get("body_battery_recharge_velocity"),
            "bb_gain_first_half": analysis["energy_recharge"].get("bb_gain_first_half"),
            "bb_gain_second_half": analysis["energy_recharge"].get("bb_gain_second_half"),

            "circadian_alignment_score": analysis["circadian_alignment"]["circadian_alignment_score"],
            "sleep_alignment_status": analysis["circadian_alignment"]["sleep_alignment_status"],
            "sleep_midpoint_minutes": analysis["circadian_alignment"].get("sleep_midpoint_minutes"),

            "sleep_need_gap_minutes": analysis["sleep_need"]["sleep_need_gap_minutes"],

            "micro_arousal_score": analysis["instability_markers"].get("micro_arousal_score"),
            "overnight_instability_score": analysis["instability_markers"].get("overnight_instability_score"),
            "movement_spike_count": analysis["instability_markers"].get("movement_spike_count"),

            "primary_limiter": findings.get("limiters", {}).get("primary_limiter", ""),
            "secondary_limiter": findings.get("limiters", {}).get("secondary_limiter", ""),
            "headline": brief.get("headline", "")
        })

    if skipped > 0:
        print(f"  [sleep_history] {skipped} noches con < 1h de sueño excluidas del historial")

    return history


def build_sleep_baselines(history):
    if not history:
        return {}

    metrics = [
        "overall_recovery_score",
        "physical_recovery_score",
        "neural_recovery_score",
        "autonomic_recovery_curve_score",
        "avg_overnight_hrv",
        "sleep_efficiency",
        "sleep_time_seconds",
        "deep_ratio",
        "rem_ratio",
        "fragmentation_index",
        "movement_index",
        "stage_transition_count",
        "architecture_stability_score",
        "early_window_deep_ratio",
        "late_window_rem_ratio",
        "avg_sleep_stress",
        "stress_load_score",
        "respiratory_stability_score",
        "respiratory_irregularity_score",
        "avg_spo2",
        "min_spo2",
        "spo2_drop_count",
        "recharge_efficiency",
        "body_battery_change",
        "circadian_alignment_score",
        "sleep_need_gap_minutes",
        "micro_arousal_score",
        "overnight_instability_score"
    ]

    baseline = {
        "window_days": len(history),
        "metrics": {}
    }

    for metric in metrics:
        vals = [x.get(metric) for x in history if isinstance(x.get(metric), (int, float))]
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        p25 = round(sorted_vals[max(0, int(n * 0.25) - 1)], 4) if n > 0 else 0.0
        baseline["metrics"][metric] = {
            "mean": safe_mean(vals),
            "median": safe_median(vals),
            "p25": p25,
            "min": round(min(vals), 4) if vals else 0.0,
            "max": round(max(vals), 4) if vals else 0.0
        }

    return baseline


def build_sleep_trends(history):
    if not history:
        return {}

    recent = history[-3:] if len(history) >= 3 else history
    baseline = history[-7:] if len(history) >= 7 else history
    older = history[-14:-7] if len(history) >= 14 else history[:-len(recent)] if len(history) > len(recent) else history

    metrics = {
        "overall_recovery_score": {"positive_is_good": True},
        "physical_recovery_score": {"positive_is_good": True},
        "neural_recovery_score": {"positive_is_good": True},
        "autonomic_recovery_curve_score": {"positive_is_good": True},
        "avg_overnight_hrv": {"positive_is_good": True},
        "sleep_efficiency": {"positive_is_good": True},
        "sleep_time_seconds": {"positive_is_good": True},
        "deep_ratio": {"positive_is_good": True},
        "rem_ratio": {"positive_is_good": True},
        "fragmentation_index": {"positive_is_good": False},
        "movement_index": {"positive_is_good": False},
        "architecture_stability_score": {"positive_is_good": True},
        "avg_sleep_stress": {"positive_is_good": False},
        "respiratory_stability_score": {"positive_is_good": True},
        "min_spo2": {"positive_is_good": True},
        "spo2_drop_count": {"positive_is_good": False},
        "recharge_efficiency": {"positive_is_good": True},
        "circadian_alignment_score": {"positive_is_good": True},
        "sleep_need_gap_minutes": {"positive_is_good": False},
        "micro_arousal_score": {"positive_is_good": False},
        "overnight_instability_score": {"positive_is_good": False},
    }

    trends = {}

    for metric, cfg in metrics.items():
        recent_avg = safe_mean([x.get(metric) for x in recent])
        baseline_avg = safe_mean([x.get(metric) for x in baseline])
        older_avg = safe_mean([x.get(metric) for x in older])

        trends[metric] = {
            "recent_avg": recent_avg,
            "baseline_avg": baseline_avg,
            "older_avg": older_avg,
            "trend_vs_baseline": trend_label(
                recent_avg,
                baseline_avg,
                positive_is_good=cfg["positive_is_good"]
            ),
            "trend_vs_older": trend_label(
                recent_avg,
                older_avg,
                positive_is_good=cfg["positive_is_good"]
            )
        }

    return trends


def build_sleep_anomalies(history, baselines):
    if not history or not baselines:
        return {"anomalies": []}

    baseline_metrics = baselines.get("metrics", {})
    anomalies = []

    checks = [
        ("avg_overnight_hrv", "low_hrv_anomaly", -15, True),
        ("deep_ratio", "low_deep_sleep_anomaly", -20, True),
        ("rem_ratio", "low_rem_sleep_anomaly", -20, True),
        ("min_spo2", "low_spo2_anomaly", -3, True),
        ("circadian_alignment_score", "low_circadian_alignment_anomaly", -15, True),
        ("overall_recovery_score", "low_recovery_anomaly", -12, True),
        ("fragmentation_index", "high_fragmentation_anomaly", 20, False),
        ("avg_sleep_stress", "high_sleep_stress_anomaly", 20, False),
        ("sleep_need_gap_minutes", "high_sleep_need_gap_anomaly", 20, False),
        ("micro_arousal_score", "high_micro_arousal_anomaly", 20, False),
        ("spo2_drop_count", "high_spo2_drop_count_anomaly", 25, False),
    ]

    for row in history:
        row_anomalies = []

        for metric, code, threshold, lower_is_bad_relative in checks:
            value = row.get(metric)
            baseline = baseline_metrics.get(metric, {}).get("median")

            if not isinstance(value, (int, float)) or not isinstance(baseline, (int, float)):
                continue

            diff = pct_diff(value, baseline)

            if lower_is_bad_relative:
                if diff <= threshold:
                    row_anomalies.append({
                        "code": code,
                        "metric": metric,
                        "value": round(value, 4),
                        "baseline_median": round(baseline, 4),
                        "pct_diff_vs_baseline": diff
                    })
            else:
                if diff >= threshold:
                    row_anomalies.append({
                        "code": code,
                        "metric": metric,
                        "value": round(value, 4),
                        "baseline_median": round(baseline, 4),
                        "pct_diff_vs_baseline": diff
                    })

        anomalies.append({
            "calendar_date": row["calendar_date"],
            "anomalies": row_anomalies
        })

    return {"anomalies": anomalies}


def classify_bottleneck(row):
    scores = {
        "circadian_bottleneck": 0,
        "autonomic_bottleneck": 0,
        "neural_bottleneck": 0,
        "respiratory_bottleneck": 0,
        "sleep_quantity_bottleneck": 0,
        "sleep_continuity_bottleneck": 0,
    }

    if row.get("circadian_alignment_score", 100) < 60:
        scores["circadian_bottleneck"] += 3
    if row.get("sleep_alignment_status", "") in ["BEHIND", "NOT_ALIGNED", "AHEAD"]:
        scores["circadian_bottleneck"] += 2

    if row.get("avg_overnight_hrv", 999) < 45:
        scores["autonomic_bottleneck"] += 3
    if row.get("autonomic_recovery_curve_score", 100) < 60:
        scores["autonomic_bottleneck"] += 3
    if row.get("avg_sleep_stress", 0) > 20:
        scores["autonomic_bottleneck"] += 2

    if row.get("rem_ratio", 1) < 0.18:
        scores["neural_bottleneck"] += 3
    if row.get("neural_recovery_score", 100) < 60:
        scores["neural_bottleneck"] += 2

    if row.get("min_spo2", 100) < 88:
        scores["respiratory_bottleneck"] += 4
    if row.get("respiratory_stability_score", 100) < 60:
        scores["respiratory_bottleneck"] += 2
    if row.get("spo2_drop_count", 0) >= 2:
        scores["respiratory_bottleneck"] += 2

    if row.get("sleep_time_seconds", 999999) < 6 * 3600:
        scores["sleep_quantity_bottleneck"] += 4
    if row.get("sleep_need_gap_minutes", 0) > 60:
        scores["sleep_quantity_bottleneck"] += 2

    if row.get("fragmentation_index", 0) > 0.30:
        scores["sleep_continuity_bottleneck"] += 3
    if row.get("movement_index", 0) > 1.5:
        scores["sleep_continuity_bottleneck"] += 2
    if row.get("micro_arousal_score", 0) > 35:
        scores["sleep_continuity_bottleneck"] += 2

    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = ordered[0][0] if ordered else ""
    secondary = ordered[1][0] if len(ordered) > 1 else ""

    return {
        "scores": scores,
        "primary_bottleneck": primary,
        "secondary_bottleneck": secondary
    }


def build_sleep_bottlenecks(history):
    if not history:
        return {"daily_bottlenecks": [], "aggregate": {}}

    daily = []
    aggregate_counts = {}

    for row in history:
        result = classify_bottleneck(row)
        primary = result["primary_bottleneck"]

        if primary:
            aggregate_counts[primary] = aggregate_counts.get(primary, 0) + 1

        daily.append({
            "calendar_date": row["calendar_date"],
            "primary_bottleneck": result["primary_bottleneck"],
            "secondary_bottleneck": result["secondary_bottleneck"],
            "scores": result["scores"]
        })

    aggregate = {
        "counts": aggregate_counts,
        "dominant_bottleneck": max(aggregate_counts, key=aggregate_counts.get) if aggregate_counts else ""
    }

    return {
        "daily_bottlenecks": daily,
        "aggregate": aggregate
    }


def assign_pattern_cluster(row):
    if row.get("min_spo2", 100) < 88 and (
        row.get("respiratory_stability_score", 100) < 60 or row.get("spo2_drop_count", 0) >= 2
    ):
        return "respiratory_strain_cluster"

    if row.get("sleep_time_seconds", 999999) < 6 * 3600 and row.get("sleep_efficiency", 0) >= 0.90:
        return "short_but_efficient_cluster"

    if row.get("circadian_alignment_score", 100) < 60 and row.get("rem_ratio", 1) < 0.18:
        return "circadian_disruption_cluster"

    if row.get("avg_overnight_hrv", 999) < 45 and row.get("avg_sleep_stress", 0) > 20:
        return "autonomic_strain_cluster"

    if row.get("deep_ratio", 1) < 0.16 and row.get("rem_ratio", 1) < 0.18:
        return "architecture_deficit_cluster"

    return "balanced_or_mixed_cluster"


def build_sleep_pattern_clusters(history):
    if not history:
        return {"daily_clusters": [], "cluster_counts": {}}

    daily_clusters = []
    cluster_counts = {}

    for row in history:
        cluster = assign_pattern_cluster(row)
        cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

        daily_clusters.append({
            "calendar_date": row["calendar_date"],
            "cluster": cluster
        })

    return {
        "daily_clusters": daily_clusters,
        "cluster_counts": cluster_counts,
        "dominant_cluster": max(cluster_counts, key=cluster_counts.get) if cluster_counts else ""
    }


def build_sleep_patterns(history, bottlenecks=None, clusters=None):
    if not history:
        return {
            "recurrent_patterns": [],
            "limiter_counts": {},
            "risk_counts": {}
        }

    recurrent_patterns = []
    limiter_counts = {}
    low_spo2_count = 0
    low_deep_count = 0
    low_rem_count = 0
    poor_circadian_count = 0
    low_hrv_count = 0
    high_stress_count = 0
    high_fragmentation_count = 0
    high_spo2_drop_nights = 0

    for h in history:
        primary = h.get("primary_limiter", "")
        if primary:
            limiter_counts[primary] = limiter_counts.get(primary, 0) + 1

        if h.get("min_spo2", 999) < 88:
            low_spo2_count += 1
        if h.get("deep_ratio", 1) < 0.16:
            low_deep_count += 1
        if h.get("rem_ratio", 1) < 0.20:
            low_rem_count += 1
        if h.get("circadian_alignment_score", 100) < 60:
            poor_circadian_count += 1
        if h.get("avg_overnight_hrv", 999) < 45:
            low_hrv_count += 1
        if h.get("avg_sleep_stress", 0) > 20:
            high_stress_count += 1
        if h.get("fragmentation_index", 0) > 0.30:
            high_fragmentation_count += 1
        if h.get("spo2_drop_count", 0) >= 2:
            high_spo2_drop_nights += 1

    n = len(history)
    trigger = max(2, n // 3)

    if low_spo2_count >= 2:
        recurrent_patterns.append({
            "code": "recurrent_low_oxygen_nadir",
            "count": low_spo2_count,
            "severity": "high" if low_spo2_count >= 4 else "moderate",
            "description": "Repeated low overnight oxygen nadirs were detected."
        })

    if high_spo2_drop_nights >= trigger:
        recurrent_patterns.append({
            "code": "recurrent_oxygen_drop_pattern",
            "count": high_spo2_drop_nights,
            "severity": "moderate",
            "description": "Multiple nights showed repeated oxygen drops."
        })

    if low_deep_count >= trigger:
        recurrent_patterns.append({
            "code": "chronic_low_deep_sleep",
            "count": low_deep_count,
            "severity": "moderate",
            "description": "Deep sleep was frequently below preferred range."
        })

    if low_rem_count >= trigger:
        recurrent_patterns.append({
            "code": "chronic_low_rem_sleep",
            "count": low_rem_count,
            "severity": "moderate",
            "description": "REM contribution was repeatedly below preferred range."
        })

    if poor_circadian_count >= trigger:
        recurrent_patterns.append({
            "code": "chronic_circadian_misalignment",
            "count": poor_circadian_count,
            "severity": "moderate",
            "description": "Sleep timing was frequently misaligned."
        })

    if low_hrv_count >= trigger:
        recurrent_patterns.append({
            "code": "recurrent_low_hrv_nights",
            "count": low_hrv_count,
            "severity": "moderate",
            "description": "HRV was repeatedly on the low side across several nights."
        })

    if high_stress_count >= trigger:
        recurrent_patterns.append({
            "code": "chronic_high_sleep_stress",
            "count": high_stress_count,
            "severity": "moderate",
            "description": "Nocturnal stress remained elevated across multiple nights."
        })

    if high_fragmentation_count >= trigger:
        recurrent_patterns.append({
            "code": "recurrent_fragmented_sleep",
            "count": high_fragmentation_count,
            "severity": "moderate",
            "description": "Sleep continuity was repeatedly compromised."
        })

    return {
        "recurrent_patterns": recurrent_patterns,
        "limiter_counts": limiter_counts,
        "risk_counts": {
            "low_spo2_count": low_spo2_count,
            "high_spo2_drop_nights": high_spo2_drop_nights,
            "low_deep_count": low_deep_count,
            "low_rem_count": low_rem_count,
            "poor_circadian_count": poor_circadian_count,
            "low_hrv_count": low_hrv_count,
            "high_stress_count": high_stress_count,
            "high_fragmentation_count": high_fragmentation_count,
        },
        "dominant_bottleneck": bottlenecks.get("aggregate", {}).get("dominant_bottleneck", "") if bottlenecks else "",
        "dominant_cluster": clusters.get("dominant_cluster", "") if clusters else ""
    }


def build_sleep_longitudinal_brief(history, trends, patterns, baselines=None, anomalies=None, bottlenecks=None, clusters=None):
    if not history:
        return {
            "window_days": 0,
            "recovery_trajectory": "no_data",
            "main_strengths": [],
            "main_risks": [],
            "longitudinal_limiter": "",
            "summary": "No sleep history data available."
        }

    strengths = []
    risks = []

    if trends["overall_recovery_score"]["recent_avg"] >= 75:
        strengths.append("Recovery trend is generally solid.")
    if trends["autonomic_recovery_curve_score"]["trend_vs_baseline"] in ["stable", "improving"]:
        strengths.append("Autonomic recovery is stable or improving.")
    if trends["recharge_efficiency"]["recent_avg"] >= 70:
        strengths.append("Overnight recharge efficiency is strong.")
    if trends["architecture_stability_score"]["recent_avg"] >= 70:
        strengths.append("Sleep architecture has been reasonably stable.")

    for p in patterns["recurrent_patterns"]:
        risks.append(p["description"])

    if trends["circadian_alignment_score"]["recent_avg"] < 60:
        risks.append("Circadian alignment remains weak across recent nights.")
    if trends["avg_sleep_stress"]["trend_vs_baseline"] == "worsening":
        risks.append("Nocturnal stress trend is worsening.")
    if trends["fragmentation_index"]["trend_vs_baseline"] == "worsening":
        risks.append("Sleep fragmentation is trending worse.")
    if trends["spo2_drop_count"]["recent_avg"] >= 2:
        risks.append("Recent nights continue to show repeated oxygen drops.")

    dominant_bottleneck = bottlenecks.get("aggregate", {}).get("dominant_bottleneck", "") if bottlenecks else ""
    dominant_cluster = clusters.get("dominant_cluster", "") if clusters else ""

    if dominant_bottleneck:
        risks.append(f"Main recovery bottleneck has been {dominant_bottleneck}.")
    if dominant_cluster and dominant_cluster != "balanced_or_mixed_cluster":
        risks.append(f"Most frequent nightly pattern cluster: {dominant_cluster}.")

    limiter_counts = patterns["limiter_counts"]
    longitudinal_limiter = ""
    if limiter_counts:
        longitudinal_limiter = max(limiter_counts, key=limiter_counts.get)

    recent_recovery = trends["overall_recovery_score"]["trend_vs_baseline"]
    recent_auto = trends["autonomic_recovery_curve_score"]["trend_vs_baseline"]

    if recent_recovery == "improving" and recent_auto in ["improving", "stable"]:
        trajectory = "improving"
    elif recent_recovery == "worsening":
        trajectory = "worsening"
    else:
        trajectory = "stable"

    if not strengths:
        strengths.append("No dominant positive pattern yet.")
    if not risks:
        risks.append("No strong recurrent risk pattern detected yet.")

    summary = (
        f"Across {len(history)} nights, the recovery trajectory appears {trajectory}. "
        f"The most recurrent limiter has been {longitudinal_limiter or 'not clearly defined'}."
    )

    return {
        "window_days": len(history),
        "recovery_trajectory": trajectory,
        "main_strengths": strengths,
        "main_risks": risks,
        "longitudinal_limiter": longitudinal_limiter,
        "dominant_bottleneck": dominant_bottleneck,
        "dominant_cluster": dominant_cluster,
        "summary": summary
    }


def run_sleep_history_engine(base_sleep_dir, out_dir):
    days = load_sleep_days(base_sleep_dir)
    history = build_sleep_history(days)
    baselines = build_sleep_baselines(history)
    trends = build_sleep_trends(history)
    anomalies = build_sleep_anomalies(history, baselines)
    bottlenecks = build_sleep_bottlenecks(history)
    clusters = build_sleep_pattern_clusters(history)
    patterns = build_sleep_patterns(history, bottlenecks=bottlenecks, clusters=clusters)
    brief = build_sleep_longitudinal_brief(
        history,
        trends,
        patterns,
        baselines=baselines,
        anomalies=anomalies,
        bottlenecks=bottlenecks,
        clusters=clusters
    )

    save_json(os.path.join(out_dir, "sleep_history.json"), history)
    save_json(os.path.join(out_dir, "sleep_baselines.json"), baselines)
    save_json(os.path.join(out_dir, "sleep_trends.json"), trends)
    save_json(os.path.join(out_dir, "sleep_anomalies.json"), anomalies)
    save_json(os.path.join(out_dir, "sleep_bottlenecks.json"), bottlenecks)
    save_json(os.path.join(out_dir, "sleep_pattern_clusters.json"), clusters)
    save_json(os.path.join(out_dir, "sleep_patterns.json"), patterns)
    save_json(os.path.join(out_dir, "sleep_longitudinal_brief.json"), brief)

    print("\n===================================")
    print("SLEEP HISTORY ENGINE")
    print("===================================")
    print(f"Noches analizadas: {brief['window_days']}")
    print(f"Recovery trajectory: {brief['recovery_trajectory']}")
    print(f"Longitudinal limiter: {brief['longitudinal_limiter']}")
    print(f"Dominant bottleneck: {brief.get('dominant_bottleneck', '')}")
    print(f"Dominant cluster: {brief.get('dominant_cluster', '')}")
    print(f"Resumen: {brief['summary']}")
    print("===================================\n")

    print("Archivos generados:")
    print(os.path.join(out_dir, "sleep_history.json"))
    print(os.path.join(out_dir, "sleep_baselines.json"))
    print(os.path.join(out_dir, "sleep_trends.json"))
    print(os.path.join(out_dir, "sleep_anomalies.json"))
    print(os.path.join(out_dir, "sleep_bottlenecks.json"))
    print(os.path.join(out_dir, "sleep_pattern_clusters.json"))
    print(os.path.join(out_dir, "sleep_patterns.json"))
    print(os.path.join(out_dir, "sleep_longitudinal_brief.json"))