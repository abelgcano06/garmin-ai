import json
import os

DATA_FOLDER = "data"


def load_analysis(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def add_finding(findings, signal, severity, summary, evidence, tags):
    findings.append({
        "signal": signal,
        "severity": severity,
        "summary": summary,
        "evidence": evidence,
        "tags": tags,
    })


def detect_repeatability_low(analysis, findings):
    fatigue = analysis.get("fatigue", {})
    repeatability = fatigue.get("climb_repeatability_pct")
    power_drop = fatigue.get("power_drop_pct")
    eff_drop = fatigue.get("efficiency_drop_pct")

    if repeatability is None:
        return

    if repeatability <= -6:
        add_finding(
            findings,
            signal="repeatability_low",
            severity="high",
            summary="Se detectó una caída importante en la capacidad de repetir subidas intensas.",
            evidence={
                "climb_repeatability_pct": repeatability,
                "power_drop_pct": power_drop,
                "efficiency_drop_pct": eff_drop,
            },
            tags=["climbing", "fatigue", "durability"],
        )
    elif repeatability <= -3:
        add_finding(
            findings,
            signal="repeatability_moderate_drop",
            severity="medium",
            summary="Se observó una caída moderada en la repetición de esfuerzos de subida.",
            evidence={
                "climb_repeatability_pct": repeatability,
                "power_drop_pct": power_drop,
                "efficiency_drop_pct": eff_drop,
            },
            tags=["climbing", "durability"],
        )


def detect_efficiency_drop(analysis, findings):
    fatigue = analysis.get("fatigue", {})
    eff_drop = fatigue.get("efficiency_drop_pct")

    if eff_drop is None:
        return

    if eff_drop <= -6:
        add_finding(
            findings,
            signal="efficiency_drop_high",
            severity="high",
            summary="La eficiencia potencia/frecuencia cardiaca se deterioró de forma clara durante la sesión.",
            evidence={
                "efficiency_drop_pct": eff_drop,
                "power_drop_pct": fatigue.get("power_drop_pct"),
            },
            tags=["cardio", "fatigue", "efficiency"],
        )
    elif eff_drop <= -3:
        add_finding(
            findings,
            signal="efficiency_drop_moderate",
            severity="medium",
            summary="La eficiencia potencia/frecuencia cardiaca mostró una caída moderada.",
            evidence={
                "efficiency_drop_pct": eff_drop,
            },
            tags=["cardio", "efficiency"],
        )


def detect_power_drop(analysis, findings):
    fatigue = analysis.get("fatigue", {})
    power_drop = fatigue.get("power_drop_pct")

    if power_drop is None:
        return

    if power_drop <= -6:
        add_finding(
            findings,
            signal="power_durability_drop",
            severity="high",
            summary="La potencia útil cayó de forma relevante entre la primera y la segunda mitad.",
            evidence={
                "power_drop_pct": power_drop,
            },
            tags=["power", "durability", "fatigue"],
        )
    elif power_drop <= -3:
        add_finding(
            findings,
            signal="power_durability_moderate_drop",
            severity="medium",
            summary="La potencia útil mostró una caída moderada conforme avanzó la sesión.",
            evidence={
                "power_drop_pct": power_drop,
            },
            tags=["power", "durability"],
        )


def detect_variable_pacing(analysis, findings):
    derived = analysis.get("derived_summary", {})
    vi = derived.get("vi")
    ride_class = derived.get("ride_classification")

    if vi is None:
        return

    if vi >= 1.22:
        add_finding(
            findings,
            signal="high_variability_ride",
            severity="medium",
            summary="La actividad tuvo una variabilidad alta, típica de esfuerzos muy estocásticos.",
            evidence={
                "vi": vi,
                "ride_classification": ride_class,
            },
            tags=["pacing", "ride_type", "mtb"],
        )
    elif vi >= 1.12:
        add_finding(
            findings,
            signal="moderate_variability_ride",
            severity="low",
            summary="La actividad mostró variabilidad moderada con varios cambios de ritmo.",
            evidence={
                "vi": vi,
                "ride_classification": ride_class,
            },
            tags=["pacing", "ride_type"],
        )


def detect_puncher_profile(analysis, findings):
    profile = analysis.get("athlete_profile", {})
    primary = profile.get("primary_type")
    secondary = profile.get("secondary_type")
    competition_style = profile.get("competition_style")

    if primary == "puncher":
        add_finding(
            findings,
            signal="puncher_profile",
            severity="medium",
            summary="El perfil del atleta está orientado a punch y esfuerzos intensos de duración corta a media.",
            evidence={
                "primary_type": primary,
                "secondary_type": secondary,
                "competition_style": competition_style,
            },
            tags=["profile", "power_profile", "athlete_type"],
        )


def detect_short_climber_profile(analysis, findings):
    profile = analysis.get("athlete_profile", {})
    secondary = profile.get("secondary_type")
    strengths = profile.get("strengths", [])

    if secondary == "short_climber":
        add_finding(
            findings,
            signal="short_climber_profile",
            severity="medium",
            summary="El atleta muestra buen encaje con esfuerzos intensos de subida corta a media.",
            evidence={
                "secondary_type": secondary,
                "strengths": strengths,
            },
            tags=["profile", "climbing", "athlete_type"],
        )


def detect_climb_strength(analysis, findings):
    climbs = analysis.get("climbs", [])

    if not climbs:
        return

    top_climb = sorted(climbs, key=lambda x: x.get("climb_score", 0), reverse=True)[0]
    avg_power = top_climb.get("avg_power")
    duration = top_climb.get("duration_min")
    gain = top_climb.get("elevation_gain_m")
    climb_type = top_climb.get("climb_type")

    add_finding(
        findings,
        signal="top_climb_detected",
        severity="medium",
        summary="Se identificó una subida especialmente representativa del rendimiento del atleta.",
        evidence={
            "climb_type": climb_type,
            "duration_min": duration,
            "elevation_gain_m": gain,
            "avg_power": avg_power,
            "climb_score": top_climb.get("climb_score"),
        },
        tags=["climbing", "signature_effort", "terrain"],
    )


def detect_cadence_issue_on_climbs(analysis, findings):
    climbs = analysis.get("climbs", [])
    if not climbs:
        return

    cad_values = [c.get("avg_cadence") for c in climbs if c.get("avg_cadence") is not None]
    if not cad_values:
        return

    avg_cad = sum(cad_values) / len(cad_values)

    if avg_cad < 68:
        add_finding(
            findings,
            signal="low_cadence_on_climbs",
            severity="medium",
            summary="La cadencia en subidas fue baja, lo que puede aumentar el costo muscular.",
            evidence={
                "avg_climb_cadence": round(avg_cad, 1),
            },
            tags=["cadence", "climbing", "efficiency", "muscular_load"],
        )


def detect_limiter_cluster(analysis, findings):
    profile = analysis.get("athlete_profile", {})
    limiters = profile.get("limiters", [])

    if not limiters:
        return

    add_finding(
        findings,
        signal="key_limiters_detected",
        severity="high" if len(limiters) >= 2 else "medium",
        summary="Se detectó un grupo claro de limitantes de rendimiento para esta sesión.",
        evidence={
            "limiters": limiters,
        },
        tags=["limiters", "training_focus", "performance"],
    )


def detect_effort_distribution(analysis, findings):
    efforts = analysis.get("efforts", [])
    if not efforts:
        return

    vo2_count = sum(1 for e in efforts if e.get("type") == "VO2")
    sprint_count = sum(1 for e in efforts if e.get("type") == "SPRINT")
    threshold_count = sum(1 for e in efforts if e.get("type") == "THRESHOLD")

    add_finding(
        findings,
        signal="intense_effort_distribution",
        severity="low",
        summary="La actividad mostró una distribución identificable de bloques intensos.",
        evidence={
            "vo2_count": vo2_count,
            "sprint_count": sprint_count,
            "threshold_count": threshold_count,
            "total_efforts": len(efforts),
        },
        tags=["efforts", "intensity_distribution", "power"],
    )


def detect_metabolic_cost_high(analysis, findings):
    metabolic = analysis.get("metabolic_index", {})
    avg_msi = metabolic.get("avg_msi")
    max_msi = metabolic.get("max_msi")
    high_msi_pct = metabolic.get("high_msi_pct")

    if avg_msi is None and high_msi_pct is None:
        return

    if high_msi_pct is not None and high_msi_pct >= 30:
        add_finding(
            findings,
            signal="metabolic_cost_high",
            severity="high",
            summary="El costo metabólico de la sesión fue alto durante una parte importante del esfuerzo útil.",
            evidence={
                "avg_msi": avg_msi,
                "max_msi": max_msi,
                "high_msi_pct": high_msi_pct,
            },
            tags=["metabolic_cost", "fatigue", "efficiency", "physiology"],
        )
    elif high_msi_pct is not None and high_msi_pct >= 18:
        add_finding(
            findings,
            signal="metabolic_cost_moderate",
            severity="medium",
            summary="La sesión mostró un costo metabólico moderadamente elevado.",
            evidence={
                "avg_msi": avg_msi,
                "max_msi": max_msi,
                "high_msi_pct": high_msi_pct,
            },
            tags=["metabolic_cost", "efficiency", "physiology"],
        )


def detect_low_cadence_metabolic_penalty(analysis, findings):
    metabolic = analysis.get("metabolic_index", {})
    climbs = analysis.get("climbs", [])

    high_msi_pct = metabolic.get("high_msi_pct")
    avg_msi = metabolic.get("avg_msi")

    if not climbs:
        return

    cad_values = [c.get("avg_cadence") for c in climbs if c.get("avg_cadence") is not None]
    if not cad_values:
        return

    avg_cad = sum(cad_values) / len(cad_values)

    if high_msi_pct is not None and high_msi_pct >= 20 and avg_cad < 72:
        severity = "high" if avg_cad < 68 and high_msi_pct >= 30 else "medium"

        add_finding(
            findings,
            signal="low_cadence_metabolic_penalty",
            severity=severity,
            summary="La combinación de cadencia baja y alto costo metabólico sugiere una penalización muscular importante en subida.",
            evidence={
                "avg_climb_cadence": round(avg_cad, 1),
                "avg_msi": avg_msi,
                "high_msi_pct": high_msi_pct,
            },
            tags=["cadence", "metabolic_cost", "climbing", "muscular_load", "fatigue"],
        )


def build_findings(analysis):
    findings = []

    detect_repeatability_low(analysis, findings)
    detect_efficiency_drop(analysis, findings)
    detect_power_drop(analysis, findings)
    detect_variable_pacing(analysis, findings)
    detect_puncher_profile(analysis, findings)
    detect_short_climber_profile(analysis, findings)
    detect_climb_strength(analysis, findings)
    detect_cadence_issue_on_climbs(analysis, findings)
    detect_limiter_cluster(analysis, findings)
    detect_effort_distribution(analysis, findings)

    # NUEVOS FINDINGS BASADOS EN MSI
    detect_metabolic_cost_high(analysis, findings)
    detect_low_cadence_metabolic_penalty(analysis, findings)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda x: severity_order.get(x["severity"], 99))

    return findings


def save_findings_json(analysis_path, findings):

    activity_folder = os.path.dirname(analysis_path)

    output_path = os.path.join(
        activity_folder,
        "activity_findings.json"
    )

    payload = {
        "findings": findings
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return output_path

def main():
    analysis_path = input("Ruta del archivo activity_analysis.json: ").strip()

    if not os.path.exists(analysis_path):
        print("No se encontró el archivo.")
        return

    analysis = load_analysis(analysis_path)
    findings = build_findings(analysis)
    output_path = save_findings_json(analysis_path, findings)

    print("\n==========================")
    print("FINDINGS DE LA ACTIVIDAD")
    print("==========================")

    if not findings:
        print("No se detectaron hallazgos.")
        return

    for i, finding in enumerate(findings, start=1):
        print(f"\nFinding #{i} [{finding['severity']}]")
        print(f"Signal: {finding['signal']}")
        print(f"Resumen: {finding['summary']}")
        print(f"Tags: {finding['tags']}")
        print(f"Evidencia: {finding['evidence']}")

    print(f"\nArchivo guardado en: {output_path}")


if __name__ == "__main__":
    main()