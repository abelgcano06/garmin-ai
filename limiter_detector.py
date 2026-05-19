import json
import os
from typing import Any, Dict, List, Optional


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_avg(values: List[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def round_if_number(value: Any, digits: int = 2) -> Any:
    if isinstance(value, (int, float)):
        return round(value, digits)
    return value


def build_evidence(
    power_drop: Optional[float],
    eff_drop: Optional[float],
    repeatability: Optional[float],
    vi: Optional[float],
    avg_climb_cad: Optional[float],
    avg_msi: Optional[float],
    high_msi_pct: Optional[float],
    profile_limiters: List[str],
    climb_count: int,
) -> Dict[str, Any]:
    return {
        "power_drop_pct": round_if_number(power_drop),
        "efficiency_drop_pct": round_if_number(eff_drop),
        "climb_repeatability_pct": round_if_number(repeatability),
        "vi": round_if_number(vi, 3),
        "avg_climb_cadence": round_if_number(avg_climb_cad, 1),
        "avg_msi": round_if_number(avg_msi, 3),
        "high_msi_pct": round_if_number(high_msi_pct, 2),
        "profile_limiters": profile_limiters,
        "climb_count": climb_count,
    }


def detect_limiter(analysis: Dict[str, Any]) -> Dict[str, Any]:
    fatigue = analysis.get("fatigue", {})
    profile = analysis.get("athlete_profile", {})
    derived = analysis.get("derived_summary", {})
    climbs = analysis.get("climbs", [])
    metabolic = analysis.get("metabolic_index", {})

    power_drop = fatigue.get("power_drop_pct")
    eff_drop = fatigue.get("efficiency_drop_pct")
    repeatability = fatigue.get("climb_repeatability_pct")
    vi = derived.get("vi")
    limiters = profile.get("limiters", []) or []

    avg_msi = metabolic.get("avg_msi")
    high_msi_pct = metabolic.get("high_msi_pct")

    cad_values = [c.get("avg_cadence") for c in climbs if c.get("avg_cadence") is not None]
    avg_climb_cad = safe_avg(cad_values)

    evidence = build_evidence(
        power_drop=power_drop,
        eff_drop=eff_drop,
        repeatability=repeatability,
        vi=vi,
        avg_climb_cad=avg_climb_cad,
        avg_msi=avg_msi,
        high_msi_pct=high_msi_pct,
        profile_limiters=limiters,
        climb_count=len(climbs),
    )

    primary = None
    secondary = None
    explanation = ""
    training_focus = ""
    confidence = "low"
    rule_triggered = None
    why_not_others: List[str] = []

    # -------------------------
    # REGLA 1: durabilidad en subidas repetidas
    # -------------------------
    if repeatability is not None and repeatability <= -6:
        primary = "durabilidad en subidas repetidas"
        explanation = (
            f"Tu repeatability en subidas cayó {round(repeatability, 2)}%, lo que indica que puedes abrir fuerte, "
            "pero te cuesta sostener ese nivel cuando las subidas se acumulan."
        )

        if high_msi_pct is not None and high_msi_pct >= 25:
            explanation += (
                f" Además, el {round(high_msi_pct, 2)}% del tiempo útil estuvo en costo metabólico alto, "
                "lo que sugiere que sostener ese esfuerzo te salió cada vez más caro fisiológicamente."
            )

        training_focus = (
            "Repeticiones de subida de 3–5 min con recuperación incompleta, buscando que la última "
            "no caiga más de 3–5% respecto a la primera."
        )
        confidence = "high" if repeatability <= -8 else "medium"
        rule_triggered = "repeatability_drop"
    else:
        why_not_others.append(
            "No se priorizó durabilidad en subidas repetidas porque la caída de repeatability no superó el umbral principal de -6%."
        )

    # -------------------------
    # REGLA 2: economía aeróbica / eficiencia
    # -------------------------
    if primary is None:
        if eff_drop is not None and eff_drop <= -6:
            primary = "economía aeróbica / eficiencia"
            explanation = (
                f"La eficiencia potencia/frecuencia cardiaca cayó {round(eff_drop, 2)}%, señal de que tu cuerpo "
                "necesitó más costo cardiovascular para sostener el esfuerzo."
            )

            if avg_msi is not None:
                explanation += (
                    f" El costo metabólico promedio estimado (MSI) fue {round(avg_msi, 3)}, lo que refuerza "
                    "que sostener esa potencia se volvió progresivamente más caro."
                )

            training_focus = (
                "Z2 larga, sweet spot y pacing más controlado para reducir deriva cardiaca y sostener mejor la potencia."
            )
            confidence = "high" if eff_drop <= -8 else "medium"
            rule_triggered = "efficiency_drop"
        else:
            why_not_others.append(
                "No se priorizó economía aeróbica porque la caída de eficiencia no superó el umbral principal de -6%."
            )

    # -------------------------
    # REGLA 3: durabilidad general de potencia
    # -------------------------
    if primary is None:
        if power_drop is not None and power_drop <= -6:
            primary = "durabilidad general de potencia"
            explanation = (
                f"La potencia útil cayó {round(power_drop, 2)}% entre la primera y la segunda mitad, lo que sugiere "
                "que el rendimiento se fue degradando conforme acumulaste carga."
            )

            if high_msi_pct is not None and high_msi_pct >= 20:
                explanation += (
                    " Ese deterioro además vino acompañado de un costo fisiológico alto durante una parte importante "
                    "de la sesión."
                )

            training_focus = (
                "Sesiones con calidad al final de rodadas largas y bloques de tempo/threshold bajo fatiga."
            )
            confidence = "high" if power_drop <= -8 else "medium"
            rule_triggered = "power_drop"
        else:
            why_not_others.append(
                "No se priorizó durabilidad general de potencia porque la caída de potencia no superó el umbral principal de -6%."
            )

    # -------------------------
    # REGLA 4: costo metabólico alto / economía muscular
    # -------------------------
    if primary is None:
        if high_msi_pct is not None and high_msi_pct >= 30:
            primary = "costo metabólico alto / economía muscular"
            explanation = (
                f"El {round(high_msi_pct, 2)}% del tiempo útil estuvo en MSI alto, lo que sugiere que "
                "producir esa potencia te salió caro fisiológicamente durante buena parte de la sesión."
            )

            if avg_climb_cad is not None and avg_climb_cad < 72:
                explanation += (
                    f" La cadencia media en subidas fue {round(avg_climb_cad, 1)} rpm, lo que probablemente "
                    "aumentó el torque por pedalada y la carga muscular."
                )

            training_focus = (
                "Mejorar economía muscular y sostenibilidad: subidas a cadencia más ágil, control de pacing y trabajo de tempo/sweet spot."
            )
            confidence = "high" if high_msi_pct >= 35 else "medium"
            rule_triggered = "high_metabolic_cost"
        else:
            why_not_others.append(
                "No se priorizó costo metabólico alto porque el porcentaje de tiempo en MSI elevado no alcanzó el umbral principal de 30%."
            )

    # -------------------------
    # REGLA 5: pacing y control de esfuerzo
    # -------------------------
    if primary is None:
        if vi is not None and vi >= 1.2:
            primary = "pacing y control de esfuerzo"
            explanation = (
                f"El VI fue {round(vi, 3)}, lo que indica una sesión bastante variable. Eso puede estar encareciendo "
                "tu fatiga y afectando cómo llegas a las últimas subidas."
            )

            if high_msi_pct is not None and high_msi_pct >= 20:
                explanation += (
                    " Esa variabilidad probablemente contribuyó también a elevar el costo metabólico del esfuerzo."
                )

            training_focus = (
                "Practicar entradas controladas en subida, evitar picos muy altos al inicio y sostener mejor el esfuerzo."
            )
            confidence = "high" if vi >= 1.24 else "medium"
            rule_triggered = "high_variability_index"
        else:
            why_not_others.append(
                "No se priorizó pacing porque el índice de variabilidad (VI) no alcanzó el umbral principal de 1.20."
            )

    # -------------------------
    # REGLA 6: cadencia baja en subidas
    # -------------------------
    if primary is None:
        if avg_climb_cad is not None and avg_climb_cad < 68:
            primary = "cadencia baja en subidas"
            explanation = (
                f"La cadencia media en subidas fue {round(avg_climb_cad, 1)} rpm, lo que sugiere mucho torque por pedalada "
                "y mayor fatiga muscular."
            )

            if high_msi_pct is not None and high_msi_pct >= 20:
                explanation += (
                    " Además, el costo metabólico alto refuerza que esa forma de empujar te salió cara en términos fisiológicos."
                )

            training_focus = (
                "Buscar 70–85 rpm en subidas medias cuando el terreno lo permita, con trabajo específico de cadencia."
            )
            confidence = "medium" if avg_climb_cad >= 64 else "high"
            rule_triggered = "low_climb_cadence"
        else:
            why_not_others.append(
                "No se priorizó cadencia baja en subidas porque la cadencia media no quedó claramente por debajo de 68 rpm."
            )

    # -------------------------
    # FALLBACK usando athlete_profile.limiters
    # -------------------------
    if primary is None and limiters:
        primary = limiters[0]
        explanation = (
            "El perfil del atleta ya detectó una limitante clara que coincide con la lógica general de esta sesión."
        )
        training_focus = "Entrenar específicamente esa limitante manteniendo tus fortalezas actuales."
        confidence = "low"
        rule_triggered = "profile_fallback"

    # -------------------------
    # FALLBACK final
    # -------------------------
    if primary is None:
        primary = "sin limitante dominante clara"
        explanation = (
            "La sesión no mostró una sola limitante dominante; parece más un perfil mixto o una sesión donde varias "
            "cosas aportaron al resultado sin que una sobresalga claramente."
        )
        training_focus = "Seguir desarrollando durabilidad, pacing y capacidad de repetición."
        confidence = "low"
        rule_triggered = "no_clear_limiter"

    # -------------------------
    # SECUNDARIA
    # -------------------------
    secondary_candidates = []

    if repeatability is not None and repeatability <= -6 and primary != "durabilidad en subidas repetidas":
        secondary_candidates.append("durabilidad en subidas repetidas")

    if eff_drop is not None and eff_drop <= -6 and primary != "economía aeróbica / eficiencia":
        secondary_candidates.append("economía aeróbica / eficiencia")

    if power_drop is not None and power_drop <= -6 and primary != "durabilidad general de potencia":
        secondary_candidates.append("durabilidad general de potencia")

    if high_msi_pct is not None and high_msi_pct >= 30 and primary != "costo metabólico alto / economía muscular":
        secondary_candidates.append("costo metabólico alto / economía muscular")

    if vi is not None and vi >= 1.2 and primary != "pacing y control de esfuerzo":
        secondary_candidates.append("pacing y control de esfuerzo")

    if avg_climb_cad is not None and avg_climb_cad < 68 and primary != "cadencia baja en subidas":
        secondary_candidates.append("cadencia baja en subidas")

    if secondary_candidates:
        secondary = secondary_candidates[0]

    return {
        "primary_limiter": primary,
        "secondary_limiter": secondary,
        "confidence": confidence,
        "rule_triggered": rule_triggered,
        "evidence": evidence,
        "why_not_others": why_not_others,
        "explanation": explanation,
        "training_focus": training_focus,
    }


def print_limiter_result(result: Dict[str, Any]) -> None:
    print("\n==========================")
    print("LIMITER DETECTOR")
    print("==========================")
    print(f"Limitante principal: {result.get('primary_limiter')}")
    print(f"Limitante secundaria: {result.get('secondary_limiter')}")
    print(f"Confianza: {result.get('confidence')}")
    print(f"Regla activada: {result.get('rule_triggered')}")
    print(f"Explicación: {result.get('explanation')}")
    print(f"Foco de entrenamiento: {result.get('training_focus')}")

    print("\nEVIDENCIA:")
    evidence = result.get("evidence", {})
    for k, v in evidence.items():
        print(f"- {k}: {v}")

    print("\nPOR QUÉ NO OTRAS:")
    for item in result.get("why_not_others", []):
        print(f"- {item}")


def main() -> None:
    analysis_path = input("Ruta del archivo activity_analysis.json: ").strip()

    if not os.path.exists(analysis_path):
        print("No se encontró el archivo.")
        return

    analysis = load_json(analysis_path)
    result = detect_limiter(analysis)
    print_limiter_result(result)


if __name__ == "__main__":
    main()