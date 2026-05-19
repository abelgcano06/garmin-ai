def clamp(value, min_value=0, max_value=100):
    return max(min_value, min(max_value, value))


def score_repeatability(repeatability_pct):
    if repeatability_pct is None:
        return None, "No hubo datos suficientes para evaluar repeatability."

    score = clamp(100 - abs(repeatability_pct) * 2.0)

    if score >= 90:
        reason = "Muy buena capacidad de repetir subidas sin perder demasiado rendimiento."
    elif score >= 80:
        reason = "Buena repeatability, aunque ya aparece una caída apreciable conforme se acumulan esfuerzos."
    elif score >= 70:
        reason = "Repeatability moderada: puedes abrir bien, pero te cuesta sostener varias subidas seguidas."
    else:
        reason = "Repeatability baja: la potencia cae demasiado cuando las subidas se encadenan."

    return round(score, 1), reason


def score_metabolic_cost(avg_msi, high_msi_pct):
    if avg_msi is None or high_msi_pct is None:
        return None, "No hubo datos suficientes para evaluar costo metabólico."

    penalty = ((avg_msi - 0.9) * 35) + (high_msi_pct * 0.9)
    score = clamp(100 - penalty)

    if score >= 90:
        reason = "El costo fisiológico de la sesión fue bajo para la carga realizada."
    elif score >= 80:
        reason = "Costo metabólico aceptable, aunque hubo momentos donde sostener el esfuerzo ya se volvió caro."
    elif score >= 70:
        reason = "Costo metabólico moderado-alto: una parte relevante de la sesión salió cara fisiológicamente."
    else:
        reason = "Costo metabólico alto: sostener el ritmo salió caro durante buena parte de la sesión."

    return round(score, 1), reason


def score_efficiency(efficiency_drop_pct):
    if efficiency_drop_pct is None:
        return None, "No hubo datos suficientes para evaluar eficiencia."

    score = clamp(100 - abs(efficiency_drop_pct) * 2.0)

    if score >= 90:
        reason = "La eficiencia potencia/FC se sostuvo muy bien durante la sesión."
    elif score >= 80:
        reason = "La eficiencia se mantuvo razonablemente estable, con algo de deterioro al final."
    elif score >= 70:
        reason = "La eficiencia cayó de forma moderada; el cuerpo necesitó más costo para producir lo mismo."
    else:
        reason = "La eficiencia cayó bastante; conforme avanzó la sesión, producir potencia salió cada vez más caro."

    return round(score, 1), reason


def score_pacing(vi):
    if vi is None:
        return None, "No hubo datos suficientes para evaluar pacing."

    score = clamp(100 - ((vi - 1.0) * 100))

    if score >= 92:
        reason = "Muy buen control del ritmo; la sesión fue bastante estable para su contexto."
    elif score >= 85:
        reason = "Buen pacing general, aunque con algunos cambios de ritmo que añadieron costo."
    elif score >= 75:
        reason = "Pacing moderadamente variable; la dosificación pudo haber sido más limpia."
    else:
        reason = "Pacing agresivo o irregular; la variabilidad probablemente elevó la fatiga."

    return round(score, 1), reason


def score_muscular_load(avg_climb_cadence):
    if avg_climb_cadence is None:
        return None, "No hubo datos suficientes para evaluar carga muscular."

    score = clamp(100 - max(0, (85 - avg_climb_cadence) * 2.5))

    if score >= 90:
        reason = "Buena gestión de cadencia; la carga muscular fue relativamente eficiente."
    elif score >= 80:
        reason = "Carga muscular razonable, aunque con margen para girar algo más suelto en subida."
    elif score >= 70:
        reason = "La cadencia en subida fue algo contenida y eso aumentó la carga por pedalada."
    else:
        reason = "Cadencia baja en subida; el torque por pedalada elevó la carga muscular y la fatiga local."

    return round(score, 1), reason


def compute_overall_score(rs, mcs, es, pcs, mls):
    valid = [x for x in [rs, mcs, es, pcs, mls] if x is not None]
    if not valid:
        return None

    weights = {
        "rs": 0.25,
        "mcs": 0.20,
        "es": 0.20,
        "pcs": 0.20,
        "mls": 0.15,
    }

    total = 0
    total_weight = 0

    for key, value in [
        ("rs", rs),
        ("mcs", mcs),
        ("es", es),
        ("pcs", pcs),
        ("mls", mls),
    ]:
        if value is not None:
            total += value * weights[key]
            total_weight += weights[key]

    if total_weight == 0:
        return None

    return round(total / total_weight, 1)


def overall_reason(score):
    if score is None:
        return "No hubo datos suficientes para evaluar el desempeño global."
    if score >= 90:
        return "Sesión muy bien ejecutada: buena sostenibilidad, costo fisiológico controlado y rendimiento sólido."
    if score >= 80:
        return "Sesión bien ejecutada, aunque con uno o dos puntos claros de mejora."
    if score >= 70:
        return "Sesión funcional pero con limitantes visibles en ejecución, economía o sostenibilidad."
    return "Sesión exigente y costosa; hubo varias señales de deterioro en sostenibilidad y ejecución."


def build_performance_scores(analysis):
    fatigue = analysis.get("fatigue", {})
    derived = analysis.get("derived_summary", {})
    metabolic = analysis.get("metabolic_index", {})
    climbs = analysis.get("climbs", [])

    repeatability = fatigue.get("climb_repeatability_pct")
    eff_drop = fatigue.get("efficiency_drop_pct")
    vi = derived.get("vi")
    avg_msi = metabolic.get("avg_msi")
    high_msi_pct = metabolic.get("high_msi_pct")

    cad_values = [c.get("avg_cadence") for c in climbs if c.get("avg_cadence") is not None]
    avg_climb_cad = (sum(cad_values) / len(cad_values)) if cad_values else None

    rs, rs_reason = score_repeatability(repeatability)
    mcs, mcs_reason = score_metabolic_cost(avg_msi, high_msi_pct)
    es, es_reason = score_efficiency(eff_drop)
    pcs, pcs_reason = score_pacing(vi)
    mls, mls_reason = score_muscular_load(avg_climb_cad)

    overall = compute_overall_score(rs, mcs, es, pcs, mls)
    overall_explanation = overall_reason(overall)

    return {
        "repeatability_score": {
            "score": rs,
            "reason": rs_reason,
        },
        "metabolic_cost_score": {
            "score": mcs,
            "reason": mcs_reason,
        },
        "efficiency_score": {
            "score": es,
            "reason": es_reason,
        },
        "pacing_score": {
            "score": pcs,
            "reason": pcs_reason,
        },
        "muscular_load_score": {
            "score": mls,
            "reason": mls_reason,
        },
        "overall_score": {
            "score": overall,
            "reason": overall_explanation,
        },
    }