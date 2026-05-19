"""
apex_ai_engine.py
=================
Motor de IA de Apex — arquitectura multi-call_type.

Cada llamada tiene su propio modelo, prompt y esquema de output.

call_type:
  verdict         -> Haiku  | 2 oraciones, string plano
  athlete_profile -> Sonnet | JSON: primary_type, strengths, limiters, development_focus
  action_plan     -> Sonnet | JSON: 3 acciones con priority, action, why, how
  full_report     -> Opus   | texto estructurado con 9 secciones
  chat            -> Haiku/Sonnet (auto-detect) | respuesta conversacional ≤150 palabras

CLI:
  python apex_ai_engine.py \\
    --call_type verdict \\
    --activity_id 22264587474 \\
    --user_id abelgcanofuentes_at_hotmail_com

Output: JSON a stdout -> { "call_type": "...", "output": "..." }
"""

import argparse
import json
import os
import sys
from statistics import mean

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = "c:/garmin-ai"

MODELS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-6",
}

CHAT_ANALYSIS_KEYWORDS = {
    "por qué", "porqué", "porque", "listo", "debo", "recomienda", "plan",
    "comparar", "historial", "mejor", "mejorar", "estrategia", "cómo",
    "debería", "puedo", "próxima", "siguiente", "semana",
}


# ─── loaders ──────────────────────────────────────────────────────────────────

def _load(path: str) -> dict | list:
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def user_root(user_id: str) -> str:
    return os.path.join(BASE_DIR, "data", "users", user_id)


def load_activity(user_id: str, activity_id: str) -> dict:
    folder = os.path.join(user_root(user_id), "activities", activity_id)
    return {
        "analysis":       _load(os.path.join(folder, "activity_analysis.json")),
        "findings":       _load(os.path.join(folder, "activity_findings.json")),
        "series_insights":_load(os.path.join(folder, "series_insights.json")),
        "brief":          _load(os.path.join(folder, "activity_brief.json")),
    }


def load_athlete_context(user_id: str) -> dict:
    root = user_root(user_id)
    pi = os.path.join(root, "performance_intelligence")

    baseline  = _load(os.path.join(pi, "athlete_baseline.json"))
    profile   = _load(os.path.join(root, "profile.json"))
    ftp_prof  = _load(os.path.join(pi, "ftp_profile.json"))

    # Últimas 5 sesiones resumidas
    idx_raw = _load(os.path.join(root, "activity_index.json"))
    activities = idx_raw.get("activities", idx_raw) if isinstance(idx_raw, dict) else idx_raw
    recent = activities[-5:] if isinstance(activities, list) else []

    recent_summary_lines = []
    for a in reversed(recent):
        line = (
            f"{a.get('date','?')[:10]} | {a.get('name','?')} | "
            f"TSS {a.get('garmin_tss') or '?'} | "
            f"NP {a.get('garmin_np') or '?'}W | "
            f"limiter: {a.get('primary_limiter','?')}"
        )
        recent_summary_lines.append(line)

    recurrent_limiters = baseline.get("recurrent_limiters", [])
    if not recurrent_limiters:
        limiter_counts: dict[str, int] = {}
        for a in recent:
            lim = a.get("primary_limiter")
            if lim:
                limiter_counts[lim] = limiter_counts.get(lim, 0) + 1
        recurrent_limiters = [k for k, v in sorted(limiter_counts.items(), key=lambda x: -x[1]) if v >= 2]

    goal_name = profile.get("goal_event_name", "")
    goal_date = profile.get("goal_event_date", "")

    return {
        "ftp_w":   ftp_prof.get("ftp_current") or baseline.get("ftp_model", {}).get("ftp_estimated"),
        "weight_kg": profile.get("weight_kg"),
        "max_hr":    profile.get("max_hr_bpm") or baseline.get("physiological_baselines", {}).get("max_hr"),
        "primary_type": baseline.get("athlete_profile", {}).get("primary_type"),
        "goal": f"{goal_name} {goal_date}".strip() or None,
        "recurrent_limiters": recurrent_limiters,
        "recent_sessions_summary": "\n".join(recent_summary_lines) if recent_summary_lines else "Sin historial reciente.",
    }


def _ctx_block(ctx: dict) -> str:
    lines = []
    if ctx.get("ftp_w"):
        lines.append(f"FTP: {ctx['ftp_w']}W")
    if ctx.get("weight_kg"):
        lines.append(f"Peso: {ctx['weight_kg']} kg")
    if ctx.get("max_hr"):
        lines.append(f"FC max: {ctx['max_hr']} bpm")
    if ctx.get("primary_type"):
        lines.append(f"Tipo: {ctx['primary_type']}")
    if ctx.get("goal"):
        lines.append(f"Objetivo: {ctx['goal']}")
    if ctx.get("recurrent_limiters"):
        lines.append(f"Limitantes recurrentes: {', '.join(ctx['recurrent_limiters'])}")
    if ctx.get("recent_sessions_summary"):
        lines.append(f"\nÚltimas sesiones:\n{ctx['recent_sessions_summary']}")
    return "\n".join(lines)


# ─── prompts ──────────────────────────────────────────────────────────────────

def _prompt_verdict(analysis: dict, ctx: dict) -> str:
    gs = analysis.get("garmin_summary", {})
    ds = analysis.get("derived_summary", {})
    ps = analysis.get("performance_scores", {})
    overall = ps.get("overall_score", {}).get("score")
    return f"""Eres el motor de análisis de Apex. Responde SOLO con 2 oraciones en español. Sin markdown. Sin bullets.

ATLETA
{_ctx_block(ctx)}

DATOS DE LA ACTIVIDAD
Nombre: {gs.get('name','')}
Distancia: {gs.get('distance_km')} km | Desnivel: {gs.get('elevation_m')} m | Tiempo: {gs.get('moving_minutes')} min
TSS: {gs.get('garmin_tss')} | NP: {gs.get('garmin_np')}W | IF: {gs.get('garmin_if')} | Score global: {overall}
VI: {ds.get('vi')} | Tipo de ride: {ds.get('ride_classification','')}
Caída de potencia: {analysis.get('fatigue',{}).get('power_drop_pct')}%
Limitante principal: {analysis.get('garmin_summary',{}).get('primary_limiter','')}

Primera oración: qué tipo de salida fue y qué sistema energético trabajó.
Segunda oración: el dato más positivo concreto y el más importante a mejorar — con número real.
"""


def _prompt_athlete_profile(analysis: dict, ctx: dict, recent_analyses: list[dict]) -> str:
    pp = analysis.get("power_profile", {})

    history_lines = []
    for a in recent_analyses[-5:]:
        gs = a.get("garmin_summary", {})
        ds = a.get("derived_summary", {})
        fa = a.get("fatigue", {})
        pp2 = a.get("power_profile", {})
        history_lines.append(
            f"{gs.get('start_date','')[:10]} | NP {gs.get('garmin_np')}W | TSS {gs.get('garmin_tss')} | "
            f"drop {fa.get('power_drop_pct')}% | "
            f"5min {pp2.get('5min',{}) and pp2.get('5min',{}).get('avg_power')}W | "
            f"20min {pp2.get('20min',{}) and pp2.get('20min',{}).get('avg_power')}W"
        )

    return f"""Responde SOLO con JSON válido. Sin texto adicional.

ATLETA
{_ctx_block(ctx)}

CURVA DE POTENCIA (esta sesión)
5s: {pp.get('5s',{}) and pp.get('5s',{}).get('avg_power')}W
15s: {pp.get('15s',{}) and pp.get('15s',{}).get('avg_power')}W
1min: {pp.get('1min',{}) and pp.get('1min',{}).get('avg_power')}W
5min: {pp.get('5min',{}) and pp.get('5min',{}).get('avg_power')}W
10min: {pp.get('10min',{}) and pp.get('10min',{}).get('avg_power')}W
20min: {pp.get('20min',{}) and pp.get('20min',{}).get('avg_power')}W
60min: {pp.get('60min',{}) and pp.get('60min',{}).get('avg_power')}W

HISTORIAL RECIENTE
{chr(10).join(history_lines) if history_lines else 'Sin historial'}

Clasifica al atleta: puncheur = domina 1–5min, climber = domina 10–60min, diesel = distribución plana, all-rounder = equilibrado.

Responde con exactamente este JSON:
{{
  "primary_type": "puncher|climber|diesel|all-rounder",
  "strengths": ["max 3 frases cortas"],
  "limiters": ["max 2 frases cortas"],
  "development_focus": ["max 3 acciones concretas"]
}}
"""


def _prompt_action_plan(findings: list, ctx: dict, analysis: dict) -> str:
    top_findings = findings[:8] if isinstance(findings, list) else []
    fa = analysis.get("fatigue", {})
    gs = analysis.get("garmin_summary", {})

    ftp = ctx.get("ftp_w", 230)
    zone4_low = round(ftp * 0.88)
    zone4_high = round(ftp * 0.95)

    return f"""Responde SOLO con JSON válido. Sin texto adicional.

ATLETA
{_ctx_block(ctx)}

DATOS CLAVE DE LA SESIÓN
TSS: {gs.get('garmin_tss')} | NP: {gs.get('garmin_np')}W | IF: {gs.get('garmin_if')}
Caída de potencia: {fa.get('power_drop_pct')}% | Fatiga en min: {fa.get('fatigue_onset_min')}

FINDINGS RANKEADOS (top 8)
{json.dumps(top_findings, ensure_ascii=False, indent=2)}

REFERENCIAS DE ZONA (FTP={ftp}W)
Z3 Tempo: {round(ftp*0.76)}–{round(ftp*0.87)}W
Z4 Umbral: {zone4_low}–{zone4_high}W
Z5 VO2max: {round(ftp*1.06)}–{round(ftp*1.20)}W

Genera exactamente 3 acciones ejecutables esta semana. Cada "how" DEBE incluir duración, intensidad en vatios reales y formato.

[
  {{
    "priority": 1,
    "action": "qué hacer — específico y accionable",
    "why": "por qué — un dato concreto de la sesión",
    "how": "cómo — duración, vatios, formato exacto"
  }},
  {{ "priority": 2, "action": "...", "why": "...", "how": "..." }},
  {{ "priority": 3, "action": "...", "why": "...", "how": "..." }}
]
"""


def _prompt_full_report(activity_data: dict, ctx: dict, recent_analyses: list[dict]) -> str:
    analysis = activity_data["analysis"]
    findings = activity_data["findings"]
    si = activity_data["series_insights"]
    gs = analysis.get("garmin_summary", {})
    ds = analysis.get("derived_summary", {})
    climbs = analysis.get("climbs", [])
    fa = analysis.get("fatigue", {})
    ps = analysis.get("performance_scores", {})
    zones = analysis.get("zones", {})

    history_block = ""
    for a in recent_analyses[-6:]:
        ags = a.get("garmin_summary", {})
        history_block += (
            f"  {ags.get('start_date','')[:10]} | {ags.get('name','')} | "
            f"NP {ags.get('garmin_np')}W | TSS {ags.get('garmin_tss')} | "
            f"drop {a.get('fatigue',{}).get('power_drop_pct')}%\n"
        )

    return f"""Eres el motor de análisis de Apex. Genera un reporte médico-deportivo estructurado en español.
Tono: coach profesional técnico. Sin markdown excesivo. Cada sección máximo 150 palabras.

ATLETA
{_ctx_block(ctx)}

GARMIN RESUMEN
{json.dumps(gs, ensure_ascii=False)}

APEX DERIVADO
{json.dumps(ds, ensure_ascii=False)}

ZONAS
{json.dumps(zones, ensure_ascii=False)}

ASCENSOS ({len(climbs)})
{json.dumps(climbs, ensure_ascii=False)}

FATIGA
{json.dumps(fa, ensure_ascii=False)}

PERFORMANCE SCORES
{json.dumps(ps, ensure_ascii=False)}

CORRELACIONES TEMPORALES
{json.dumps(si, ensure_ascii=False)}

FINDINGS RANKEADOS
{json.dumps((findings if isinstance(findings, list) else findings.get('findings', []))[:10], ensure_ascii=False)}

HISTORIAL RECIENTE (últimas 6)
{history_block or 'Sin historial'}

Genera el reporte con EXACTAMENTE estas 9 secciones, en este orden:
1. Resumen ejecutivo
2. Análisis de carga (TSS, IF, VI, energy_kj)
3. Perfil energético de la sesión (zonas, ride_classification, curva de potencia)
4. Análisis de ascensos (VAM, cadence_fatigue_per_climb, best_vs_worst)
5. Fatiga y durabilidad (cardiac_decoupling, second_half_degradation, power_drop)
6. Fortalezas detectadas
7. Limitantes detectados
8. Plan de desarrollo (próximas 2–3 semanas, sesiones específicas con vatios)
9. Contexto histórico (comparación con últimas 6 sesiones)

No repitas datos entre secciones. Sin bloques de código.
"""


def _detect_chat_model(message: str) -> str:
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in CHAT_ANALYSIS_KEYWORDS):
        return "sonnet"
    return "haiku"


def _prompt_chat(message: str, activity_data: dict, ctx: dict) -> tuple[str, str]:
    model_key = _detect_chat_model(message)
    analysis = activity_data.get("analysis", {})
    gs = analysis.get("garmin_summary", {})
    ds = analysis.get("derived_summary", {})
    fa = analysis.get("fatigue", {})
    si = activity_data.get("series_insights", {})
    ps = analysis.get("performance_scores", {})

    context_summary = f"""ATLETA
{_ctx_block(ctx)}

ACTIVIDAD ACTUAL ({gs.get('start_date','')[:10]})
{gs.get('name','')} | {gs.get('distance_km')} km | {gs.get('elevation_m')} m | {gs.get('moving_minutes')} min
TSS {gs.get('garmin_tss')} | NP {gs.get('garmin_np')}W | IF {gs.get('garmin_if')}
Caída potencia: {fa.get('power_drop_pct')}% | Active cadence: {ds.get('active_cadence_rpm')} rpm
Score global: {ps.get('overall_score',{}).get('score')}
Correlaciones clave: {json.dumps({k: v.get('interpretation','') for k,v in (si or {}).items() if isinstance(v,dict) and 'interpretation' in v}, ensure_ascii=False)}"""

    prompt = f"""{context_summary}

MENSAJE DEL ATLETA
{message}

Responde en español. Máximo 150 palabras. Tono de coach que ya lleva meses siguiendo este atleta.
Sin presentaciones. Sin "según tus datos". Sin "como coach". Directo al punto.
Si no tienes el dato, di: "No tengo ese dato en tu historial aún."
"""
    return prompt, model_key


# ─── API pública ──────────────────────────────────────────────────────────────

def call_apex(
    call_type: str,
    user_id: str,
    activity_id: str | None = None,
    message: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    ctx = load_athlete_context(user_id)
    activity_data = load_activity(user_id, activity_id) if activity_id else {}
    analysis = activity_data.get("analysis", {})

    # Cargar historial de análisis anteriores
    recent_analyses: list[dict] = []
    root = user_root(user_id)
    idx_raw = _load(os.path.join(root, "activity_index.json"))
    activities = idx_raw.get("activities", idx_raw) if isinstance(idx_raw, dict) else idx_raw
    if isinstance(activities, list):
        current_id = str(activity_id or "")
        prev_acts = [a for a in activities if str(a.get("activity_id", "")) != current_id][-6:]
        for pa in reversed(prev_acts):
            af = pa.get("analysis_file", "")
            full = af if os.path.isabs(af) else os.path.join(root, af)
            if full and os.path.exists(full):
                recent_analyses.append(_load(full))

    client = anthropic.Anthropic()

    # ── verdict ────────────────────────────────────────────────────────────────
    if call_type == "verdict":
        prompt = _prompt_verdict(analysis, ctx)
        resp = client.messages.create(
            model=MODELS["haiku"],
            max_tokens=max_tokens or 120,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"call_type": "verdict", "output": resp.content[0].text.strip()}

    # ── athlete_profile ────────────────────────────────────────────────────────
    elif call_type == "athlete_profile":
        prompt = _prompt_athlete_profile(analysis, ctx, recent_analyses)
        resp = client.messages.create(
            model=MODELS["sonnet"],
            max_tokens=max_tokens or 600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        try:
            return {"call_type": "athlete_profile", "output": json.loads(text)}
        except json.JSONDecodeError:
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            return {"call_type": "athlete_profile", "output": json.loads(m.group()) if m else text}

    # ── action_plan ────────────────────────────────────────────────────────────
    elif call_type == "action_plan":
        findings_raw = activity_data.get("findings", {})
        findings_list = findings_raw if isinstance(findings_raw, list) else findings_raw.get("findings", [])
        prompt = _prompt_action_plan(findings_list, ctx, analysis)
        resp = client.messages.create(
            model=MODELS["sonnet"],
            max_tokens=max_tokens or 900,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        try:
            return {"call_type": "action_plan", "output": json.loads(text)}
        except json.JSONDecodeError:
            import re
            m = re.search(r'\[.*\]', text, re.DOTALL)
            return {"call_type": "action_plan", "output": json.loads(m.group()) if m else text}

    # ── full_report ────────────────────────────────────────────────────────────
    elif call_type == "full_report":
        prompt = _prompt_full_report(activity_data, ctx, recent_analyses)
        resp = client.messages.create(
            model=MODELS["opus"],
            max_tokens=max_tokens or 3000,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"call_type": "full_report", "output": resp.content[0].text.strip()}

    # ── chat ───────────────────────────────────────────────────────────────────
    elif call_type == "chat":
        if not message:
            return {"call_type": "chat", "output": "No recibí un mensaje."}
        prompt, model_key = _prompt_chat(message, activity_data, ctx)
        resp = client.messages.create(
            model=MODELS[model_key],
            max_tokens=max_tokens or 300,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"call_type": "chat", "model_used": model_key, "output": resp.content[0].text.strip()}

    else:
        return {"error": f"call_type desconocido: {call_type}"}


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--call_type", required=True,
                        choices=["verdict", "athlete_profile", "action_plan", "full_report", "chat"])
    parser.add_argument("--activity_id", default=None)
    parser.add_argument("--user_id", default=None)
    parser.add_argument("--message", default=None)
    parser.add_argument("--max_tokens", type=int, default=None)
    args = parser.parse_args()

    from app_context import get_current_user_id
    user_id = args.user_id or get_current_user_id()

    result = call_apex(
        call_type=args.call_type,
        user_id=user_id,
        activity_id=args.activity_id,
        message=args.message,
        max_tokens=args.max_tokens,
    )

    # stdout limpio — solo el JSON
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
