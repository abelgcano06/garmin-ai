import json
import os


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fmt_num(x):
    if isinstance(x, float):
        return f"{round(x, 2)}"
    return str(x)


def fmt_pct(x):
    return f"{round(x * 100, 1)}%"


def get_day_status(score):
    if score >= 80:
        return "strong"
    if score >= 65:
        return "stable"
    if score >= 50:
        return "managed"
    return "strained"


def get_day_quality_label(overall_day_state_score, system_strain_score):
    if overall_day_state_score >= 80 and system_strain_score <= 40:
        return "high_capacity"
    if overall_day_state_score >= 60:
        return "functional"
    return "compromised"


def humanize_limiter(code):
    mapping = {
        "nervous_system_load": "nervous system strain",
        "physical_load": "physical load",
        "cognitive_load": "cognitive load",
        "stress_behavior": "stress accumulation",
        "energy_depletion": "energy depletion",
        "recovery_failure": "poor intraday recovery",
        "respiratory_instability": "breathing instability",
    }
    return mapping.get(code, code.replace("_", " "))


def build_headline(day_status, primary_limiter, overall_day_state_score):
    limiter_h = humanize_limiter(primary_limiter)

    if day_status == "strong":
        if primary_limiter:
            return f"Strong day capacity with a remaining limiter in {limiter_h}."
        return "Strong day capacity."
    if day_status in ["stable", "managed"]:
        if primary_limiter:
            return f"Usable day state with a clear limiter in {limiter_h}."
        return "Usable day state with some accumulated load."
    if primary_limiter:
        return f"Day state ended constrained, mainly by {limiter_h}."
    return "Day state ended constrained."


def build_overall_summary(analysis, findings):
    summary = analysis["recovery_summary"]
    stress = analysis["stress_behavior"]
    energy = analysis["energy_dynamics"]
    recovery = analysis["recovery_response"]

    text = (
        f"Overall day state score was {round(summary['overall_day_state_score'], 1)}, "
        f"with system strain at {round(summary['system_strain_score'], 1)} "
        f"and day capacity at {round(summary['day_capacity_score'], 1)}. "
        f"Average stress was {round(stress['avg_stress'], 1)} "
        f"and Body Battery changed by {round(energy['body_battery_change'], 1)} points."
    )

    if findings["flags"]["high_stress"]:
        text += " Stress remained meaningfully elevated during the day."

    if findings["flags"]["energy_crash"]:
        text += " Energy handling also looked unstable."

    if findings["flags"]["low_recovery"]:
        text += " Recovery during the day appeared limited."

    return text


def build_physiology_interpretation(analysis, findings):
    nervous = analysis["nervous_system_load"]
    energy = analysis["energy_dynamics"]
    physical = analysis["physical_load"]
    cognitive = analysis["cognitive_load"]
    stress = analysis["stress_behavior"]
    recovery = analysis["recovery_response"]
    respiratory = analysis["respiratory_behavior"]

    parts = []

    if nervous["nervous_system_load_score"] >= 75:
        parts.append("The nervous system looks heavily loaded across the day.")
    elif nervous["nervous_system_load_score"] >= 55:
        parts.append("The nervous system carries moderate load but not extreme strain.")
    else:
        parts.append("The nervous system load stayed relatively manageable.")

    if energy["energy_dynamics_score"] <= 40:
        parts.append("Energy dynamics suggest rapid reserve loss and poor stability.")
    elif energy["energy_dynamics_score"] <= 60:
        parts.append("Energy handling was acceptable but not especially robust.")
    else:
        parts.append("Energy dynamics remained relatively stable for most of the day.")

    if physical["physical_load_score"] >= 72:
        parts.append("Physical load was high enough to accumulate relevant fatigue.")
    else:
        parts.append("Physical load was present but not dominant.")

    if cognitive["cognitive_load_score"] >= 68:
        parts.append("Mental load appears elevated, likely driven by sustained stress and limited reset periods.")

    if recovery["recovery_response_score"] <= 35:
        parts.append("The body did not downshift efficiently once it got loaded.")

    if findings["flags"]["respiratory_instability"]:
        parts.append("Breathing behavior looked less stable than expected and may deserve monitoring if recurrent.")

    if stress["stress_behavior_score"] >= 70:
        parts.append("Stress was not just peaky, but sustained enough to shape the whole day state.")

    return " ".join(parts)


def build_performance_impact(analysis, findings):
    overall = analysis["recovery_summary"]["overall_day_state_score"]
    energy = analysis["energy_dynamics"]["energy_dynamics_score"]
    nervous = analysis["nervous_system_load"]["nervous_system_load_score"]

    if overall >= 80 and energy >= 65 and nervous <= 55:
        return "The body should still support solid performance, especially for controlled work or quality training."
    if overall >= 60:
        return "Performance is still workable, but the body may feel less sharp if demands rise late in the day."
    if findings["flags"]["energy_crash"]:
        return "Performance is likely to fade as the day progresses unless load is reduced."
    return "The body looks constrained enough that performance, decision quality, and tolerance to intensity may be reduced."


def build_training_recommendation(analysis, findings):
    overall = analysis["recovery_summary"]["overall_day_state_score"]
    primary = findings["limiters"]["primary_limiter"]

    if overall >= 80:
        return "You can still handle a normal session if the rest of the context is favorable."
    if overall >= 65:
        return "Training is still possible, but leave room to reduce intensity if the body feels flat."
    if primary in ["energy_depletion", "recovery_failure", "stress_behavior", "nervous_system_load"]:
        return "Bias toward lower intensity, controlled volume, or recovery-oriented work."
    return "Avoid adding unnecessary stress; prioritize recovery support over performance stress."


def build_recovery_recommendation(analysis, findings):
    recs = []

    if findings["flags"]["high_stress"]:
        recs.append("reduce incoming stress and create a real downshift window")
    if findings["flags"]["energy_crash"]:
        recs.append("protect energy by cutting unnecessary output and improving pacing")
    if findings["flags"]["low_recovery"]:
        recs.append("insert short recovery blocks during the day instead of pushing continuously")
    if findings["flags"]["high_physical_load"]:
        recs.append("lower extra physical demand for the rest of the day")
    if findings["flags"]["high_cognitive_load"]:
        recs.append("reduce mental switching and decision overload")
    if findings["flags"]["respiratory_instability"]:
        recs.append("track whether irregular breathing behavior repeats across days")

    if not recs:
        return "Keep the same pacing; day markers were generally manageable."

    return "Main recovery focus: " + "; ".join(recs) + "."


def build_positive_markers(analysis, findings):
    positives = []

    if analysis["recovery_summary"]["overall_day_state_score"] >= 75:
        positives.append("Good overall day capacity")
    if analysis["energy_dynamics"]["energy_dynamics_score"] >= 65:
        positives.append("Stable energy dynamics")
    if analysis["recovery_response"]["recovery_response_score"] >= 60:
        positives.append("Good intraday recovery response")
    if analysis["stress_behavior"]["high_stress_ratio"] <= 0.12 and analysis["stress_behavior"]["avg_stress"] <= 35:
        positives.append("Controlled stress exposure")
    if analysis["respiratory_behavior"]["respiratory_behavior_score"] >= 65 and analysis["timeline_summary"]["respiration_points"] > 0:
        positives.append("Stable breathing behavior")

    return positives


def build_risk_markers(findings):
    return [f["title"] for f in findings.get("findings", [])]


def build_key_evidence(analysis):
    summary = analysis["recovery_summary"]
    nervous = analysis["nervous_system_load"]
    stress = analysis["stress_behavior"]
    energy = analysis["energy_dynamics"]
    recovery = analysis["recovery_response"]

    return [
        {
            "label": "Overall day state",
            "value": fmt_num(summary["overall_day_state_score"]),
            "meaning": "Integrated balance between total daily strain and remaining capacity."
        },
        {
            "label": "System strain",
            "value": fmt_num(summary["system_strain_score"]),
            "meaning": "Represents how much physiological load accumulated through the day."
        },
        {
            "label": "Day capacity",
            "value": fmt_num(summary["day_capacity_score"]),
            "meaning": "Represents how much usable capacity and recovery response remained available."
        },
        {
            "label": "Average stress",
            "value": fmt_num(stress["avg_stress"]),
            "meaning": "Average daytime stress signal across available samples."
        },
        {
            "label": "Body Battery change",
            "value": fmt_num(energy["body_battery_change"]),
            "meaning": "Net reserve change across the day."
        },
        {
            "label": "Recovery response",
            "value": fmt_num(recovery["recovery_response_score"]),
            "meaning": "Reflects how well the body downshifted after loading."
        },
        {
            "label": "Nervous system load",
            "value": fmt_num(nervous["nervous_system_load_score"]),
            "meaning": "Reflects cumulative nervous system strain across the day."
        }
    ]


def build_readiness_hint(analysis):
    overall = analysis["recovery_summary"]["overall_day_state_score"]
    if overall >= 80:
        return "day_capacity_positive"
    if overall >= 60:
        return "day_capacity_ok"
    return "day_capacity_caution"


def build_coach_note(analysis, findings):
    primary = humanize_limiter(findings["limiters"]["primary_limiter"])
    overall = analysis["recovery_summary"]["overall_day_state_score"]

    if overall >= 80 and primary:
        return f"The body held up well overall, but keep an eye on {primary}."
    if overall >= 60:
        return "The day is still workable, but not every system looks equally protected."
    return "This looks more like a day to manage load than a day to force output."


def build_day_brief(analysis, findings):
    overall_day_state_score = analysis["recovery_summary"]["overall_day_state_score"]
    system_strain_score = analysis["recovery_summary"]["system_strain_score"]

    day_status = get_day_status(overall_day_state_score)
    day_quality_label = get_day_quality_label(overall_day_state_score, system_strain_score)

    follow_up_needed = (
        findings["flags"]["high_stress"]
        or findings["flags"]["energy_crash"]
        or findings["flags"]["low_recovery"]
        or findings["flags"]["respiratory_instability"]
    )

    return {
        "calendar_date": analysis["calendar_date"],
        "headline": build_headline(
            day_status,
            findings["limiters"]["primary_limiter"],
            overall_day_state_score
        ),
        "day_status": day_status,
        "day_quality_label": day_quality_label,
        "primary_limiter": findings["limiters"]["primary_limiter"],
        "secondary_limiter": findings["limiters"]["secondary_limiter"],
        "overall_summary": build_overall_summary(analysis, findings),
        "physiology_interpretation": build_physiology_interpretation(analysis, findings),
        "performance_impact": build_performance_impact(analysis, findings),
        "training_recommendation": build_training_recommendation(analysis, findings),
        "recovery_recommendation": build_recovery_recommendation(analysis, findings),
        "key_evidence": build_key_evidence(analysis),
        "positive_markers": build_positive_markers(analysis, findings),
        "risk_markers": build_risk_markers(findings),
        "coach_note": build_coach_note(analysis, findings),
        "readiness_hint": build_readiness_hint(analysis),
        "follow_up_needed": follow_up_needed
    }


def main():
    analysis_path = input("Ruta de day_analysis.json: ").strip()
    findings_path = input("Ruta de day_findings.json: ").strip()
    out_path = input("Ruta de salida de day_brief.json: ").strip()

    analysis = load_json(analysis_path)
    findings = load_json(findings_path)

    brief = build_day_brief(analysis, findings)
    save_json(out_path, brief)

    print("Archivo generado:")
    print(out_path)


if __name__ == "__main__":
    main()