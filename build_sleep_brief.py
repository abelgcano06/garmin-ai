import json
import os


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fmt_pct(x):
    return f"{round(x * 100, 1)}%"


def fmt_num(x):
    if isinstance(x, float):
        return f"{round(x, 2)}"
    return str(x)


def get_recovery_status(score):
    if score >= 85:
        return "high"
    if score >= 70:
        return "moderate_high"
    if score >= 55:
        return "moderate"
    return "low"


def get_sleep_quality_label(overall_recovery_score, sleep_efficiency):
    if sleep_efficiency >= 0.90 and overall_recovery_score >= 80:
        return "strong"
    if overall_recovery_score >= 65:
        return "decent"
    return "compromised"


def build_headline(recovery_status, primary_limiter, overall_recovery_score):
    if recovery_status == "high":
        if primary_limiter:
            return f"Strong overnight recovery with a remaining limiter in {primary_limiter.replace('_', ' ')}."
        return "Strong overnight recovery."
    if recovery_status in ["moderate_high", "moderate"]:
        if primary_limiter:
            return f"Moderate recovery with a clear limiter in {primary_limiter.replace('_', ' ')}."
        return "Moderate overnight recovery."
    if primary_limiter:
        return f"Recovery was limited, mainly by {primary_limiter.replace('_', ' ')}."
    return "Recovery was limited overnight."


def build_overall_summary(analysis, findings):
    summary = analysis["recovery_summary"]
    arch = analysis["sleep_architecture"]
    auto = analysis["autonomic_recovery"]
    oxy = analysis["oxygenation"]
    circ = analysis["circadian_alignment"]

    overall = summary["overall_recovery_score"]
    auto_score = auto["autonomic_recovery_curve_score"]

    text = (
        f"Overall recovery score was {round(overall, 1)}, "
        f"with autonomic recovery at {round(auto_score, 1)}. "
        f"Sleep efficiency was {round(analysis['sleep_window']['sleep_efficiency'] * 100, 1)}% "
        f"and REM sleep represented {round(arch['rem_ratio'] * 100, 1)}% of total sleep."
    )

    if oxy["oxygen_risk_flag"]:
        text += " A low overnight oxygen nadir was detected and deserves monitoring if repeated."

    if circ["circadian_alignment_score"] < 60:
        text += " Sleep timing also appeared misaligned with the preferred window."

    return text


def build_physiology_interpretation(analysis, findings_json):
    summary = analysis["recovery_summary"]
    arch = analysis["sleep_architecture"]
    auto = analysis["autonomic_recovery"]
    stress = analysis["stress_recovery"]
    resp = analysis["respiratory_recovery"]
    oxy = analysis["oxygenation"]

    parts = []

    if auto["autonomic_recovery_curve_score"] >= 75:
        parts.append("The autonomic system appears to have recovered well overnight.")
    elif auto["autonomic_recovery_curve_score"] >= 55:
        parts.append("Autonomic recovery was acceptable but not fully optimal.")
    else:
        parts.append("Autonomic recovery was incomplete overnight.")

    if arch["deep_ratio"] < 0.16:
        parts.append("Deep sleep proportion was below the preferred range, suggesting physical recovery may have been incomplete.")
    else:
        parts.append("Deep sleep proportion was supportive of physical recovery.")

    if arch["rem_ratio"] < 0.20:
        parts.append("REM sleep was below target, which may limit neural and cognitive recovery.")
    else:
        parts.append("REM sleep was adequate for neural recovery.")

    if stress["avg_sleep_stress"] > 20:
        parts.append("Nocturnal stress remained elevated, suggesting incomplete downregulation during sleep.")

    if resp["respiratory_stability_score"] < 60:
        parts.append("Breathing stability was not ideal and should be monitored over multiple nights.")

    if oxy["oxygen_risk_flag"]:
        parts.append("An oxygen nadir flag was triggered, which is not diagnostic but should be tracked if recurrent.")

    return " ".join(parts)


def build_performance_impact(analysis, findings):
    overall = analysis["recovery_summary"]["overall_recovery_score"]
    neural = analysis["recovery_summary"]["neural_recovery_score"]
    physical = analysis["recovery_summary"]["physical_recovery_score"]
    flags = findings["flags"]

    if flags["possible_oxygenation_issue"]:
        return "You may feel generally recovered, but respiratory or oxygenation-related strain could reduce resilience under high intensity if this pattern repeats."
    if overall >= 85 and neural >= 80 and physical >= 75:
        return "This night should support good training readiness, especially for normal to moderately demanding sessions."
    if overall >= 70:
        return "You should tolerate training reasonably well, but performance may be slightly limited if intensity is very high."
    return "Training readiness appears reduced, and high intensity may feel harder than expected."


def build_training_recommendation(analysis, findings):
    overall = analysis["recovery_summary"]["overall_recovery_score"]
    primary = findings["limiters"]["primary_limiter"]
    flags = findings["flags"]

    if flags["possible_oxygenation_issue"]:
        return "Train normally only if you feel good, but monitor breathing, unusual fatigue, and repeated overnight oxygen drops across future nights."
    if overall >= 85:
        return "Green light for a normal session. You can tolerate quality work if the rest of the context is favorable."
    if overall >= 70:
        return "Proceed with training, but keep room to reduce intensity if the body does not feel sharp."
    if primary in ["autonomic_fatigue", "short_sleep"]:
        return "Prioritize low to moderate intensity today and avoid unnecessary physiological stress."
    return "Bias toward recovery-oriented or low-intensity training today."


def build_recovery_recommendation(analysis, findings):
    arch = analysis["sleep_architecture"]
    circ = analysis["circadian_alignment"]
    flags = findings["flags"]

    recommendations = []

    if arch["deep_ratio"] < 0.16:
        recommendations.append("protect deep sleep by reducing late stimulation and improving wind-down")
    if circ["circadian_alignment_score"] < 60:
        recommendations.append("move sleep timing closer to your preferred window")
    if flags["possible_oxygenation_issue"]:
        recommendations.append("monitor overnight oxygen behavior across several nights")
    if analysis["stress_recovery"]["avg_sleep_stress"] > 20:
        recommendations.append("reduce late-night stress load, large meals, or alcohol exposure")

    if not recommendations:
        return "Keep the same sleep routine; recovery markers were generally favorable."

    return "Main recovery focus: " + "; ".join(recommendations) + "."


def build_positive_markers(analysis):
    positives = []

    if analysis["sleep_window"]["sleep_efficiency"] >= 0.90:
        positives.append("High sleep efficiency")
    if analysis["autonomic_recovery"]["autonomic_recovery_curve_score"] >= 75:
        positives.append("Strong autonomic recovery")
    if analysis["recovery_summary"]["overall_recovery_score"] >= 80:
        positives.append("High overall recovery score")
    if analysis["energy_recharge"]["recharge_efficiency"] >= 75:
        positives.append("Strong overnight recharge efficiency")
    if analysis["sleep_architecture"]["rem_ratio"] >= 0.20:
        positives.append("Adequate REM contribution")

    return positives


def build_risk_markers(findings):
    risks = []
    for f in findings["findings"]:
        risks.append(f["title"])
    return risks


def build_key_evidence(analysis):
    arch = analysis["sleep_architecture"]
    auto = analysis["autonomic_recovery"]
    oxy = analysis["oxygenation"]
    circ = analysis["circadian_alignment"]
    summary = analysis["recovery_summary"]

    return [
        {
            "label": "Overall recovery",
            "value": fmt_num(summary["overall_recovery_score"]),
            "meaning": "Composite recovery output from sleep architecture, autonomic state, recharge, and stability."
        },
        {
            "label": "Autonomic recovery curve",
            "value": fmt_num(auto["autonomic_recovery_curve_score"]),
            "meaning": "Represents how well the nervous system appears to recover overnight."
        },
        {
            "label": "Deep sleep ratio",
            "value": fmt_pct(arch["deep_ratio"]),
            "meaning": "Reflects contribution of deep sleep to physical recovery."
        },
        {
            "label": "Minimum SpO2",
            "value": fmt_num(oxy["min_spo2"]),
            "meaning": "Lowest overnight oxygen saturation observed."
        },
        {
            "label": "Circadian alignment",
            "value": fmt_num(circ["circadian_alignment_score"]),
            "meaning": "Indicates how aligned sleep timing was with the preferred window."
        }
    ]


def build_readiness_hint(analysis):
    overall = analysis["recovery_summary"]["overall_recovery_score"]
    if overall >= 85:
        return "readiness_positive"
    if overall >= 70:
        return "readiness_ok"
    return "readiness_caution"


def build_coach_note(analysis, findings):
    primary = findings["limiters"]["primary_limiter"]
    overall = analysis["recovery_summary"]["overall_recovery_score"]

    if overall >= 85 and primary:
        return f"Recovery was strong overall, but keep an eye on {primary.replace('_', ' ')}."
    if overall >= 70:
        return "You are likely functional for training, but not all systems look equally strong."
    return "This looks more like a recovery-support night than a performance-support night."


def build_sleep_brief(analysis, findings):
    recovery_status = get_recovery_status(analysis["recovery_summary"]["overall_recovery_score"])
    sleep_quality_label = get_sleep_quality_label(
        analysis["recovery_summary"]["overall_recovery_score"],
        analysis["sleep_window"]["sleep_efficiency"]
    )

    oxygen_flag = findings["flags"]["possible_oxygenation_issue"]
    respiratory_flag = findings["flags"]["possible_respiratory_instability"]
    autonomic_flag = findings["flags"]["possible_autonomic_strain"]

    follow_up_needed = oxygen_flag or respiratory_flag or autonomic_flag

    return {
        "calendar_date": analysis["calendar_date"],
        "headline": build_headline(
            recovery_status,
            findings["limiters"]["primary_limiter"],
            analysis["recovery_summary"]["overall_recovery_score"]
        ),
        "recovery_status": recovery_status,
        "sleep_quality_label": sleep_quality_label,
        "primary_limiter": findings["limiters"]["primary_limiter"],
        "secondary_limiter": findings["limiters"]["secondary_limiter"],
        "overall_summary": build_overall_summary(analysis, findings),
        "physiology_interpretation": build_physiology_interpretation(analysis, findings),
        "performance_impact": build_performance_impact(analysis, findings),
        "training_recommendation": build_training_recommendation(analysis, findings),
        "recovery_recommendation": build_recovery_recommendation(analysis, findings),
        "key_evidence": build_key_evidence(analysis),
        "positive_markers": build_positive_markers(analysis),
        "risk_markers": build_risk_markers(findings),
        "coach_note": build_coach_note(analysis, findings),
        "readiness_hint": build_readiness_hint(analysis),
        "follow_up_needed": follow_up_needed
    }


def main():
    analysis_path = input("Ruta de sleep_analysis.json: ").strip()
    findings_path = input("Ruta de sleep_findings.json: ").strip()
    out_path = input("Ruta de salida de sleep_brief.json: ").strip()

    analysis = load_json(analysis_path)
    findings = load_json(findings_path)

    brief = build_sleep_brief(analysis, findings)
    save_json(out_path, brief)

    print("Archivo generado:")
    print(out_path)


if __name__ == "__main__":
    main()