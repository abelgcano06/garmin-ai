"""
run_sync.py
===========
Script CLI que sincroniza todos los datos pendientes desde la última
fecha procesada hasta hoy. Diseñado para ser lanzado desde Next.js
via subprocess o ejecutado directamente en terminal.

Detecta automáticamente cuántos días hay que recuperar.
Escribe data/sync_status.json con progreso en tiempo real.
Imprime resultado JSON a stdout al finalizar.

Uso:
    python run_sync.py
    python run_sync.py --days_back 30   # forzar rango
"""

import json
import os
import sys
import argparse
from datetime import date, timedelta, datetime

# Ruta base del proyecto Python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from garmin_auth import login_garmin
from app_context import (
    get_current_user_id, get_user_root,
    set_current_garmin_email, ensure_current_user_profile,
)
from auto_sync import sync_sleep, sync_day, sync_activities, sync_master
from ftp_engine import run_ftp_engine
from profile_intelligence import run_profile_intelligence

DEFAULT_STATUS_FILE = os.path.join(BASE_DIR, "data", "sync_status.json")
DEFAULT_SESSION_FILE = os.path.join(BASE_DIR, "data", "session.json")


# ─── helpers ─────────────────────────────────────────────────────────────────

def write_status(data: dict):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def calculate_days_back(user_id: str) -> int:
    """
    Calcula cuántos días buscar en Garmin.
    Fuente de verdad: PostgreSQL. Si no hay actividades en DB, usa 90 días.
    Mínimo 14, máximo 90.
    """
    days_back = 90  # default para usuario nuevo

    try:
        from db import get_conn, ensure_user
        from app_context import get_current_garmin_email
        email = get_current_garmin_email()
        db_uid = ensure_user(email)
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT MAX(start_date)::text FROM activities WHERE user_id = %s
                """, (db_uid,))
                row = cur.fetchone()
                latest = row[0] if row and row[0] else None
        finally:
            conn.close()

        if latest:
            last_dt = datetime.strptime(latest, "%Y-%m-%d").date()
            days_since = (date.today() - last_dt).days
            days_back = max(14, min(days_since + 2, 90))
            print(f"  [sync]  Última actividad en DB: {latest} ({days_since} días) -> buscando {days_back} días")
        else:
            print(f"  [sync]  Sin actividades en DB -> buscando {days_back} días")
    except Exception as e:
        print(f"  [sync]  Error calculando days_back: {e} -> usando {days_back} días")

    return days_back


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days_back", type=int, default=None, help="Forzar rango de días a buscar")
    parser.add_argument("--log-file", default=None, help="Redirigir stdout/stderr a este archivo")
    parser.add_argument("--sections", default="sleep,day,activities,master,ftp,profile",
                        help="Secciones a sincronizar separadas por coma")
    parser.add_argument("--session-file", default=None, help="Ruta al archivo de credenciales del usuario")
    parser.add_argument("--status-file", default=None, help="Ruta al archivo de estado de sincronización")
    args = parser.parse_args()
    sections = set(s.strip() for s in args.sections.split(","))

    session_file = args.session_file or DEFAULT_SESSION_FILE
    status_file = args.status_file or DEFAULT_STATUS_FILE

    # Override write_status to use the correct status file for this user
    global write_status
    def write_status(data: dict):  # noqa: F811
        os.makedirs(os.path.dirname(os.path.abspath(status_file)), exist_ok=True)
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Redirect output to log file when launched from Next.js
    if args.log_file:
        log_fh = open(args.log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = log_fh
        sys.stderr = log_fh

    # 1) Leer credenciales
    if not os.path.exists(session_file):
        write_status({"status": "error", "message": "No hay sesión guardada. Inicia sesión primero."})
        print(json.dumps({"ok": False, "error": "No session file"}))
        sys.exit(1)

    try:
        session = json.load(open(session_file, encoding="utf-8"))
    except Exception:
        write_status({"status": "error", "message": "No se pudo leer session.json."})
        print(json.dumps({"ok": False, "error": "Cannot read session"}))
        sys.exit(1)

    email = session.get("email", "").strip()
    password = session.get("password", "").strip()

    if not email or not password:
        write_status({"status": "error", "message": "Credenciales incompletas en sesion.json."})
        print(json.dumps({"ok": False, "error": "Missing credentials"}))
        sys.exit(1)

    write_status({
        "status": "running",
        "step": "Conectando con Garmin...",
        "started_at": datetime.now().isoformat(),
    })

    # 2) Login Garmin
    print("  [sync]  Conectando con Garmin...")
    client = login_garmin(email, password)
    if not client:
        write_status({"status": "error", "message": "No se pudo conectar con Garmin. Verifica tus credenciales."})
        print(json.dumps({"ok": False, "error": "Garmin login failed"}))
        sys.exit(1)

    set_current_garmin_email(email)
    ensure_current_user_profile(garmin_email=email)
    user_id = get_current_user_id()
    print(f"  [sync]  Usuario: {user_id}")

    results = {
        "ok": True,
        "user_id": user_id,
        "started_at": datetime.now().isoformat(),
        "steps": {},
    }

    # 3) Calcular rango de días
    days_back = args.days_back or calculate_days_back(user_id)

    write_status({
        "status": "running",
        "step": f"Buscando actividades de los ultimos {days_back} dias...",
        "days_back": days_back,
    })

    user_dir = get_user_root(user_id)

    # 4a) FTP pre-sync: actualizar ftp_apex en profile.json ANTES de analizar
    #     para que las actividades nuevas usen el FTP más reciente disponible
    write_status({"status": "running", "step": "Actualizando FTP previo al análisis..."})
    try:
        run_ftp_engine(user_dir)
        print("  [sync]  FTP pre-sync completado")
    except Exception as e:
        print(f"  [sync]  FTP pre-sync WARNING: {e}")

    now_iso = datetime.now().isoformat()
    # Leer secciones previas del status para preservar timestamps
    prev_status = {}
    if os.path.exists(status_file):
        try:
            prev_status = json.load(open(status_file, encoding="utf-8"))
        except Exception:
            pass
    section_ts = prev_status.get("sections", {})

    # 4b) Actividades
    new_acts = 0
    if "activities" in sections:
        acts = sync_activities(client, user_id, days_back=days_back, verbose=True)
        new_acts = sum(1 for a in acts if a.get("ok"))
        results["steps"]["activities"] = {
            "new": new_acts,
            "total_checked": len(acts),
            "details": [{"name": a.get("name"), "ok": a.get("ok")} for a in acts],
        }
        section_ts["activities"] = {"last_synced": now_iso, "new_found": new_acts}
    else:
        print("  [sync]  Actividades: omitidas")

    # 5) Sueño
    if "sleep" in sections:
        write_status({"status": "running", "step": "Procesando sueno...", "new_activities": new_acts})
        sleep_res = sync_sleep(client, user_id, verbose=True)
        results["steps"]["sleep"] = {
            "skipped": sleep_res.get("skipped", False),
            "date": sleep_res.get("date"),
            "error": sleep_res.get("error"),
        }
        section_ts["sleep"] = {"last_synced": now_iso, "date": sleep_res.get("date")}
    else:
        print("  [sync]  Sueño: omitido")

    # 6) Día
    if "day" in sections:
        write_status({"status": "running", "step": "Procesando estado del dia..."})
        day_res = sync_day(client, user_id, verbose=True)
        results["steps"]["day"] = {
            "skipped": day_res.get("skipped", False),
            "date": day_res.get("date"),
            "error": day_res.get("error"),
        }
        section_ts["day"] = {"last_synced": now_iso, "date": day_res.get("date")}
    else:
        print("  [sync]  Día: omitido")

    # 7) Master
    if "master" in sections:
        write_status({"status": "running", "step": "Calculando readiness y correlaciones..."})
        master_res = sync_master(user_id, verbose=True)
        results["steps"]["master"] = {"ok": master_res is not None}
        section_ts["master"] = {"last_synced": now_iso}
    else:
        print("  [sync]  Master: omitido")

    # 8) FTP
    if "ftp" in sections:
        write_status({"status": "running", "step": "Recalculando FTP con nuevas actividades..."})
        try:
            ftp_result = run_ftp_engine(user_dir)
            achievements = ftp_result.get("achievements", []) if ftp_result else []
            results["steps"]["ftp"] = {
                "ok": True,
                "ftp_current": ftp_result.get("ftp_current") if ftp_result else None,
                "ftp_improved": ftp_result.get("ftp_improved", False) if ftp_result else False,
                "achievements": achievements,
            }
            if achievements:
                print(f"  [sync]  🏆 {len(achievements)} logro(s): {[a['title'] for a in achievements]}")
            print("  [sync]  FTP actualizado")
        except Exception as e:
            results["steps"]["ftp"] = {"ok": False, "error": str(e)}
            print(f"  [sync]  FTP ERROR: {e}")
        section_ts["ftp"] = {"last_synced": now_iso}

    # 9) Profile
    profile_path = os.path.join(user_dir, "profile.json")
    if "profile" in sections and os.path.exists(profile_path):
        try:
            run_profile_intelligence(user_dir)
            results["steps"]["profile"] = {"ok": True}
            print("  [sync]  Perfil actualizado")
        except Exception as e:
            results["steps"]["profile"] = {"ok": False, "error": str(e)}
            print(f"  [sync]  Profile ERROR: {e}")
        section_ts["profile"] = {"last_synced": now_iso}

    # 10) Finalizar
    finished_at = datetime.now().isoformat()
    results["finished_at"] = finished_at

    all_achievements = results.get("steps", {}).get("ftp", {}).get("achievements", [])
    write_status({
        "status": "done",
        "finished_at": finished_at,
        "new_activities": new_acts,
        "days_back": days_back,
        "achievements": all_achievements,
        "sections": section_ts,
    })

    print(f"\n  [sync]  Completado — {new_acts} actividades nuevas")
    print(json.dumps(results, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
