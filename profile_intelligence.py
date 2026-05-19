"""
profile_intelligence.py
========================
Cruza el perfil declarado del usuario con sus datos fisiológicos reales
para generar athlete_baseline.json — la huella digital del atleta.

Se ejecuta:
  - Después de crear el perfil por primera vez
  - Al final de cada auto_sync si existe profile.json

Guarda en:
  performance_intelligence/athlete_baseline.json

Uso:
    python profile_intelligence.py --user_dir data/users/abelgcanofuentes_at_hotmail_com
    python profile_intelligence.py  # usa usuario activo en contexto
"""

import json
import os
import argparse
import math
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Optional


# ─── Helpers ────────────────────────────────────────────────────────────────

def load_json(path: str) -> dict | list | None:
    """Carga un JSON de forma segura. Devuelve None si no existe."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def safe_mean(values: list) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(float(v))]
    return round(sum(vals) / len(vals), 2) if vals else None


def safe_std(values: list) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    variance = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
    return round(math.sqrt(variance), 2)


def safe_percentile(values: list, p: float) -> Optional[float]:
    vals = sorted([float(v) for v in values if v is not None and not math.isnan(float(v))])
    if not vals:
        return None
    idx = (p / 100) * (len(vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (idx - lo), 2)


def parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def trend_direction(recent: Optional[float], prior: Optional[float], threshold_pct: float = 5.0) -> str:
    """Clasifica tendencia como improving/stable/declining."""
    if recent is None or prior is None or prior == 0:
        return "stable"
    change_pct = ((recent - prior) / abs(prior)) * 100
    if change_pct >= threshold_pct:
        return "improving"
    if change_pct <= -threshold_pct:
        return "declining"
    return "stable"


WEEKDAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ─── Sección 1: Baselines fisiológicos ──────────────────────────────────────

def compute_physiological_baselines(
    sleep_history: list,
    sleep_baselines: dict,
    day_baselines: dict,
    readiness_history: list
) -> dict:
    """Calcula baselines reales desde el historial de datos."""

    result = {}

    # HRV basal — de sleep_history (datos granulares) o sleep_baselines
    hrv_vals = [r.get("avg_overnight_hrv") for r in sleep_history
                if r.get("avg_overnight_hrv") and r["avg_overnight_hrv"] > 0]
    if hrv_vals:
        result["hrv_basal"] = {
            "mean": safe_mean(hrv_vals),
            "std": safe_std(hrv_vals),
            "n": len(hrv_vals),
            "unit": "ms"
        }
    elif sleep_baselines:
        m = sleep_baselines.get("metrics", {}).get("avg_overnight_hrv", {})
        if m.get("mean"):
            result["hrv_basal"] = {
                "mean": round(m["mean"], 1),
                "std": None,
                "n": sleep_baselines.get("window_days", 0),
                "unit": "ms"
            }

    # SpO2 nadir basal — percentil 25 de min_spo2 (el peor recurrente, no el outlier)
    spo2_vals = [r.get("min_spo2") for r in sleep_history
                 if r.get("min_spo2") and r["min_spo2"] > 50]  # excluir 0 / datos faltantes
    if spo2_vals:
        result["spo2_nadir_basal"] = {
            "p25": safe_percentile(spo2_vals, 25),
            "median": safe_percentile(spo2_vals, 50),
            "n_nights": len(spo2_vals),
            "unit": "%"
        }

    # Recovery basal (sueño)
    rec_vals = [r.get("overall_recovery_score") for r in sleep_history
                if r.get("overall_recovery_score")]
    if rec_vals:
        result["recovery_basal"] = {
            "mean": safe_mean(rec_vals),
            "p25": safe_percentile(rec_vals, 25),
            "unit": "/100"
        }
    elif sleep_baselines:
        m = sleep_baselines.get("metrics", {}).get("overall_recovery_score", {})
        if m.get("mean"):
            result["recovery_basal"] = {
                "mean": round(m["mean"], 1),
                "p25": round(m.get("p25", 0), 1),
                "unit": "/100"
            }

    # Readiness basal
    r_vals = [r.get("readiness_score") for r in readiness_history
              if r.get("readiness_score")]
    if r_vals:
        result["readiness_basal"] = {
            "mean": safe_mean(r_vals),
            "p25": safe_percentile(r_vals, 25),
            "unit": "/100"
        }

    # Stress basal (día)
    stress_vals_meta = day_baselines.get("metrics", {}).get("avg_stress", {})
    if stress_vals_meta.get("mean") is not None:
        result["stress_basal"] = {
            "mean": round(stress_vals_meta["mean"], 1),
            "unit": "/100"
        }

    # Body battery recharge basal (sueño — ganancia nocturna)
    bb_vals = [r.get("body_battery_change") for r in sleep_history
               if r.get("body_battery_change") is not None and r["body_battery_change"] > 0]
    if bb_vals:
        result["bb_recharge_basal"] = {
            "mean": safe_mean(bb_vals),
            "p25": safe_percentile(bb_vals, 25),
            "unit": "puntos",
            "note": "ganancia nocturna promedio"
        }
    elif sleep_baselines:
        m = sleep_baselines.get("metrics", {}).get("body_battery_change", {})
        if m.get("mean"):
            result["bb_recharge_basal"] = {
                "mean": round(m["mean"], 1),
                "p25": round(m.get("p25", 0), 1),
                "unit": "puntos"
            }

    return result


# ─── Sección 2: Patrones detectados ─────────────────────────────────────────

def compute_patterns(
    readiness_history: list,
    sleep_history: list,
    activity_index: list,
    ftp_profile: dict
) -> dict:
    """Detecta patrones de comportamiento del atleta."""

    patterns = {}

    # ── Mejor/Peor día de la semana por readiness
    if len(readiness_history) >= 7:
        weekday_scores = defaultdict(list)
        for r in readiness_history:
            d = parse_date(r.get("calendar_date", ""))
            score = r.get("readiness_score")
            if d and score:
                weekday_scores[d.weekday()].append(score)

        if weekday_scores:
            weekday_means = {wd: safe_mean(scores) for wd, scores in weekday_scores.items()
                             if len(scores) >= 2}
            if weekday_means:
                best_wd = max(weekday_means, key=lambda k: weekday_means[k])
                worst_wd = min(weekday_means, key=lambda k: weekday_means[k])
                patterns["mejor_dia_semana"] = {
                    "dia": WEEKDAY_NAMES[best_wd],
                    "weekday_num": best_wd,
                    "readiness_promedio": round(weekday_means[best_wd], 1)
                }
                patterns["peor_dia_semana"] = {
                    "dia": WEEKDAY_NAMES[worst_wd],
                    "weekday_num": worst_wd,
                    "readiness_promedio": round(weekday_means[worst_wd], 1)
                }

    # ── Cronótipo / patrón de sueño (early_bird / night_owl / irregular)
    midpoints = [r.get("sleep_midpoint_minutes") for r in sleep_history
                 if r.get("sleep_midpoint_minutes") is not None and r["sleep_midpoint_minutes"] > 0]
    if midpoints:
        avg_midpoint = safe_mean(midpoints)
        std_midpoint = safe_std(midpoints)
        # midpoint_minutes = minutos desde medianoche hasta el punto medio del sueño
        # Ej: dormir 23:00 – 07:00 → midpoint = 3:00 AM = 180 min
        if std_midpoint and std_midpoint > 90:
            patron = "irregular"
        elif avg_midpoint is not None and avg_midpoint < 120:  # antes de 2 AM
            patron = "early_bird"
        elif avg_midpoint is not None and avg_midpoint > 210:  # después de 3:30 AM
            patron = "night_owl"
        else:
            patron = "regular"

        patterns["patron_sueno"] = {
            "tipo": patron,
            "midpoint_promedio_min": round(avg_midpoint or 0, 0),
            "variabilidad_min": round(std_midpoint or 0, 0),
            "nota": f"Punto medio promedio del sueño: {int((avg_midpoint or 180) // 60):02d}:{int((avg_midpoint or 180) % 60):02d} AM"
        }
    else:
        # Si no hay midpoint_minutes, inferir por actividades (hora de entrenamiento)
        patterns["patron_sueno"] = {
            "tipo": "desconocido",
            "nota": "Datos de horario de sueño no disponibles aún"
        }

    # ── Hora óptima de entrenamiento
    # Inferir de cuándo el usuario ha entrenado (mañana/tarde/noche)
    if activity_index:
        hour_counts = defaultdict(int)
        for a in activity_index:
            date_str = a.get("date", "")
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                h = dt.hour
                if h < 12:
                    hour_counts["mañana"] += 1
                elif h < 17:
                    hour_counts["tarde"] += 1
                else:
                    hour_counts["noche"] += 1
            except Exception:
                pass
        if hour_counts:
            hora_optima = max(hour_counts, key=lambda k: hour_counts[k])
            patterns["hora_habitual_entreno"] = {
                "franja": hora_optima,
                "distribucion": dict(hour_counts),
                "nota": "Basado en historial de actividades registradas"
            }

    # ── Días de recuperación óptimos entre sesiones intensas
    # Mide cuántos días tarda HRV en volver al basal tras sesión intensa
    # Sesión intensa = actividad con moving_minutes > 60 o elevation > 400m
    if activity_index and len(readiness_history) >= 7:
        # Índice de readiness por fecha
        readiness_by_date = {
            r["calendar_date"]: r["readiness_score"]
            for r in readiness_history
            if r.get("calendar_date") and r.get("readiness_score")
        }
        hrv_by_date = {
            r["calendar_date"]: r["avg_overnight_hrv"]
            for r in sleep_history
            if r.get("calendar_date") and r.get("avg_overnight_hrv") and r["avg_overnight_hrv"] > 0
        }

        recovery_days_list = []
        hrv_mean = safe_mean(list(hrv_by_date.values())) or 60

        intense_activities = [
            a for a in activity_index
            if (a.get("moving_minutes") or 0) > 60 or (a.get("elevation_m") or 0) > 400
        ]

        for act in intense_activities:
            act_date = parse_date(act.get("date", ""))
            if not act_date:
                continue
            # Busca cuántos días después el HRV vuelve a >=95% del basal
            for days_after in range(1, 5):
                check_date = (act_date + timedelta(days=days_after)).isoformat()
                hrv_after = hrv_by_date.get(check_date)
                if hrv_after and hrv_after >= hrv_mean * 0.95:
                    recovery_days_list.append(days_after)
                    break

        if recovery_days_list:
            avg_rec_days = safe_mean(recovery_days_list)
            patterns["dias_recuperacion_optimos"] = {
                "promedio": round(avg_rec_days or 2, 1),
                "basado_en_n_sesiones": len(recovery_days_list),
                "nota": "Días hasta que HRV vuelve a ≥95% del basal tras sesión intensa"
            }
        else:
            patterns["dias_recuperacion_optimos"] = {
                "promedio": 2,
                "nota": "Estimación por defecto — insuficientes datos de actividades intensas"
            }

    return patterns


# ─── Sección 3: Carga sostenible ────────────────────────────────────────────

def compute_sustainable_load(
    activity_index: list,
    sleep_history: list,
    readiness_history: list,
    ftp_profile: dict
) -> dict:
    """Calcula los límites de carga sostenible del atleta."""

    load_data = {}

    if not activity_index:
        return load_data

    # Índice HRV por fecha
    hrv_by_date = {
        r["calendar_date"]: r["avg_overnight_hrv"]
        for r in sleep_history
        if r.get("calendar_date") and r.get("avg_overnight_hrv") and r["avg_overnight_hrv"] > 0
    }
    hrv_mean = safe_mean(list(hrv_by_date.values())) or 60

    readiness_by_date = {
        r["calendar_date"]: r["readiness_score"]
        for r in readiness_history
        if r.get("calendar_date") and r.get("readiness_score")
    }

    # Estimar TSS de cada actividad: IF² × tiempo_horas × 100
    # IF = estimated_np / ftp_current (o garmin_np / ftp si disponible)
    ftp = (ftp_profile or {}).get("ftp_current") or 208

    def estimate_tss(act: dict) -> Optional[float]:
        np_val = act.get("garmin_np") or act.get("estimated_np")
        minutes = act.get("moving_minutes", 0)
        if np_val and minutes and ftp:
            intensity_factor = np_val / ftp
            tss = (intensity_factor ** 2) * (minutes / 60) * 100
            return round(tss, 1)
        # Fallback: minutos × 0.8 (carga genérica sin potencia)
        if minutes:
            return round(minutes * 0.8, 1)
        return None

    # Agrupar actividades por semana
    weekly_load = defaultdict(list)
    for act in activity_index:
        act_date = parse_date(act.get("date", ""))
        if not act_date:
            continue
        # ISO week key
        week_key = f"{act_date.isocalendar()[0]}-W{act_date.isocalendar()[1]:02d}"
        tss = estimate_tss(act)
        if tss:
            weekly_load[week_key].append((act_date, tss))

    # TSS semanal total
    weekly_tss = {}
    for week, acts in weekly_load.items():
        weekly_tss[week] = sum(t for _, t in acts)

    if weekly_tss:
        # Semanas con HRV saludable (≥90% del basal)
        sustainable_tss_weeks = []
        for week, tss in weekly_tss.items():
            year, week_num = week.split("-W")
            # Obtener el lunes de esa semana
            week_monday = date.fromisocalendar(int(year), int(week_num), 1)
            # HRV promedio esa semana
            hrv_week_vals = []
            for days_offset in range(7):
                d = (week_monday + timedelta(days=days_offset)).isoformat()
                if d in hrv_by_date:
                    hrv_week_vals.append(hrv_by_date[d])
            if hrv_week_vals:
                avg_hrv_week = safe_mean(hrv_week_vals)
                if avg_hrv_week and avg_hrv_week >= hrv_mean * 0.90:
                    sustainable_tss_weeks.append(tss)

        if sustainable_tss_weeks:
            load_data["tss_semana_max_sostenible"] = {
                "valor": safe_percentile(sustainable_tss_weeks, 75),  # p75 de semanas saludables
                "media_semanas_sanas": safe_mean(sustainable_tss_weeks),
                "nota": "TSS semanal donde HRV se mantuvo ≥90% del basal",
                "n_semanas": len(sustainable_tss_weeks)
            }
        elif weekly_tss:
            all_tss = list(weekly_tss.values())
            load_data["tss_semana_max_sostenible"] = {
                "valor": safe_percentile(all_tss, 60),
                "nota": "Estimación sin suficientes semanas con HRV saludable",
                "n_semanas": len(all_tss)
            }

    # Readiness caída bajo carga alta (proxy ATL)
    # Grupos: ¿Cuándo cae readiness < 50?
    if readiness_by_date:
        consecutive_heavy = 0
        max_consecutive = 0
        for act in sorted(activity_index, key=lambda a: a.get("date", "")):
            act_date = parse_date(act.get("date", ""))
            if not act_date:
                continue
            tss = estimate_tss(act)
            if tss and tss > 80:  # sesión pesada
                consecutive_heavy += 1
                max_consecutive = max(max_consecutive, consecutive_heavy)
            else:
                # Ver si readiness cayó después de racha
                tomorrow = (act_date + timedelta(days=1)).isoformat()
                r_score = readiness_by_date.get(tomorrow)
                if consecutive_heavy >= 2 and r_score and r_score < 50:
                    pass  # racha terminó porque readiness cayó
                consecutive_heavy = 0

        if max_consecutive > 0:
            load_data["dias_alto_volumen_max"] = {
                "valor": max_consecutive,
                "nota": "Máx días consecutivos con TSS>80 antes de caída de readiness"
            }

    return load_data


# ─── Sección 4: Flags de salud ──────────────────────────────────────────────

def compute_health_flags(
    sleep_history: list,
    sleep_patterns: dict,
    readiness_history: list,
    day_baselines: dict
) -> dict:
    """Detecta flags de riesgo para salud y rendimiento."""

    flags = {}

    # SpO2 risk: min_spo2 < 88 en >30% de las noches
    spo2_vals = [r.get("min_spo2") for r in sleep_history
                 if r.get("min_spo2") is not None and r["min_spo2"] > 50]
    if spo2_vals:
        low_nights = sum(1 for v in spo2_vals if v < 88)
        pct_low = (low_nights / len(spo2_vals)) * 100
        flags["spo2_risk"] = {
            "activo": pct_low > 30,
            "porcentaje_noches_bajas": round(pct_low, 1),
            "n_noches_analizadas": len(spo2_vals),
            "umbral": "min_spo2 < 88%",
            "severidad": "alta" if pct_low > 60 else ("moderada" if pct_low > 30 else "baja")
        }
        # También incluir el patrón detectado del motor de patrones
        recurrent = sleep_patterns.get("recurrent_patterns", [])
        for p in recurrent:
            if p.get("code") == "recurrent_low_oxygen_nadir":
                flags["spo2_risk"]["patron_detectado"] = True
                flags["spo2_risk"]["conteo_noches_motor"] = p.get("count", 0)

    # HRV trend — últimos 14 días vs 14 anteriores
    recent_hrv = sorted(
        [(r["calendar_date"], r["avg_overnight_hrv"]) for r in sleep_history
         if r.get("avg_overnight_hrv") and r["avg_overnight_hrv"] > 0],
        key=lambda x: x[0]
    )
    if len(recent_hrv) >= 14:
        mid = len(recent_hrv) // 2
        prior_14 = safe_mean([v for _, v in recent_hrv[-28:-14]] if len(recent_hrv) >= 28 else [v for _, v in recent_hrv[:mid]])
        last_14 = safe_mean([v for _, v in recent_hrv[-14:]])
        flags["hrv_trend"] = {
            "direccion": trend_direction(last_14, prior_14),
            "ultimos_14_dias": last_14,
            "periodo_previo": prior_14
        }

    # Recovery trend — últimos 14 días vs 14 anteriores
    recent_rec = sorted(
        [(r["calendar_date"], r["overall_recovery_score"]) for r in sleep_history
         if r.get("overall_recovery_score")],
        key=lambda x: x[0]
    )
    if len(recent_rec) >= 14:
        prior_rec = safe_mean([v for _, v in recent_rec[-28:-14]] if len(recent_rec) >= 28 else [v for _, v in recent_rec[:len(recent_rec)//2]])
        last_rec = safe_mean([v for _, v in recent_rec[-14:]])
        flags["recovery_trend"] = {
            "direccion": trend_direction(last_rec, prior_rec),
            "ultimos_14_dias": last_rec,
            "periodo_previo": prior_rec
        }

    # Readiness trend
    recent_readiness = sorted(
        [(r["calendar_date"], r["readiness_score"]) for r in readiness_history
         if r.get("readiness_score")],
        key=lambda x: x[0]
    )
    if len(recent_readiness) >= 14:
        prior_r = safe_mean([v for _, v in recent_readiness[-28:-14]] if len(recent_readiness) >= 28 else [v for _, v in recent_readiness[:len(recent_readiness)//2]])
        last_r = safe_mean([v for _, v in recent_readiness[-14:]])
        flags["readiness_trend"] = {
            "direccion": trend_direction(last_r, prior_r),
            "ultimos_14_dias": last_r,
            "periodo_previo": prior_r
        }

    # Overtraining risk — readiness < 45 más de 5 días seguidos
    low_readiness_streak = 0
    max_streak = 0
    for _, score in sorted(recent_readiness, key=lambda x: x[0]):
        if score < 45:
            low_readiness_streak += 1
            max_streak = max(max_streak, low_readiness_streak)
        else:
            low_readiness_streak = 0
    flags["overtraining_risk"] = {
        "activo": max_streak >= 5,
        "racha_maxima_dias_bajos": max_streak,
        "umbral": "readiness < 45 durante ≥5 días"
    }

    return flags


# ─── Sección 5: Coherencia objetivo vs datos ────────────────────────────────

def compute_goal_coherence(
    profile: dict,
    ftp_profile: dict,
    readiness_history: list,
    day_baselines: dict
) -> dict:
    """Cruza el objetivo declarado con los datos reales del atleta."""

    coherence = {}
    today = date.today()

    # Extraer datos del perfil
    goal_date_str = profile.get("goal_date")
    goal_event = profile.get("goal_event", profile.get("event_name"))
    goal_target = profile.get("goal_target")  # Ej: "sub 2:45"
    weight_kg = profile.get("weight_kg") or profile.get("weight")
    age = profile.get("age")
    name = profile.get("name") or profile.get("garmin_email", "").split("@")[0]

    ftp_current = (ftp_profile or {}).get("ftp_current")

    # W/kg real
    if ftp_current and weight_kg:
        coherence["ftp_wkg_real"] = {
            "valor": round(ftp_current / weight_kg, 2),
            "ftp_watts": ftp_current,
            "peso_kg": weight_kg
        }
    elif ftp_current:
        coherence["ftp_wkg_real"] = {
            "valor": None,
            "ftp_watts": ftp_current,
            "nota": "Agrega tu peso en el perfil para calcular W/kg"
        }

    # CTL actual (aproximado de readiness y carga)
    # Si no hay ATL/CTL en los datos, estimamos desde readiness y carga física
    ctl_aprox = day_baselines.get("metrics", {}).get("physical_load_score", {}).get("mean")
    if ctl_aprox:
        coherence["ctl_aproximado"] = round(ctl_aprox, 1)

    # Análisis del objetivo si existe goal_date
    if goal_date_str:
        goal_date = parse_date(goal_date_str)
        if goal_date:
            semanas = max(0, (goal_date - today).days // 7)
            coherence["semanas_restantes"] = semanas
            coherence["goal_date"] = goal_date_str
            if goal_event:
                coherence["goal_event"] = goal_event
            if goal_target:
                coherence["goal_target"] = goal_target

            # Fase según semanas restantes (periodización típica)
            if semanas > 16:
                fase = "base"
            elif semanas > 8:
                fase = "construcción"
            elif semanas > 4:
                fase = "pico"
            elif semanas > 1:
                fase = "taper"
            else:
                fase = "competición"
            coherence["fase_actual"] = fase

            # Viabilidad del objetivo (heurística)
            if semanas < 4:
                viable = None  # demasiado cerca para evaluar
                razon = "Insuficientes semanas para cambio significativo de fitness"
            elif ctl_aprox and ctl_aprox < 20 and semanas < 8:
                viable = False
                razon = "CTL actual muy bajo para el tiempo disponible"
            else:
                viable = True
                razon = "Tiempo y base de fitness suficientes para el objetivo"
            coherence["objetivo_viable"] = {"viable": viable, "razon": razon}
    else:
        coherence["nota"] = "Agrega tu objetivo y fecha de evento en el perfil para análisis completo"

    return coherence


# ─── Sección 6: Athlete context string ──────────────────────────────────────

def build_context_string(
    profile: dict,
    baselines: dict,
    patterns: dict,
    flags: dict,
    goal_coherence: dict,
    ftp_profile: dict
) -> str:
    """Genera el string de contexto listo para inyectar en prompts de Claude."""

    parts = []

    # Identidad del atleta
    name = profile.get("name") or profile.get("garmin_email", "").split("@")[0].split("_")[0].capitalize()
    age = profile.get("age")
    weight = profile.get("weight_kg") or profile.get("weight")
    sport = ", ".join(profile.get("sport_focus", ["cycling"]))

    identity_parts = [f"PERFIL: {name}"]
    if age:
        identity_parts.append(f"{age} años")
    if weight:
        identity_parts.append(f"{weight}kg")
    identity_parts.append(f"Deportes: {sport}")
    parts.append(", ".join(identity_parts))

    # Objetivo
    if goal_coherence.get("goal_event") or goal_coherence.get("semanas_restantes") is not None:
        goal_parts = []
        if goal_coherence.get("goal_event"):
            goal_parts.append(f"Objetivo: {goal_coherence['goal_event']}")
        if goal_coherence.get("goal_target"):
            goal_parts.append(goal_coherence["goal_target"])
        if goal_coherence.get("semanas_restantes") is not None:
            sw = goal_coherence["semanas_restantes"]
            fase = goal_coherence.get("fase_actual", "entrenamiento")
            goal_parts.append(f"en {sw} semanas (fase: {fase})")
        if goal_parts:
            parts.append(" ".join(goal_parts))

    # FTP y potencia
    ftp_current = (ftp_profile or {}).get("ftp_current")
    if ftp_current:
        ftp_str = f"FTP real {round(ftp_current)}W"
        wkg = goal_coherence.get("ftp_wkg_real", {}).get("valor")
        if wkg:
            ftp_str += f"/{wkg}wkg"
        ftp_declared = profile.get("ftp")
        if ftp_declared and abs(ftp_declared - ftp_current) > 20:
            ftp_str += f" (declarado {ftp_declared}W — actualizar perfil)"
        parts.append(ftp_str)

    # Baselines reales
    baseline_parts = []
    hrv = baselines.get("hrv_basal", {}).get("mean")
    if hrv:
        baseline_parts.append(f"HRV basal {round(hrv)}ms")
    spo2 = baselines.get("spo2_nadir_basal", {}).get("p25")
    spo2_flag = flags.get("spo2_risk", {}).get("activo", False)
    if spo2:
        spo2_str = f"SpO2 nadir recurrente {round(spo2)}%"
        if spo2_flag:
            spo2_str += " (FLAG ACTIVO)"
        baseline_parts.append(spo2_str)
    rec = baselines.get("recovery_basal", {}).get("mean")
    if rec:
        baseline_parts.append(f"Recovery basal {round(rec)}/100")
    readiness = baselines.get("readiness_basal", {}).get("mean")
    if readiness:
        baseline_parts.append(f"Readiness basal {round(readiness)}/100")
    stress = baselines.get("stress_basal", {}).get("mean")
    if stress:
        baseline_parts.append(f"Estrés basal {round(stress)}/100")

    if baseline_parts:
        parts.append("BASELINES REALES: " + ", ".join(baseline_parts))

    # Patrones
    pattern_parts = []
    mejor_dia = patterns.get("mejor_dia_semana", {}).get("dia")
    peor_dia = patterns.get("peor_dia_semana", {}).get("dia")
    def pluralize_day(dia: str) -> str:
        """Evita 'martess', 'vierneses', etc."""
        if dia.endswith("s"):
            return dia  # lunes, martes, miércoles, jueves, viernes
        return dia + "s"  # sábado→sábados, domingo→domingos

    if mejor_dia and peor_dia:
        pattern_parts.append(f"mejor rendimiento los {pluralize_day(mejor_dia)}, peor los {pluralize_day(peor_dia)}")
    hora = patterns.get("hora_habitual_entreno", {}).get("franja")
    if hora:
        pattern_parts.append(f"entrena habitualmente por la {hora}")
    rec_days = patterns.get("dias_recuperacion_optimos", {}).get("promedio")
    if rec_days:
        pattern_parts.append(f"necesita {rec_days} días entre sesiones intensas")
    patron_sueno = patterns.get("patron_sueno", {}).get("tipo")
    if patron_sueno and patron_sueno not in ("desconocido", "regular"):
        pattern_parts.append(f"cronótipo: {patron_sueno}")

    if pattern_parts:
        parts.append("PATRONES: " + ", ".join(pattern_parts))

    # Flags activos
    active_flags = []
    if spo2_flag:
        active_flags.append("hipoxia nocturna recurrente")
    hrv_trend = flags.get("hrv_trend", {}).get("direccion")
    if hrv_trend == "declining":
        active_flags.append("HRV en declive últimas 2 semanas")
    elif hrv_trend == "improving":
        active_flags.append("HRV en recuperación")
    overtraining = flags.get("overtraining_risk", {}).get("activo", False)
    if overtraining:
        active_flags.append("riesgo de sobreentrenamiento detectado")

    if active_flags:
        parts.append("FLAGS: " + ", ".join(active_flags))

    return ". ".join(parts) + "."


# ─── Motor principal ─────────────────────────────────────────────────────────

def run_profile_intelligence(user_dir: str) -> dict:
    """
    Motor principal. Lee todos los datos disponibles, cruza con el perfil
    y guarda athlete_baseline.json.
    """

    # Paths
    profile_path = os.path.join(user_dir, "profile.json")
    sleep_history_path = os.path.join(user_dir, "sleep_history", "sleep_history.json")
    sleep_baselines_path = os.path.join(user_dir, "sleep_history", "sleep_baselines.json")
    sleep_patterns_path = os.path.join(user_dir, "sleep_history", "sleep_patterns.json")
    day_history_path = os.path.join(user_dir, "day_history", "day_history.json")
    day_baselines_path = os.path.join(user_dir, "day_history", "day_baselines.json")
    readiness_history_path = os.path.join(user_dir, "performance_intelligence", "readiness_history.json")
    ftp_profile_path = os.path.join(user_dir, "performance_intelligence", "ftp_profile.json")
    activity_index_path = os.path.join(user_dir, "activity_index.json")
    output_path = os.path.join(user_dir, "performance_intelligence", "athlete_baseline.json")

    # Cargar datos
    profile = load_json(profile_path) or {}
    sleep_history = load_json(sleep_history_path) or []
    sleep_baselines = load_json(sleep_baselines_path) or {}
    sleep_patterns = load_json(sleep_patterns_path) or {}
    day_baselines = load_json(day_baselines_path) or {}
    readiness_history = load_json(readiness_history_path) or []
    ftp_profile = load_json(ftp_profile_path) or {}
    activity_index_raw = load_json(activity_index_path) or {}
    activity_index = activity_index_raw.get("activities", []) if isinstance(activity_index_raw, dict) else activity_index_raw

    # Validar mínimo de datos
    n_sleep = len(sleep_history)
    n_readiness = len(readiness_history)
    has_enough_data = n_sleep >= 7 or n_readiness >= 7

    if not has_enough_data:
        print(f"  ⚠ Datos insuficientes: {n_sleep} noches de sueño, {n_readiness} días de readiness.")
        print("    Se necesitan ≥7 días para calcular patrones. Guardando baseline parcial.")

    # Calcular todas las secciones
    baselines = compute_physiological_baselines(
        sleep_history, sleep_baselines, day_baselines, readiness_history
    )

    patterns = compute_patterns(
        readiness_history, sleep_history, activity_index, ftp_profile
    ) if has_enough_data else {}

    sustainable_load = compute_sustainable_load(
        activity_index, sleep_history, readiness_history, ftp_profile
    ) if has_enough_data else {}

    health_flags = compute_health_flags(
        sleep_history, sleep_patterns, readiness_history, day_baselines
    ) if n_sleep >= 7 or n_readiness >= 7 else {}

    goal_coherence = compute_goal_coherence(
        profile, ftp_profile, readiness_history, day_baselines
    )

    # String de contexto para Claude
    athlete_context_string = build_context_string(
        profile, baselines, patterns, health_flags, goal_coherence, ftp_profile
    )

    # Ensamblar resultado
    baseline = {
        "generated_at": datetime.now().isoformat(),
        "user_id": profile.get("user_id", os.path.basename(user_dir)),
        "data_window": {
            "sleep_nights": n_sleep,
            "readiness_days": n_readiness,
            "activities": len(activity_index)
        },
        "physiological_baselines": baselines,
        "patterns": patterns,
        "sustainable_load": sustainable_load,
        "health_flags": health_flags,
        "goal_coherence": goal_coherence,
        "athlete_context_string": athlete_context_string
    }

    save_json(output_path, baseline)

    # ── FTP estimado desde datos reales ──────────────────────────────────────
    try:
        from ftp_estimator import estimate_ftp
        ftp_result = estimate_ftp(user_dir)
        if ftp_result:
            ftp_estimated = ftp_result.get("ftp_estimated")
            ftp_declared = profile.get("ftp_watts")

            # Si el perfil no tiene FTP declarado, usar el estimado
            if not ftp_declared and ftp_estimated:
                profile["ftp_watts"] = ftp_estimated
                profile_path_local = os.path.join(user_dir, "profile.json")
                try:
                    save_json(profile_path_local, profile)
                    print(f"  [ftp] Sin FTP declarado -> usando estimado: {ftp_estimated}W")
                except Exception:
                    pass

            # Si existe FTP declarado, comparar con estimado y agregar nota
            elif ftp_declared and ftp_estimated:
                diff = abs(ftp_estimated - ftp_declared)
                if diff > 15:
                    note = (
                        f"NOTA: Tu FTP declarado ({ftp_declared}W) difiere del estimado "
                        f"({ftp_estimated}W) por {diff:.0f}W. "
                        f"{'El estimado es mayor — podrias estar entrenando con zonas conservadoras.' if ftp_estimated > ftp_declared else 'El estimado es menor — revisa si tu FTP declarado sigue vigente.'}"
                    )
                    # Reload from disk to preserve ftp_model section added by update_baseline_with_ftp
                    on_disk = load_json(output_path) or baseline
                    on_disk["ftp_model_note"] = note
                    baseline["ftp_model_note"] = note  # keep in-memory in sync too
                    print(f"  [ftp] Diferencia: declarado={ftp_declared}W vs estimado={ftp_estimated}W ({diff:.0f}W)")
                    save_json(output_path, on_disk)
    except Exception as e:
        print(f"  [ftp_estimator] No se pudo estimar FTP: {e}")

    # ── Resumen en consola ──
    hrv_mean = baselines.get("hrv_basal", {}).get("mean", "N/D")
    rec_mean = baselines.get("recovery_basal", {}).get("mean", "N/D")
    spo2_flag = health_flags.get("spo2_risk", {}).get("activo", False)
    semanas = goal_coherence.get("semanas_restantes", "N/D")
    ftp_val = ftp_profile.get("ftp_current", "N/D")
    hrv_trend = health_flags.get("hrv_trend", {}).get("direccion", "?")
    readiness_mean = baselines.get("readiness_basal", {}).get("mean", "N/D")

    ftp_estimated_val = baseline.get("ftp_model_note", None)
    ftp_estimate_path = os.path.join(user_dir, "performance_intelligence", "ftp_estimate.json")
    ftp_est_data = load_json(ftp_estimate_path) or {}
    ftp_estimated_w = ftp_est_data.get("ftp_estimated")

    print(f"\n{'='*60}")
    print(f"ATHLETE BASELINE GENERADO")
    print(f"{'='*60}")
    print(f"  HRV basal:       {hrv_mean} ms")
    print(f"  Recovery basal:  {rec_mean} /100")
    print(f"  Readiness:       {readiness_mean} /100")
    print(f"  FTP declarado:   {ftp_val} W")
    if ftp_estimated_w:
        print(f"  FTP estimado:    {ftp_estimated_w} W")
    print(f"  SpO2 flag:       {'SI' if spo2_flag else 'NO'}")
    print(f"  HRV tendencia:   {hrv_trend}")
    if semanas != "N/D":
        print(f"  Semanas evento:  {semanas}")
    if ftp_estimated_val:
        print(f"  Nota FTP:        {ftp_estimated_val}")
    print(f"  Guardado en:     {output_path}")
    print(f"{'='*60}\n")

    return baseline


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Profile Intelligence Engine")
    parser.add_argument(
        "--user_dir",
        type=str,
        default=None,
        help="Directorio del usuario (ej: data/users/abelgcanofuentes_at_hotmail_com)"
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Email Garmin del usuario (alternativo a --user_dir)"
    )
    args = parser.parse_args()

    if args.user_dir:
        user_dir = args.user_dir
    elif args.email:
        clean = args.email.strip().lower().replace("@", "_at_").replace(".", "_")
        user_dir = os.path.join("data", "users", clean)
    else:
        # Default: Abel para pruebas
        user_dir = os.path.join("data", "users", "abelgcanofuentes_at_hotmail_com")

    if not os.path.exists(user_dir):
        print(f"ERROR: Directorio no encontrado: {user_dir}")
        exit(1)

    print(f"Generando baseline para: {user_dir}")
    result = run_profile_intelligence(user_dir)
