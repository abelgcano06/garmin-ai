"""
garmin_server.py
================
Microservidor local (FastAPI) que expone endpoints para que la app
Next.js pueda subir workouts a Garmin Connect sin exponer credenciales.

Uso:
    python garmin_server.py

Corre en http://localhost:7845
Requiere que garmin_save_tokens.py haya sido ejecutado al menos una vez.
"""

import contextvars
import json
import os
from datetime import date, timedelta

import uvicorn
from typing import Any

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from garminconnect import Garmin

try:
    import psycopg2
    import psycopg2.extras
    from db import get_conn
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
TOKENSTORE = os.path.join(BASE_DIR, "data", "garth_tokens")
SESSION_FILE = os.path.join(BASE_DIR, "garmin_session.json")
DATA_DIR     = os.path.join(BASE_DIR, "data", "users")

# Per-request user context — set by HTTP middleware from X-Apex-User / X-Apex-Email headers
_current_user_key: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_key", default="")
_current_garmin_email: contextvars.ContextVar[str] = contextvars.ContextVar("current_garmin_email", default="")


def get_user_dir() -> str:
    """Retorna el directorio del usuario activo. Usa header X-Apex-User si está presente."""
    user_key = _current_user_key.get()
    if user_key:
        user_dir = os.path.join(DATA_DIR, user_key)
        if not os.path.exists(user_dir):
            raise HTTPException(status_code=404, detail=f"Usuario no encontrado: {user_key}")
        return user_dir
    # Legacy fallback: leer garmin_session.json
    if not os.path.exists(SESSION_FILE):
        raise HTTPException(status_code=503, detail="Sin sesión activa")
    with open(SESSION_FILE, encoding="utf-8") as f:
        session = json.load(f)
    email_key = session.get("email", "").replace("@", "_at_").replace(".", "_")
    user_dir = os.path.join(DATA_DIR, email_key)
    if not os.path.exists(user_dir):
        raise HTTPException(status_code=404, detail=f"Directorio de usuario no encontrado: {user_dir}")
    return user_dir


def get_db_user_id() -> int | None:
    """Retorna el user_id de PostgreSQL para la sesión activa, o None si no disponible."""
    if not DB_AVAILABLE:
        return None
    try:
        email = _current_garmin_email.get()
        if not email and os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, encoding="utf-8") as f:
                email = json.load(f).get("email", "").strip().lower()
        if not email:
            return None
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            conn.close()
    except Exception:
        return None


def read_json(path: str) -> dict:
    """Lee un archivo JSON y retorna su contenido. Lanza 404 si no existe."""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_json_opt(path: str):
    """Como read_json pero retorna None si el archivo no existe."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_path(rel_path: str) -> str:
    """Resuelve un path relativo a BASE_DIR. Si es absoluto, lo retorna tal cual."""
    if not rel_path:
        return ""
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.join(BASE_DIR, rel_path)


app = FastAPI(title="Apex Garmin Bridge", version="1.0.0")


@app.middleware("http")
async def user_context_middleware(request, call_next):
    """Extrae X-Apex-User y X-Apex-Email de cada petición y los inyecta como contextvars."""
    tok_key = _current_user_key.set(request.headers.get("X-Apex-User", "").strip())
    tok_email = _current_garmin_email.set(request.headers.get("X-Apex-Email", "").strip().lower())
    try:
        response = await call_next(request)
    finally:
        _current_user_key.reset(tok_key)
        _current_garmin_email.reset(tok_email)
    return response


# Allow calls from Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# ── Garmin client singleton ────────────────────────────────────────────────────

_client: Garmin | None = None


def get_client() -> Garmin:
    global _client
    if _client is not None:
        return _client

    if not os.path.exists(TOKENSTORE) or not os.listdir(TOKENSTORE):
        raise HTTPException(
            status_code=503,
            detail="Tokens no encontrados. Ejecuta garmin_save_tokens.py primero."
        )

    email = ""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, encoding="utf-8") as f:
            email = json.load(f).get("email", "")

    client = Garmin(email)
    client.login(tokenstore=TOKENSTORE)
    _client = client
    return _client


# ── Models ────────────────────────────────────────────────────────────────────

class WorkoutStep(BaseModel):
    type: str           # "warmup" | "interval" | "recovery" | "cooldown"
    label: str
    duration_min: float
    target_watts_low: float | None = None
    target_watts_high: float | None = None
    target_hr_max: int | None = None
    notes: str = ""


class SendWorkoutRequest(BaseModel):
    workout_name: str
    description: str
    steps: list[WorkoutStep]
    schedule_date: str | None = None   # "YYYY-MM-DD", default = tomorrow


# ── Helpers ───────────────────────────────────────────────────────────────────

STEP_TYPE_MAP = {
    "warmup":   {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
}


def build_garmin_step(step: WorkoutStep, order: int) -> dict:
    step_type = STEP_TYPE_MAP.get(step.type, STEP_TYPE_MAP["interval"])
    duration_s = round(step.duration_min * 60)

    # Target
    if step.target_watts_low is not None and step.target_watts_high is not None:
        target = {
            "workoutTargetTypeId": 6,
            "workoutTargetTypeKey": "power",
        }
        target_low  = step.target_watts_low
        target_high = step.target_watts_high
    elif step.target_hr_max is not None:
        target = {
            "workoutTargetTypeId": 8,
            "workoutTargetTypeKey": "heart.rate",
        }
        target_low  = 0
        target_high = step.target_hr_max
    else:
        target      = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"}
        target_low  = None
        target_high = None

    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": step_type,
        "endCondition": {
            "conditionTypeId": 2,
            "conditionTypeKey": "time",
        },
        "endConditionValue": float(duration_s),
        "targetType": target,
        "targetValueOne": target_low,
        "targetValueTwo": target_high,
        "description": step.notes or None,
    }


def build_garmin_workout(req: SendWorkoutRequest) -> dict:
    steps = [build_garmin_step(s, i + 1) for i, s in enumerate(req.steps)]
    return {
        "workoutName": req.workout_name,
        "description": req.description or None,
        "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
            "workoutSteps": steps,
        }],
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/status")
def status():
    try:
        client = get_client()
        profile = client.get_full_name()
        return {"ok": True, "user": profile}
    except HTTPException as e:
        return {"ok": False, "error": e.detail}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/workout/send")
def send_workout(req: SendWorkoutRequest):
    client = get_client()

    workout_json = build_garmin_workout(req)

    # Upload workout
    try:
        result = client.upload_workout(workout_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error subiendo workout: {e}")

    workout_id = result.get("workoutId")
    if not workout_id:
        raise HTTPException(status_code=500, detail=f"Respuesta inesperada de Garmin: {result}")

    # Schedule for tomorrow (or specified date)
    target_date = req.schedule_date
    if not target_date:
        target_date = (date.today() + timedelta(days=1)).isoformat()

    try:
        client.garth.post(
            "connectapi",
            f"/workout-service/schedule/{workout_id}",
            json={"date": target_date},
            api=True,
        )
    except Exception as e:
        # Upload worked — scheduling failed. Return partial success.
        return {
            "ok": True,
            "workout_id": workout_id,
            "scheduled": False,
            "schedule_error": str(e),
            "workout_name": req.workout_name,
        }

    return {
        "ok": True,
        "workout_id": workout_id,
        "scheduled": True,
        "scheduled_date": target_date,
        "workout_name": req.workout_name,
    }


@app.delete("/workout/{workout_id}")
def delete_workout(workout_id: int):
    client = get_client()
    try:
        client.garth.delete(
            "connectapi",
            f"/workout-service/workout/{workout_id}",
            api=True,
        )
        return {"ok": True, "deleted_id": workout_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Data endpoints ────────────────────────────────────────────────────────────

@app.get("/api/activities")
def get_activities():
    user_id = get_db_user_id()
    if user_id and DB_AVAILABLE:
        try:
            conn = get_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            garmin_activity_id AS activity_id,
                            name, activity_type AS type,
                            start_date::text AS date,
                            distance_km, elevation_m, moving_minutes, elapsed_minutes,
                            calories, avg_hr, max_hr, avg_power,
                            estimated_tss, garmin_tss, aerobic_te, anaerobic_te, vo2max,
                            overall_score, score_label
                        FROM activities
                        WHERE user_id = %s
                        ORDER BY start_date DESC
                    """, (user_id,))
                    rows = [dict(r) for r in cur.fetchall()]
                    return {"activities": rows}
            finally:
                conn.close()
        except Exception as e:
            print(f"[DB] /api/activities fallback a JSON: {e}")
    user_dir = get_user_dir()
    return read_json(os.path.join(user_dir, "activity_index.json"))


@app.get("/api/activity/{activity_id}")
def get_activity(activity_id: str):
    user_id = get_db_user_id()
    if user_id and DB_AVAILABLE:
        try:
            conn = get_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT analysis_json FROM activities
                        WHERE user_id = %s AND garmin_activity_id = %s
                    """, (user_id, int(activity_id)))
                    row = cur.fetchone()
                    if row and row["analysis_json"]:
                        return row["analysis_json"]
            finally:
                conn.close()
        except Exception as e:
            print(f"[DB] /api/activity/{activity_id} fallback a JSON: {e}")
    user_dir = get_user_dir()
    path = os.path.join(user_dir, "activities", activity_id, "activity_analysis.json")
    return read_json(path)


@app.get("/api/sleep/{fecha}")
def get_sleep(fecha: str):
    user_dir = get_user_dir()
    path = os.path.join(user_dir, "sleep", fecha, "sleep_analysis.json")
    return read_json(path)


@app.get("/api/master-brief")
def get_master_brief():
    user_id = get_db_user_id()
    if user_id and DB_AVAILABLE:
        try:
            from db import get_intelligence
            intel = get_intelligence(user_id)
            if intel.get("master_brief"):
                return intel["master_brief"]
        except Exception as e:
            print(f"[DB] /api/master-brief fallback a JSON: {e}")
    user_dir = get_user_dir()
    return read_json(os.path.join(user_dir, "performance_intelligence", "master_brief.json"))


@app.get("/api/profile")
def get_profile():
    user_id = get_db_user_id()
    if user_id and DB_AVAILABLE:
        try:
            from db import get_profile as db_get_profile
            profile = db_get_profile(user_id)
            if profile:
                return profile
        except Exception as e:
            print(f"[DB] /api/profile fallback a JSON: {e}")
    user_dir = get_user_dir()
    path = os.path.join(user_dir, "profile.json")
    if not os.path.exists(path):
        path = os.path.join(BASE_DIR, "data", "profile.json")
    return read_json(path)


@app.post("/api/sync")
def trigger_sync():
    import subprocess
    script = os.path.join(BASE_DIR, "run_sync.py")
    if not os.path.exists(script):
        raise HTTPException(status_code=404, detail="run_sync.py no encontrado")
    try:
        result = subprocess.run(
            ["python", script],
            capture_output=True, text=True, timeout=120
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else ""
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Sync tardó más de 2 minutos")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Aggregated / extended data endpoints ──────────────────────────────────────

@app.get("/api/home")
def get_home():
    user_dir = get_user_dir()
    pi = os.path.join(user_dir, "performance_intelligence")

    intel = {}
    if user_id and DB_AVAILABLE:
        try:
            from db import get_intelligence
            intel = get_intelligence(user_id)
        except Exception:
            pass
    master = intel.get("master_brief") or read_json_opt(os.path.join(pi, "master_brief.json"))
    rh = intel.get("readiness_history") or read_json_opt(os.path.join(pi, "readiness_history.json")) or []
    last7 = rh[-7:] if isinstance(rh, list) else []

    sleep_score   = None
    day_score     = None
    activity_info = None

    user_id = get_db_user_id()
    if user_id and DB_AVAILABLE:
        try:
            conn = get_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT overall_recovery_score FROM sleep_daily
                        WHERE user_id = %s AND overall_recovery_score IS NOT NULL
                        ORDER BY date DESC LIMIT 1
                    """, (user_id,))
                    row = cur.fetchone()
                    if row:
                        sleep_score = row["overall_recovery_score"]

                    cur.execute("""
                        SELECT overall_day_state_score FROM day_daily
                        WHERE user_id = %s AND overall_day_state_score IS NOT NULL
                        ORDER BY date DESC LIMIT 1
                    """, (user_id,))
                    row = cur.fetchone()
                    if row:
                        day_score = row["overall_day_state_score"]

                    cur.execute("""
                        SELECT garmin_activity_id AS activity_id, name, activity_type AS type,
                               start_date::text AS date, overall_score, brief_json
                        FROM activities WHERE user_id = %s
                        ORDER BY start_date DESC LIMIT 1
                    """, (user_id,))
                    row = cur.fetchone()
                    if row:
                        brief_obj = row["brief_json"] or {}
                        score = (
                            ((brief_obj.get("phase_1_quick_insight") or {}).get("overall_score") or {}).get("score")
                            or row["overall_score"]
                        )
                        activity_info = {"name": row["name"], "score": score, "date": row["date"], "type": row["type"]}
            finally:
                conn.close()
        except Exception as e:
            print(f"[DB] /api/home fallback a JSON: {e}")

    # Fallback a JSON para lo que no llegó de DB
    if sleep_score is None or day_score is None or activity_info is None:
        today = date.today().isoformat()
        def latest_date(subdir: str, filename: str) -> str:
            root = os.path.join(user_dir, subdir)
            if not os.path.exists(root):
                return today
            available = sorted([e for e in os.listdir(root) if os.path.isfile(os.path.join(root, e, filename))])
            return available[-1] if available else today

        if sleep_score is None:
            sleep_date = today if os.path.exists(os.path.join(user_dir, "sleep", today, "sleep_analysis.json")) else latest_date("sleep", "sleep_analysis.json")
            sleep = read_json_opt(os.path.join(user_dir, "sleep", sleep_date, "sleep_analysis.json"))
            sleep_score = ((sleep or {}).get("recovery_summary") or {}).get("overall_recovery_score")

        if day_score is None:
            day_date = today if os.path.exists(os.path.join(user_dir, "day", today, "day_analysis.json")) else latest_date("day", "day_analysis.json")
            day = read_json_opt(os.path.join(user_dir, "day", day_date, "day_analysis.json"))
            day_score = ((day or {}).get("recovery_summary") or {}).get("overall_day_state_score")

        if activity_info is None:
            index_raw = read_json_opt(os.path.join(user_dir, "activity_index.json")) or {}
            acts = sorted(index_raw.get("activities", []), key=lambda a: a.get("date", ""), reverse=True)
            last = acts[0] if acts else None
            activity_score = None
            if last:
                brief = read_json_opt(resolve_path(last.get("brief_file", "")))
                if brief:
                    activity_score = ((brief.get("phase_1_quick_insight") or {}).get("overall_score") or {}).get("score")
            activity_info = {"name": last.get("name"), "score": activity_score, "date": last.get("date"), "type": last.get("type")} if last else None

    return {
        "master":    {k: master.get(k) for k in ("readiness_score", "readiness_label", "recommendation", "risk_flags", "calendar_date")} if master else None,
        "history_7": last7,
        "sleep_score":  sleep_score,
        "day_score":    day_score,
        "activity":     activity_info,
    }


@app.get("/api/activity/{activity_id}/full")
def get_activity_full_bundle(activity_id: str):
    user_id  = get_db_user_id()
    analysis = None
    brief    = None

    if user_id and DB_AVAILABLE:
        try:
            conn = get_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT analysis_json, brief_json FROM activities
                        WHERE user_id = %s AND garmin_activity_id = %s
                    """, (user_id, int(activity_id)))
                    row = cur.fetchone()
                    if row:
                        analysis = row["analysis_json"]
                        brief    = row["brief_json"]
            finally:
                conn.close()
        except Exception as e:
            print(f"[DB] /api/activity/{activity_id}/full fallback a JSON: {e}")

    user_dir = get_user_dir()
    pi       = os.path.join(user_dir, "performance_intelligence")

    if analysis is None:
        index_raw = read_json_opt(os.path.join(user_dir, "activity_index.json")) or {}
        activity_meta = next((a for a in index_raw.get("activities", []) if str(a.get("activity_id")) == activity_id), None)
        if not activity_meta:
            raise HTTPException(status_code=404, detail=f"Actividad {activity_id} no encontrada")
        analysis = read_json_opt(resolve_path(activity_meta.get("analysis_file", "")))
        brief    = read_json_opt(resolve_path(activity_meta.get("brief_file", "")))

    act_dir = os.path.join(user_dir, "activities", activity_id)
    gs      = (analysis or {}).get("garmin_summary") or {}

    intel = {}
    if user_id and DB_AVAILABLE:
        try:
            from db import get_intelligence, get_profile as db_get_profile
            intel   = get_intelligence(user_id)
            profile = db_get_profile(user_id)
        except Exception:
            profile = None
    else:
        profile = None

    return {
        "activity":         {"activity_id": activity_id, "name": gs.get("name"), "type": gs.get("type"), "date": (gs.get("start_date") or "")[:10]},
        "brief":            brief,
        "analysis":         analysis,
        "series_insights":  read_json_opt(os.path.join(act_dir, "series_insights.json")),
        "ftp_profile":      intel.get("ftp_profile")      or read_json_opt(os.path.join(pi, "ftp_profile.json")),
        "athlete_baseline": intel.get("athlete_baseline") or read_json_opt(os.path.join(pi, "athlete_baseline.json")),
        "profile":          profile or read_json_opt(os.path.join(user_dir, "profile.json")),
    }


@app.get("/api/activity/{activity_id}/series")
def get_activity_series_data(activity_id: str):
    import csv as _csv
    import io

    user_dir = get_user_dir()
    csv_path = os.path.join(user_dir, "activities", activity_id, "activity_series_clean.csv")
    if not os.path.exists(csv_path):
        return {"series": [], "has_power": False, "has_cadence": False, "active_cadence_rpm": None, "pedaling_pct": None}

    with open(csv_path, encoding="utf-8") as f:
        content = f.read()

    def to_float(v):
        try:
            x = float(v)
            return None if x != x else x
        except Exception:
            return None

    rows   = list(_csv.DictReader(io.StringIO(content)))
    TARGET = 300
    raw    = []
    for row in rows:
        t = to_float(row.get("elapsed_s", ""))
        if t is None:
            continue
        spd = to_float(row.get("speed_mps", ""))
        raw.append({
            "t":       round((t / 60) * 10) / 10,
            "elev":    to_float(row.get("elevation_m", "")),
            "hr":      to_float(row.get("heart_rate_bpm", "")),
            "power":   to_float(row.get("power_w", "")),
            "speed":   round(spd * 3.6 * 10) / 10 if spd else None,
            "cadence": to_float(row.get("cadence_rpm", "")),
        })

    sampled = raw if len(raw) <= TARGET else [raw[round(i * len(raw) / TARGET)] for i in range(TARGET)]
    has_power   = any((p["power"]   or 0) > 0 for p in sampled)
    has_cadence = any((p["cadence"] or 0) > 0 for p in sampled)

    cad_vals = [to_float(r.get("cadence_rpm", "")) for r in rows]
    pow_vals = [to_float(r.get("power_w",     "")) for r in rows]
    active   = [(c, p) for c, p in zip(cad_vals, pow_vals) if c is not None and c > 5 and (p is None or p > 30)]
    total    = [c for c in cad_vals if c is not None]
    return {
        "series":            sampled,
        "has_power":         has_power,
        "has_cadence":       has_cadence,
        "active_cadence_rpm": round(sum(c for c, _ in active) / len(active) * 10) / 10 if active else None,
        "pedaling_pct":      round(len(active) / len(total) * 1000) / 10 if total else None,
    }


@app.get("/api/master")
def get_master():
    user_id = get_db_user_id()
    intel = {}
    if user_id and DB_AVAILABLE:
        try:
            from db import get_intelligence
            intel = get_intelligence(user_id)
        except Exception as e:
            print(f"[DB] /api/master fallback a JSON: {e}")

    user_dir = get_user_dir()
    pi = os.path.join(user_dir, "performance_intelligence")
    rh = intel.get("readiness_history") or read_json_opt(os.path.join(pi, "readiness_history.json")) or []
    return {
        "master":          intel.get("master_brief")     or read_json_opt(os.path.join(pi, "master_brief.json")),
        "history_30":      rh[-30:] if isinstance(rh, list) else [],
        "correlations":    intel.get("correlations")     or read_json_opt(os.path.join(pi, "performance_correlations.json")),
        "dynamic_weights": intel.get("dynamic_weights")  or read_json_opt(os.path.join(pi, "dynamic_weights.json")),
        "ftp_profile":     intel.get("ftp_profile")      or read_json_opt(os.path.join(pi, "ftp_profile.json")),
    }


@app.get("/api/sleep-full")
def get_sleep_full(date_param: str = None):
    user_dir = get_user_dir()
    d = date_param or date.today().isoformat()
    user_id = get_db_user_id()

    raw_from_db = None
    brief_from_db = None
    brief_ai_from_db = None

    if user_id and DB_AVAILABLE:
        try:
            conn = get_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT date::text, analysis_json, brief_json, brief_ai_json
                        FROM sleep_daily
                        WHERE user_id = %s AND date = %s
                    """, (user_id, d))
                    row = cur.fetchone()
                    if not row:
                        cur.execute("""
                            SELECT date::text, analysis_json, brief_json, brief_ai_json
                            FROM sleep_daily
                            WHERE user_id = %s AND analysis_json IS NOT NULL
                            ORDER BY date DESC LIMIT 1
                        """, (user_id,))
                        row = cur.fetchone()
                    if row:
                        d = row["date"]
                        raw_from_db    = row["analysis_json"]
                        brief_from_db  = row["brief_json"]
                        brief_ai_from_db = row["brief_ai_json"]
            finally:
                conn.close()
        except Exception as e:
            print(f"[DB] /api/sleep-full fallback a JSON: {e}")

    # Si DB no tiene el análisis, caer a archivo
    if raw_from_db is None:
        sleep_root = os.path.join(user_dir, "sleep")
        if not os.path.exists(os.path.join(sleep_root, d, "sleep_analysis.json")):
            available = sorted([
                e for e in os.listdir(sleep_root)
                if os.path.isfile(os.path.join(sleep_root, e, "sleep_analysis.json"))
            ])
            if available:
                d = available[-1]

    base = os.path.join(user_dir, "sleep", d)
    raw  = raw_from_db or read_json_opt(os.path.join(base, "sleep_analysis.json"))
    analysis = None
    if raw:
        rs = raw.get("recovery_summary")    or {}
        ar = raw.get("autonomic_recovery")  or {}
        sa = raw.get("sleep_architecture")  or {}
        ox = raw.get("oxygenation")         or {}
        er = raw.get("energy_recharge")     or {}
        sr = raw.get("stress_recovery")     or {}
        ca = raw.get("circadian_alignment") or {}
        sw = raw.get("sleep_window")        or {}
        cr = raw.get("cardiac_recovery")    or {}
        rr = raw.get("respiratory_recovery") or {}
        sn = raw.get("sleep_need")          or {}
        im = raw.get("instability_markers") or {}
        analysis = {
            # — recovery summary —
            "calendar_date":                   raw.get("calendar_date"),
            "overall_recovery_score":          rs.get("overall_recovery_score"),
            "physical_recovery_score":         rs.get("physical_recovery_score"),
            "neural_recovery_score":           rs.get("neural_recovery_score"),
            # — sleep window —
            "sleep_time_seconds":              sw.get("sleep_time_seconds"),
            "time_in_bed_seconds":             sw.get("time_in_bed_seconds"),
            "sleep_efficiency":                sw.get("sleep_efficiency"),   # fixed: was sa
            "sleep_start_local":               sw.get("sleep_start_local"),
            "sleep_end_local":                 sw.get("sleep_end_local"),
            # — sleep architecture —
            "deep_ratio":                      sa.get("deep_ratio"),
            "rem_ratio":                       sa.get("rem_ratio"),
            "light_ratio":                     sa.get("light_ratio"),
            "awake_ratio":                     sa.get("awake_ratio"),
            "awake_count":                     sa.get("awake_count"),
            "fragmentation_index":             sa.get("fragmentation_index"),
            "movement_index":                  sa.get("movement_index"),
            "restlessness_score":              sa.get("restlessness_score"),
            "architecture_balance_score":      sa.get("architecture_balance_score"),
            "architecture_stability_score":    sa.get("architecture_stability_score"),
            "stage_transition_count":          sa.get("stage_transition_count"),
            "early_window_deep_ratio":         sa.get("early_window_deep_ratio"),
            "late_window_rem_ratio":           sa.get("late_window_rem_ratio"),
            "deep_distribution_score":         sa.get("deep_distribution_score"),
            "rem_distribution_score":          sa.get("rem_distribution_score"),
            # — cardiac recovery —
            "avg_sleep_hr":                    cr.get("avg_sleep_hr"),
            "resting_hr":                      cr.get("resting_hr"),
            "min_sleep_hr":                    cr.get("min_sleep_hr"),
            "max_sleep_hr":                    cr.get("max_sleep_hr"),
            "hr_drop":                         cr.get("hr_drop"),
            "hr_stability_index":              cr.get("hr_stability_index"),
            "hr_recovery_slope":               cr.get("hr_recovery_slope"),
            "hr_first_third_avg":              cr.get("hr_first_third_avg"),
            "hr_last_third_avg":               cr.get("hr_last_third_avg"),
            "hr_overnight_drop_pct":           cr.get("hr_overnight_drop_pct"),
            # — autonomic recovery —
            "avg_overnight_hrv":               ar.get("avg_overnight_hrv"),
            "hrv_status":                      ar.get("hrv_status"),
            "hrv_recovery_score":              ar.get("hrv_recovery_score"),
            "hrv_ramp_score":                  ar.get("hrv_ramp_score"),
            "autonomic_recovery_curve_score":  ar.get("autonomic_recovery_curve_score"),
            "sympathetic_activation_score":    ar.get("sympathetic_activation_score"),
            "hrv_first_half":                  ar.get("hrv_first_half"),
            "hrv_second_half":                 ar.get("hrv_second_half"),
            "stress_first_third_avg":          ar.get("stress_first_third_avg"),
            "stress_last_third_avg":           ar.get("stress_last_third_avg"),
            # — stress recovery —
            "avg_sleep_stress":                sr.get("avg_sleep_stress"),
            "stress_load_score":               sr.get("stress_load_score"),
            "stress_stability_index":          sr.get("stress_stability_index"),
            "stress_spike_count":              sr.get("stress_spike_count"),
            # — respiratory recovery —
            "avg_respiration":                 rr.get("avg_respiration"),
            "min_respiration":                 rr.get("min_respiration"),
            "max_respiration":                 rr.get("max_respiration"),
            "respiration_variability":         rr.get("respiration_variability"),
            "respiratory_stability_score":     rr.get("respiratory_stability_score"),
            "breathing_disruption_severity":   rr.get("breathing_disruption_severity"),
            "respiratory_irregularity_score":  rr.get("respiratory_irregularity_score"),
            # — oxygenation —
            "avg_spo2":                        ox.get("avg_spo2"),
            "min_spo2":                        ox.get("min_spo2"),
            "max_spo2":                        ox.get("max_spo2"),
            "oxygen_risk_flag":                ox.get("oxygen_risk_flag", False),
            "oxygen_stability_score":          ox.get("oxygen_stability_score"),
            "spo2_drop_count":                 ox.get("spo2_drop_count"),
            "spo2_drop_depth_avg":             ox.get("spo2_drop_depth_avg"),
            "oxygen_recovery_after_drop_score": ox.get("oxygen_recovery_after_drop_score"),
            # — energy recharge —
            "body_battery_start":              er.get("body_battery_start"),
            "body_battery_end":                er.get("body_battery_end"),
            "body_battery_change":             er.get("body_battery_change"),
            "recharge_efficiency":             er.get("recharge_efficiency"),
            "bb_gain_first_half":              er.get("bb_gain_first_half"),
            "bb_gain_second_half":             er.get("bb_gain_second_half"),
            "body_battery_recharge_velocity":  er.get("body_battery_recharge_velocity"),
            # — sleep need —
            "sleep_need_baseline_minutes":     sn.get("baseline_minutes"),
            "sleep_need_actual_minutes":       sn.get("actual_minutes"),
            "sleep_need_gap_minutes":          sn.get("sleep_need_gap_minutes"),
            "sleep_need_feedback":             sn.get("feedback"),
            "sleep_need_training_feedback":    sn.get("training_feedback"),
            # — circadian alignment —
            "circadian_alignment_score":       ca.get("circadian_alignment_score"),
            "sleep_alignment_status":          ca.get("sleep_alignment_status"),
            "sleep_midpoint_minutes":          ca.get("sleep_midpoint_minutes"),
            "optimal_midpoint_minutes":        ca.get("optimal_midpoint_minutes"),
            # — instability markers —
            "overnight_instability_score":     im.get("overnight_instability_score"),
            "micro_arousal_score":             im.get("micro_arousal_score"),
            "movement_spike_count":            im.get("movement_spike_count"),
        }
    baselines_raw = read_json_opt(os.path.join(user_dir, "sleep_history", "sleep_baselines.json"))
    baselines = baselines_raw.get("metrics") if baselines_raw else None

    # Build sleep_stages from raw Garmin data (activityLevel → stage name)
    ACTIVITY_LEVEL_MAP = {0.0: "deep", 1.0: "light", 2.0: "rem", 3.0: "awake"}
    sleep_stages = []
    raw_data = read_json_opt(os.path.join(base, "sleep_raw.json")) or {}
    garmin_levels = None
    calls = raw_data.get("calls") or {}
    if isinstance(calls, dict):
        gsd = calls.get("get_sleep_data") or {}
        garmin_levels = (gsd.get("data") or {}).get("sleepLevels")
    if isinstance(garmin_levels, list):
        from datetime import datetime as _dt
        def _parse_gmt(s):
            if not s: return None
            try: return _dt.fromisoformat(str(s).replace(".0", "").replace("Z", "+00:00"))
            except: return None
        for item in garmin_levels:
            al = item.get("activityLevel")
            stage = ACTIVITY_LEVEL_MAP.get(float(al) if al is not None else -1, "unknown")
            s_ts = item.get("startGMT", "")
            e_ts = item.get("endGMT", "")
            dur = item.get("durationSeconds")
            if not dur:
                s_dt, e_dt = _parse_gmt(s_ts), _parse_gmt(e_ts)
                if s_dt and e_dt:
                    dur = int((e_dt - s_dt).total_seconds())
            sleep_stages.append({
                "stage":            stage,
                "start_ts":         s_ts,
                "end_ts":           e_ts,
                "duration_seconds": int(dur or 0),
            })

    return {
        "date":         d,
        "analysis":     analysis,
        "baselines":    baselines,
        "sleep_stages": sleep_stages,
        "brief":        brief_from_db or read_json_opt(os.path.join(base, "sleep_brief.json")),
        "brief_ai":     brief_ai_from_db or read_json_opt(os.path.join(base, "sleep_brief_ai.json")),
        "deep_ai":      read_json_opt(os.path.join(base, "sleep_deep_ai.json")),
    }


@app.get("/api/day")
def get_day(date_param: str = None):
    user_dir = get_user_dir()
    d = date_param or date.today().isoformat()
    user_id = get_db_user_id()

    analysis_from_db = None
    brief_ai_from_db = None

    if user_id and DB_AVAILABLE:
        try:
            conn = get_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT date::text, analysis_json, brief_ai_json
                        FROM day_daily
                        WHERE user_id = %s AND date = %s
                    """, (user_id, d))
                    row = cur.fetchone()
                    if not row:
                        cur.execute("""
                            SELECT date::text, analysis_json, brief_ai_json
                            FROM day_daily
                            WHERE user_id = %s AND analysis_json IS NOT NULL
                            ORDER BY date DESC LIMIT 1
                        """, (user_id,))
                        row = cur.fetchone()
                    if row:
                        d = row["date"]
                        analysis_from_db = row["analysis_json"]
                        brief_ai_from_db = row["brief_ai_json"]
            finally:
                conn.close()
        except Exception as e:
            print(f"[DB] /api/day fallback a JSON: {e}")

    if analysis_from_db is None:
        day_root = os.path.join(user_dir, "day")
        if not os.path.exists(os.path.join(day_root, d, "day_analysis.json")):
            available = sorted([
                e for e in os.listdir(day_root)
                if os.path.isfile(os.path.join(day_root, e, "day_analysis.json"))
            ])
            if available:
                d = available[-1]

    base = os.path.join(user_dir, "day", d)
    return {
        "date":     d,
        "analysis": analysis_from_db or read_json_opt(os.path.join(base, "day_analysis.json")),
        "brief_ai": brief_ai_from_db or read_json_opt(os.path.join(base, "day_brief_ai.json")),
        "deep_ai":  read_json_opt(os.path.join(base, "day_deep_ai.json")),
    }


@app.get("/api/history")
def get_history(section: str, days: int = 7):
    days = min(days, 365)
    user_id = get_db_user_id()

    if user_id and DB_AVAILABLE:
        try:
            conn = get_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    if section == "sleep":
                        cur.execute("""
                            SELECT
                                date::text AS calendar_date,
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
                            FROM sleep_daily
                            WHERE user_id = %s AND overall_recovery_score > 0
                            ORDER BY date DESC
                            LIMIT %s
                        """, (user_id, days))
                        rows = [dict(r) for r in cur.fetchall()]
                        return sorted(rows, key=lambda r: r["calendar_date"])
                    elif section == "day":
                        cur.execute("""
                            SELECT
                                date::text AS calendar_date,
                                overall_day_state_score, system_strain_score, day_capacity_score,
                                nervous_system_load_score, energy_dynamics_score, physical_load_score,
                                avg_day_hr, max_hr, hr_variability, avg_hrv,
                                avg_stress, max_stress, stress_spike_count, high_stress_count, high_stress_ratio,
                                body_battery_change, body_battery_slope, recharge_events, crash_events,
                                steps, intensity_minutes, active_calories,
                                recovery_response_score, downshift_count, downshift_ratio,
                                atl, ctl, tsb, tsb_label,
                                primary_limiter, secondary_limiter, headline
                            FROM day_daily
                            WHERE user_id = %s
                            ORDER BY date DESC
                            LIMIT %s
                        """, (user_id, days))
                        rows = [dict(r) for r in cur.fetchall()]
                        return sorted(rows, key=lambda r: r["calendar_date"])
            finally:
                conn.close()
        except Exception as e:
            print(f"[DB] /api/history fallback a JSON: {e}")

    # Fallback a JSON
    user_dir = get_user_dir()
    if section == "sleep":
        data = read_json_opt(os.path.join(user_dir, "sleep_history", "sleep_history.json")) or []
        return data[-days:]
    if section == "day":
        data = read_json_opt(os.path.join(user_dir, "day_history", "day_history.json")) or []
        return data[-days:]
    raise HTTPException(status_code=400, detail="section debe ser 'sleep' o 'day'")


@app.get("/api/profile-full")
def get_profile_full():
    user_id  = get_db_user_id()
    profile  = None
    if user_id and DB_AVAILABLE:
        try:
            from db import get_profile as db_get_profile
            profile = db_get_profile(user_id)
        except Exception as e:
            print(f"[DB] /api/profile-full fallback a JSON: {e}")
    user_dir = get_user_dir()
    if profile is None:
        profile = read_json_opt(os.path.join(user_dir, "profile.json"))
    return {
        "profile":  profile,
        "baseline": read_json_opt(os.path.join(user_dir, "performance_intelligence", "athlete_baseline.json")),
    }


@app.put("/api/profile")
def update_profile(body: dict[str, Any] = Body(...)):
    user_id  = get_db_user_id()
    user_dir = get_user_dir()
    path     = os.path.join(user_dir, "profile.json")

    # Si no hay user_id en DB, crearlo ahora (onboarding antes del primer sync)
    if not user_id and DB_AVAILABLE:
        try:
            from db import ensure_user
            email = _current_garmin_email.get()
            if email:
                user_id = ensure_user(email)
        except Exception:
            pass

    # Leer existente (DB primero, luego archivo)
    existing = None
    if user_id and DB_AVAILABLE:
        try:
            from db import get_profile as db_get_profile
            existing = db_get_profile(user_id)
        except Exception:
            pass
    if existing is None:
        existing = read_json_opt(path) or {}

    updated = {**existing, **body, "user_id": existing.get("user_id"), "garmin_email": existing.get("garmin_email")}

    # Guardar en DB
    if user_id and DB_AVAILABLE:
        try:
            from db import upsert_profile
            upsert_profile(user_id, updated)
        except Exception as e:
            print(f"[DB] Warning: no se pudo guardar perfil en PostgreSQL: {e}")

    # Guardar también en archivo (respaldo)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)

    return {"ok": True, "profile": updated}


@app.get("/api/sync-status")
def get_sync_status():
    return read_json_opt(os.path.join(BASE_DIR, "data", "sync_status.json")) or {"status": "idle"}


@app.get("/api/sync-log")
def get_sync_log():
    log_file = os.path.join(BASE_DIR, "data", "sync_log.txt")
    if not os.path.exists(log_file):
        return Response("(sin log)", media_type="text/plain; charset=utf-8")
    with open(log_file, encoding="utf-8") as f:
        return Response(f.read(), media_type="text/plain; charset=utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Apex Garmin Bridge — localhost:7845")
    print("=" * 50)

    if not os.path.exists(TOKENSTORE) or not os.listdir(TOKENSTORE):
        print("⚠  Sin tokens. Ejecuta primero:")
        print("   python garmin_save_tokens.py")
    else:
        print(f"OK Tokens encontrados en {TOKENSTORE}")

    print("Iniciando servidor...\n")
    uvicorn.run(app, host="0.0.0.0", port=7845, log_level="warning")
