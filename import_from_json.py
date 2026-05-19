"""
import_from_json.py
==================
Script ONE-TIME para importar todos los datos existentes (JSON) a PostgreSQL.
Itera sobre todos los usuarios y todas sus fechas.
Es idempotente: puedes correrlo varias veces sin duplicar datos (upsert).

Uso:
    python import_from_json.py
    python import_from_json.py --user abelgcanofuentes@hotmail.com   # solo un usuario
    python import_from_json.py --dry-run                              # muestra qué haría

Requiere: db_config.json configurado.
"""

import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "users"
SESSION  = BASE_DIR / "data" / "session.json"

def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def email_from_key(key: str) -> str:
    return key.replace("_at_", "@").replace("_", ".", 1) if "_at_" in key else key

def key_from_email(email: str) -> str:
    return email.strip().lower().replace("@", "_at_").replace(".", "_")

# ── Import por usuario ────────────────────────────────────────

def import_user(email_key: str, dry_run: bool) -> dict:
    from db import ensure_user, upsert_sleep_from_history_row, upsert_sleep, \
                   upsert_day_from_history_row, upsert_day, upsert_activity

    email    = email_from_key(email_key)
    user_dir = DATA_DIR / email_key
    stats    = {"sleep_history": 0, "sleep_rich": 0,
                "day_history": 0,   "day_rich": 0,
                "activities": 0,    "errors": 0}

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Usuario: {email}")

    if not dry_run:
        user_id = ensure_user(email)
        print(f"  user_id = {user_id}")
    else:
        user_id = 0

    # ── Sleep history (flat) ──────────────────────────────────
    sleep_hist_path = user_dir / "sleep_history" / "sleep_history.json"
    if sleep_hist_path.exists():
        rows = load_json(sleep_hist_path) or []
        print(f"  sleep_history: {len(rows)} filas")
        for row in rows:
            if not dry_run:
                try:
                    upsert_sleep_from_history_row(user_id, row)
                    stats["sleep_history"] += 1
                except Exception as e:
                    print(f"    ERROR sleep_history {row.get('calendar_date')}: {e}")
                    stats["errors"] += 1
            else:
                stats["sleep_history"] += 1

    # ── Sleep rich (analysis + brief + brief_ai por fecha) ────
    sleep_dir = user_dir / "sleep"
    if sleep_dir.exists():
        date_dirs = sorted(sleep_dir.iterdir())
        print(f"  sleep rich: {len(date_dirs)} fechas")
        for d in date_dirs:
            if not d.is_dir():
                continue
            analysis = load_json(d / "sleep_analysis.json")
            brief    = load_json(d / "sleep_brief.json")
            brief_ai = load_json(d / "sleep_brief_ai.json")
            if analysis or brief_ai:
                if not dry_run:
                    try:
                        upsert_sleep(user_id, d.name, analysis, brief, brief_ai)
                        stats["sleep_rich"] += 1
                    except Exception as e:
                        print(f"    ERROR sleep rich {d.name}: {e}")
                        stats["errors"] += 1
                else:
                    stats["sleep_rich"] += 1

    # ── Day history (flat) ────────────────────────────────────
    day_hist_path = user_dir / "day_history" / "day_history.json"
    if day_hist_path.exists():
        rows = load_json(day_hist_path) or []
        print(f"  day_history: {len(rows)} filas")
        for row in rows:
            if not dry_run:
                try:
                    upsert_day_from_history_row(user_id, row)
                    stats["day_history"] += 1
                except Exception as e:
                    print(f"    ERROR day_history {row.get('calendar_date')}: {e}")
                    stats["errors"] += 1
            else:
                stats["day_history"] += 1

    # ── Day rich ──────────────────────────────────────────────
    day_dir = user_dir / "day"
    if day_dir.exists():
        date_dirs = sorted(day_dir.iterdir())
        print(f"  day rich: {len(date_dirs)} fechas")
        for d in date_dirs:
            if not d.is_dir():
                continue
            analysis = load_json(d / "day_analysis.json")
            brief_ai = load_json(d / "day_brief_ai.json")
            if analysis:
                if not dry_run:
                    try:
                        upsert_day(user_id, d.name, analysis, brief_ai)
                        stats["day_rich"] += 1
                    except Exception as e:
                        print(f"    ERROR day rich {d.name}: {e}")
                        stats["errors"] += 1
                else:
                    stats["day_rich"] += 1

    # ── Activities ────────────────────────────────────────────
    act_dir = user_dir / "activities"
    if act_dir.exists():
        act_dirs = sorted(act_dir.iterdir())
        print(f"  activities: {len(act_dirs)} actividades")
        for d in act_dirs:
            if not d.is_dir():
                continue
            analysis = load_json(d / "activity_analysis.json")
            brief    = load_json(d / "activity_brief.json")
            if analysis:
                if not dry_run:
                    try:
                        upsert_activity(user_id, analysis, brief)
                        stats["activities"] += 1
                    except Exception as e:
                        print(f"    ERROR activity {d.name}: {e}")
                        stats["errors"] += 1
                else:
                    stats["activities"] += 1

    return stats

# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Importa JSONs a PostgreSQL")
    parser.add_argument("--user",    help="Email del usuario a importar (todos si se omite)")
    parser.add_argument("--dry-run", action="store_true", help="No escribe, solo cuenta")
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(f"ERROR: No existe {DATA_DIR}")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN — no se escribirá nada en la base de datos ===")

    # Seleccionar usuarios
    if args.user:
        user_keys = [key_from_email(args.user)]
        if not (DATA_DIR / user_keys[0]).exists():
            print(f"ERROR: No existe directorio para {args.user}")
            sys.exit(1)
    else:
        user_keys = [d.name for d in DATA_DIR.iterdir() if d.is_dir()]

    total = {"sleep_history": 0, "sleep_rich": 0,
             "day_history": 0,   "day_rich": 0,
             "activities": 0,    "errors": 0}

    for key in user_keys:
        stats = import_user(key, args.dry_run)
        for k, v in stats.items():
            total[k] += v

    print("\n" + "="*50)
    print("RESUMEN FINAL")
    print(f"  sleep_history rows : {total['sleep_history']}")
    print(f"  sleep rich (JSON)  : {total['sleep_rich']}")
    print(f"  day_history rows   : {total['day_history']}")
    print(f"  day rich (JSON)    : {total['day_rich']}")
    print(f"  activities         : {total['activities']}")
    print(f"  errores            : {total['errors']}")
    if total["errors"] == 0:
        print("\n✓ Importación completa sin errores.")
    else:
        print(f"\n⚠ {total['errors']} errores — revisa los mensajes arriba.")

if __name__ == "__main__":
    main()
