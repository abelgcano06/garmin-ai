import json
import os
import anthropic

client = anthropic.Anthropic()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_activity_chat_context(analysis, findings=None, brief=None, limiter=None, trends=None):
    findings = findings or {}
    brief = brief or {}
    limiter = limiter or {}
    trends = trends or {}

    garmin = analysis.get("garmin_summary", {})
    derived = analysis.get("derived_summary", {})
    fatigue = analysis.get("fatigue", {})
    profile = analysis.get("athlete_profile", {})
    climbs = analysis.get("climbs", [])
    efforts = analysis.get("efforts", [])
    zones = analysis.get("zones", {})

    return f"""
Responde completamente en español.

Eres un analista élite de rendimiento en ciclismo y deportes de resistencia.
Tienes formación avanzada en fisiología del ejercicio, entrenamiento de endurance,
análisis de potencia, biomecánica, fatiga, rendimiento en subida y prescripción de entrenamiento.

Tu trabajo es responder preguntas sobre ESTA actividad específica.
No hables en genérico si los datos permiten una respuesta concreta.
Conecta datos, sensaciones probables, limitantes y decisiones de entrenamiento.

Reglas:
- Responde como coach/fisiólogo premium.
- Sé técnico pero claro.
- No repitas números sin interpretarlos.
- Cuando el usuario pregunte algo específico, responde primero eso y luego amplía.
- Usa el brief, limiter detector y findings como fuentes principales de interpretación.
- Si trend analyzer trae error por falta de historial, ignóralo.
- No inventes datos que no estén en el contexto.

=====================
RESUMEN GARMIN
=====================
{json.dumps(garmin, ensure_ascii=False, indent=2)}

=====================
MÉTRICAS DERIVADAS
=====================
{json.dumps(derived, ensure_ascii=False, indent=2)}

=====================
FATIGA
=====================
{json.dumps(fatigue, ensure_ascii=False, indent=2)}

=====================
PERFIL DEL ATLETA
=====================
{json.dumps(profile, ensure_ascii=False, indent=2)}

=====================
SUBIDAS
=====================
{json.dumps(climbs, ensure_ascii=False, indent=2)}

=====================
ESFUERZOS
=====================
{json.dumps(efforts, ensure_ascii=False, indent=2)}

=====================
ZONAS
=====================
{json.dumps(zones, ensure_ascii=False, indent=2)}

=====================
FINDINGS
=====================
{json.dumps(findings, ensure_ascii=False, indent=2)}

=====================
BRIEF
=====================
{json.dumps(brief, ensure_ascii=False, indent=2)}

=====================
LIMITER DETECTOR
=====================
{json.dumps(limiter, ensure_ascii=False, indent=2)}

=====================
TREND ANALYZER
=====================
{json.dumps(trends, ensure_ascii=False, indent=2)}
"""


def interactive_chat(context):
    print("\n==========================")
    print("ACTIVITY AI CHAT")
    print("==========================")
    print("Ya puedes preguntarle a la IA sobre esta actividad.")
    print("Escribe 0 para salir.\n")

    history = [
        {
            "role": "system",
            "content": (
                "Eres un analista élite de rendimiento en ciclismo. "
                "Responde siempre en español, con explicaciones claras, técnicas y útiles "
                "para mejorar el rendimiento."
            )
        },
        {
            "role": "user",
            "content": context
        }
    ]

    while True:
        question = input("\nPregunta sobre tu actividad (0 para salir): ").strip()

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


def run_activity_ai_chat(
    analysis_path,
    findings_path=None,
    brief_path=None,
    limiter=None,
    trends=None
):
    if not os.path.exists(analysis_path):
        print("No se encontró el archivo de analysis para abrir el chat.")
        return

    analysis = load_json(analysis_path)

    findings = {}
    brief = {}

    if findings_path and os.path.exists(findings_path):
        findings = load_json(findings_path)

    if brief_path and os.path.exists(brief_path):
        brief = load_json(brief_path)

    context = build_activity_chat_context(
        analysis=analysis,
        findings=findings,
        brief=brief,
        limiter=limiter,
        trends=trends,
    )

    interactive_chat(context)


def main():
    analysis_path = input("Ruta del archivo activity_analysis.json: ").strip()
    findings_path = input("Ruta del archivo activity_findings.json (opcional): ").strip()
    brief_path = input("Ruta del archivo activity_brief.json (opcional): ").strip()

    findings_path = findings_path if findings_path else None
    brief_path = brief_path if brief_path else None

    run_activity_ai_chat(
        analysis_path=analysis_path,
        findings_path=findings_path,
        brief_path=brief_path,
        limiter=None,
        trends=None
    )


if __name__ == "__main__":
    main()