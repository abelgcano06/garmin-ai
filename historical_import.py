"""
historical_import.py
====================
Importa hasta 90 días de datos históricos para un usuario nuevo.

Qué hace:
  1. Sueño:      descarga y procesa N días hacia atrás (sin AI)
  2. Día:        descarga y procesa N días hacia atrás (sin AI)
  3. Actividades: descarga y procesa todas las actividades en el rango (sin AI)
  4. Histories:  re-corre sleep_history + day_history + activity_history con
                 todos los datos ya procesados para generar baselines limpios

Diseño:
  - Saltea fechas ya procesadas (reanudable si se interrumpe)
  - Pausa breve entre llamadas para no saturar la API de Garmin
  - Corre sin AI para que sea rápido y no cueste tokens
  - Al final corre todos los history engines para tener baselines completos

Uso:
    python historical_import.py --email tu@email.com
    python historical_import.py --email tu@email.com --days 60
"""

import os
import time
import argparse
from datetime import date, timedelta

from app_context import (
    set_current_garmin_email,
    ensure_current_user_profile,
    get_current_user_id,
    get_sleep_analysis_path,
    get_day_analysis_path,
    get_activity_analysis_path,
    get_sleep_dir,
    get_sleep_history_dir,
    get_day_dir,
    get_day_history_dir,
)


# =========================================================
# Config
# =========================================================

SLEEP_DELAY_S   = 0.8   # pausa entre llamadas de sueño
DAY_DELAY_S     = 0.8   # pausa entre llamadas de día
ACTIVITY_DELAY_S = 1.2  # pausa entre actividades (más datos por llamada)


# =========================================================
# Helpers
# =========================================================

def _date_range(days_back):
    """Lista de fechas desde hoy-days_back hasta ayer, en orden cronológico."""
    today = date.today()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(1, days_back + 1)]
    return list(reversed(dates))  # del más viejo al más nuevo


def _already_processed(path):
    return os.path.exists(path)


def _print_progress(current, total, label=""):
    pct = int(current / total * 100) if total else 0
    bar = ("█" * (pct // 5)).ljust(20)
    print(f"  [{bar}] {pct:3d}%  {current}/{total}  {label}", end="\r")


# =========================================================
# Importar sueño
# =========================================================

def import_sleep(client, user_id, dates, verbose=True):
    from sleep_full_flow import run_sleep_full_flow

    total   = len(dates)
    ok      = 0
    skipped = 0
    errors  = 0

    if verbose:
        print(f"\n[SUEÑO] Importando {total} noches...")

    for i, date_str in enumerate(dates):
        analysis_path = get_sleep_analysis_path(date_str, user_id)

        if _already_processed(analysis_path):
            skipped += 1
            if verbose:
                _print_progress(i + 1, total, f"{date_str} — ya existe")
            continue

        if verbose:
            _print_progress(i + 1, total, f"procesando {date_str}...")

        try:
            result = run_sleep_full_flow(
                client, date_str,
                user_id=user_id,
                run_history=False,   # al final se corre uno solo para todo
                run_ai=False,        # sin AI en import masivo
                verbose=False,
            )
            if result:
                ok += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            if verbose:
                print(f"\n  [!] {date_str}: {e}")

        time.sleep(SLEEP_DELAY_S)

    if verbose:
        print(f"\n  → {ok} procesadas | {skipped} ya existían | {errors} errores")

    return {"ok": ok, "skipped": skipped, "errors": errors}


# =========================================================
# Importar día
# =========================================================

def import_day(client, user_id, dates, verbose=True):
    from day_full_flow import run_day_full_flow

    total   = len(dates)
    ok      = 0
    skipped = 0
    errors  = 0

    if verbose:
        print(f"\n[DÍA] Importando {total} días...")

    for i, date_str in enumerate(dates):
        analysis_path = get_day_analysis_path(date_str, user_id)

        if _already_processed(analysis_path):
            skipped += 1
            if verbose:
                _print_progress(i + 1, total, f"{date_str} — ya existe")
            continue

        if verbose:
            _print_progress(i + 1, total, f"procesando {date_str}...")

        try:
            result = run_day_full_flow(
                client, date_str,
                user_id=user_id,
                run_history=False,
                run_ai=False,
                verbose=False,
            )
            if result:
                ok += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            if verbose:
                print(f"\n  [!] {date_str}: {e}")

        time.sleep(DAY_DELAY_S)

    if verbose:
        print(f"\n  → {ok} procesados | {skipped} ya existían | {errors} errores")

    return {"ok": ok, "skipped": skipped, "errors": errors}


# =========================================================
# Importar actividades
# =========================================================

def import_activities(client, user_id, days_back, verbose=True):
    from activity_full_flow import run_activity_full_flow

    today     = date.today()
    start_str = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end_str   = today.strftime("%Y-%m-%d")

    if verbose:
        print(f"\n[ACTIVIDADES] Buscando actividades entre {start_str} y {end_str}...")

    try:
        activities = client.get_activities_by_date(start_str, end_str)
    except Exception as e:
        if verbose:
            print(f"  [!] Error jalando actividades: {e}")
        return {"ok": 0, "skipped": 0, "errors": 1}

    if not activities:
        if verbose:
            print("  Sin actividades en el rango.")
        return {"ok": 0, "skipped": 0, "errors": 0}

    total   = len(activities)
    ok      = 0
    skipped = 0
    errors  = 0

    if verbose:
        print(f"  Encontradas: {total} actividades")

    for i, activity in enumerate(activities):
        activity_id   = activity.get("activityId")
        activity_name = activity.get("activityName", "Sin nombre")
        analysis_path = get_activity_analysis_path(activity_id, user_id)

        if _already_processed(analysis_path):
            skipped += 1
            if verbose:
                _print_progress(i + 1, total, f"{activity_name} — ya existe")
            continue

        if verbose:
            _print_progress(i + 1, total, f"procesando: {activity_name}...")

        try:
            result = run_activity_full_flow(client, activity, user_id=user_id)
            if result is not None:
                ok += 1
            else:
                skipped += 1  # filtro de calidad (< 10 min)
        except Exception as e:
            errors += 1
            if verbose:
                print(f"\n  [!] {activity_name}: {e}")

        time.sleep(ACTIVITY_DELAY_S)

    if verbose:
        print(f"\n  → {ok} procesadas | {skipped} ya existían/inválidas | {errors} errores")

    return {"ok": ok, "skipped": skipped, "errors": errors}


# =========================================================
# Re-correr history engines
# =========================================================

def rebuild_histories(user_id, verbose=True):
    if verbose:
        print("\n[HISTORIES] Reconstruyendo baselines y tendencias...")

    # Sleep history
    try:
        from sleep_history_engine import run_sleep_history_engine
        base_sleep_dir = get_sleep_dir(user_id)
        out_sleep_dir  = get_sleep_history_dir(user_id)
        run_sleep_history_engine(base_sleep_dir, out_sleep_dir)
        if verbose:
            print("  [OK] sleep_history + baselines + trends")
    except Exception as e:
        if verbose:
            print(f"  [!] sleep_history: {e}")

    # Day history
    try:
        from day_history_engine import run_day_history_engine
        base_day_dir = get_day_dir(user_id)
        out_day_dir  = get_day_history_dir(user_id)
        run_day_history_engine(base_day_dir, out_day_dir)
        if verbose:
            print("  [OK] day_history + baselines + trends")
    except Exception as e:
        if verbose:
            print(f"  [!] day_history: {e}")

    # Activity history
    try:
        from activity_history_engine import run_activity_history_engine
        run_activity_history_engine(user_id=user_id)
        if verbose:
            print("  [OK] activity_history + baselines + trends")
    except Exception as e:
        if verbose:
            print(f"  [!] activity_history: {e}")

    # Master engine (readiness + correlaciones con toda la data)
    try:
        from master_engine import run_master_engine
        from app_context import get_user_root
        from datetime import date, timedelta
        user_dir  = get_user_root(user_id)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        run_master_engine(user_dir, target_date=yesterday)
        if verbose:
            print("  [OK] master_engine (readiness + correlaciones)")
    except Exception as e:
        if verbose:
            print(f"  [!] master_engine: {e}")


# =========================================================
# Flujo principal
# =========================================================

def run_historical_import(client, user_id=None, days_back=90, verbose=True):
    user_id = user_id or get_current_user_id()
    dates   = _date_range(days_back)

    if verbose:
        print("\n" + "=" * 50)
        print("HISTORICAL IMPORT")
        print("=" * 50)
        print(f"Usuario:  {user_id}")
        print(f"Período:  últimos {days_back} días ({dates[0]} → {dates[-1]})")
        print("=" * 50)

    results = {}

    results["sleep"]      = import_sleep(client, user_id, dates, verbose=verbose)
    results["day"]        = import_day(client, user_id, dates, verbose=verbose)
    results["activities"] = import_activities(client, user_id, days_back, verbose=verbose)

    rebuild_histories(user_id, verbose=verbose)

    if verbose:
        print("\n" + "=" * 50)
        print("HISTORICAL IMPORT TERMINADO")
        print("=" * 50)
        s = results["sleep"]
        d = results["day"]
        a = results["activities"]
        print(f"Sueño:      {s['ok']} procesadas, {s['skipped']} existían, {s['errors']} errores")
        print(f"Día:        {d['ok']} procesados, {d['skipped']} existían, {d['errors']} errores")
        print(f"Actividades:{a['ok']} procesadas, {a['skipped']} existían, {a['errors']} errores")
        print("Baselines, tendencias y master engine actualizados.")
        print("=" * 50 + "\n")

    return results


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa historial de 90 días para un usuario nuevo.")
    parser.add_argument("--email",    required=True,        help="Email Garmin del usuario")
    parser.add_argument("--password", required=True,        help="Password Garmin")
    parser.add_argument("--days",     type=int, default=90, help="Días hacia atrás (default: 90)")
    parser.add_argument("--ftp",      type=int, default=None, help="FTP en vatios (ej: 215)")
    parser.add_argument("--max_hr",   type=int, default=None, help="Frecuencia cardiaca máxima (ej: 182)")
    args = parser.parse_args()

    set_current_garmin_email(args.email)
    ensure_current_user_profile(garmin_email=args.email, ftp=args.ftp, max_hr=args.max_hr)
    user_id = get_current_user_id()

    from garminconnect import Garmin
    client = Garmin(args.email, args.password)
    client.login()
    print(f"[OK] Login Garmin: {args.email}")

    run_historical_import(client, user_id=user_id, days_back=args.days)
