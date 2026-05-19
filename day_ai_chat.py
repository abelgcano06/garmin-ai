import json
import os
import anthropic

client = anthropic.Anthropic()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_day_chat_context(
    analysis,
    findings=None,
    brief=None,
    brief_ai=None,
    longitudinal_brief=None,
    trends=None,
    patterns=None
):
    findings = findings or {}
    brief = brief or {}
    brief_ai = brief_ai or {}
    longitudinal_brief = longitudinal_brief or {}
    trends = trends or {}
    patterns = patterns or {}

    timeline_summary = analysis.get("timeline_summary", {})
    segments = analysis.get("segments", {})
    nervous = analysis.get("nervous_system_load", {})
    energy = analysis.get("energy_dynamics", {})
    physical = analysis.get("physical_load", {})
    cognitive = analysis.get("cognitive_load", {})
    stress = analysis.get("stress_behavior", {})
    recovery = analysis.get("recovery_response", {})
    respiratory = analysis.get("respiratory_behavior", {})
    recovery_summary = analysis.get("recovery_summary", {})

    return f"""
Responde completamente en español.

Eres un especialista premium en fisiología humana, recuperación, sistema nervioso,
estrés, carga física, carga mental, energía, regulación autonómica
y rendimiento diario.

Tu trabajo es responder preguntas sobre ESTE día específico y, si existe,
sobre su contexto longitudinal.
No hables en genérico si los datos permiten una respuesta concreta.
Conecta carga, recuperación intra-día, energía, limitantes y decisiones para el resto del día.

Reglas:
- Responde como especialista premium en fisiología diaria y rendimiento.
- Sé claro, técnico y útil.
- No repitas números sin interpretarlos.
- Si el usuario pregunta algo específico, responde primero eso y luego amplía.
- Usa findings, brief, brief AI y longitudinal brief como base principal de interpretación.
- Si hay una señal aislada, dilo.
- Si parece repetida por patrones longitudinales, dilo.
- No inventes datos que no estén en el contexto.
- Si el usuario pregunta por entrenamiento, conecta el estado del cuerpo con tolerancia al esfuerzo.
- Si el usuario pregunta por energía o estrés, diferencia entre evento agudo y patrón del día.

=====================
TIMELINE SUMMARY
=====================
{json.dumps(timeline_summary, ensure_ascii=False, indent=2)}

=====================
SEGMENTS
=====================
{json.dumps(segments, ensure_ascii=False, indent=2)}

=====================
NERVOUS SYSTEM LOAD
=====================
{json.dumps(nervous, ensure_ascii=False, indent=2)}

=====================
ENERGY DYNAMICS
=====================
{json.dumps(energy, ensure_ascii=False, indent=2)}

=====================
PHYSICAL LOAD
=====================
{json.dumps(physical, ensure_ascii=False, indent=2)}

=====================
COGNITIVE LOAD
=====================
{json.dumps(cognitive, ensure_ascii=False, indent=2)}

=====================
STRESS BEHAVIOR
=====================
{json.dumps(stress, ensure_ascii=False, indent=2)}

=====================
RECOVERY RESPONSE
=====================
{json.dumps(recovery, ensure_ascii=False, indent=2)}

=====================
RESPIRATORY BEHAVIOR
=====================
{json.dumps(respiratory, ensure_ascii=False, indent=2)}

=====================
DAY RECOVERY SUMMARY
=====================
{json.dumps(recovery_summary, ensure_ascii=False, indent=2)}

=====================
FINDINGS
=====================
{json.dumps(findings, ensure_ascii=False, indent=2)}

=====================
RULE-BASED BRIEF
=====================
{json.dumps(brief, ensure_ascii=False, indent=2)}

=====================
AI BRIEF
=====================
{json.dumps(brief_ai, ensure_ascii=False, indent=2)}

=====================
LONGITUDINAL BRIEF
=====================
{json.dumps(longitudinal_brief, ensure_ascii=False, indent=2)}

=====================
DAY TRENDS
=====================
{json.dumps(trends, ensure_ascii=False, indent=2)}

=====================
DAY PATTERNS
=====================
{json.dumps(patterns, ensure_ascii=False, indent=2)}
"""


def interactive_chat(context):
    print("\n==========================")
    print("DAY AI CHAT")
    print("==========================")
    print("Ya puedes preguntarle a la IA sobre este día, tu carga, energía y patrones.")
    print("Escribe 0 para salir.\n")

    history = [
        {
            "role": "system",
            "content": (
                "Eres un especialista élite en fisiología diaria, recuperación, "
                "sistema nervioso, estrés, carga física y rendimiento humano. "
                "Responde siempre en español, de forma clara, útil, técnica y accionable."
            )
        },
        {
            "role": "user",
            "content": context
        }
    ]

    while True:
        question = input("\nPregunta sobre tu día/recovery/energía (0 para salir): ").strip()

        if question == "0":
            break

        if not question:
            continue

        history.append({"role": "user", "content": question})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=history[0]["content"] if history and history[0]["role"] == "system" else None,
            messages=[m for m in history if m["role"] != "system"]
        )

        answer = response.content[0].text

        print("\n==========================")
        print("RESPUESTA")
        print("==========================\n")
        print(answer)

        history.append({"role": "assistant", "content": answer})


def run_day_ai_chat(
    analysis_path,
    findings_path=None,
    brief_path=None,
    brief_ai_path=None,
    longitudinal_brief_path=None,
    trends_path=None,
    patterns_path=None
):
    if not os.path.exists(analysis_path):
        print("No se encontró day_analysis.json.")
        return

    analysis = load_json(analysis_path)
    findings = load_json(findings_path) if findings_path and os.path.exists(findings_path) else {}
    brief = load_json(brief_path) if brief_path and os.path.exists(brief_path) else {}
    brief_ai = load_json(brief_ai_path) if brief_ai_path and os.path.exists(brief_ai_path) else {}
    longitudinal_brief = load_json(longitudinal_brief_path) if longitudinal_brief_path and os.path.exists(longitudinal_brief_path) else {}
    trends = load_json(trends_path) if trends_path and os.path.exists(trends_path) else {}
    patterns = load_json(patterns_path) if patterns_path and os.path.exists(patterns_path) else {}

    context = build_day_chat_context(
        analysis=analysis,
        findings=findings,
        brief=brief,
        brief_ai=brief_ai,
        longitudinal_brief=longitudinal_brief,
        trends=trends,
        patterns=patterns
    )

    interactive_chat(context)


def main():
    analysis_path = input("Ruta de day_analysis.json: ").strip()
    findings_path = input("Ruta de day_findings.json (opcional): ").strip() or None
    brief_path = input("Ruta de day_brief.json (opcional): ").strip() or None
    brief_ai_path = input("Ruta de day_brief_ai.json (opcional): ").strip() or None
    longitudinal_brief_path = input("Ruta de day_longitudinal_brief.json (opcional): ").strip() or None
    trends_path = input("Ruta de day_trends.json (opcional): ").strip() or None
    patterns_path = input("Ruta de day_patterns.json (opcional): ").strip() or None

    run_day_ai_chat(
        analysis_path=analysis_path,
        findings_path=findings_path,
        brief_path=brief_path,
        brief_ai_path=brief_ai_path,
        longitudinal_brief_path=longitudinal_brief_path,
        trends_path=trends_path,
        patterns_path=patterns_path
    )


if __name__ == "__main__":
    main()