"""
athlete_context.py
==================
Helper central para cargar y construir el contexto del atleta.

Cualquier script de AI puede importar get_athlete_context(user_dir)
para obtener el bloque de texto que se inyecta en los prompts de Claude.

Si existe athlete_baseline.json (generado por profile_intelligence.py),
usa ese contexto rico. Si no, usa profile.json como fallback mínimo.

USO:
    from athlete_context import get_athlete_context, build_personal_baselines_block

    ctx = get_athlete_context(user_dir)
    prompt = f"{ctx}\\n\\n{resto_del_prompt}"
"""

import json
import os
from typing import Optional


def _load_json(path: str) -> dict | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_athlete_context(user_dir: str) -> str:
    """
    Devuelve el bloque de contexto completo del atleta listo para inyectar
    al inicio de cualquier prompt.

    Prioridad:
    1. athlete_baseline.json → athlete_context_string (contexto completo)
    2. profile.json → fallback mínimo con FTP, deporte, email
    3. Sin perfil → string vacío
    """
    baseline_path = os.path.join(user_dir, "performance_intelligence", "athlete_baseline.json")
    profile_path = os.path.join(user_dir, "profile.json")

    baseline = _load_json(baseline_path)
    profile = _load_json(profile_path)

    if baseline and baseline.get("athlete_context_string"):
        context = baseline["athlete_context_string"]
        # Añadir contexto de baselines personales para que el modelo compare
        baselines_block = build_personal_baselines_block(baseline)
        return f"{context}\n{baselines_block}"

    if profile:
        # Fallback mínimo
        email = profile.get("garmin_email", "usuario")
        sports = ", ".join(profile.get("sport_focus", ["ciclismo"]))
        ftp = profile.get("ftp")
        max_hr = profile.get("max_hr")
        parts = [f"PERFIL: Atleta ({email}). Deportes: {sports}."]
        if ftp:
            parts.append(f"FTP declarado: {ftp}W.")
        if max_hr:
            parts.append(f"FC max: {max_hr}bpm.")
        return " ".join(parts)

    return ""


def build_personal_baselines_block(baseline: dict) -> str:
    """
    Construye el bloque de REFERENCIAS PERSONALES para el prompt.

    CRÍTICO: Esto es lo que permite al modelo comparar el día de HOY
    contra lo que es NORMAL para ESTE atleta específico, no contra
    promedios poblacionales.

    Ejemplo de output:
    'REFERENCIAS PERSONALES (usa estas para interpretar, NO promedios poblacionales):
     HRV basal: 62ms (±12ms). Si hoy < 50ms → bajo para él. Si > 74ms → muy bueno.
     Recovery basal: 67/100. Rango normal: 63-71.
     Readiness basal: 50/100. Este atleta opera en un nivel base más bajo que la media.'
    """
    phys = baseline.get("physiological_baselines", {})
    flags = baseline.get("health_flags", {})
    load = baseline.get("sustainable_load", {})
    patterns = baseline.get("patterns", {})
    gc = baseline.get("goal_coherence", {})

    lines = ["REFERENCIAS PERSONALES (interpreta los valores de HOY contra estas referencias, NO contra promedios poblacionales):"]

    # HRV personal
    hrv = phys.get("hrv_basal", {})
    if hrv.get("mean"):
        m, s = hrv["mean"], hrv.get("std", 10)
        low = round(m - s, 0)
        high = round(m + s, 0)
        lines.append(f"- HRV basal: {m}ms ±{s}ms. Rango normal para él: {low}–{high}ms. Por debajo de {low}ms = señal de alarma personal.")

    # Recovery personal
    rec = phys.get("recovery_basal", {})
    if rec.get("mean"):
        lines.append(f"- Recovery basal: {rec['mean']}/100 (p25={rec.get('p25', '?')}). Un score de {round(rec['mean'])} es su día típico, NO es malo aunque parezca bajo.")

    # Readiness personal
    read = phys.get("readiness_basal", {})
    if read.get("mean"):
        lines.append(f"- Readiness basal: {read['mean']}/100. IMPORTANTE: este atleta opera normalmente en torno a {round(read['mean'])}/100. No asumir que es bajo por comparación poblacional.")

    # SpO2 flag
    spo2 = phys.get("spo2_nadir_basal", {})
    spo2_risk = flags.get("spo2_risk", {})
    if spo2_risk.get("activo"):
        pct = spo2_risk.get("porcentaje_noches_bajas", 0)
        lines.append(f"- SpO2: FLAG DE RIESGO ACTIVO. El {pct}% de sus noches tiene SpO2 mínimo < 88%. Esto es una condición crónica subyacente (probable hipoxia nocturna), no un evento aislado. Mencionarlo cuando sea relevante.")

    # Stress basal
    stress = phys.get("stress_basal", {})
    if stress.get("mean"):
        lines.append(f"- Estrés basal: {stress['mean']}/100. Su nivel de estrés crónico base.")

    # Carga sostenible
    tss = load.get("tss_semana_max_sostenible", {})
    if tss.get("valor"):
        lines.append(f"- Carga sostenible: TSS semanal máx ~{round(tss['valor'])} antes de que HRV caiga. Por encima de esto el cuerpo no absorbe bien.")

    # Patrones
    mejor = patterns.get("mejor_dia_semana", {})
    rec_days = patterns.get("dias_recuperacion_optimos", {})
    if mejor.get("dia"):
        lines.append(f"- Patrón: su mejor día fisiológico es el {mejor['dia']}.")
    if rec_days.get("promedio"):
        lines.append(f"- Recuperación: necesita ~{rec_days['promedio']} días entre sesiones intensas para restaurar HRV.")

    # Tendencias recientes
    hrv_trend = flags.get("hrv_trend", {})
    if hrv_trend.get("direccion") == "declining":
        lines.append(f"- TENDENCIA ACTUAL: HRV bajando (últimas 2 sem: {hrv_trend.get('ultimos_14_dias', '?')}ms vs previo: {hrv_trend.get('periodo_previo', '?')}ms). Contexto de fatiga acumulada.")
    elif hrv_trend.get("direccion") == "improving":
        lines.append(f"- TENDENCIA ACTUAL: HRV recuperándose (de {hrv_trend.get('periodo_previo', '?')} a {hrv_trend.get('ultimos_14_dias', '?')}ms). Señal positiva de adaptación.")

    # Fase del objetivo
    if gc.get("semanas_restantes") is not None:
        sw = gc["semanas_restantes"]
        fase = gc.get("fase_actual", "entrenamiento")
        event = gc.get("goal_event", "su evento objetivo")
        lines.append(f"- CONTEXTO DE TEMPORADA: {sw} semanas para {event}. Fase: {fase}. Calibra las recomendaciones según esta fase.")

    return "\n".join(lines)


def get_athlete_context_for_section(user_dir: str, section: str) -> str:
    """
    Versión específica por sección con instrucciones adicionales de personalización.
    """
    base_context = get_athlete_context(user_dir)
    if not base_context:
        return ""

    section_addons = {
        "sleep": "\nAL INTERPRETAR EL SUEÑO: Usa los baselines personales para decir si HOY fue mejor o peor que su norma. El SpO2 flag es condición crónica — integrar en el análisis de recuperación.",
        "day": "\nAL INTERPRETAR EL DÍA: Su readiness base ~50/100 es su operación normal. Un 58 para él es un buen día. Calibra las recomendaciones a su nivel real de atleta.",
        "activity": "\nAL INTERPRETAR LA ACTIVIDAD: FTP real 208W (calculado de sus últimas sesiones). Compara su rendimiento contra su propio historial, no contra estándares externos. Si tiene goal_event próximo, considera la fase de entrenamiento en las recomendaciones.",
        "master": "\nAL GENERAR EL ANÁLISIS MASTER: Integra TODOS los factores personales. Un score de 50/100 para él es su zona de precaución habitual — explica qué lo lleva arriba o abajo de su propio basal.",
    }

    addon = section_addons.get(section, "")
    return f"{base_context}{addon}"
