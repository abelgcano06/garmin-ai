def safe_get_power(power_profile, label):
    item = power_profile.get(label)
    if isinstance(item, dict):
        return item.get("avg_power")
    return None


def average(values):
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def classify_primary_type(pp):
    p_5s = safe_get_power(pp, "5s")
    p_1min = safe_get_power(pp, "1min")
    p_5min = safe_get_power(pp, "5min")
    p_20min = safe_get_power(pp, "20min")
    p_60min = safe_get_power(pp, "60min")

    if p_5s and p_5min and p_5s / p_5min > 2.5:
        return "puncher"

    if p_5min and p_20min and p_20min / p_5min > 0.82:
        if p_60min and p_20min and p_60min / p_20min > 0.88:
            return "diesel"

    if p_1min and p_5min and p_1min / p_5min > 1.18:
        return "short_climber"

    return "mixed"


def classify_secondary_type(pp, climbs, fatigue):
    p_3min = safe_get_power(pp, "3min")
    p_8min = safe_get_power(pp, "8min")
    p_20min = safe_get_power(pp, "20min")

    if climbs:
        avg_climb_power = average([c.get("avg_power") for c in climbs])
        avg_climb_grade = average([c.get("avg_grade_pct") for c in climbs])

        if avg_climb_power and avg_climb_grade and avg_climb_grade >= 6:
            if p_3min and p_8min and p_8min > 0 and (p_3min / p_8min) > 1.08:
                return "short_climber"

    power_drop = fatigue.get("power_drop_pct")
    if power_drop is not None and power_drop < -10:
        return "fragile_repeatability"

    if p_20min:
        return "tempo_builder"

    return "unknown"


def classify_competition_style(primary_type, climbs, efforts, derived_summary):
    vi = derived_summary.get("vi")

    climb_count = len(climbs) if climbs else 0
    effort_count = len(efforts) if efforts else 0

    if vi is not None and vi >= 1.22 and climb_count >= 5:
        if primary_type in ["puncher", "short_climber"]:
            return "xc_punchy"

    if climb_count >= 5:
        return "climbing_repeatable"

    if effort_count >= 3:
        return "stochastic_attacker"

    if primary_type == "diesel":
        return "steady_endurance"

    return "mixed_terrain"


def build_strengths(pp, climbs, efforts, derived_summary, fatigue):
    strengths = []

    p_5s = safe_get_power(pp, "5s")
    p_1min = safe_get_power(pp, "1min")
    p_5min = safe_get_power(pp, "5min")
    p_20min = safe_get_power(pp, "20min")
    p_60min = safe_get_power(pp, "60min")

    if p_5s and p_5min and p_5s / p_5min > 2.5:
        strengths.append("explosividad corta")

    if p_1min and p_5min and p_1min / p_5min > 1.18:
        strengths.append("esfuerzos intensos de 1 a 5 min")

    if climbs:
        avg_climb_grade = average([c.get("avg_grade_pct") for c in climbs])
        avg_climb_power = average([c.get("avg_power") for c in climbs])
        if avg_climb_grade and avg_climb_grade >= 6:
            strengths.append("rendimiento en subida media a steep")
        if avg_climb_power and p_5min and avg_climb_power >= p_5min * 0.85:
            strengths.append("transferencia de potencia a subidas")

    repeatability = fatigue.get("climb_repeatability_pct")
    if repeatability is not None and repeatability > -5:
        strengths.append("repeatability aceptable en subidas")

    vi = derived_summary.get("vi")
    if vi is not None and vi >= 1.2:
        strengths.append("tolerancia a esfuerzos variables")

    if p_20min and p_5min and (p_20min / p_5min) >= 0.78:
        strengths.append("sostenimiento medio")

    if p_60min and p_20min and (p_60min / p_20min) >= 0.88:
        strengths.append("fondo relativamente estable")

    return list(dict.fromkeys(strengths))


def build_limiters(pp, climbs, efforts, derived_summary, fatigue):
    limiters = []

    p_5min = safe_get_power(pp, "5min")
    p_20min = safe_get_power(pp, "20min")
    p_60min = safe_get_power(pp, "60min")

    if p_5min and p_20min and (p_20min / p_5min) < 0.78:
        limiters.append("potencia sostenida de 20 min")

    if p_20min and p_60min and (p_60min / p_20min) < 0.88:
        limiters.append("motor sostenido largo")

    power_drop = fatigue.get("power_drop_pct")
    if power_drop is not None and power_drop < -7:
        limiters.append("caída de potencia con el paso de la sesión")

    eff_drop = fatigue.get("efficiency_drop_pct")
    if eff_drop is not None and eff_drop < -6:
        limiters.append("deterioro de eficiencia potencia/HR")

    repeatability = fatigue.get("climb_repeatability_pct")
    if repeatability is not None and repeatability < -6:
        limiters.append("repeatability limitada en subidas")

    if climbs:
        avg_cad = average([c.get("avg_cadence") for c in climbs])
        if avg_cad is not None and avg_cad < 68:
            limiters.append("cadencia baja en subidas exigentes")

    return list(dict.fromkeys(limiters))


def build_development_focus(primary_type, strengths, limiters):
    focus = []

    if "potencia sostenida de 20 min" in limiters:
        focus.append("sweet spot y threshold sostenido")

    if "motor sostenido largo" in limiters:
        focus.append("tempo largo y endurance extensivo")

    if "repeatability limitada en subidas" in limiters:
        focus.append("repeticiones de subida con recuperación incompleta")

    if "deterioro de eficiencia potencia/HR" in limiters:
        focus.append("mejora aeróbica y control de pacing")

    if primary_type == "puncher":
        focus.append("mantener punch mientras se sube el 20-30 min")

    if primary_type == "diesel":
        focus.append("desarrollar capacidad de cambio de ritmo")

    return list(dict.fromkeys(focus))


def compute_confidence(power_profile, climbs, efforts, fatigue):
    score = 0

    available_pp = sum(
        1 for label in ["5s", "1min", "5min", "20min", "60min"]
        if safe_get_power(power_profile, label) is not None
    )
    score += min(available_pp, 5)

    if climbs and len(climbs) >= 3:
        score += 2

    if efforts and len(efforts) >= 2:
        score += 2

    if fatigue.get("power_drop_pct") is not None:
        score += 1

    if score >= 8:
        return "high"
    elif score >= 5:
        return "medium"
    else:
        return "low"


def build_athlete_profile_v2(power_profile, climbs, efforts, derived_summary, fatigue):
    primary_type = classify_primary_type(power_profile)
    secondary_type = classify_secondary_type(power_profile, climbs, fatigue)
    competition_style = classify_competition_style(primary_type, climbs, efforts, derived_summary)

    strengths = build_strengths(power_profile, climbs, efforts, derived_summary, fatigue)
    limiters = build_limiters(power_profile, climbs, efforts, derived_summary, fatigue)
    development_focus = build_development_focus(primary_type, strengths, limiters)
    confidence = compute_confidence(power_profile, climbs, efforts, fatigue)

    return {
        "primary_type": primary_type,
        "secondary_type": secondary_type,
        "competition_style": competition_style,
        "strengths": strengths,
        "limiters": limiters,
        "development_focus": development_focus,
        "confidence": confidence,
    }


if __name__ == "__main__":
    print("Este archivo está pensado para ser importado desde activity_analyzer.py")