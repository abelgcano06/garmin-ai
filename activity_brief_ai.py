"""
activity_brief_ai.py
====================
Genera el brief IA de actividad usando Claude.

Schema de salida:
  quick_brief       — 5 insights comparativos + veredicto + recomendaciones
  three_day_plan    — plan 3 días basado en TSS, fatiga y objetivo del perfil
  phase_1_quick_insight  — resumen ejecutivo con scores (legacy)
  phase_2_deep_analysis  — análisis fisiológico profundo
  training_guidance      — guía técnica de entrenamiento
  contextual_layer       — identidad y patrones
"""

import json
import os
import anthropic
from athlete_context import get_athlete_context_for_section
from dotenv import load_dotenv
load_dotenv()


def load_json(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_motor_score(analysis: dict) -> int:
    """Use the motor-computed overall_score — Claude cannot override this."""
    ps = analysis.get("performance_scores", {})
    score = ps.get("overall_score", {}).get("score")
    if score is not None:
        return max(0, min(100, int(round(score))))
    return 65  # safe default when no scores available


def build_motor_score_label(score: int) -> str:
    if score >= 85:
        return "Sólido y eficiente"
    elif score >= 72:
        return "Fuerte pero caro"
    elif score >= 58:
        return "Exigente y limitado"
    else:
        return "Debajo del potencial"


def normalize_quick_output(brief: dict, motor_score: int, motor_label: str) -> dict:
    """
    Protect motor-computed values from Claude hallucination.
    Score and score_label are always overridden with motor values.
    """
    qb = brief.get("quick_brief", {})

    qb["score"] = motor_score
    qb["score_label"] = motor_label

    # Validate highlights (max 5, ensure required fields exist)
    highlights = qb.get("highlights", [])
    clean = []
    for h in highlights[:5]:
        if not isinstance(h, dict):
            continue
        clean.append({
            "titulo": str(h.get("titulo", ""))[:80],
            "valor": str(h.get("valor", ""))[:60],
            "contexto": str(h.get("contexto", ""))[:160],
            "delta": h.get("delta"),
            "sentimiento": h.get("sentimiento") if h.get("sentimiento") in ("positivo", "neutro", "negativo") else "neutro",
            "detalle": str(h.get("detalle", ""))[:220],
        })
    qb["highlights"] = clean

    # Validate correlations (max 2, require systems + insight)
    raw_corr = brief.get("correlations", [])
    clean_corr = []
    for c in raw_corr[:2]:
        if not isinstance(c, dict):
            continue
        if not c.get("systems") or not c.get("insight"):
            continue
        clean_corr.append({
            "systems": [str(s) for s in c.get("systems", [])[:3]],
            "root_cause": str(c.get("root_cause", ""))[:220],
            "insight": str(c.get("insight", ""))[:220],
            "severity": c.get("severity") if c.get("severity") in ("high", "medium") else "medium",
        })
    brief["correlations"] = clean_corr
    brief["quick_brief"] = qb
    return brief


def fill_quick_fallbacks(analysis: dict, findings: dict) -> dict:
    """
    Build a minimal motor-only brief when Claude fails or times out.
    Guarantees the UI always has data.
    """
    motor_score = build_motor_score(analysis)
    motor_label = build_motor_score_label(motor_score)

    gs = analysis.get("garmin_summary", {})
    ds = analysis.get("derived_summary", {})
    fat = analysis.get("fatigue", {})
    ps = analysis.get("performance_scores", {})

    highlights = []

    np_val = ds.get("estimated_np") or gs.get("garmin_np")
    if np_val:
        highlights.append({
            "titulo": "Potencia normalizada",
            "valor": f"{round(np_val)} W",
            "contexto": "Potencia sostenida promedio de la sesión",
            "delta": None,
            "sentimiento": "neutro",
            "detalle": ps.get("efficiency_score", {}).get("reason", ""),
        })

    tss = gs.get("garmin_tss") or ds.get("estimated_tss")
    if tss:
        highlights.append({
            "titulo": "Carga de la sesión (TSS)",
            "valor": f"{round(tss)}",
            "contexto": "Training Stress Score acumulado",
            "delta": None,
            "sentimiento": "neutro" if tss < 100 else "negativo",
            "detalle": ps.get("pacing_score", {}).get("reason", ""),
        })

    power_drop = fat.get("power_drop_pct")
    if power_drop is not None:
        highlights.append({
            "titulo": "Sostenibilidad",
            "valor": f"{power_drop:+.1f}%",
            "contexto": "Cambio de potencia entre primera y segunda mitad",
            "delta": None,
            "sentimiento": "positivo" if power_drop > -5 else "negativo",
            "detalle": ps.get("repeatability_score", {}).get("reason", ""),
        })

    finding_list = findings.get("findings", [])
    if finding_list:
        top = finding_list[0]
        highlights.append({
            "titulo": "Limitante principal",
            "valor": top.get("signal", "").replace("_", " ").title(),
            "contexto": "Señal con mayor impacto en el rendimiento de hoy",
            "delta": None,
            "sentimiento": "negativo" if top.get("severity") == "high" else "neutro",
            "detalle": top.get("summary", ""),
        })

    return {
        "meta": {
            "version": "2.0",
            "sport": "cycling",
            "activity_name": gs.get("name", ""),
            "activity_date": gs.get("start_date", "")[:10],
            "fallback": True,
        },
        "quick_brief": {
            "headline": "Análisis generado por el motor — resumen en proceso",
            "score": motor_score,
            "score_label": motor_label,
            "highlights": highlights,
            "veredicto": ps.get("overall_score", {}).get("reason", ""),
            "recomendacion_tecnica": "",
            "recomendacion_entrenamiento": "",
        },
        "three_day_plan": {"contexto": "", "dias": []},
        "phase_2_deep_analysis": {"medical_interpretation": "", "findings_summary": []},
        "correlations": [],
    }


def build_previous_activities_summary(previous_analyses: list[dict]) -> list[dict]:
    """
    Extrae un resumen comparativo de las últimas N actividades para dar contexto
    al modelo. Solo los datos relevantes para comparar con la actividad actual.
    """
    summaries = []
    for a in previous_analyses:
        gs = a.get("garmin_summary", {})
        ds = a.get("derived_summary", {})
        pp = a.get("power_profile", {})
        cl = a.get("climbs", [])
        fa = a.get("fatigue", {})

        # Mejor VAM entre las subidas
        best_vam = max((c.get("vam", 0) for c in cl), default=None)
        best_climb_grade = next(
            (c.get("avg_grade_pct") for c in sorted(cl, key=lambda x: x.get("elevation_gain_m", 0), reverse=True)),
            None
        )

        summaries.append({
            "date": gs.get("start_date", "")[:10],
            "name": gs.get("name", ""),
            "distance_km": gs.get("distance_km"),
            "elevation_m": gs.get("elevation_m"),
            "moving_min": gs.get("moving_minutes"),
            "avg_hr": gs.get("avg_hr"),
            "garmin_np": gs.get("garmin_np"),
            "garmin_tss": gs.get("garmin_tss"),
            "aerobic_efficiency": ds.get("aerobic_efficiency"),
            "avg_cadence_rpm": ds.get("avg_cadence_rpm"),
            "power_5min": pp.get("5min", {}).get("avg_power") if pp.get("5min") else None,
            "power_20min": pp.get("20min", {}).get("avg_power") if pp.get("20min") else None,
            "power_60min": pp.get("60min", {}).get("avg_power") if pp.get("60min") else None,
            "best_vam": best_vam,
            "best_climb_grade_pct": best_climb_grade,
            "fatigue_onset_min": fa.get("fatigue_onset_min"),
            "power_drop_pct": fa.get("power_drop_pct"),
        })
    return summaries


def build_prompt(
    analysis: dict,
    findings: dict,
    limiter: dict = None,
    trends: dict = None,
    athlete_context: str = "",
    previous_activities: list[dict] = None,
    athlete_baseline: dict = None,
    profile: dict = None,
    series_insights: dict = None,
    notable_events: list = None,
) -> str:
    limiter = limiter or {}
    trends = trends or {}
    previous_activities = previous_activities or []
    athlete_baseline = athlete_baseline or {}
    profile = profile or {}
    series_insights = series_insights or {}
    notable_events = notable_events or []

    # Motor-computed score — Claude cannot override these
    motor_score = build_motor_score(analysis)
    motor_label = build_motor_score_label(motor_score)

    garmin = analysis.get("garmin_summary", {})
    derived = analysis.get("derived_summary", {})
    power_profile = analysis.get("power_profile", {})
    zones = analysis.get("zones", {})
    fatigue = analysis.get("fatigue", {})
    profile_a = analysis.get("athlete_profile", {})
    climbs = analysis.get("climbs", [])
    efforts = analysis.get("efforts", [])
    metabolic = analysis.get("metabolic_index", {})
    performance_scores = analysis.get("performance_scores", {})
    finding_list = findings.get("findings", [])

    # Athlete block
    athlete_block = f"""
=========================================================
ATLETA — QUIÉN ES ESTA PERSONA
=========================================================
{athlete_context}

INSTRUCCIÓN CRÍTICA: Calibra TODO contra sus referencias personales.
No uses estándares genéricos de población.
=========================================================
""" if athlete_context else ""

    # Previous activities context
    prev_block = ""
    if previous_activities:
        prev_block = f"""
=========================================================
HISTORIAL RECIENTE — ACTIVIDADES COMPARABLES (últimas {len(previous_activities)})
=========================================================
{json.dumps(previous_activities, ensure_ascii=False, indent=2)}

USA ESTE HISTORIAL PARA:
- Comparar NP, eficiencia, VAM y potencia en duraciones clave
- Detectar mejoras o retrocesos concretos con números reales
- Detectar si las subidas fueron mejor/peor que el promedio reciente
=========================================================
"""

    # Baseline FTP curve for "tu mejor esfuerzo histórico"
    ftp_model = athlete_baseline.get("ftp_model", {})
    best_power_block = ""
    if ftp_model:
        best_power_block = f"""
=========================================================
MEJOR POTENCIA HISTÓRICA (curva all-time)
=========================================================
FTP estimado: {ftp_model.get('ftp_estimated')} W
CP: {ftp_model.get('cp_watts')} W
W': {ftp_model.get('w_prime_joules')} J
=========================================================
"""

    # Goal context for 3-day plan
    goal_event = profile.get("goal_event_name", "")
    goal_date = profile.get("goal_event_date", "")
    goal_block = ""
    if goal_event or goal_date:
        goal_coherence = athlete_baseline.get("goal_coherence", {})
        weeks_left = goal_coherence.get("semanas_restantes")
        phase = goal_coherence.get("fase_temporada", "")
        goal_block = f"""
=========================================================
OBJETIVO DEL ATLETA
=========================================================
Evento: {goal_event}
Fecha: {goal_date}
Semanas restantes: {weeks_left if weeks_left else "desconocido"}
Fase de temporada: {phase}

El plan de 3 días DEBE estar alineado con este objetivo y fase.
=========================================================
"""

    # TSS context for 3-day plan
    sustainable_load = athlete_baseline.get("sustainable_load", {})
    tss_today = garmin.get("garmin_tss")
    max_weekly_tss = sustainable_load.get("max_weekly_tss")

    return f"""
Eres un especialista de élite en fisiología del rendimiento, ciclismo MTB,
medicina del deporte, entrenamiento por potencia, fatiga y recuperación.

Responde completamente en español.
Responde SOLO con JSON válido, sin markdown ni texto adicional.
{athlete_block}{prev_block}{best_power_block}{goal_block}
==================================================
FILOSOFÍA DEL PRODUCTO
==================================================

Este producto debe sentirse como algo que el usuario NO sabía que necesitaba.

QUICK BRIEF (5 insights):
- Cada insight es UN hallazgo ESPECÍFICO con DATOS REALES
- Compara con historial si existe (con números concretos, no vagos)
- Ejemplo bueno: "Tu potencia en 5min fue 287W — 95% de tu mejor histórico (302W). Mejor que la semana pasada (271W +6%)"
- Ejemplo malo: "Buena potencia en los esfuerzos cortos"
- Usa delta: "+X% vs actividad anterior", "igual que tu mejor", "caída de X% vs hace 2 semanas"
- Si no hay historial: compara contra baselines personales del atleta
- El 5to insight siempre es el LIMITANTE PRINCIPAL de hoy explicado humanamente

PLAN 3 DÍAS:
- Mañana: siempre empieza por necesidad de recuperación según TSS de hoy
- Días 2 y 3: progresión lógica hacia el objetivo del evento
- Sin vaguedades: especifica tipo, duración, zona, y qué medir

ANÁLISIS PROFUNDO (phase_2):
- Aquí sí puedes ser nerd fisiológico
- Explica POR QUÉ pasó lo que pasó, no solo QUÉ pasó
- Conecta: causa fisiológica → mecanismo → consecuencia para el rendimiento

==================================================
LENGUAJE CON IDENTIDAD
==================================================
- "fuerte pero caro fisiológicamente"
- "buen motor, mala conservación"
- "explosivo pero no sostenible"
- "llegaste cargado" / "el sistema no bajó marchas"
- "ejecutaste bien con lo que había"
- NO uses: "buena sesión", "rendimiento aceptable"

==================================================
SALIDA OBLIGATORIA — JSON EXACTO
==================================================

{{
  "meta": {{
    "version": "2.0",
    "sport": "cycling",
    "activity_name": "{garmin.get('name', '')}",
    "activity_date": "{garmin.get('start_date', '')[:10]}"
  }},

  "quick_brief": {{
    "headline": "Una línea potente y memorable que resume la sesión completa",
    "score": {motor_score},
    "score_label": "{motor_label}",

    "highlights": [
      {{
        "titulo": "nombre del insight (ej: Potencia en subidas)",
        "valor": "el dato concreto (ej: 4.2 W/kg)",
        "contexto": "contra qué se compara (ej: tu media últimas 3 salidas fue 3.9 W/kg)",
        "delta": "cambio numérico (ej: +8% vs semana pasada) — null si no hay historial",
        "sentimiento": "positivo|neutro|negativo",
        "detalle": "1 línea explicando qué significa para el atleta específicamente"
      }},
      {{
        "titulo": "...",
        "valor": "...",
        "contexto": "...",
        "delta": null,
        "sentimiento": "...",
        "detalle": "..."
      }},
      {{
        "titulo": "...",
        "valor": "...",
        "contexto": "...",
        "delta": null,
        "sentimiento": "...",
        "detalle": "..."
      }},
      {{
        "titulo": "...",
        "valor": "...",
        "contexto": "...",
        "delta": null,
        "sentimiento": "...",
        "detalle": "..."
      }},
      {{
        "titulo": "Limitante del día",
        "valor": "nombre del limitante",
        "contexto": "en qué momento se manifestó",
        "delta": null,
        "sentimiento": "negativo",
        "detalle": "qué significó para el rendimiento de hoy"
      }}
    ],

    "veredicto": "La verdad incómoda o poderosa en 1 línea",
    "recomendacion_tecnica": "Para mejorar específicamente esto: acción concreta (ej: en la próxima subida de >7%, mantén cadencia >80rpm aunque bajes potencia)",
    "recomendacion_entrenamiento": "Para entrenar esta semana: sesión específica con tipo, duración, zona e indicador de éxito"
  }},

  "three_day_plan": {{
    "contexto": "2 líneas explicando por qué este plan específico (TSS de hoy, fatiga detectada, semanas al evento)",
    "dias": [
      {{
        "dia": "Mañana",
        "tipo": "nombre del tipo de sesión",
        "descripcion": "qué hacer exactamente",
        "duracion": "ej: 45-60 min",
        "intensidad": "zona o descripción (ej: Z1-Z2, conversacional, <65% FCmax)",
        "metricas_objetivo": "qué medir para saber que fue bien",
        "si_te_sientes_mal": "alternativa si el cuerpo no responde"
      }},
      {{
        "dia": "Pasado mañana",
        "tipo": "...",
        "descripcion": "...",
        "duracion": "...",
        "intensidad": "...",
        "metricas_objetivo": "...",
        "si_te_sientes_mal": "..."
      }},
      {{
        "dia": "En 3 días",
        "tipo": "...",
        "descripcion": "...",
        "duracion": "...",
        "intensidad": "...",
        "metricas_objetivo": "...",
        "si_te_sientes_mal": "..."
      }}
    ]
  }},

  "phase_2_deep_analysis": {{
    "medical_interpretation": "2-3 párrafos: causa fisiológica → mecanismo → consecuencia para el rendimiento. Sé técnico y específico con los datos de hoy.",
    "findings_summary": ["hallazgo 1", "hallazgo 2", "hallazgo 3"]
  }},

  "correlations": [
    {{
      "systems": ["FC", "Stamina"],
      "root_cause": "el evento temporal compartido que explica la correlación (ej: sprint en min 47 agotó stamina y disparó FC)",
      "insight": "qué significa que estas dos señales fallen juntas para el rendimiento del atleta",
      "severity": "high"
    }},
    {{
      "systems": ["Cadencia", "Potencia"],
      "root_cause": "...",
      "insight": "...",
      "severity": "medium"
    }}
  ]
}}

INSTRUCCIÓN CORRELACIONES:
Busca eventos en SERIES INSIGHTS y EVENTOS NOTABLES donde dos señales distintas
cayeron o se dispararon con menos de 10 minutos de diferencia.
Solo escribe una correlación si realmente ves la conexión temporal en los datos.
Máximo 2 correlaciones. Si no hay correlación real, devuelve "correlations": [].
SCORE: {motor_score} — EL MOTOR LO CALCULÓ. CÓPIALO EXACTO, NO LO CAMBIES.

==================================================
INPUTS ANALÍTICOS — ACTIVIDAD DE HOY
==================================================

GARMIN SUMMARY
{json.dumps(garmin, ensure_ascii=False, indent=2)}

DERIVED SUMMARY
{json.dumps(derived, ensure_ascii=False, indent=2)}

POWER PROFILE
{json.dumps(power_profile, ensure_ascii=False, indent=2)}

ZONES
{json.dumps(zones, ensure_ascii=False, indent=2)}

CLIMBS ({len(climbs)} ascensos)
{json.dumps(climbs, ensure_ascii=False, indent=2)}

FATIGUE
{json.dumps(fatigue, ensure_ascii=False, indent=2)}

ATHLETE PROFILE
{json.dumps(profile_a, ensure_ascii=False, indent=2)}

METABOLIC INDEX
{json.dumps(metabolic, ensure_ascii=False, indent=2)}

PERFORMANCE SCORES
{json.dumps(performance_scores, ensure_ascii=False, indent=2)}

LIMITER DETECTOR
{json.dumps(limiter, ensure_ascii=False, indent=2)}

TRENDS
{json.dumps(trends, ensure_ascii=False, indent=2)}

FINDINGS
{json.dumps(finding_list[:10], ensure_ascii=False, indent=2)}

SERIES INSIGHTS (correlaciones temporales extraídas del CSV punto a punto)
{json.dumps(series_insights, ensure_ascii=False, indent=2) if series_insights else "No disponibles — usa los datos agregados anteriores"}

INSTRUCCIÓN PARA SERIES INSIGHTS:
Los datos anteriores son correlaciones REALES calculadas de la serie temporal completa.
Úsalos directamente en los highlights cuando sean relevantes:
- cardiac_decoupling -> eficiencia cardiovascular y fatiga aeróbica
- stamina_depletion -> cuándo y qué tan rápido se agotó la disponibilidad energética
- cadence_fatigue_per_climb -> cadencia vs fatiga neuromuscular por ascenso
- wbpm_efficiency_segments -> deterioro de eficiencia W/FC a lo largo del tiempo
- second_half_degradation -> degradación global de la segunda mitad

EVENTOS NOTABLES — TIMESTAMPS REALES DEL CSV
{json.dumps(notable_events, ensure_ascii=False, indent=2) if notable_events else "No detectados."}

INSTRUCCIÓN EVENTOS:
Estos eventos tienen timestamp exacto. Úsalos para:
- Citar el momento específico en highlights ("en min 47, la cadencia cayó a 53rpm…")
- Detectar correlaciones: si FC y Stamina colapsan dentro de 10 min = correlación real
- Explicar en deep_analysis POR QUÉ ese momento fue el punto de quiebre

TSS HOY: {tss_today if tss_today else "no disponible"}
CARGA SEMANAL MAX SOSTENIBLE: {max_weekly_tss if max_weekly_tss else "no calculada aún"}
"""


def call_ai(prompt: str) -> str:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def save_brief_json(analysis_path: str, brief: dict) -> str:
    activity_folder = os.path.dirname(analysis_path)
    output_path = os.path.join(activity_folder, "activity_brief.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2, ensure_ascii=False)
    return output_path


def print_brief(brief: dict) -> None:
    qb = brief.get("quick_brief", {})
    tdp = brief.get("three_day_plan", {})
    p2 = brief.get("phase_2_deep_analysis", {})

    print(f"\n{'='*60}")
    print("QUICK BRIEF")
    print(f"{'='*60}")
    print(f"Headline: {qb.get('headline', '')}")
    print(f"Score: {qb.get('score', '')}/100 — {qb.get('score_label', '')}")
    print("\n5 INSIGHTS:")
    for h in qb.get("highlights", []):
        delta = f" ({h.get('delta')})" if h.get("delta") else ""
        print(f"  [{h.get('sentimiento','?').upper()[:3]}] {h.get('titulo')}: {h.get('valor')}{delta}")
        print(f"        {h.get('detalle')}")
    print(f"\nVeredicto: {qb.get('veredicto', '')}")
    print(f"Tecnico: {qb.get('recomendacion_tecnica', '')}")
    print(f"Entrenamiento: {qb.get('recomendacion_entrenamiento', '')}")

    print(f"\n{'='*60}")
    print("PLAN 3 DÍAS")
    print(f"{'='*60}")
    print(f"Contexto: {tdp.get('contexto', '')}")
    for d in tdp.get("dias", []):
        print(f"\n  {d.get('dia')} — {d.get('tipo')} ({d.get('duracion')})")
        print(f"  Intensidad: {d.get('intensidad')}")
        print(f"  Descripción: {d.get('descripcion')}")
        print(f"  Objetivo: {d.get('metricas_objetivo')}")

    print(f"\n{'='*60}")
    print("ANÁLISIS PROFUNDO")
    print(f"{'='*60}")
    print(p2.get("medical_interpretation", ""))
