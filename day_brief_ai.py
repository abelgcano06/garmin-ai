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

def build_motor_system_scores(analysis):
    """
    Compute 5 system scores from the day analysis.
    These values come from the motor — Claude CANNOT change them.
    """
    summary = analysis.get("summary_scores", {})
    return {
        "nervous_system": score10(summary.get("nervous")),
        "energy":         score10(summary.get("energy")),
        "physical_load":  score10(summary.get("physical")),
        "cognitive_load": score10(summary.get("cognitive")),
        "stress":         score10(summary.get("stress")),
    }


def build_motor_hero(analysis):
    overall = safe_get(analysis, "recovery_summary", "overall_day_state_score", default=0.0)
    score = clamp100(overall)

    if score >= 80:
        status = "Día sólido"
    elif score >= 65:
        status = "Listo con control"
    elif score >= 50:
        status = "Día exigente"
    else:
        status = "Capacidad limitada"

    return {"score": score, "status": status, "headline": ""}


def build_motor_system_shells(system_scores):
    def status_from_score(s):
        if s >= 7.5:
            return "up"
        if s >= 5.5:
            return "stable"
        if s >= 3.5:
            return "down"
        return "warning"

    ordered = [
        ("Energía",          "energy"),
        ("Sistema nervioso", "nervous_system"),
        ("Estrés",           "stress"),
        ("Carga física",     "physical_load"),
        ("Carga mental",     "cognitive_load"),
    ]

    systems = []
    for label, key in ordered:
        s = float(system_scores.get(key, 0.0))
        systems.append({
            "name":    label,
            "score":   round(s, 1),
            "status":  status_from_score(s),
            "message": "",
        })
    return systems


def build_motor_quick_base(analysis):
    hero = build_motor_hero(analysis)
    system_scores = build_motor_system_scores(analysis)
    systems = build_motor_system_shells(system_scores)
    return {
        "hero":    hero,
        "systems": systems,
        "today":   {"performance": "", "action": ""},
        "pattern": {"message": ""},
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
    brief             = brief or {}
    notable_events    = notable_events or []
    longitudinal_brief = longitudinal_brief or {}
    trends            = trends or {}
    patterns          = patterns or {}
    athlete_context   = athlete_context or ""

    quick_base = build_motor_quick_base(analysis)

    athlete_block = f"""
=========================================================
ATLETA — QUIÉN ES ESTA PERSONA
=========================================================
{athlete_context}

INSTRUCCIÓN CRÍTICA: Los scores y valores de HOY deben interpretarse contra las
REFERENCIAS PERSONALES del atleta listadas arriba, NO contra promedios poblacionales.
=========================================================
""" if athlete_context else ""

    # Build the fixed JSON schema lines (scores locked by motor)
    sys_lines = "\n".join(
        f"""    {{{{
      "name": "{s["name"]}",
      "score": {s["score"]},
      "status": "{s["status"]}",
      "message": "..."
    }}}}{"," if i < len(quick_base["systems"]) - 1 else ""}"""
        for i, s in enumerate(quick_base["systems"])
    )

    return f"""
Responde completamente en español.

Eres un especialista de élite en fisiología humana, rendimiento, sistema nervioso autónomo,
estrés, recuperación intra-día, energía, carga física, carga cognitiva y desempeño diario.

Tu trabajo es interpretar TODA la información ya procesada por el motor analítico
y traducirla a una salida clara, humana, útil y premium para producto.
{athlete_block}
IMPORTANTE:
- No recalculas nada.
- No inventas scores.
- No cambias scores.
- Usas TODA la información disponible:
  - analysis
  - findings
  - brief
  - notable_events (eventos con timestamp — úsalos para dar contexto temporal específico)
  - longitudinal_brief
  - trends
  - patterns

=========================================================
QUICK REPORT BASE (YA VIENE DEL MOTOR)
=========================================================

Debes RESPETAR ESTA ESTRUCTURA EXACTA y completar solo los textos:

{json.dumps(quick_base, ensure_ascii=False, indent=2)}

- hero.score y hero.status ya vienen del motor → NO cambiarlos
- systems[].name, systems[].score y systems[].status → NO cambiarlos
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
{sys_lines}
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
    "day_type_interpretation": "...",
    "primary_limiter": "...",
    "secondary_limiter": "...",
    "main_insight": "...",
    "what_is_happening": "...",
    "what_it_means_in_you": "...",
    "likely_drivers": "...",
    "physiology_summary": "...",
    "performance_outlook": "...",
    "training_guidance": "...",
    "recovery_focus": "...",
    "follow_up_priority": "...",
    "key_takeaways": ["...", "...", "...", "..."],
    "extra_insights": [
      {{"title": "...", "text": "..."}},
      {{"title": "...", "text": "..."}}
    ],
    "chat_starters": ["...", "...", "..."]
  }}
}}

=========================================================
INSTRUCCIONES DE ESTILO
=========================================================

HERO:
- headline = 1 sola línea fuerte y clara que resume la verdad del día
- no pongas números en headline
- debe reflejar el patrón dominante del día, no solo el score

SYSTEMS:
- message = 1 sola frase corta por sistema
- Si el sistema tiene status "up" o "stable" y score >= 6.5: mensaje positivo breve o déjalo vacío ""
- Si el sistema tiene status "down" o "warning": menciona el evento específico de notable_events
  si existe (hora, señal, magnitud)
- NO recomendaciones aquí — solo lectura del cuerpo
- Ejemplo bueno: "Caída de 22 pts de Body Battery entre las 2 y las 4pm — energía frágil."
- Ejemplo malo: "La energía no fue el mejor punto del día."

CORRELACIONES:
- Busca activamente si 2+ sistemas bajaron POR LA MISMA CAUSA RAÍZ
- Patrones comunes en día: BB crash + estrés alto en misma ventana → Energía + Estrés
- Pico de estrés sostenido + HR elevado → Estrés + Sistema nervioso
- Si encuentras correlación genuina: documéntala con la hora del evento que las conecta
- Si NO hay correlación clara: devuelve "correlations": []
- Máximo 2 correlaciones reales

TODAY:
- performance = cómo se sentirá el rendimiento en lo que queda del día
- action = qué conviene hacer ahora — concreto, accionable, máximo 2 frases
- Calibrar según hora del día implícita en los datos (mañana/tarde/noche)

PATTERN:
- message = la señal histórica más importante sobre este usuario
- Integra longitudinal_brief, trends, patterns
- Di si esto se repite, si mejora o empeora, si confirma el patrón dominante
- Que suene personal e inteligente, no genérico

DEEP ANALYSIS:
- Desarrolla más — fisiología, mecanismos, drivers, predicción futura
- what_is_happening: qué proceso fisiológico está activo
- what_it_means_in_you: cómo afecta a ESTE atleta específicamente
- likely_drivers: comportamientos probables que generan este patrón
- performance_outlook: qué puede pasar en las próximas horas si no cambia nada

=========================================================
EVENTOS NOTABLES DEL DÍA (con timestamp real)
=========================================================
{json.dumps(notable_events, ensure_ascii=False, indent=2)}

Instrucción: Cuando un sistema tenga status "down" o "warning", busca en esta lista
si hay un evento que lo explique. Menciona la hora y magnitud en el message del sistema.
Busca también si dos eventos de señales distintas ocurrieron cerca en el tiempo (< 20 min)
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
    return json.loads(text.strip())


# =========================================================
# Normalize + fallbacks
# =========================================================

def normalize_quick_output(ai_brief, analysis, findings):
    """
    Ensures motor scores always take precedence over Claude's output.
    Extracts text fields from Claude's response and merges into the
    motor-computed skeleton.
    """
    quick_base = build_motor_quick_base(analysis)

    out = {
        "hero":         quick_base["hero"],
        "systems":      quick_base["systems"],
        "today":        quick_base["today"],
        "pattern":      quick_base["pattern"],
        "correlations": [],
        "deep_analysis": {},
    }

    if not isinstance(ai_brief, dict):
        return fill_quick_fallbacks(out, analysis, findings)

    # HERO — only take headline, protect score+status
    hero_in = ai_brief.get("hero", {})
    if isinstance(hero_in, dict):
        out["hero"]["headline"] = hero_in.get("headline", "") or ""

    # SYSTEMS — match by name, only take message
    systems_in = ai_brief.get("systems", [])
    if isinstance(systems_in, list):
        by_name = {
            s["name"]: s
            for s in systems_in
            if isinstance(s, dict) and s.get("name")
        }
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
        out["today"]["action"]      = today_in.get("action", "") or ""

    # PATTERN
    pattern_in = ai_brief.get("pattern", {})
    if isinstance(pattern_in, dict):
        out["pattern"]["message"] = pattern_in.get("message", "") or ""

    # CORRELATIONS
    corr_in = ai_brief.get("correlations", [])
    if isinstance(corr_in, list):
        valid = [
            {
                "systems":    c.get("systems", []),
                "root_cause": c.get("root_cause", ""),
                "insight":    c.get("insight", ""),
                "severity":   c.get("severity", "medium"),
            }
            for c in corr_in
            if isinstance(c, dict) and c.get("systems") and c.get("insight")
        ]
        out["correlations"] = valid[:2]

    # DEEP
    deep_in = ai_brief.get("deep_analysis", {})
    if isinstance(deep_in, dict):
        out["deep_analysis"] = deep_in

    return fill_quick_fallbacks(out, analysis, findings)


def fill_quick_fallbacks(brief, analysis, findings):
    """
    Fill any empty text fields with rule-based fallbacks so the UI
    always has something to show even when Claude's response is partial.
    """
    hero       = brief.get("hero", {})
    systems    = brief.get("systems", [])
    today      = brief.get("today", {})
    pattern    = brief.get("pattern", {})
    deep       = brief.get("deep_analysis", {})

    primary_limiter = safe_get(findings, "limiters", "primary_limiter", default="")
    overall         = safe_get(analysis, "recovery_summary", "overall_day_state_score", default=0)
    flags           = safe_get(findings, "flags", default={})

    # Fallback headline
    if not hero.get("headline"):
        if flags.get("energy_crash"):
            hero["headline"] = "El día está consumiendo más de lo que el cuerpo puede sostener."
        elif flags.get("high_stress"):
            hero["headline"] = "Estrés elevado sostenido — el sistema nervioso lleva demasiada carga."
        elif overall >= 75:
            hero["headline"] = "El cuerpo responde bien — buen día para producir."
        elif overall >= 55:
            hero["headline"] = "Día funcional, pero con margen ajustado para demandas altas."
        else:
            hero["headline"] = "Capacidad reducida hoy — conviene administrar la carga."

    # Fallback system messages
    default_messages = {
        "Energía":          "La energía del día está por debajo de lo óptimo.",
        "Sistema nervioso": "El sistema nervioso muestra carga acumulada.",
        "Estrés":           "El nivel de estrés del día está elevado.",
        "Carga física":     "La carga física del día fue alta.",
        "Carga mental":     "La demanda cognitiva fue importante hoy.",
    }
    for s in systems:
        if not s.get("message") and s.get("status") in ("down", "warning"):
            s["message"] = default_messages.get(s["name"], "Este sistema mostró limitación hoy.")

    # Fallback today
    if not today.get("performance"):
        if overall >= 75:
            today["performance"] = "Buen potencial para la segunda parte del día."
        elif overall >= 55:
            today["performance"] = "Rendimiento funcional — los picos de intensidad pueden sentirse más caros."
        else:
            today["performance"] = "El rendimiento puede sentirse limitado; evita demandas muy altas."

    if not today.get("action"):
        if flags.get("energy_crash"):
            today["action"] = "Prioriza recuperación activa y evita carga física adicional."
        elif flags.get("high_stress"):
            today["action"] = "Reduce estímulos, programa una pausa real y protege el sueño de esta noche."
        elif primary_limiter == "high_nervous_load":
            today["action"] = "Baja el ritmo cognitivo en lo que resta del día y evita decisiones de alta presión."
        else:
            today["action"] = "Mantén el ritmo controlado y cierra el día sin agregar carga innecesaria."

    # Fallback pattern
    if not pattern.get("message"):
        trajectory = safe_get(analysis, "longitudinal_brief", "recovery_trajectory", default="")
        if trajectory == "improving":
            pattern["message"] = "La tendencia general mejora — el cuerpo está respondiendo mejor que semanas anteriores."
        elif flags.get("energy_crash"):
            pattern["message"] = "Se repite un patrón de crash energético en días de carga alta — el sistema no alcanza a recuperarse entre sesiones."
        elif flags.get("high_stress"):
            pattern["message"] = "El estrés elevado sostenido es recurrente — conviene revisar la gestión de carga mental y recuperación."
        else:
            pattern["message"] = "El día encaja con tu patrón reciente de capacidad moderada."

    # Fallback deep
    if not deep:
        deep = {
            "headline":              hero.get("headline", ""),
            "day_type_interpretation": "Día funcional con limitaciones detectadas.",
            "primary_limiter":       primary_limiter,
            "secondary_limiter":     "",
            "main_insight":          "El día tuvo demanda real sobre el sistema — importante cerrar bien.",
            "what_is_happening":     "El cuerpo está gestionando carga activa con reservas parciales.",
            "what_it_means_in_you":  "Para este atleta, este patrón suele anticipar fatiga acumulada si no se gestiona.",
            "likely_drivers":        "Carga física o cognitiva sin suficiente micro-recuperación entre bloques.",
            "physiology_summary":    "Energía y sistema nervioso bajo demanda — recuperación parcial.",
            "performance_outlook":   today.get("performance", ""),
            "training_guidance":     today.get("action", ""),
            "recovery_focus":        "Proteger el sueño de esta noche y reducir estímulos en la tarde.",
            "follow_up_priority":    pattern.get("message", ""),
            "key_takeaways": [
                "El día tuvo demanda real sobre la fisiología.",
                "El limitante principal sigue activo.",
                "Puedes producir si administras la carga restante.",
                "Esta noche es clave para consolidar recuperación.",
            ],
            "extra_insights": [],
            "chat_starters":  [],
        }

    brief["hero"]         = hero
    brief["systems"]      = systems
    brief["today"]        = today
    brief["pattern"]      = pattern
    brief["correlations"] = brief.get("correlations", [])
    brief["deep_analysis"] = deep

    return brief


# =========================================================
# Save
# =========================================================

def save_brief_json(analysis_path, brief):
    day_folder  = os.path.dirname(analysis_path)
    output_path = os.path.join(day_folder, "day_brief_ai.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2, ensure_ascii=False)
    return output_path


# =========================================================
# Main generator
# =========================================================

def generate_day_ai_brief(
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
        print("No se encontró el archivo day_analysis.json.")
        return None

    if not os.path.exists(findings_path):
        print("No se encontró el archivo day_findings.json.")
        return None

    analysis = load_json(analysis_path)
    findings = load_json(findings_path)

    brief             = load_json(brief_path)             if brief_path             and os.path.exists(brief_path)             else {}
    notable_events    = load_json(events_path)            if events_path            and os.path.exists(events_path)            else []
    longitudinal_brief = load_json(longitudinal_brief_path) if longitudinal_brief_path and os.path.exists(longitudinal_brief_path) else {}
    trends            = load_json(trends_path)            if trends_path            and os.path.exists(trends_path)            else {}
    patterns          = load_json(patterns_path)          if patterns_path          and os.path.exists(patterns_path)          else {}

    athlete_context = get_athlete_context_for_section(user_dir, "day") if user_dir else ""

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
        print(f"[ERROR] No se pudo parsear JSON del modelo: {e}")
        print("Respuesta cruda:\n", raw_text[:500])
        # Return fallback-only output
        fallback = fill_quick_fallbacks(
            {
                "hero":         build_motor_hero(analysis),
                "systems":      build_motor_system_shells(build_motor_system_scores(analysis)),
                "today":        {"performance": "", "action": ""},
                "pattern":      {"message": ""},
                "correlations": [],
                "deep_analysis": {},
            },
            analysis,
            findings,
        )
        output_path = save_brief_json(analysis_path, fallback)
        return fallback, output_path

    ai_brief = normalize_quick_output(ai_brief_raw, analysis, findings)
    output_path = save_brief_json(analysis_path, ai_brief)
    return ai_brief, output_path


def main():
    analysis_path          = input("Ruta de day_analysis.json: ").strip()
    findings_path          = input("Ruta de day_findings.json: ").strip()
    brief_path             = input("Ruta de day_brief.json (opcional): ").strip() or None
    events_path            = input("Ruta de day_events.json (opcional): ").strip() or None
    longitudinal_brief_path = input("Ruta de day_longitudinal_brief.json (opcional): ").strip() or None
    trends_path            = input("Ruta de day_trends.json (opcional): ").strip() or None
    patterns_path          = input("Ruta de day_patterns.json (opcional): ").strip() or None

    result = generate_day_ai_brief(
        analysis_path=analysis_path,
        findings_path=findings_path,
        brief_path=brief_path,
        events_path=events_path,
        longitudinal_brief_path=longitudinal_brief_path,
        trends_path=trends_path,
        patterns_path=patterns_path,
    )

    if result:
        _, output_path = result
        print(f"\nArchivo generado: {output_path}")


if __name__ == "__main__":
    main()
