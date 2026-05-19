"""
db.py
=====
Módulo central de base de datos para Apex Garmin AI.
Maneja la conexión a PostgreSQL y los upserts de cada tipo de dato.

Uso en otros scripts:
    from db import get_conn, upsert_sleep, upsert_day, upsert_activity, ensure_user

Configuración: crea db_config.json con:
    {"dsn": "postgresql://user:password@localhost:5432/apexgarmin"}
"""

import json
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import date as date_type

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "db_config.json")

# ── Conexión ─────────────────────────────────────────────────

def _load_dsn() -> str:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            return json.load(f)["dsn"]
    dsn = os.environ.get("APEX_DB_DSN")
    if dsn:
        return dsn
    raise RuntimeError("No se encontró db_config.json ni la variable APEX_DB_DSN")

def get_conn():
    """Retorna una conexión psycopg2. El llamador es responsable de cerrarla."""
    return psycopg2.connect(_load_dsn())

@contextmanager
def db_cursor():
    """Context manager: abre conexión, da cursor, hace commit o rollback automático."""
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()

# ── Usuarios ─────────────────────────────────────────────────

def ensure_user(email: str) -> int:
    """
    Crea el usuario si no existe y retorna su id.
    email_key = email con @ → _at_ y . → _
    """
    email      = email.strip().lower()
    email_key  = email.replace("@", "_at_").replace(".", "_")
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO users (email, email_key)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET updated_at = NOW()
            RETURNING id
        """, (email, email_key))
        return cur.fetchone()[0]

def get_user_id(email: str) -> int | None:
    """Retorna el id del usuario o None si no existe."""
    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (email.strip().lower(),))
        row = cur.fetchone()
        return row[0] if row else None

# ── Sleep ────────────────────────────────────────────────────

def upsert_sleep(user_id: int, sleep_date: str,
                 analysis: dict | None = None,
                 brief: dict | None = None,
                 brief_ai: dict | None = None) -> None:
    """
    Inserta o actualiza un registro de sueño.
    Extrae los campos clave del analysis dict y guarda los 3 JSONs completos.
    Si un JSON es None, no sobreescribe el que ya hay en DB.
    """
    a   = analysis or {}
    rs  = a.get("recovery_summary",  {}) or {}
    sa  = a.get("sleep_architecture", {}) or {}
    sw  = a.get("sleep_window",       {}) or {}
    cr  = a.get("cardiac_recovery",   {}) or {}
    ar  = a.get("autonomic_recovery", {}) or {}
    sr  = a.get("stress_recovery",    {}) or {}
    rr  = a.get("respiratory_recovery", {}) or {}
    ox  = a.get("oxygenation",        {}) or {}
    er  = a.get("energy_recharge",    {}) or {}
    ca  = a.get("circadian_alignment", {}) or {}
    im  = a.get("instability_markers", {}) or {}
    sn  = a.get("sleep_need",         {}) or {}

    # limitantes del brief (non-AI)
    primary_limiter   = (brief or {}).get("primary_limiter")
    secondary_limiter = (brief or {}).get("secondary_limiter")
    headline          = (brief or {}).get("headline") or (brief_ai or {}).get("hero", {}).get("headline")

    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO sleep_daily (
                user_id, date,
                overall_recovery_score, physical_recovery_score, neural_recovery_score,
                sleep_time_seconds, sleep_efficiency,
                deep_ratio, rem_ratio, light_ratio, awake_ratio,
                fragmentation_index, movement_index,
                micro_arousal_score, overnight_instability_score,
                architecture_stability_score, movement_spike_count, stage_transition_count,
                avg_sleep_hr, resting_hr,
                avg_overnight_hrv, hrv_recovery_score, hrv_ramp_score,
                hrv_first_half, hrv_second_half, autonomic_recovery_curve_score,
                avg_sleep_stress, stress_load_score, stress_spike_count,
                avg_respiration, respiration_variability,
                respiratory_stability_score, respiratory_irregularity_score,
                avg_spo2, min_spo2, oxygen_stability_score, spo2_drop_count,
                body_battery_start, body_battery_end, body_battery_change,
                recharge_efficiency, body_battery_recharge_velocity,
                circadian_alignment_score, sleep_midpoint_minutes, sleep_need_gap_minutes,
                primary_limiter, secondary_limiter, headline,
                analysis_json, brief_json, brief_ai_json
            ) VALUES (
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (user_id, date) DO UPDATE SET
                overall_recovery_score      = COALESCE(EXCLUDED.overall_recovery_score,      sleep_daily.overall_recovery_score),
                physical_recovery_score     = COALESCE(EXCLUDED.physical_recovery_score,     sleep_daily.physical_recovery_score),
                neural_recovery_score       = COALESCE(EXCLUDED.neural_recovery_score,       sleep_daily.neural_recovery_score),
                sleep_time_seconds          = COALESCE(EXCLUDED.sleep_time_seconds,          sleep_daily.sleep_time_seconds),
                sleep_efficiency            = COALESCE(EXCLUDED.sleep_efficiency,            sleep_daily.sleep_efficiency),
                deep_ratio                  = COALESCE(EXCLUDED.deep_ratio,                  sleep_daily.deep_ratio),
                rem_ratio                   = COALESCE(EXCLUDED.rem_ratio,                   sleep_daily.rem_ratio),
                light_ratio                 = COALESCE(EXCLUDED.light_ratio,                 sleep_daily.light_ratio),
                awake_ratio                 = COALESCE(EXCLUDED.awake_ratio,                 sleep_daily.awake_ratio),
                fragmentation_index         = COALESCE(EXCLUDED.fragmentation_index,         sleep_daily.fragmentation_index),
                avg_overnight_hrv           = COALESCE(EXCLUDED.avg_overnight_hrv,           sleep_daily.avg_overnight_hrv),
                avg_spo2                    = COALESCE(EXCLUDED.avg_spo2,                    sleep_daily.avg_spo2),
                min_spo2                    = COALESCE(EXCLUDED.min_spo2,                    sleep_daily.min_spo2),
                body_battery_start          = COALESCE(EXCLUDED.body_battery_start,          sleep_daily.body_battery_start),
                body_battery_end            = COALESCE(EXCLUDED.body_battery_end,            sleep_daily.body_battery_end),
                body_battery_change         = COALESCE(EXCLUDED.body_battery_change,         sleep_daily.body_battery_change),
                recharge_efficiency         = COALESCE(EXCLUDED.recharge_efficiency,         sleep_daily.recharge_efficiency),
                circadian_alignment_score   = COALESCE(EXCLUDED.circadian_alignment_score,   sleep_daily.circadian_alignment_score),
                sleep_need_gap_minutes      = COALESCE(EXCLUDED.sleep_need_gap_minutes,      sleep_daily.sleep_need_gap_minutes),
                primary_limiter             = COALESCE(EXCLUDED.primary_limiter,             sleep_daily.primary_limiter),
                secondary_limiter           = COALESCE(EXCLUDED.secondary_limiter,           sleep_daily.secondary_limiter),
                headline                    = COALESCE(EXCLUDED.headline,                    sleep_daily.headline),
                analysis_json               = COALESCE(EXCLUDED.analysis_json,               sleep_daily.analysis_json),
                brief_json                  = COALESCE(EXCLUDED.brief_json,                  sleep_daily.brief_json),
                brief_ai_json               = COALESCE(EXCLUDED.brief_ai_json,               sleep_daily.brief_ai_json),
                updated_at                  = NOW()
        """, (
            user_id, sleep_date,
            _f(rs.get("overall_recovery_score")),
            _f(rs.get("physical_recovery_score")),
            _f(rs.get("neural_recovery_score")),
            _i(sw.get("sleep_time_seconds")),
            _f(sw.get("sleep_efficiency")),
            _f(sa.get("deep_ratio")), _f(sa.get("rem_ratio")),
            _f(sa.get("light_ratio")), _f(sa.get("awake_ratio")),
            _f(sa.get("fragmentation_index")), _f(sa.get("movement_index")),
            _f(im.get("micro_arousal_score")), _f(im.get("overnight_instability_score")),
            _f(sa.get("architecture_stability_score")),
            _i(im.get("movement_spike_count")), _i(sa.get("stage_transition_count")),
            _f(cr.get("avg_sleep_hr")), _f(cr.get("resting_hr")),
            _f(ar.get("avg_overnight_hrv")), _f(ar.get("hrv_recovery_score")),
            _f(ar.get("hrv_ramp_score")), _f(ar.get("hrv_first_half")),
            _f(ar.get("hrv_second_half")), _f(ar.get("autonomic_recovery_curve_score")),
            _f(sr.get("avg_sleep_stress")), _f(sr.get("stress_load_score")),
            _i(sr.get("stress_spike_count")),
            _f(rr.get("avg_respiration")), _f(rr.get("respiration_variability")),
            _f(rr.get("respiratory_stability_score")), _f(rr.get("respiratory_irregularity_score")),
            _f(ox.get("avg_spo2")), _f(ox.get("min_spo2")),
            _f(ox.get("oxygen_stability_score")), _i(ox.get("spo2_drop_count")),
            _f(er.get("body_battery_start")), _f(er.get("body_battery_end")),
            _f(er.get("body_battery_change")), _f(er.get("recharge_efficiency")),
            _f(er.get("body_battery_recharge_velocity")),
            _f(ca.get("circadian_alignment_score")), _f(ca.get("sleep_midpoint_minutes")),
            _i(sn.get("sleep_need_gap_minutes")),
            primary_limiter, secondary_limiter, headline,
            _json(analysis), _json(brief), _json(brief_ai),
        ))


def upsert_sleep_from_history_row(user_id: int, row: dict) -> None:
    """Upsert desde una fila del sleep_history.json (campos planos)."""
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO sleep_daily (
                user_id, date,
                overall_recovery_score, physical_recovery_score, neural_recovery_score,
                avg_overnight_hrv, hrv_recovery_score, hrv_ramp_score,
                hrv_first_half, hrv_second_half, autonomic_recovery_curve_score,
                sleep_efficiency, sleep_time_seconds,
                deep_ratio, rem_ratio, fragmentation_index, movement_index,
                stage_transition_count, architecture_stability_score,
                avg_sleep_stress, stress_load_score, stress_spike_count,
                avg_respiration, respiration_variability,
                respiratory_stability_score, respiratory_irregularity_score,
                avg_spo2, min_spo2, oxygen_stability_score, spo2_drop_count,
                recharge_efficiency, body_battery_change, body_battery_recharge_velocity,
                circadian_alignment_score, sleep_midpoint_minutes, sleep_need_gap_minutes,
                micro_arousal_score, overnight_instability_score, movement_spike_count,
                primary_limiter, secondary_limiter, headline
            ) VALUES (
                %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (user_id, date) DO UPDATE SET
                overall_recovery_score = COALESCE(EXCLUDED.overall_recovery_score, sleep_daily.overall_recovery_score),
                avg_overnight_hrv      = COALESCE(EXCLUDED.avg_overnight_hrv,      sleep_daily.avg_overnight_hrv),
                deep_ratio             = COALESCE(EXCLUDED.deep_ratio,             sleep_daily.deep_ratio),
                rem_ratio              = COALESCE(EXCLUDED.rem_ratio,              sleep_daily.rem_ratio),
                recharge_efficiency    = COALESCE(EXCLUDED.recharge_efficiency,    sleep_daily.recharge_efficiency),
                primary_limiter        = COALESCE(EXCLUDED.primary_limiter,        sleep_daily.primary_limiter),
                secondary_limiter      = COALESCE(EXCLUDED.secondary_limiter,      sleep_daily.secondary_limiter),
                updated_at             = NOW()
        """, (
            user_id, row["calendar_date"],
            _f(row.get("overall_recovery_score")),
            _f(row.get("physical_recovery_score")),
            _f(row.get("neural_recovery_score")),
            _f(row.get("avg_overnight_hrv")),
            _f(row.get("hrv_recovery_score")),
            _f(row.get("hrv_ramp_score")),
            _f(row.get("hrv_first_half")),
            _f(row.get("hrv_second_half")),
            _f(row.get("autonomic_recovery_curve_score")),
            _f(row.get("sleep_efficiency")),
            _i(row.get("sleep_time_seconds")),
            _f(row.get("deep_ratio")),
            _f(row.get("rem_ratio")),
            _f(row.get("fragmentation_index")),
            _f(row.get("movement_index")),
            _i(row.get("stage_transition_count")),
            _f(row.get("architecture_stability_score")),
            _f(row.get("avg_sleep_stress")),
            _f(row.get("stress_load_score")),
            _i(row.get("stress_spike_count")),
            _f(row.get("avg_respiration")),
            _f(row.get("respiration_variability")),
            _f(row.get("respiratory_stability_score")),
            _f(row.get("respiratory_irregularity_score")),
            _f(row.get("avg_spo2")),
            _f(row.get("min_spo2")),
            _f(row.get("oxygen_stability_score")),
            _i(row.get("spo2_drop_count")),
            _f(row.get("recharge_efficiency")),
            _f(row.get("body_battery_change")),
            _f(row.get("body_battery_recharge_velocity")),
            _f(row.get("circadian_alignment_score")),
            _f(row.get("sleep_midpoint_minutes")),
            _i(row.get("sleep_need_gap_minutes")),
            _f(row.get("micro_arousal_score")),
            _f(row.get("overnight_instability_score")),
            _i(row.get("movement_spike_count")),
            row.get("primary_limiter"),
            row.get("secondary_limiter"),
            row.get("headline"),
        ))


# ── Day ──────────────────────────────────────────────────────

def upsert_day_from_history_row(user_id: int, row: dict) -> None:
    """Upsert desde una fila del day_history.json."""
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO day_daily (
                user_id, date,
                overall_day_state_score, system_strain_score, day_capacity_score,
                nervous_system_load_score, energy_dynamics_score, physical_load_score,
                avg_day_hr, max_hr, hr_variability, avg_hrv,
                avg_stress, max_stress, stress_spike_count, high_stress_count, high_stress_ratio,
                body_battery_change, body_battery_slope, recharge_events, crash_events,
                steps, intensity_minutes, active_calories,
                recovery_response_score, downshift_count, downshift_ratio,
                avg_respiration, respiration_variability,
                atl, ctl, tsb, tsb_label,
                primary_limiter, secondary_limiter, headline
            ) VALUES (
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (user_id, date) DO UPDATE SET
                overall_day_state_score = COALESCE(EXCLUDED.overall_day_state_score, day_daily.overall_day_state_score),
                steps                   = COALESCE(EXCLUDED.steps,                   day_daily.steps),
                avg_stress              = COALESCE(EXCLUDED.avg_stress,              day_daily.avg_stress),
                body_battery_change     = COALESCE(EXCLUDED.body_battery_change,     day_daily.body_battery_change),
                atl                     = COALESCE(EXCLUDED.atl,                     day_daily.atl),
                ctl                     = COALESCE(EXCLUDED.ctl,                     day_daily.ctl),
                tsb                     = COALESCE(EXCLUDED.tsb,                     day_daily.tsb),
                primary_limiter         = COALESCE(EXCLUDED.primary_limiter,         day_daily.primary_limiter),
                updated_at              = NOW()
        """, (
            user_id, row["calendar_date"],
            _f(row.get("overall_day_state_score")),
            _f(row.get("system_strain_score")),
            _f(row.get("day_capacity_score")),
            _f(row.get("nervous_system_load_score")),
            _f(row.get("energy_dynamics_score")),
            _f(row.get("physical_load_score")),
            _f(row.get("avg_day_hr")),
            _f(row.get("max_hr")),
            _f(row.get("hr_variability")),
            _f(row.get("avg_hrv")),
            _f(row.get("avg_stress")),
            _f(row.get("max_stress")),
            _i(row.get("stress_spike_count")),
            _i(row.get("high_stress_count")),
            _f(row.get("high_stress_ratio")),
            _f(row.get("body_battery_change")),
            _f(row.get("body_battery_slope")),
            _i(row.get("recharge_events")),
            _i(row.get("crash_events")),
            _i(row.get("steps")),
            _f(row.get("intensity_minutes")),
            _f(row.get("active_calories")),
            _f(row.get("recovery_response_score")),
            _i(row.get("downshift_count")),
            _f(row.get("downshift_ratio")),
            _f(row.get("avg_respiration")),
            _f(row.get("respiration_variability")),
            _f(row.get("atl")),
            _f(row.get("ctl")),
            _f(row.get("tsb")),
            row.get("tsb_label"),
            row.get("primary_limiter"),
            row.get("secondary_limiter"),
            row.get("headline") or "",
        ))


def upsert_day(user_id: int, day_date: str,
               analysis: dict | None = None,
               brief_ai: dict | None = None) -> None:
    """Upsert día con analysis completo."""
    a   = analysis or {}
    rs  = a.get("recovery_summary",    {}) or {}
    ed  = a.get("energy_dynamics",     {}) or {}
    nsl = a.get("nervous_system_load", {}) or {}
    pl  = a.get("physical_load",       {}) or {}
    dq  = a.get("data_quality",        {}) or {}

    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO day_daily (user_id, date,
                overall_day_state_score, body_battery_start, body_battery_end,
                body_battery_change, avg_stress, avg_day_hr, steps, intensity_minutes,
                primary_limiter, analysis_json, brief_ai_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id, date) DO UPDATE SET
                overall_day_state_score = COALESCE(EXCLUDED.overall_day_state_score, day_daily.overall_day_state_score),
                analysis_json           = COALESCE(EXCLUDED.analysis_json,           day_daily.analysis_json),
                brief_ai_json           = COALESCE(EXCLUDED.brief_ai_json,           day_daily.brief_ai_json),
                updated_at              = NOW()
        """, (
            user_id, day_date,
            _f(rs.get("overall_day_state_score")),
            _f(ed.get("body_battery_start")),
            _f(ed.get("body_battery_end")),
            _f(ed.get("body_battery_change")),
            _f(nsl.get("avg_stress")),
            _f(nsl.get("avg_hr")),
            _i(pl.get("steps")),
            _f(pl.get("intensity_minutes")),
            rs.get("primary_limiter"),
            _json(analysis),
            _json(brief_ai),
        ))


# ── Activities ───────────────────────────────────────────────

def upsert_activity(user_id: int,
                    analysis: dict | None = None,
                    brief: dict | None = None) -> None:
    """Upsert actividad desde analysis + brief JSONs."""
    a  = analysis or {}
    gs = a.get("garmin_summary",  {}) or {}
    ds = a.get("derived_summary", {}) or {}
    qb = ((brief or {}).get("phase_1_quick_insight") or
          (brief or {}).get("quick_brief") or {})
    score_obj = qb.get("overall_score") or {}

    garmin_id = gs.get("activity_id") or a.get("activity_id")
    if not garmin_id:
        return

    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO activities (
                user_id, garmin_activity_id, name, activity_type, start_date,
                distance_km, elevation_m, moving_minutes, elapsed_minutes, calories,
                avg_hr, max_hr,
                avg_power, estimated_np, garmin_np,
                estimated_tss, garmin_tss,
                aerobic_te, anaerobic_te, vo2max,
                overall_score, score_label,
                analysis_json, brief_json
            ) VALUES (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,
                %s,%s,%s,
                %s,%s,
                %s,%s,%s,
                %s,%s,
                %s,%s
            )
            ON CONFLICT (garmin_activity_id) DO UPDATE SET
                name          = COALESCE(EXCLUDED.name,          activities.name),
                overall_score = COALESCE(EXCLUDED.overall_score, activities.overall_score),
                score_label   = COALESCE(EXCLUDED.score_label,   activities.score_label),
                analysis_json = COALESCE(EXCLUDED.analysis_json, activities.analysis_json),
                brief_json    = COALESCE(EXCLUDED.brief_json,    activities.brief_json),
                updated_at    = NOW()
        """, (
            user_id, int(garmin_id),
            gs.get("name"),
            gs.get("type"),
            (gs.get("start_date") or "")[:10] or None,
            _f(gs.get("distance_km")),
            _f(gs.get("elevation_m")),
            _f(gs.get("moving_minutes")),
            _f(gs.get("elapsed_minutes")),
            _i(gs.get("calories")),
            _f(gs.get("avg_hr") or ds.get("avg_hr")),
            _f(gs.get("max_hr") or ds.get("max_hr")),
            _f(gs.get("avg_power") or ds.get("avg_power")),
            _f(ds.get("estimated_np")),
            _f(gs.get("garmin_np")),
            _f(ds.get("estimated_tss")),
            _f(gs.get("garmin_tss")),
            _f(gs.get("aerobic_te")),
            _f(gs.get("anaerobic_te")),
            _f(gs.get("vo2max")),
            _f(score_obj.get("score")),
            score_obj.get("label"),
            _json(analysis),
            _json(brief),
        ))


# ── Helpers internos ─────────────────────────────────────────

def _f(v) -> float | None:
    """Convierte a float o None."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None

def _i(v) -> int | None:
    """Convierte a int o None."""
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None

def _json(v) -> str | None:
    """Convierte dict a JSON string para psycopg2, o None."""
    if v is None:
        return None
    return psycopg2.extras.Json(v)
