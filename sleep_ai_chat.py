import json
import os
import anthropic

client = anthropic.Anthropic()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_sleep_chat_context(
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

    sleep_window = analysis.get("sleep_window", {})
    architecture = analysis.get("sleep_architecture", {})
    cardiac = analysis.get("cardiac_recovery", {})
    autonomic = analysis.get("autonomic_recovery", {})
    stress = analysis.get("stress_recovery", {})
    respiratory = analysis.get("respiratory_recovery", {})
    oxygenation = analysis.get("oxygenation", {})
    energy = analysis.get("energy_recharge", {})
    sleep_need = analysis.get("sleep_need", {})
    circadian = analysis.get("circadian_alignment", {})
    recovery_summary = analysis.get("recovery_summary", {})

    return f"""
Responde completamente en español.

Eres un especialista premium en sueño, recuperación fisiológica y rendimiento humano.
Tienes formación avanzada en fisiología del sueño, sistema nervioso autónomo, ritmos circadianos,
respiración nocturna, estrés fisiológico, HRV (variabilidad de la frecuencia cardiaca)
y recuperación para el rendimiento deportivo.

Tu trabajo es responder preguntas sobre ESTA noche específica y, si existe, sobre su contexto longitudinal.
No hables en genérico si los datos permiten una respuesta concreta.
Conecta métricas, patrones, recuperación, limitantes y decisiones para el día siguiente.

Reglas:
- Responde como especialista premium en sueño y recovery.
- Sé claro, técnico y útil.
- No repitas números sin interpretarlos.
- Si el usuario pregunta algo específico, responde primero eso y luego amplía.
- Usa findings, brief, brief AI y longitudinal brief como base principal de interpretación.
- Si hay bandera de oxigenación o respiración, no diagnostiques; habla de seguimiento y contexto.
- No inventes datos que no estén en el contexto.
- Si una señal parece aislada, dilo.
- Si parece repetida por patrones longitudinales, dilo.

=====================
SLEEP WINDOW
=====================
{json.dumps(sleep_window, ensure_ascii=False, indent=2)}

=====================
SLEEP ARCHITECTURE
=====================
{json.dumps(architecture, ensure_ascii=False, indent=2)}

=====================
CARDIAC RECOVERY
=====================
{json.dumps(cardiac, ensure_ascii=False, indent=2)}

=====================
AUTONOMIC RECOVERY
=====================
{json.dumps(autonomic, ensure_ascii=False, indent=2)}

=====================
STRESS RECOVERY
=====================
{json.dumps(stress, ensure_ascii=False, indent=2)}

=====================
RESPIRATORY RECOVERY
=====================
{json.dumps(respiratory, ensure_ascii=False, indent=2)}

=====================
OXYGENATION
=====================
{json.dumps(oxygenation, ensure_ascii=False, indent=2)}

=====================
ENERGY RECHARGE
=====================
{json.dumps(energy, ensure_ascii=False, indent=2)}

=====================
SLEEP NEED
=====================
{json.dumps(sleep_need, ensure_ascii=False, indent=2)}

=====================
CIRCADIAN ALIGNMENT
=====================
{json.dumps(circadian, ensure_ascii=False, indent=2)}

=====================
RECOVERY SUMMARY
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
SLEEP TRENDS
=====================
{json.dumps(trends, ensure_ascii=False, indent=2)}

=====================
SLEEP PATTERNS
=====================
{json.dumps(patterns, ensure_ascii=False, indent=2)}
"""


def interactive_chat(context):
    print("\n==========================")
    print("SLEEP AI CHAT")
    print("==========================")
    print("Ya puedes preguntarle a la IA sobre esta noche, tu recuperación y patrones.")
    print("Escribe 0 para salir.\n")

    history = [
        {
            "role": "system",
            "content": (
                "Eres un especialista élite en sueño, recuperación y rendimiento humano. "
                "Responde siempre en español, de forma clara, útil, técnica y accionable."
            )
        },
        {
            "role": "user",
            "content": context
        }
    ]

    while True:
        question = input("\nPregunta sobre tu sueño/recovery (0 para salir): ").strip()

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

        print("\nIA:")
        print(answer)

        history.append({"role": "assistant", "content": answer})


def run_sleep_ai_chat(
    analysis_path,
    findings_path=None,
    brief_path=None,
    brief_ai_path=None,
    longitudinal_brief_path=None,
    trends_path=None,
    patterns_path=None
):
    if not os.path.exists(analysis_path):
        print("No se encontró el archivo sleep_analysis.json para abrir el chat.")
        return

    analysis = load_json(analysis_path)

    findings = {}
    brief = {}
    brief_ai = {}
    longitudinal_brief = {}
    trends = {}
    patterns = {}

    if findings_path and os.path.exists(findings_path):
        findings = load_json(findings_path)

    if brief_path and os.path.exists(brief_path):
        brief = load_json(brief_path)

    if brief_ai_path and os.path.exists(brief_ai_path):
        brief_ai = load_json(brief_ai_path)

    if longitudinal_brief_path and os.path.exists(longitudinal_brief_path):
        longitudinal_brief = load_json(longitudinal_brief_path)

    if trends_path and os.path.exists(trends_path):
        trends = load_json(trends_path)

    if patterns_path and os.path.exists(patterns_path):
        patterns = load_json(patterns_path)

    context = build_sleep_chat_context(
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
    analysis_path = input("Ruta de sleep_analysis.json: ").strip()
    findings_path = input("Ruta de sleep_findings.json (opcional): ").strip()
    brief_path = input("Ruta de sleep_brief.json (opcional): ").strip()
    brief_ai_path = input("Ruta de sleep_brief_ai.json (opcional): ").strip()
    longitudinal_brief_path = input("Ruta de sleep_longitudinal_brief.json (opcional): ").strip()
    trends_path = input("Ruta de sleep_trends.json (opcional): ").strip()
    patterns_path = input("Ruta de sleep_patterns.json (opcional): ").strip()

    findings_path = findings_path if findings_path else None
    brief_path = brief_path if brief_path else None
    brief_ai_path = brief_ai_path if brief_ai_path else None
    longitudinal_brief_path = longitudinal_brief_path if longitudinal_brief_path else None
    trends_path = trends_path if trends_path else None
    patterns_path = patterns_path if patterns_path else None

    run_sleep_ai_chat(
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