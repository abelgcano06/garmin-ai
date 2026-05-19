import json
import os
import anthropic
from athlete_context import get_athlete_context_for_section

client = anthropic.Anthropic()


# =========================================================
# Utils
# =========================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clamp(value, low=0.0, high=10.0):
    return max(low, min(high, value))


def clamp100(value):
    return max(0, min(100, int(round(value))))


def score10(value_100):
    if value_100 is None:
        return 0.0
    return round(clamp(float(value_100) / 10.0), 1)


def safe_get(dct, *keys, default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# =========================================================
# Motor-derived quick layer
# =========================================================

def build_motor_system_scores(analysis, findings=None, longitudinal_brief=None, trends=None, patterns=None):
    findings = findings or {}
    longitudinal_brief = longitudinal_brief or {}
    trends = trends or {}
    patterns = patterns or {}

    recovery_summary = analysis.get("recovery_summary", {})
    autonomic = analysis.get("autonomic_recovery", {})
    respiratory = analysis.get("respiratory_recovery", {})
    oxygenation = analysis.get("oxygenation", {})
    circadian = analysis.get("circadian_alignment", {})
    energy = analysis.get("energy_recharge", {})
    flags = findings.get("flags", {})

    neural_score = score10(recovery_summary.get("neural_recovery_score"))
    physical_score = score10(recovery_summary.get("physical_recovery_score"))
    autonomic_score = score10(autonomic.get("autonomic_recovery_curve_score"))

    respiratory_raw = None
    if respiratory.get("respiratory_stability_score") is not None and oxygenation.get("oxygen_stability_score") is not None:
        respiratory_raw = (
            float(respiratory.get("respiratory_stability_score")) * 0.55
            + float(oxygenation.get("oxygen_stability_score")) * 0.45
        )
    elif respiratory.get("respiratory_stability_score") is not None:
        respiratory_raw = float(respiratory.get("respiratory_stability_score"))
    elif oxygenation.get("oxygen_stability_score") is not None:
        respiratory_raw = float(oxygenation.get("oxygen_stability_score"))
    else:
        respiratory_raw = 0.0

    if flags.get("possible_oxygenation_issue"):
        respiratory_raw -= 12
    if flags.get("possible_respiratory_instability"):
        respiratory_raw -= 8

    respiratory_score = score10(max(0.0, respiratory_raw))
    circadian_score = score10(circadian.get("circadian_alignment_score"))
    energy_score = score10(energy.get("recharge_efficiency"))

    return {
        "brain_mind": neural_score,
        "body_physical": physical_score,
        "nervous_system": autonomic_score,
        "breathing_oxygen": respiratory_score,
        "body_clock": circadian_score,
        "energy_reserve": energy_score,
    }


def build_motor_hero(analysis, findings=None, longitudinal_brief=None, trends=None, patterns=None):
    findings = findings or {}
    longitudinal_brief = longitudinal_brief or {}
    trends = trends or {}
    patterns = patterns or {}

    overall = safe_get(analysis, "recovery_summary", "overall_recovery_score", default=0.0)
    hero_score = clamp100(overall)

    if hero_score >= 85:
        status = "Recuperación sólida"
    elif hero_score >= 70:
        status = "Listo con cautela"
    elif hero_score >= 55:
        status = "Recuperación parcial"
    else:
        status = "Recuperación limitada"

    return {
        "score": hero_score,
        "status": status,
        "headline": ""
    }


def build_motor_system_shells(system_scores):
    def status_from_score(score):
        if score >= 7.5:
            return "up"
        if score >= 5.8:
            return "stable"
        if score >= 4.0:
            return "down"
        return "warning"

    ordered = [
        ("Mente", "brain_mind"),
        ("Cuerpo", "body_physical"),
        ("Sistema nervioso", "nervous_system"),
        ("Respiración", "breathing_oxygen"),
        ("Ritmo biológico", "body_clock"),
        ("Energía", "energy_reserve"),
    ]

    systems = []
    for label, key in ordered:
        score = float(system_scores.get(key, 0.0))
        systems.append({
            "name": label,
            "score": round(score, 1),
            "status": status_from_score(score),
            "message": ""
        })
    return systems


def build_motor_quick_base(analysis, findings=None, longitudinal_brief=None, trends=None, patterns=None):
    findings = findings or {}
    longitudinal_brief = longitudinal_brief or {}
    trends = trends or {}
    patterns = patterns or {}

    hero = build_motor_hero(
        analysis=analysis,
        findings=findings,
        longitudinal_brief=longitudinal_brief,
        trends=trends,
        patterns=patterns,
    )

    system_scores = build_motor_system_scores(
        analysis=analysis,
        findings=findings,
        longitudinal_brief=longitudinal_brief,
        trends=trends,
        patterns=patterns,
    )

    systems = build_motor_system_shells(system_scores)

    return {
        "hero": hero,
        "systems": systems,
        "today": {
            "performance": "",
            "action": ""
        },
        "pattern": {
            "message": ""
        }
    }


# =========================================================
# Prompt
# =========================================================

def build_prompt(
    analysis,
    findings,
    brief=None,
    notable_events=None,
    longitudinal_brief=None,
    trends=None,
    patterns=None,
    athlete_context=None,
):
    brief = brief or {}
    notable_events = notable_events or []
    longitudinal_brief = longitudinal_brief or {}
    trends = trends or {}
    patterns = patterns or {}
    athlete_context = athlete_context or ""

    quick_base = build_motor_quick_base(
        analysis=analysis,
        findings=findings,
        longitudinal_brief=longitudinal_brief,
        trends=trends,
        patterns=patterns,
    )

    athlete_block = f"""
=========================================================
ATLETA — QUIÉN ES ESTA PERSONA
=========================================================
{athlete_context}

INSTRUCCIÓN CRÍTICA: Los scores y valores de HOY deben interpretarse contra las
REFERENCIAS PERSONALES del atleta listadas arriba, NO contra promedios poblacionales.
Si su HRV basal es 62ms y hoy tiene 58ms → está por debajo de SU norma, eso es relevante.
Si su readiness basal es 50 y hoy tiene 53 → para ÉL es un buen día.
=========================================================
""" if athlete_context else ""

    return f"""
Responde completamente en español.

Eres un especialista de élite en sueño, recuperación fisiológica, sistema nervioso autónomo,
ritmos circadianos, respiración nocturna, HRV, oxigenación, fatiga acumulada y rendimiento humano.

Tu trabajo es interpretar TODA la información ya procesada por el motor analítico
y traducirla a una salida clara, humana, útil y premium para producto.
{athlete_block}
IMPORTANTE:
- No recalculas nada.
- No inventas scores.
- No cambias scores.
- No cambias nombres del quick report.
- Usas TODA la información disponible:
  - analysis
  - findings
  - brief
  - notable_events (eventos con timestamp — úsalos para dar contexto temporal específico)
  - longitudinal_brief
  - trends
  - patterns

OBJETIVO:
La app debe mostrar primero una capa rápida y poderosa:
- cómo está el cuerpo hoy
- qué fue lo más importante
- qué sistemas amanecieron bien o mal
- qué impacto tendrá hoy
- qué conviene hacer
- qué patrón personal se repite

Y luego una capa profunda:
- deep_analysis completo

=========================================================
REGLAS CLAVE
=========================================================

1. El quick report debe sentirse como una app premium.
2. El quick report debe estar SIEMPRE completo.
3. El histórico debe influir de forma clara en "pattern.message".
4. Si la noche actual contradice o confirma el patrón, dilo.
5. Si hay bottleneck dominante histórico, úsalo.
6. Si hay riesgo respiratorio recurrente, intégralo.
7. No repitas tags técnicos robóticos literalmente si suenan feos.
8. Traduce la fisiología a lenguaje humano.
9. No hagas párrafos largos en hero/systems/today/pattern.
10. El análisis largo sí puede desarrollar más.

=========================================================
QUICK REPORT BASE (YA VIENE DEL MOTOR)
=========================================================

Debes RESPETAR ESTA ESTRUCTURA EXACTA y completar solo los textos:

{json.dumps(quick_base, ensure_ascii=False, indent=2)}

Explicación:
- hero.score y hero.status ya vienen del motor → NO cambiarlos
- systems[].name, systems[].score y systems[].status ya vienen del motor → NO cambiarlos
- Tú debes rellenar:
  - hero.headline
  - systems[].message
  - today.performance
  - today.action
  - pattern.message
  - correlations[] (máximo 2, solo si son genuinas — ver instrucciones abajo)

=========================================================
SALIDA OBLIGATORIA
=========================================================

Devuelve JSON válido con esta estructura EXACTA:

{{
  "hero": {{
    "score": {quick_base["hero"]["score"]},
    "status": "{quick_base["hero"]["status"]}",
    "headline": "..."
  }},
  "systems": [
    {{
      "name": "Mente",
      "score": {quick_base["systems"][0]["score"]},
      "status": "{quick_base["systems"][0]["status"]}",
      "message": "..."
    }},
    {{
      "name": "Cuerpo",
      "score": {quick_base["systems"][1]["score"]},
      "status": "{quick_base["systems"][1]["status"]}",
      "message": "..."
    }},
    {{
      "name": "Sistema nervioso",
      "score": {quick_base["systems"][2]["score"]},
      "status": "{quick_base["systems"][2]["status"]}",
      "message": "..."
    }},
    {{
      "name": "Respiración",
      "score": {quick_base["systems"][3]["score"]},
      "status": "{quick_base["systems"][3]["status"]}",
      "message": "..."
    }},
    {{
      "name": "Ritmo biológico",
      "score": {quick_base["systems"][4]["score"]},
      "status": "{quick_base["systems"][4]["status"]}",
      "message": "..."
    }},
    {{
      "name": "Energía",
      "score": {quick_base["systems"][5]["score"]},
      "status": "{quick_base["systems"][5]["status"]}",
      "message": "..."
    }}
  ],
  "today": {{
    "performance": "...",
    "action": "..."
  }},
  "pattern": {{
    "message": "..."
  }},
  "correlations": [
    {{
      "systems": ["Sistema A", "Sistema B"],
      "root_cause": "qué evento o señal los conecta — menciona hora si está disponible",
      "insight": "1-2 frases explicando que no son dos problemas sino uno y por qué importa",
      "severity": "high | medium"
    }}
  ],
  "deep_analysis": {{
    "headline": "...",
    "night_type_interpretation": "...",
    "primary_limiter": "...",
    "secondary_limiter": "...",
    "main_insight": "...",
    "what_happened": "...",
    "what_it_means_in_you": "...",
    "likely_drivers": "...",
    "physiology_summary": "...",
    "performance_outlook": "...",
    "training_guidance": "...",
    "recovery_focus": "...",
    "follow_up_priority": "...",
    "key_takeaways": [
      "...",
      "...",
      "...",
      "..."
    ],
    "extra_insights": [
      {{
        "title": "...",
        "text": "..."
      }},
      {{
        "title": "...",
        "text": "..."
      }}
    ],
    "chat_starters": [
      "...",
      "...",
      "..."
    ]
  }}
}}

=========================================================
INSTRUCCIONES DE ESTILO
=========================================================

HERO:
- headline = 1 sola línea fuerte y clara
- no pongas números en headline
- debe resumir la verdad principal de la noche

SYSTEMS:
- message = 1 sola frase corta por sistema
- Si el sistema tiene status "up" o "stable" y score >= 6.5: mensaje positivo breve o déjalo vacío ""
- Si el sistema tiene status "down" o "warning": menciona el evento específico de notable_events si existe (hora, señal, magnitud)
- NO recomendaciones aquí
- NO métricas crudas
- que suene humano
- Ejemplo bueno: "Dos drops de SpO₂ entre las 2 y las 4am afectaron la estabilidad respiratoria."
- Ejemplo malo: "La respiración no fue el mejor punto de la noche."

CORRELACIONES:
- Busca activamente si 2 o más sistemas bajaron POR LA MISMA CAUSA RAÍZ
- Las correlaciones más comunes: SpO₂ drop → HRV collapse (Respiración + Sistema nervioso)
- Otros patrones: stress spike nocturno → HR arousal (Estrés + SNA), deuda de sueño → Mente comprometida
- Si encuentras correlación genuina: documéntala en "correlations" con la hora del evento que las conecta
- Si NO hay correlación clara: devuelve "correlations": [] — no inventes conexiones
- Máximo 2 correlaciones reales

TODAY:
- performance = cómo se sentirá hoy el rendimiento
- action = qué conviene hacer hoy
- 1–2 frases máximo

PATTERN:
- message = la señal histórica más importante
- debe integrar tendencias, patterns, bottlenecks y longitudinal brief
- debe sonar como algo inteligente y personal
- si esto se repite, dilo
- si mejora o empeora, dilo
- si la noche confirma el patrón dominante, dilo

DEEP ANALYSIS:
- aquí sí puedes desarrollar más
- debe seguir siendo humano, técnico y accionable

=========================================================
EVENTOS NOTABLES DE LA NOCHE (con timestamp real)
=========================================================
{json.dumps(notable_events, ensure_ascii=False, indent=2)}

Instrucción: Cuando un sistema tenga status "down" o "warning", busca en esta lista
si hay un evento que lo explique. Menciona la hora y magnitud en el message del sistema.
Busca también si dos eventos de señales distintas ocurrieron cerca en el tiempo (< 15 min)
— eso es una correlación real para incluir en "correlations".

=========================================================
ANALYSIS
=========================================================
{json.dumps(analysis, ensure_ascii=False, indent=2)}

=========================================================
FINDINGS
=========================================================
{json.dumps(findings, ensure_ascii=False, indent=2)}

=========================================================
RULE-BASED BRIEF
=========================================================
{json.dumps(brief, ensure_ascii=False, indent=2)}

=========================================================
LONGITUDINAL BRIEF
=========================================================
{json.dumps(longitudinal_brief, ensure_ascii=False, indent=2)}

=========================================================
TRENDS
=========================================================
{json.dumps(trends, ensure_ascii=False, indent=2)}

=========================================================
PATTERNS
=========================================================
{json.dumps(patterns, ensure_ascii=False, indent=2)}
"""


# =========================================================
# Model / parse
# =========================================================

def call_ai(prompt):
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def parse_json_response(text):
    text = text.strip()

    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()
    return json.loads(text)


# =========================================================
# Fallback / normalization
# =========================================================

def normalize_quick_output(ai_brief, analysis, findings, longitudinal_brief=None, trends=None, patterns=None):
    longitudinal_brief = longitudinal_brief or {}
    trends = trends or {}
    patterns = patterns or {}

    quick_base = build_motor_quick_base(
        analysis=analysis,
        findings=findings,
        longitudinal_brief=longitudinal_brief,
        trends=trends,
        patterns=patterns,
    )

    out = {
        "hero": quick_base["hero"],
        "systems": quick_base["systems"],
        "today": quick_base["today"],
        "pattern": quick_base["pattern"],
        "correlations": [],
        "deep_analysis": {}
    }

    if not isinstance(ai_brief, dict):
        return out

    # HERO
    hero_in = ai_brief.get("hero", {})
    if isinstance(hero_in, dict):
        out["hero"]["headline"] = hero_in.get("headline", "") or ""

    # SYSTEMS
    systems_in = ai_brief.get("systems", [])
    if isinstance(systems_in, list):
        by_name = {}
        for s in systems_in:
            if isinstance(s, dict):
                name = s.get("name")
                if name:
                    by_name[name] = s

        for system in out["systems"]:
            s_in = by_name.get(system["name"], {})
            if isinstance(s_in, dict):
                msg = s_in.get("message", "")
                if msg:
                    system["message"] = msg

    # TODAY
    today_in = ai_brief.get("today", {})
    if isinstance(today_in, dict):
        out["today"]["performance"] = today_in.get("performance", "") or ""
        out["today"]["action"] = today_in.get("action", "") or ""

    # PATTERN
    pattern_in = ai_brief.get("pattern", {})
    if isinstance(pattern_in, dict):
        out["pattern"]["message"] = pattern_in.get("message", "") or ""

    # CORRELATIONS
    corr_in = ai_brief.get("correlations", [])
    if isinstance(corr_in, list):
        valid = []
        for c in corr_in:
            if isinstance(c, dict) and c.get("systems") and c.get("insight"):
                valid.append({
                    "systems": c.get("systems", []),
                    "root_cause": c.get("root_cause", ""),
                    "insight": c.get("insight", ""),
                    "severity": c.get("severity", "medium"),
                })
        out["correlations"] = valid[:2]

    # DEEP
    deep_in = ai_brief.get("deep_analysis", {})
    if isinstance(deep_in, dict):
        out["deep_analysis"] = deep_in

    return fill_quick_fallbacks(out, analysis, findings, longitudinal_brief, trends, patterns)


def fill_quick_fallbacks(brief, analysis, findings, longitudinal_brief=None, trends=None, patterns=None):
    longitudinal_brief = longitudinal_brief or {}
    trends = trends or {}
    patterns = patterns or {}

    hero = brief.get("hero", {})
    systems = brief.get("systems", [])
    today = brief.get("today", {})
    pattern = brief.get("pattern", {})
    deep = brief.get("deep_analysis", {})

    # fallback headline
    if not hero.get("headline"):
        primary_limiter = safe_get(findings, "limiters", "primary_limiter", default="")
        overall = safe_get(analysis, "recovery_summary", "overall_recovery_score", default=0)

        if primary_limiter == "respiratory_instability":
            hero["headline"] = "Recuperaste energía, pero la respiración sigue siendo el principal freno de calidad."
        elif primary_limiter == "sleep_quantity_deficit":
            hero["headline"] = "Dormiste funcional, pero todavía te faltaron horas reales para una recuperación completa."
        elif primary_limiter == "poor_neural_recovery":
            hero["headline"] = "La noche sostuvo lo físico, pero la recuperación mental quedó corta."
        elif primary_limiter == "circadian_misalignment":
            hero["headline"] = "El horario de sueño volvió a jugar en contra de una recuperación más profunda."
        elif overall >= 80:
            hero["headline"] = "La noche fue sólida y te deja bien parado para el día."
        elif overall >= 65:
            hero["headline"] = "La noche fue utilizable, pero no completamente restauradora."
        else:
            hero["headline"] = "La recuperación quedó corta y hoy conviene administrar carga."

    # fallback systems messages
    default_messages = {
        "Mente": "La recuperación mental no quedó del todo fina y hoy el foco puede sentirse más lento.",
        "Cuerpo": "La parte física está utilizable, aunque no en su mejor versión.",
        "Sistema nervioso": "Tu sistema nervioso no terminó de bajar completamente durante la noche.",
        "Respiración": "La respiración no fue el mejor punto de la noche y merece seguimiento dentro de tu patrón.",
        "Ritmo biológico": "El reloj biológico no fue el principal problema hoy.",
        "Energía": "Tienes energía suficiente para el día si administras bien la carga."
    }

    for s in systems:
        if not s.get("message"):
            s["message"] = default_messages.get(s.get("name", ""), "Este sistema amaneció con recuperación parcial.")

    # fallback today
    if not today.get("performance"):
        overall = safe_get(analysis, "recovery_summary", "overall_recovery_score", default=0)
        if overall >= 80:
            today["performance"] = "Buen potencial para rendir hoy, especialmente si mantienes control y regularidad."
        elif overall >= 65:
            today["performance"] = "Día funcional y productivo, pero los picos de intensidad pueden sentirse más caros."
        else:
            today["performance"] = "Hoy el rendimiento puede sostenerse solo si evitas apretar demasiado."

    if not today.get("action"):
        primary_limiter = safe_get(findings, "limiters", "primary_limiter", default="")
        if primary_limiter == "sleep_quantity_deficit":
            today["action"] = "Entrena con control y prioriza sumar sueño real esta noche."
        elif primary_limiter == "respiratory_instability":
            today["action"] = "Entrena con moderación y protege la respiración nocturna hoy."
        elif primary_limiter == "poor_neural_recovery":
            today["action"] = "Prioriza base, técnica o trabajo controlado y evita exprimir la parte mental."
        else:
            today["action"] = "Prioriza trabajo controlado, evita máximos y busca cerrar mejor la recuperación esta noche."

    # fallback pattern
    if not pattern.get("message"):
        dominant_bottleneck = longitudinal_brief.get("dominant_bottleneck", "")
        longitudinal_limiter = longitudinal_brief.get("longitudinal_limiter", "")
        recovery_trajectory = longitudinal_brief.get("recovery_trajectory", "")
        recurrent_patterns = patterns.get("recurrent_patterns", [])

        if dominant_bottleneck == "respiratory_bottleneck":
            pattern["message"] = "Tu patrón dominante sigue apuntando a fragilidad respiratoria nocturna, aunque la energía general haya mejorado."
        elif longitudinal_limiter == "sleep_quantity_deficit":
            pattern["message"] = "Se repite tu patrón dominante: quedarte corto de horas reales de sueño."
        elif recurrent_patterns:
            pattern["message"] = recurrent_patterns[0].get("description", "Se mantiene un patrón repetido en tu historial.")
        elif recovery_trajectory == "improving":
            pattern["message"] = "La tendencia general mejora, aunque el sistema todavía no está del todo limpio."
        else:
            pattern["message"] = "La noche actual encaja con tu patrón reciente de recuperación parcial."

    # fallback deep analysis
    if not deep:
        deep = {
            "headline": hero.get("headline", ""),
            "night_type_interpretation": "Noche funcional con recuperación parcial.",
            "primary_limiter": safe_get(findings, "limiters", "primary_limiter", default=""),
            "secondary_limiter": safe_get(findings, "limiters", "secondary_limiter", default=""),
            "main_insight": "La noche dejó energía utilizable, pero no una recuperación completamente limpia.",
            "what_happened": "La noche combinó aspectos buenos y otros que limitaron una restauración más completa.",
            "what_it_means_in_you": "Esto encaja con tu patrón reciente y ayuda a explicar cómo suele responder tu cuerpo.",
            "likely_drivers": "Combinación probable de carga acumulada, arquitectura incompleta y factores de horario o respiración.",
            "physiology_summary": "La recuperación fue parcial: energía disponible, pero con limitantes de fondo.",
            "performance_outlook": today.get("performance", ""),
            "training_guidance": today.get("action", ""),
            "recovery_focus": "Proteger la siguiente noche y atacar el cuello de botella dominante.",
            "follow_up_priority": pattern.get("message", ""),
            "key_takeaways": [
                "La noche fue funcional, no perfecta.",
                "El cuello de botella principal sigue activo.",
                "Puedes producir hoy si administras la carga.",
                "La siguiente noche importa mucho para consolidar recuperación."
            ],
            "extra_insights": [],
            "chat_starters": []
        }

    brief["hero"] = hero
    brief["systems"] = systems
    brief["today"] = today
    brief["pattern"] = pattern
    brief["correlations"] = brief.get("correlations", [])
    brief["deep_analysis"] = deep

    return brief


# =========================================================
# Save / print
# =========================================================

def save_brief_json(analysis_path, brief):
    sleep_folder = os.path.dirname(analysis_path)
    output_path = os.path.join(sleep_folder, "sleep_brief_ai.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2, ensure_ascii=False)

    return output_path


def print_brief(brief):
    hero = brief.get("hero", {})
    systems = brief.get("systems", [])
    today = brief.get("today", {})
    pattern = brief.get("pattern", {})
    deep_analysis = brief.get("deep_analysis", {})

    print("\n==========================")
    print("SLEEP HERO")
    print("==========================\n")
    print(f"SLEEP SCORE: {hero.get('score', '')}/100")
    print(f"STATUS: {hero.get('status', '')}\n")
    print(f"{hero.get('headline', '')}\n")

    if systems:
        print("==========================")
        print("CÓMO AMANECIERON TUS SISTEMAS")
        print("==========================\n")

        for system in systems:
            print(f"{system.get('name', '')}")
            print(f"Score: {system.get('score', '')}/10")
            print(f"Estado: {system.get('status', '')}")
            print(f"{system.get('message', '')}\n")

    print("==========================")
    print("HOY")
    print("==========================\n")
    print(f"Rendimiento: {today.get('performance', '')}\n")
    print(f"Acción: {today.get('action', '')}\n")

    print("==========================")
    print("TU PATRÓN")
    print("==========================\n")
    print(f"{pattern.get('message', '')}\n")

    print("==========================")
    print("DEEP ANALYSIS")
    print("==========================\n")

    print(f"Headline: {deep_analysis.get('headline', '')}\n")
    print(f"Tipo de noche: {deep_analysis.get('night_type_interpretation', '')}\n")
    print(f"Insight principal: {deep_analysis.get('main_insight', '')}\n")
    print(f"Qué pasó: {deep_analysis.get('what_happened', '')}\n")
    print(f"Qué significa en ti: {deep_analysis.get('what_it_means_in_you', '')}\n")
    print(f"Probables drivers: {deep_analysis.get('likely_drivers', '')}\n")
    print(f"Resumen fisiológico: {deep_analysis.get('physiology_summary', '')}\n")
    print(f"Impacto en rendimiento: {deep_analysis.get('performance_outlook', '')}\n")
    print(f"Qué hacer con entrenamiento: {deep_analysis.get('training_guidance', '')}\n")
    print(f"Foco de recuperación: {deep_analysis.get('recovery_focus', '')}\n")
    print(f"Seguimiento: {deep_analysis.get('follow_up_priority', '')}\n")

    print("KEY TAKEAWAYS:")
    for item in deep_analysis.get("key_takeaways", []):
        print(f"- {item}")

    extra_insights = deep_analysis.get("extra_insights", [])
    if extra_insights:
        print("\n==========================")
        print("EXTRA INSIGHTS")
        print("==========================")
        for i, item in enumerate(extra_insights, start=1):
            print(f"\n{i}. {item.get('title')}")
            print(item.get("text"))

    chat_starters = deep_analysis.get("chat_starters", [])
    if chat_starters:
        print("\n==========================")
        print("PREGUNTAS SUGERIDAS")
        print("==========================")
        for q in chat_starters:
            print(f"- {q}")


# =========================================================
# Main generator
# =========================================================

def generate_sleep_ai_brief(
    analysis_path,
    findings_path,
    brief_path=None,
    events_path=None,
    longitudinal_brief_path=None,
    trends_path=None,
    patterns_path=None,
    user_dir=None,
):
    if not os.path.exists(analysis_path):
        print("No se encontró el archivo sleep_analysis.json.")
        return None

    if not os.path.exists(findings_path):
        print("No se encontró el archivo sleep_findings.json.")
        return None

    analysis = load_json(analysis_path)
    findings = load_json(findings_path)

    brief = {}
    notable_events = []
    longitudinal_brief = {}
    trends = {}
    patterns = {}

    if brief_path and os.path.exists(brief_path):
        brief = load_json(brief_path)

    if events_path and os.path.exists(events_path):
        notable_events = load_json(events_path)

    if longitudinal_brief_path and os.path.exists(longitudinal_brief_path):
        longitudinal_brief = load_json(longitudinal_brief_path)

    if trends_path and os.path.exists(trends_path):
        trends = load_json(trends_path)

    if patterns_path and os.path.exists(patterns_path):
        patterns = load_json(patterns_path)

    athlete_context = get_athlete_context_for_section(user_dir, "sleep") if user_dir else ""

    prompt = build_prompt(
        analysis=analysis,
        findings=findings,
        brief=brief,
        notable_events=notable_events,
        longitudinal_brief=longitudinal_brief,
        trends=trends,
        patterns=patterns,
        athlete_context=athlete_context,
    )

    raw_text = call_ai(prompt)

    try:
        ai_brief_raw = parse_json_response(raw_text)
    except Exception as e:
        print("\nNo se pudo parsear JSON del modelo.")
        print("Respuesta cruda:\n")
        print(raw_text)
        print(f"\nError: {e}")
        return None

    ai_brief = normalize_quick_output(
        ai_brief_raw,
        analysis=analysis,
        findings=findings,
        longitudinal_brief=longitudinal_brief,
        trends=trends,
        patterns=patterns
    )

    output_path = save_brief_json(analysis_path, ai_brief)
    return ai_brief, output_path