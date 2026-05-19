"""
master_ai_brief.py
==================
Genera dos versiones del análisis del día usando Claude:

  V1 — QUICK BRIEF (pantalla de inicio, estilo Garmin/Oura)
       Score + métricas + por qué + acción concreta

  V2 — DEEP BRIEF (relato completo para el usuario que quiere saber más)
       Narrativa experta integrando sueño + día + actividad

Guarda en:
  performance_intelligence/master_brief_quick.json
  performance_intelligence/master_brief_deep.json

Uso:
    python master_ai_brief.py --user_dir data/users/TU_USER --date 2026-03-17
"""

import json
import os
import argparse
from datetime import date
from athlete_context import get_athlete_context_for_section
from dotenv import load_dotenv
load_dotenv()

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_load(path):
    if path and os.path.exists(path):
        return load_json(path)
    return {}


def parse_json_response(raw_text):
    import re
    clean = raw_text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:])
    if clean.endswith("```"):
        clean = clean[:-3].strip()
    clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    last_brace = clean.rfind("}")
    if last_brace != -1:
        try:
            return json.loads(clean[:last_brace + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No se pudo parsear JSON:\n{clean[:500]}")


def call_claude(prompt, system_prompt):
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


SYSTEM_QUICK = (
    "Eres un especialista en rendimiento humano y recuperación. "
    "Responde siempre en español. "
    "Responde SOLO con JSON valido, sin markdown ni texto adicional."
)

SYSTEM_DEEP = (
    "Eres un especialista de elite en rendimiento humano, recuperacion fisiologica, "
    "sueno, entrenamiento de resistencia y ciclismo de montana. "
    "Responde siempre en espanol con analisis tecnicos, claros y de alto valor. "
    "Responde SOLO con JSON valido, sin markdown ni texto adicional."
)


def build_prompt_quick(master_brief, sleep_brief, sleep_findings, day_brief, activity_brief, athlete_context=""):
    athlete_block = f"""
=========================================================
ATLETA — QUIEN ES ESTA PERSONA
=========================================================
{athlete_context}

INSTRUCCION CRITICA: Un score de 50/100 para este atleta puede ser su operacion
normal — interpreta SIEMPRE contra sus referencias personales, no contra la poblacion.
=========================================================
""" if athlete_context else ""

    return f"""Responde completamente en espanol.
{athlete_block}

Genera el QUICK BRIEF del dia para mostrar en la pantalla principal de la app.
Estilo: Garmin / Oura. Limpio, directo, visual.
El usuario ve esto primero: debe entenderlo en menos de 10 segundos.

FILOSOFIA:
- Score grande y claro
- Cada metrica tiene semaforo verde/amarillo/rojo
- El "por que" en 2-3 lineas maximo, sin terminos tecnicos
- Una sola accion concreta para mejorar hoy
- Lenguaje humano, no clinico

REGLAS:
- No recalcules nada. Usa los scores ya calculados.
- Maximo impacto, minimas palabras.
- Si hay actividad, incluyela como metrica.
- Semaforo: verde>=70, amarillo=50-69, rojo<50
- Responde SOLO con JSON valido.

ESTRUCTURA:
{{
  "score": numero 0-100,
  "label": "frase corta con personalidad",
  "color": "verde|amarillo|rojo",
  "metricas": [
    {{"nombre": "Sueno", "valor": "63/100", "semaforo": "amarillo", "detalle": "max 5 palabras"}},
    {{"nombre": "Estado del dia", "valor": "47/100", "semaforo": "rojo", "detalle": "max 5 palabras"}},
    {{"nombre": "Oxigenacion nocturna", "valor": "Alerta", "semaforo": "rojo", "detalle": "max 5 palabras"}},
    {{"nombre": "Actividad", "valor": "82/100", "semaforo": "verde", "detalle": "max 5 palabras"}}
  ],
  "por_que": "2-3 lineas en lenguaje humano. Sin tecnicismos.",
  "accion_hoy": "Una sola accion concreta y especifica. Max 2 lineas.",
  "mejora_esta_noche": "Una sola cosa para hacer esta noche. Max 1 linea."
}}

MASTER BRIEF
{json.dumps(master_brief, ensure_ascii=False, indent=2)}

SLEEP BRIEF
{json.dumps(sleep_brief, ensure_ascii=False, indent=2)}

SLEEP FINDINGS
{json.dumps(sleep_findings, ensure_ascii=False, indent=2)}

DAY BRIEF
{json.dumps(day_brief, ensure_ascii=False, indent=2)}

ACTIVITY BRIEF
{json.dumps(activity_brief, ensure_ascii=False, indent=2)}
"""


def build_prompt_deep(master_brief, sleep_brief, sleep_analysis, sleep_findings, day_brief, day_analysis, activity_brief, athlete_context=""):
    athlete_block = f"""
=========================================================
ATLETA — QUIEN ES ESTA PERSONA
=========================================================
{athlete_context}

INSTRUCCION CRITICA: Usa las referencias personales del atleta para contextualizar
cada hallazgo. Su HRV basal, su carga sostenible, su fase de temporada y su objetivo
determinan si el dia fue bueno, regular o critico PARA EL especificamente.
=========================================================
""" if athlete_context else ""

    return f"""Responde completamente en espanol.
{athlete_block}

Genera el DEEP BRIEF del dia. Analisis experto completo para el usuario que quiere entender que paso en su cuerpo.

FILOSOFIA:
- Esto no es Garmin... es otro nivel.
- Conecta sueno, dia y actividad como una sola historia coherente.
- Explica lo que el atleta sintio pero no sabia describir.
- Usa lenguaje con identidad: "llegaste cargado", "el sistema no bajo marchas",
  "fuerte pero caro", "ejecutaste bien con lo que habia"

REGLAS:
- No recalcules nada.
- No repitas el quick brief, ve mas profundo.
- Conecta los tres motores como una narrativa, no como tres reportes separados.
- Si hay una contradiccion interesante (readiness bajo pero actividad buena), cuentala.
- Responde SOLO con JSON valido.

ESTRUCTURA:
{{
  "headline": "Una linea potente y memorable que resume el dia completo",
  "resumen_ejecutivo": "3-4 oraciones que cuentan la historia del dia. Sueno, Dia, Actividad.",
  "sistemas": [
    {{"nombre": "Sueno y recuperacion", "score": numero, "estado": "bien|regular|mal", "interpretacion": "2-3 oraciones especificas con datos reales"}},
    {{"nombre": "Estado del dia", "score": numero, "estado": "bien|regular|mal", "interpretacion": "2-3 oraciones"}},
    {{"nombre": "Actividad", "score": numero, "estado": "bien|regular|mal|sin_actividad", "interpretacion": "2-3 oraciones"}}
  ],
  "limitante_principal": "El cuello de botella dominante. Causa, efecto, consecuencia.",
  "la_historia": "El parrafo mas importante. 4-6 oraciones que conectan todo. Estilo narrativo.",
  "que_sintio_pero_no_sabia": "1-2 oraciones de algo que probablemente sintio pero no podia articular.",
  "proyeccion": "Que esperar en las proximas 24-48 horas. Especifico.",
  "entrenamiento_recomendado": {{
    "tipo": "nombre del tipo de sesion",
    "descripcion": "que hacer exactamente",
    "intensidad": "zona o nivel especifico",
    "duracion": "tiempo recomendado",
    "si_te_sientes_mal": "que hacer si el cuerpo no responde"
  }},
  "recuperacion_esta_noche": "Instrucciones especificas. Horarios, acciones concretas, que evitar.",
  "flags_criticos": [
    {{"flag": "nombre", "que_significa": "explicacion humana", "que_hacer": "accion concreta"}}
  ],
  "patron_personal": "Como este dia encaja con el patron historico del atleta.",
  "correlaciones_personales": "Que dicen sus propios datos sobre como este estado afecta su rendimiento.",
  "proxima_noche": "Objetivo concreto para esta noche. Especifico, con horarios si aplica."
}}

MASTER BRIEF
{json.dumps(master_brief, ensure_ascii=False, indent=2)}

SLEEP BRIEF AI
{json.dumps(sleep_brief, ensure_ascii=False, indent=2)}

SLEEP ANALYSIS
{json.dumps(sleep_analysis, ensure_ascii=False, indent=2)}

SLEEP FINDINGS
{json.dumps(sleep_findings, ensure_ascii=False, indent=2)}

DAY BRIEF
{json.dumps(day_brief, ensure_ascii=False, indent=2)}

DAY ANALYSIS
{json.dumps(day_analysis, ensure_ascii=False, indent=2)}

ACTIVITY BRIEF
{json.dumps(activity_brief, ensure_ascii=False, indent=2)}
"""


def print_quick(r):
    print(f"\n{'='*50}")
    print("QUICK BRIEF — PANTALLA PRINCIPAL")
    print(f"{'='*50}\n")
    print(f"  SCORE:  {r.get('score')}/100")
    print(f"  LABEL:  {r.get('label')}")
    print(f"  COLOR:  {r.get('color')}\n")
    print("  METRICAS:")
    for m in r.get("metricas", []):
        s = {"verde": "GREEN", "amarillo": "YELLOW", "rojo": "RED"}.get(m.get("semaforo"), "---")
        print(f"    [{s}] {m.get('nombre')}: {m.get('valor')} — {m.get('detalle')}")
    print(f"\n  POR QUE:\n  {r.get('por_que')}")
    print(f"\n  ACCION HOY:\n  {r.get('accion_hoy')}")
    print(f"\n  ESTA NOCHE:\n  {r.get('mejora_esta_noche')}")


def print_deep(r):
    print(f"\n{'='*50}")
    print("DEEP BRIEF — ANALISIS EXPERTO")
    print(f"{'='*50}\n")
    print(f"HEADLINE:\n{r.get('headline')}\n")
    print(f"RESUMEN:\n{r.get('resumen_ejecutivo')}\n")
    print("SISTEMAS:")
    for s in r.get("sistemas", []):
        print(f"  {s.get('nombre')} ({s.get('score')}) — {s.get('estado')}")
        print(f"    {s.get('interpretacion')}\n")
    print(f"LIMITANTE:\n{r.get('limitante_principal')}\n")
    print(f"LA HISTORIA:\n{r.get('la_historia')}\n")
    print(f"LO QUE SENTISTE:\n{r.get('que_sintio_pero_no_sabia')}\n")
    print(f"PROYECCION:\n{r.get('proyeccion')}\n")
    ent = r.get("entrenamiento_recomendado", {})
    print(f"ENTRENAMIENTO: {ent.get('tipo')} — {ent.get('duracion')}")
    print(f"  {ent.get('descripcion')}")
    print(f"  Si no responde: {ent.get('si_te_sientes_mal')}\n")
    print(f"ESTA NOCHE:\n{r.get('recuperacion_esta_noche')}\n")
    for f in r.get("flags_criticos", []):
        print(f"  FLAG: {f.get('flag')}: {f.get('que_significa')}")
        print(f"    -> {f.get('que_hacer')}")
    print(f"\nPATRON:\n{r.get('patron_personal')}\n")
    print(f"CORRELACIONES:\n{r.get('correlaciones_personales')}\n")
    print(f"PROXIMA NOCHE:\n{r.get('proxima_noche')}\n")


def run_master_ai_brief(user_dir, target_date=None):
    if target_date is None:
        target_date = date.today().isoformat()

    pi_dir    = os.path.join(user_dir, "performance_intelligence")
    sleep_dir = os.path.join(user_dir, "sleep", target_date)
    day_dir   = os.path.join(user_dir, "day", target_date)

    print(f"\n{'='*50}")
    print("MASTER AI BRIEF")
    print(f"Fecha: {target_date}")
    print(f"{'='*50}")

    master_brief_path = os.path.join(pi_dir, "master_brief.json")
    if not os.path.exists(master_brief_path):
        print(f"\n[ERROR] No se encontro master_brief.json")
        print("Corre primero: python master_engine.py --user_dir ... --date ...")
        return None

    master_brief   = load_json(master_brief_path)
    sleep_brief    = safe_load(os.path.join(sleep_dir, "sleep_brief_ai.json"))
    sleep_analysis = safe_load(os.path.join(sleep_dir, "sleep_analysis.json"))
    sleep_findings = safe_load(os.path.join(sleep_dir, "sleep_findings.json"))
    day_brief      = safe_load(os.path.join(day_dir, "day_brief.json"))
    day_analysis   = safe_load(os.path.join(day_dir, "day_analysis.json"))

    activity_brief = {}
    index_path = os.path.join(user_dir, "activity_index.json")
    if os.path.exists(index_path):
        index = load_json(index_path)
        for entry in index.get("activities", []):
            if (entry.get("date") or "")[:10] == target_date:
                bf = entry.get("brief_file")
                if bf and os.path.exists(bf):
                    activity_brief = load_json(bf)
                    print(f"  Actividad: {entry.get('name', '')}")
                break

    if not activity_brief:
        print(f"  Sin actividad para {target_date}")

    athlete_context = get_athlete_context_for_section(user_dir, "master")

    results = {}

    print("\n  Generando Quick Brief...")
    try:
        raw = call_claude(build_prompt_quick(master_brief, sleep_brief, sleep_findings, day_brief, activity_brief, athlete_context=athlete_context), SYSTEM_QUICK)
        quick = parse_json_response(raw)
        results["quick"] = quick
        save_json(os.path.join(pi_dir, "master_brief_quick.json"), quick)
        print("  [OK] Quick Brief")
    except Exception as e:
        print(f"  [ERROR] Quick Brief: {e}")
        results["quick"] = None

    print("  Generando Deep Brief...")
    try:
        raw = call_claude(build_prompt_deep(master_brief, sleep_brief, sleep_analysis, sleep_findings, day_brief, day_analysis, activity_brief, athlete_context=athlete_context), SYSTEM_DEEP)
        deep = parse_json_response(raw)
        results["deep"] = deep
        save_json(os.path.join(pi_dir, "master_brief_deep.json"), deep)
        print("  [OK] Deep Brief")
    except Exception as e:
        print(f"  [ERROR] Deep Brief: {e}")
        results["deep"] = None

    if results.get("quick"):
        print_quick(results["quick"])
    if results.get("deep"):
        print_deep(results["deep"])

    print(f"\n{'='*50}")
    print("Archivos guardados:")
    print(f"  {os.path.join(pi_dir, 'master_brief_quick.json')}")
    print(f"  {os.path.join(pi_dir, 'master_brief_deep.json')}")
    print(f"{'='*50}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master AI Brief — Quick + Deep")
    parser.add_argument("--user_dir", type=str, default="data/users/TU_USER")
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()
    run_master_ai_brief(args.user_dir, target_date=args.date)