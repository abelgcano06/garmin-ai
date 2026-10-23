"""
apex_tools.py
=============
Capa de consulta de Apex por usuario. La usan el conector MCP (apex_mcp.py) y
cualquier otro canal (app web, artifact). Lee lo que ya calcularon los motores
(sleep_engine, day_engine, activity_analyzer, master_engine, ftp_engine) en
data/users/<user_id>/ y lo regresa en dicts compactos y legibles.

No llama a Garmin salvo `sincronizar`, que corre el sync completo en segundo plano.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "data", "users")

_sync_state: dict[str, dict] = {}
_sync_lock = threading.Lock()
# Los motores usan un "usuario actual" global (app_context): un sync a la vez.
_run_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def user_dir(user_id: str) -> str:
    return os.path.join(USERS_DIR, user_id)


def _load(path: str, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _today() -> str:
    return date.today().isoformat()


def _pi(user_id: str, name: str, default: Any = None) -> Any:
    return _load(os.path.join(user_dir(user_id), "performance_intelligence", name), default)


def _dated_dirs(user_id: str, kind: str) -> list[str]:
    root = os.path.join(user_dir(user_id), kind)
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if len(d) == 10 and d[4] == "-")


def _has_sleep(analysis: dict | None) -> bool:
    return bool(analysis and (analysis.get("sleep_window") or {}).get("sleep_time_seconds"))


def _strip(d: dict | None, drop: tuple = ()) -> dict:
    return {k: v for k, v in (d or {}).items() if k not in drop}


def _findings(items: list | None, limit: int = 8) -> list:
    out = []
    for f in (items or [])[:limit]:
        out.append({k: f.get(k) for k in ("title", "summary", "description", "severity", "signal", "code", "evidence") if f.get(k) is not None})
    return out


def _round(x, n=1):
    return round(x, n) if isinstance(x, (int, float)) else x


# ─────────────────────────────────────────────────────────────────────────────
# Perfil
# ─────────────────────────────────────────────────────────────────────────────

def perfil(user_id: str) -> dict:
    p = _load(os.path.join(user_dir(user_id), "profile.json"), {}) or {}
    ftp = _pi(user_id, "ftp_profile.json", {}) or {}
    return {
        "nombre": (p.get("name") or "").strip(),
        "enfoque": p.get("sport_focus"),
        "edad": p.get("age"), "peso_kg": p.get("weight_kg"), "estatura_cm": p.get("height_cm"),
        "fc_max": p.get("max_hr"),
        "ftp_declarado": p.get("ftp"),
        "ftp_apex": ftp.get("ftp_current") or p.get("ftp_apex"),
        "ftp_metodo": ftp.get("ftp_method"),
        "w_kg": round(ftp["ftp_current"] / p["weight_kg"], 2) if ftp.get("ftp_current") and p.get("weight_kg") else None,
        "horas_semana": p.get("weekly_hours_available"),
        "objetivo": p.get("goal_event"), "fecha_objetivo": p.get("goal_date"),
        "dias_al_objetivo": (date.fromisoformat(p["goal_date"]) - date.today()).days if p.get("goal_date") else None,
    }


_PROFILE_FIELDS = {
    "nombre": "name", "peso_kg": "weight_kg", "estatura_cm": "height_cm", "edad": "age",
    "ftp": "ftp", "fc_max": "max_hr", "horas_semana": "weekly_hours_available",
    "objetivo": "goal_event", "fecha_objetivo": "goal_date", "anios_experiencia": "experience_years",
}


def actualizar_perfil(user_id: str, **cambios) -> dict:
    """Actualiza el perfil del atleta (solo los campos que vienen con valor)."""
    path = os.path.join(user_dir(user_id), "profile.json")
    p = _load(path, {}) or {}
    for k, v in cambios.items():
        if v is None or k not in _PROFILE_FIELDS:
            continue
        if k == "fecha_objetivo":
            date.fromisoformat(str(v))  # valida YYYY-MM-DD
        p[_PROFILE_FIELDS[k]] = v
    os.makedirs(user_dir(user_id), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(p, fh, ensure_ascii=False, indent=2)
    return {"ok": True, "perfil": perfil(user_id)}


# ─────────────────────────────────────────────────────────────────────────────
# Hoy
# ─────────────────────────────────────────────────────────────────────────────

def hoy(user_id: str) -> dict:
    """Readiness del día, recomendación, limitantes, carga y la última noche/día con datos."""
    brief = _pi(user_id, "master_brief.json", {}) or {}
    hist = _pi(user_id, "readiness_history.json", []) or []
    last_sleep = ultima_noche(user_id, resumen=True)
    return {
        "fecha": _today(),
        "readiness": {
            "fecha_calculo": brief.get("calendar_date"),
            "score": _round(brief.get("readiness_score")),
            "nivel": brief.get("readiness_label"),
            "recomendacion": brief.get("recommendation"),
            "limitante_principal": brief.get("primary_limiter"),
            "limitante_secundario": brief.get("secondary_limiter"),
            "proyeccion_actividad": brief.get("activity_projection"),
            "penalizaciones": brief.get("penalty_notes"),
            "alertas": {k: v for k, v in (brief.get("risk_flags") or {}).items() if v},
            "componentes": brief.get("contributing_scores"),
            "pesos": brief.get("dynamic_weights"),
        },
        "readiness_7_dias": [{"fecha": r.get("calendar_date"), "score": _round(r.get("readiness_score")),
                              "sueno": _round(r.get("sleep_score")), "dia": _round(r.get("day_score"))}
                             for r in hist[-7:]],
        "ultima_noche": last_sleep,
        "carga": carga(user_id, resumen=True),
        "perfil": perfil(user_id),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sueño
# ─────────────────────────────────────────────────────────────────────────────

def ultima_noche(user_id: str, resumen: bool = False) -> dict | None:
    for d in reversed(_dated_dirs(user_id, "sleep")):
        a = _load(os.path.join(user_dir(user_id), "sleep", d, "sleep_analysis.json"))
        if _has_sleep(a):
            return sueno(user_id, d, resumen=resumen)
    return None


def sueno(user_id: str, fecha: str | None = None, resumen: bool = False) -> dict:
    """Análisis Apex de la noche que terminó en `fecha` (mañana en que despertaste)."""
    if not fecha:
        last = ultima_noche(user_id, resumen=resumen)
        return last or {"error": "No hay noches con datos todavía. Corre sincronizar."}
    base = os.path.join(user_dir(user_id), "sleep", fecha)
    a = _load(os.path.join(base, "sleep_analysis.json"))
    if not _has_sleep(a):
        return {"fecha": fecha, "sin_datos": True, "nota": "Garmin no registró sueño esa noche (reloj sin usar o sin sincronizar)."}
    f = _load(os.path.join(base, "sleep_findings.json"), {}) or {}
    out = {
        "fecha": fecha,
        "recuperacion": a.get("recovery_summary"),
        "ventana": a.get("sleep_window"),
        "arquitectura": a.get("sleep_architecture"),
        "hallazgos": _findings(f.get("findings"), 5 if resumen else 10),
        "limitantes": f.get("limiters") or a.get("limiters"),
    }
    if not resumen:
        out["analisis_completo"] = _strip(a, ("calendar_date", "sleep_window", "sleep_architecture", "recovery_summary"))
        brief = _load(os.path.join(base, "sleep_brief.json"))
        if brief:
            out["brief"] = brief
    return out


def tendencia_sueno(user_id: str, dias: int = 14) -> list:
    out = []
    for d in _dated_dirs(user_id, "sleep")[-dias:]:
        a = _load(os.path.join(user_dir(user_id), "sleep", d, "sleep_analysis.json"))
        if not _has_sleep(a):
            out.append({"fecha": d, "sin_datos": True})
            continue
        w, ar, r = a.get("sleep_window") or {}, a.get("sleep_architecture") or {}, a.get("recovery_summary") or {}
        out.append({"fecha": d, "horas": round((w.get("sleep_time_seconds") or 0) / 3600, 2),
                    "recuperacion": _round(r.get("overall_recovery_score")),
                    "profundo_pct": _round((ar.get("deep_ratio") or 0) * 100), "rem_pct": _round((ar.get("rem_ratio") or 0) * 100),
                    "despertares": ar.get("awake_count")})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Día
# ─────────────────────────────────────────────────────────────────────────────

def dia(user_id: str, fecha: str | None = None) -> dict:
    """Análisis Apex del día: energía, estrés, carga física/cognitiva, recuperación intradía."""
    fecha = fecha or (_dated_dirs(user_id, "day") or [_today()])[-1]
    base = os.path.join(user_dir(user_id), "day", fecha)
    a = _load(os.path.join(base, "day_analysis.json"))
    if not a:
        return {"fecha": fecha, "sin_datos": True}
    f = _load(os.path.join(base, "day_findings.json"), {}) or {}
    return {
        "fecha": fecha,
        "estado": a.get("recovery_summary"),
        "hallazgos": _findings(f.get("findings")),
        "limitantes": f.get("limiters"),
        "banderas": {k: v for k, v in (f.get("flags") or {}).items() if v},
        "analisis_completo": _strip(a, ("calendar_date", "recovery_summary")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Carga
# ─────────────────────────────────────────────────────────────────────────────

def _activities(user_id: str) -> list:
    idx = _load(os.path.join(user_dir(user_id), "activity_index.json"), {}) or {}
    acts = idx.get("activities") or []
    return sorted(acts, key=lambda a: a.get("date") or "", reverse=True)


def _tss(a: dict) -> float:
    for k in ("garmin_tss", "tss", "estimated_tss"):
        if isinstance(a.get(k), (int, float)):
            return float(a[k])
    an = _load(_abs(a.get("analysis_file")), {}) or {}
    ds = an.get("derived_summary") or {}
    gs = an.get("garmin_summary") or {}
    v = gs.get("garmin_tss") or gs.get("tss") or ds.get("estimated_tss")
    return float(v) if isinstance(v, (int, float)) else 0.0


def _abs(p: str | None) -> str:
    if not p:
        return ""
    p = p.replace("\\", "/")
    return p if os.path.isabs(p) else os.path.join(BASE_DIR, p)


def pmc(user_id: str, dias: int = 120) -> list:
    """CTL (42 d) / ATL (7 d) / TSB por día, con promedios exponenciales estándar."""
    tss: dict[str, float] = {}
    for a in _activities(user_id):
        d = (a.get("date") or "")[:10]
        if d:
            tss[d] = tss.get(d, 0.0) + _tss(a)
    start = date.today() - timedelta(days=dias + 41)
    ctl = atl = 0.0
    out = []
    for i in range(dias + 42):
        d = (start + timedelta(days=i)).isoformat()
        v = tss.get(d, 0.0)
        ctl += (v - ctl) / 42
        atl += (v - atl) / 7
        if i >= 42:
            out.append({"fecha": d, "tss": round(v), "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(ctl - atl, 1)})
    return out


def carga(user_id: str, resumen: bool = False) -> dict:
    p = pmc(user_id, 120)
    if not p:
        return {"sin_datos": True}
    last, wk_ago, m_ago = p[-1], p[-8], p[-29]
    tsb = last["tsb"]
    out = {
        "ctl_forma": last["ctl"], "atl_fatiga": last["atl"], "tsb_frescura": tsb,
        "estado": "fresco" if tsb > 10 else "neutro" if tsb >= -10 else "cargado" if tsb >= -20 else "fatigado",
        "ramp_rate_semana": round(last["ctl"] - wk_ago["ctl"], 1),
        "ctl_vs_hace_4_semanas": round(last["ctl"] - m_ago["ctl"], 1),
        "tss_7_dias": sum(x["tss"] for x in p[-7:]),
        "tss_semana_previa": sum(x["tss"] for x in p[-14:-7]),
    }
    if not resumen:
        ftp = _pi(user_id, "ftp_profile.json", {}) or {}
        out["ftp"] = {k: ftp.get(k) for k in ("ftp_current", "ftp_method", "ftp_confidence", "has_power_meter", "power_activity_count")}
        out["curva_potencia_mejor"] = ftp.get("power_curve_best")
        out["pmc_28_dias"] = p[-28:]
        weeks = []
        for w in range(11, -1, -1):
            chunk = p[len(p) - 7 * (w + 1): len(p) - 7 * w] if w else p[-7:]
            if chunk:
                weeks.append({"semana_desde": chunk[0]["fecha"], "tss": sum(x["tss"] for x in chunk)})
        out["tss_por_semana"] = weeks
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Actividades
# ─────────────────────────────────────────────────────────────────────────────

def _notes_path(user_id: str) -> str:
    return os.path.join(user_dir(user_id), "notes.json")


def _notes(user_id: str) -> dict:
    return _load(_notes_path(user_id), {}) or {}


def actividades(user_id: str, desde: str | None = None, hasta: str | None = None,
                tipo: str | None = None, etiqueta: str | None = None, limite: int = 20) -> list:
    notes = _notes(user_id)
    out = []
    for a in _activities(user_id):
        d = (a.get("date") or "")[:10]
        if desde and d < desde or hasta and d > hasta:
            continue
        if tipo and a.get("type") != tipo:
            continue
        n = notes.get(str(a.get("activity_id")), {})
        if etiqueta and n.get("etiqueta") != etiqueta:
            continue
        out.append({
            "id": a.get("activity_id"), "fecha": a.get("date"), "nombre": a.get("name"), "tipo": a.get("type"),
            "km": a.get("distance_km"), "min": a.get("moving_minutes"), "desnivel_m": a.get("elevation_m"),
            "fc": a.get("avg_hr"), "pot_media": a.get("avg_power"), "np": a.get("garmin_np") or a.get("estimated_np"),
            "vi": a.get("vi"), "tss": round(_tss(a)), "clasificacion": a.get("ride_classification"),
            "limitante": a.get("primary_limiter"), "etiqueta": n.get("etiqueta"), "rpe": n.get("rpe"),
        })
        if len(out) >= limite:
            break
    return out


def actividad(user_id: str, activity_id: int | str) -> dict:
    """Análisis Apex completo de una actividad."""
    aid = str(activity_id)
    base = os.path.join(user_dir(user_id), "activities", aid)
    a = _load(os.path.join(base, "activity_analysis.json"))
    if not a:
        return {"id": aid, "sin_analisis": True, "nota": "Esa actividad no está procesada. Corre sincronizar."}
    f = _load(os.path.join(base, "activity_findings.json"), {}) or {}
    ins = _load(os.path.join(base, "series_insights.json"))
    return {
        "id": aid,
        "resumen_garmin": a.get("garmin_summary"),
        "resumen_apex": a.get("derived_summary"),
        "scores": a.get("performance_scores"),
        "perfil_potencia": a.get("power_profile"),
        "zonas": a.get("zones"),
        "esfuerzos": a.get("efforts"),
        "subidas": a.get("climbs"),
        "fatiga": a.get("fatigue"),
        "indice_metabolico": a.get("metabolic_index"),
        "hallazgos": _findings(f.get("findings"), 10),
        "insights_serie": ins,
        "nota_usuario": _notes(user_id).get(aid),
    }


def guardar_nota(user_id: str, activity_id: int | str, etiqueta: str | None = None,
                 rpe: int | None = None, texto: str | None = None) -> dict:
    notes = _notes(user_id)
    n = notes.get(str(activity_id), {})
    if etiqueta is not None:
        n["etiqueta"] = etiqueta.strip()[:40]
    if rpe is not None:
        n["rpe"] = max(1, min(10, int(rpe)))
    if texto is not None:
        n["texto"] = texto.strip()[:2000]
    n["actualizado"] = datetime.now().isoformat(timespec="seconds")
    notes[str(activity_id)] = n
    os.makedirs(user_dir(user_id), exist_ok=True)
    with open(_notes_path(user_id), "w", encoding="utf-8") as fh:
        json.dump(notes, fh, ensure_ascii=False, indent=2)
    return {"ok": True, "id": str(activity_id), "nota": n}


# ─────────────────────────────────────────────────────────────────────────────
# Tendencias y correlaciones
# ─────────────────────────────────────────────────────────────────────────────

def tendencias(user_id: str, dias: int = 30) -> dict:
    hist = _pi(user_id, "readiness_history.json", []) or []
    corr = (_pi(user_id, "performance_correlations.json", {}) or {}).get("correlations") or []
    strong = [c for c in corr if isinstance(c.get("pearson_r"), (int, float)) and abs(c["pearson_r"]) >= 0.3 and (c.get("n_pairs") or 0) >= 5]
    return {
        "readiness": [{"fecha": r.get("calendar_date"), "score": _round(r.get("readiness_score")),
                       "sueno": _round(r.get("sleep_score")), "dia": _round(r.get("day_score")),
                       "actividad": r.get("has_activity")} for r in hist[-dias:]],
        "sueno": tendencia_sueno(user_id, min(dias, 30)),
        "correlaciones_personales": [{"nombre": c.get("name"), "r": c.get("pearson_r"), "n": c.get("n_pairs"),
                                      "interpretacion": c.get("interpretation"), "que_dice": c.get("what_it_says")} for c in strong],
        "pesos_readiness": _pi(user_id, "dynamic_weights.json"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sync
# ─────────────────────────────────────────────────────────────────────────────

def _run_sync(user_id: str, email: str, days_back: int):
    from app_context import set_current_garmin_email, ensure_current_user_profile
    from garmin_official import ApexGarminClient
    from auto_sync import sync_sleep, sync_day, sync_activities, sync_master
    st = _sync_state[user_id]
    _run_lock.acquire()
    try:
        set_current_garmin_email(email)
        ensure_current_user_profile(garmin_email=email)
        client = ApexGarminClient.for_user(user_id)
        for step, fn in (("actividades", lambda: sync_activities(client, user_id, days_back=days_back, verbose=False)),
                         ("sueño", lambda: sync_sleep(client, user_id, verbose=False)),
                         ("día", lambda: sync_day(client, user_id, verbose=False)),
                         ("readiness", lambda: sync_master(user_id, verbose=False))):
            st["paso"] = step
            try:
                st["resultados"][step] = fn()
            except Exception as e:
                st["resultados"][step] = {"error": str(e)}
        try:
            from ftp_engine import run_ftp_engine
            st["paso"] = "ftp"
            run_ftp_engine(user_dir(user_id))
        except Exception as e:
            st["resultados"]["ftp"] = {"error": str(e)}
        st["estado"] = "terminado"
    except Exception as e:
        st["estado"], st["error"] = "error", str(e)
    finally:
        st["termino"] = datetime.now().isoformat(timespec="seconds")
        _run_lock.release()


def sincronizar(user_id: str, email: str, days_back: int = 7) -> dict:
    """Arranca el sync con Garmin en segundo plano. Consulta el avance con estado_sync()."""
    with _sync_lock:
        cur = _sync_state.get(user_id)
        if cur and cur.get("estado") == "corriendo":
            return {"ya_corriendo": True, **cur}
        _sync_state[user_id] = {"estado": "corriendo", "inicio": datetime.now().isoformat(timespec="seconds"),
                                "paso": "conectando", "resultados": {}}
    threading.Thread(target=_run_sync, args=(user_id, email, days_back), daemon=True).start()
    return {"iniciado": True, "nota": "El sync tarda de 1 a 5 minutos. Consulta estado_sync."}


def estado_sync(user_id: str) -> dict:
    return _sync_state.get(user_id) or {"estado": "sin_sync_en_esta_sesion"}
