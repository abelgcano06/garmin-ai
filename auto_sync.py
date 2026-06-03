"""
auto_sync.py
============
Corre automáticamente después del login.
Mantiene todos los datos frescos sin que el usuario tenga que hacer nada.

Qué hace:
  1. Sueño: escanea 90 días, procesa todas las noches faltantes
  2. Día:   escanea 90 días, procesa todos los días faltantes + hoy siempre
  3. Actividades: recupera hasta 90 días atrás según el último registro
  4. Master engine (readiness + correlaciones)

El usuario nunca ve esto — solo ve "Sincronizando..." y listo.
"""

import json
import os
from datetime import date, timedelta

from app_context import get_current_user_id, get_user_root
from sleep_full_flow import run_sleep_full_flow
from master_engine import run_master_engine
from ftp_engine import run_ftp_engine
from profile_intelligence import run_profile_intelligence


# =========================================================
# Sync sueño
# =========================================================

def sync_sleep(client, user_id, verbose=True):
    """
    Escanea los últimos 90 días completos y procesa cualquier noche que no tenga
    sleep_analysis.json. Garantiza que el usuario siempre tenga 90 días al corriente
    sin importar cuántos días no abrió la app.
    """
    from app_context import get_sleep_analysis_path
    from sleep_history_engine import run_sleep_history_engine
    from app_context import get_sleep_dir, get_sleep_history_dir

    today = date.today()
    today_str = today.isoformat()

    # Si el usuario no tiene ningún dato todavía (primer login), limitar a 30 días
    # para que la app cargue rápido. Los 90 días completos se llenan en syncs posteriores.
    from app_context import get_sleep_dir
    sleep_root = get_sleep_dir(user_id)
    is_new_user = not os.path.exists(sleep_root) or not any(
        os.path.isdir(os.path.join(sleep_root, d)) for d in os.listdir(sleep_root)
        if os.path.isdir(os.path.join(sleep_root, d))
    ) if os.path.exists(sleep_root) else True
    scan_days = 30 if is_new_user else 90

    if verbose and is_new_user:
        print(f"  [sueño] Primer login — backfill limitado a {scan_days} días para inicio rápido")

    # Escanear días y recolectar TODOS los que faltan.
    # No se corta al primer día encontrado — un gap en el medio también se llena.
    # El orden es cronológico (más antiguo primero) para que el historial sea coherente.
    dates_to_process = []
    for i in range(scan_days, -1, -1):   # scan_days atrás → hoy
        d = (today - timedelta(days=i)).isoformat()
        analysis_path = get_sleep_analysis_path(d, user_id)
        if not os.path.exists(analysis_path):
            dates_to_process.append(d)
        elif d == today_str:
            # Hoy siempre se re-procesa: el sueño de esta noche es parcial
            dates_to_process.append(d)

    if not dates_to_process:
        if verbose:
            print("  [sueño] Todo al corriente — sin noches faltantes")
        return {"skipped": True, "date": today_str, "processed": 0, "errors": 0}

    if verbose:
        print(f"  [sueño] {len(dates_to_process)} noches pendientes...")

    processed, errors = 0, 0

    for sleep_date in dates_to_process:
        if verbose:
            print(f"  [sueño] Procesando {sleep_date}...")
        try:
            result = run_sleep_full_flow(
                client,
                sleep_date,
                user_id=user_id,
                run_history=False,   # se reconstruye una sola vez al final
                run_ai=False,        # on-demand cuando el usuario abre ese día
                run_charts=False,    # los charts PNG no se usan en el frontend
                verbose=False,
            )
            if result:
                processed += 1
                if verbose:
                    score = result.get("analysis", {}).get("recovery_summary", {}).get("overall_recovery_score", "?")
                    print(f"  [sueño] OK {sleep_date} — recovery: {score}")
            else:
                if verbose:
                    print(f"  [sueño] Sin datos para {sleep_date} (Garmin no registró noche)")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  [sueño] ERROR {sleep_date}: {e}")

    # Reconstruir historial una sola vez con todos los días ya procesados
    if processed > 0:
        try:
            run_sleep_history_engine(
                base_sleep_dir=get_sleep_dir(user_id),
                out_history_dir=get_sleep_history_dir(user_id),
            )
            if verbose:
                print("  [sueño] Historial reconstruido")
        except Exception as e:
            if verbose:
                print(f"  [sueño] WARNING historial: {e}")

    if verbose:
        print(f"  [sueño] Completado — {processed} nuevas, {errors} errores")

    return {
        "skipped": processed == 0,
        "date": today_str,
        "processed": processed,
        "errors": errors,
    }


# =========================================================
# Sync día
# =========================================================

def sync_day(client, user_id, verbose=True):
    """
    Escanea los últimos 90 días completos y procesa cualquier día que no tenga
    day_analysis.json. Hoy siempre se re-procesa (datos en tiempo real).
    Reconstruye el historial una sola vez al final.
    """
    from app_context import get_day_analysis_path, get_day_dir, get_day_history_dir
    from day_full_flow import run_day_full_flow
    from day_history_engine import run_day_history_engine

    today = date.today()
    today_str = today.isoformat()

    # Recolectar TODOS los días faltantes en los últimos 90 días (más antiguo primero).
    # Hoy siempre se procesa aunque ya exista — los datos cambian durante el día.
    dates_to_process = []
    for i in range(89, 0, -1):          # 89 días atrás → ayer
        d = (today - timedelta(days=i)).isoformat()
        if not os.path.exists(get_day_analysis_path(d, user_id)):
            dates_to_process.append(d)
    dates_to_process.append(today_str)  # hoy siempre al final

    if verbose:
        backfill_count = len(dates_to_process) - 1   # sin contar hoy
        if backfill_count:
            print(f"  [día]   {backfill_count} día(s) pendiente(s) + hoy...")
        else:
            print(f"  [día]   Procesando estado de hoy {today_str}...")

    processed, errors = 0, 0

    for day_date in dates_to_process:
        try:
            result = run_day_full_flow(
                client,
                day_date,
                user_id=user_id,
                run_history=False,   # se reconstruye una sola vez al final
                run_ai=False,        # on-demand cuando el usuario abre ese día
                run_charts=False,    # los charts PNG no se usan en el frontend
                verbose=False,
            )
            if result:
                processed += 1
                if verbose:
                    score = result.get("analysis", {}).get("recovery_summary", {}).get("overall_day_state_score", "?")
                    label = "hoy" if day_date == today_str else day_date
                    print(f"  [día]   OK {label} — score: {score}")
            else:
                if verbose:
                    print(f"  [día]   Sin datos para {day_date} (Garmin no tiene registro)")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  [día]   ERROR {day_date}: {e}")

    # Reconstruir historial una sola vez con todos los días ya procesados
    if processed > 0:
        try:
            run_day_history_engine(
                base_day_dir=get_day_dir(user_id),
                out_history_dir=get_day_history_dir(user_id),
            )
            if verbose:
                print("  [día]   Historial reconstruido")
        except Exception as e:
            if verbose:
                print(f"  [día]   WARNING historial: {e}")

    if verbose:
        print(f"  [día]   Completado — {processed} procesados, {errors} errores")

    return {"skipped": processed == 0, "date": today_str, "processed": processed, "errors": errors}


# =========================================================
# Sync actividades
# =========================================================

def sync_activities(client, user_id, days_back=7, verbose=True):
    """
    Jala actividades de los últimos N días.
    Solo procesa las que no tienen activity_analysis.json todavía.
    """
    from app_context import get_activity_analysis_path
    from activity_full_flow import run_activity_full_flow

    if verbose:
        print(f"  [acts]  Buscando actividades de los últimos {days_back} días...")

    today     = date.today()
    start_str = (today - timedelta(days=days_back - 1)).strftime("%Y-%m-%d")
    end_str   = today.strftime("%Y-%m-%d")

    try:
        activities = client.get_activities_by_date(start_str, end_str)
    except Exception as e:
        if verbose:
            print(f"  [acts]  ERROR jalando actividades: {e}")
        return []

    if not activities:
        if verbose:
            print(f"  [acts]  Sin actividades en los últimos {days_back} días")
        return []

    results = []
    new_count = 0
    skip_count = 0

    # IDs ya en PostgreSQL para este usuario
    db_activity_ids = set()
    try:
        from db import get_conn, ensure_user
        from app_context import get_current_garmin_email
        email = get_current_garmin_email()
        db_uid = ensure_user(email)
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT garmin_activity_id FROM activities WHERE user_id = %s", (db_uid,))
                db_activity_ids = {str(r[0]) for r in cur.fetchall()}
        finally:
            conn.close()
    except Exception:
        pass

    for activity in activities:
        activity_id = activity.get("activityId")
        analysis_path = get_activity_analysis_path(activity_id, user_id)
        already_in_db = str(activity_id) in db_activity_ids

        if os.path.exists(analysis_path):
            # JSON existe — si ya está en DB, saltar; si no, escribir a DB
            if already_in_db:
                skip_count += 1
                continue
            # Está en disco pero no en DB — upsert sin reprocesar
            try:
                analysis = json.load(open(analysis_path, encoding="utf-8"))
                brief_path = analysis_path.replace("activity_analysis.json", "activity_brief.json")
                brief = json.load(open(brief_path, encoding="utf-8")) if os.path.exists(brief_path) else None
                from db import upsert_activity
                upsert_activity(db_uid, analysis, brief)
                skip_count += 1
                if verbose:
                    print(f"  [acts]  DB sync: {activity.get('activityName', activity_id)}")
            except Exception as e:
                if verbose:
                    print(f"  [acts]  DB sync ERROR {activity_id}: {e}")
            continue

        name = activity.get("activityName", "Sin nombre")
        if verbose:
            print(f"  [acts]  Nueva actividad: {name}")

        try:
            run_activity_full_flow(client, activity, user_id=user_id, run_ai=False, run_charts=False)
            results.append({"activity_id": activity_id, "name": name, "ok": True})
            new_count += 1
        except Exception as e:
            if verbose:
                print(f"  [acts]  ERROR en {name}: {e}")
            results.append({"activity_id": activity_id, "name": name, "ok": False, "error": str(e)})

    if verbose:
        print(f"  [acts]  {new_count} nuevas procesadas, {skip_count} ya existían")

    return results


# =========================================================
# Sync master
# =========================================================

def sync_master(user_id, verbose=True):
    """
    Corre el master engine con todos los datos actualizados.
    Calcula readiness, correlaciones y pesos dinámicos.
    """
    user_dir  = get_user_root(user_id)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    if verbose:
        print(f"  [master] Calculando readiness y correlaciones...")

    try:
        result = run_master_engine(user_dir, target_date=yesterday)
        if verbose and result:
            brief = result.get("master_brief")
            if brief:
                score = brief.get("readiness_score", "?")
                label = brief.get("readiness_label", "?")
                print(f"  [master] OK — readiness: {score}/100 ({label})")
        return result
    except Exception as e:
        if verbose:
            print(f"  [master] ERROR: {e}")
        return None


# =========================================================
# AUTO SYNC PRINCIPAL
# =========================================================

def run_auto_sync(client, user_id=None, verbose=True):
    """
    Punto de entrada principal. Se llama justo después del login.
    Sincroniza todo en orden y retorna un resumen.
    """
    user_id = user_id or get_current_user_id()

    if verbose:
        print("\n===================================")
        print("SINCRONIZANDO TUS DATOS...")
        print("===================================")

    results = {}

    # 1) Sueño de anoche
    results["sleep"] = sync_sleep(client, user_id, verbose=verbose)

    # 2) Estado del día de hoy
    results["day"] = sync_day(client, user_id, verbose=verbose)

    # 3) Actividades nuevas — calcular cuántos días hay que recuperar
    user_dir = get_user_root(user_id)
    import json as _json
    _index_path = os.path.join(user_dir, "activity_index.json")
    _days_back = 30  # default si no hay historial
    if os.path.exists(_index_path):
        try:
            _raw = _json.load(open(_index_path, encoding="utf-8"))
            _acts = _raw.get("activities", _raw) if isinstance(_raw, dict) else _raw
            _dates = [a.get("date", "")[:10] for a in _acts if a.get("date")]
            if _dates:
                from datetime import datetime as _dt
                _last = _dt.strptime(max(_dates), "%Y-%m-%d").date()
                _days_back = max(7, min((date.today() - _last).days + 2, 90))
        except Exception:
            pass
    results["activities"] = sync_activities(client, user_id, days_back=_days_back, verbose=verbose)

    # 4) Master engine
    results["master"] = sync_master(user_id, verbose=verbose)

    # 5) FTP engine
    user_dir = get_user_root(user_id)
    try:
        ftp = run_ftp_engine(user_dir)
        results["ftp"] = ftp
    except Exception as e:
        if verbose:
            print(f"  [ftp] ERROR: {e}")

    # 6) Profile intelligence — actualiza athlete_baseline con datos frescos
    profile_path = os.path.join(user_dir, "profile.json")
    if os.path.exists(profile_path):
        try:
            baseline = run_profile_intelligence(user_dir)
            results["profile_baseline"] = baseline
        except Exception as e:
            if verbose:
                print(f"  [profile_intelligence] ERROR: {e}")

    if verbose:
        print("===================================")
        print("SYNC COMPLETADO")
        print("===================================\n")

    return results