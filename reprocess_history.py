"""
reprocess_history.py
--------------------
Reprocesa los análisis de día y sueño usando los raw JSONs ya guardados,
sin hacer ninguna llamada a la API de Garmin.

Uso:
    python reprocess_history.py --email tu@email.com
    python reprocess_history.py --email tu@email.com --only day
    python reprocess_history.py --email tu@email.com --only sleep
"""

import argparse
import json
import os


def setup(email):
    from app_context import set_current_garmin_email, get_current_user_id
    set_current_garmin_email(email)
    return get_current_user_id()


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip().strip("\x00")
    return json.loads(content) if content else None


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Reprocess día ───────────────────────────────────────────────────────────────
def reprocess_day(user_id, verbose=True):
    from app_context import get_day_dir, get_day_analysis_path, get_day_findings_path, get_day_history_dir
    from day_engine_v1 import compute_day_analysis, build_findings
    from day_history_engine import run_day_history_engine

    day_dir = get_day_dir(user_id)
    history_dir = get_day_history_dir(user_id)
    dates = sorted(os.listdir(day_dir)) if os.path.exists(day_dir) else []

    ok = skipped = errors = 0

    baselines = load_json(os.path.join(history_dir, "day_baselines.json"))

    for date_str in dates:
        date_dir = os.path.join(day_dir, date_str)
        raw_path    = os.path.join(date_dir, "day_raw.json")
        series_path = os.path.join(date_dir, "day_series.json")

        raw = load_json(raw_path)
        if not raw:
            skipped += 1
            continue

        series = load_json(series_path) or {}

        try:
            analysis = compute_day_analysis(
                raw_dump=raw,
                series=series,
                user_dir=os.path.dirname(day_dir),
                baselines=baselines,
            )

            if not analysis:
                skipped += 1
                continue

            quality = analysis.get("quality", {})
            if not quality.get("has_real_data", True):
                skipped += 1
                continue

            save_json(get_day_analysis_path(date_str, user_id), analysis)

            findings = build_findings(analysis, baselines=baselines)
            save_json(get_day_findings_path(date_str, user_id), findings)

            ok += 1
            if verbose:
                score  = analysis.get("recovery_summary", {}).get("overall_day_state_score", "?")
                energy = analysis.get("energy_dynamics", {}).get("energy_dynamics_score", "?")
                bb_s   = analysis.get("energy_dynamics", {}).get("body_battery_start", "?")
                bb_e   = analysis.get("energy_dynamics", {}).get("body_battery_end", "?")
                print(f"  [día] {date_str}  state={score}  energy={energy}  bb={bb_s}→{bb_e}")

        except Exception as e:
            errors += 1
            if verbose:
                print(f"  [día] {date_str} ERROR: {e}")

    if ok > 0:
        try:
            run_day_history_engine(base_day_dir=day_dir, out_history_dir=history_dir)
            print(f"\n  [day_history] Recalculado con {ok} días actualizados")
        except Exception as e:
            print(f"\n  [day_history] ERROR al recalcular: {e}")

    return ok, skipped, errors


# ── Reprocess sueño ─────────────────────────────────────────────────────────────
def reprocess_sleep(user_id, verbose=True):
    from app_context import get_sleep_dir, get_sleep_analysis_path, get_sleep_history_dir
    from sleep_engine_v1 import compute_analysis
    from sleep_history_engine import run_sleep_history_engine

    sleep_dir   = get_sleep_dir(user_id)
    history_dir = get_sleep_history_dir(user_id)
    dates = sorted(os.listdir(sleep_dir)) if os.path.exists(sleep_dir) else []

    ok = skipped = errors = 0

    baselines = load_json(os.path.join(history_dir, "sleep_baselines.json"))

    for date_str in dates:
        raw_path    = os.path.join(sleep_dir, date_str, "sleep_raw.json")
        series_path = os.path.join(sleep_dir, date_str, "sleep_series.json")

        raw = load_json(raw_path)
        if not raw:
            skipped += 1
            continue

        series = load_json(series_path) or {}

        try:
            analysis = compute_analysis(
                raw_dump=raw,
                series=series,
                user_dir=os.path.dirname(sleep_dir),
                baselines=baselines,
            )

            if not analysis:
                skipped += 1
                continue

            sleep_time = analysis.get("sleep_window", {}).get("sleep_time_seconds", 0) or 0
            if sleep_time < 3600:
                skipped += 1
                if verbose:
                    print(f"  [sueño] {date_str} SKIP — {sleep_time}s")
                continue

            save_json(get_sleep_analysis_path(date_str, user_id), analysis)

            ok += 1
            if verbose:
                score    = analysis.get("recovery_summary", {}).get("overall_recovery_score", "?")
                recharge = analysis.get("energy_recharge", {}).get("recharge_efficiency", "?")
                bb_end   = analysis.get("energy_recharge", {}).get("body_battery_end", "?")
                print(f"  [sueño] {date_str}  recovery={score}  recharge={recharge}  bb_wake={bb_end}")

        except Exception as e:
            errors += 1
            if verbose:
                print(f"  [sueño] {date_str} ERROR: {e}")

    if ok > 0:
        try:
            run_sleep_history_engine(sleep_dir, history_dir)
            print(f"\n  [sleep_history] Recalculado con {ok} noches actualizadas")
        except Exception as e:
            print(f"\n  [sleep_history] ERROR al recalcular: {e}")

    return ok, skipped, errors


# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--only", choices=["day", "sleep"], default=None)
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    user_id = setup(args.email)

    print(f"\n{'='*52}")
    print(f"REPROCESS HISTORY — {user_id}")
    print(f"{'='*52}\n")

    if args.only != "sleep":
        print("── DÍA ──────────────────────────────────────────────")
        ok, skip, err = reprocess_day(user_id)
        print(f"Resultado día:   {ok} OK | {skip} saltados | {err} errores\n")

    if args.only != "day":
        print("── SUEÑO ────────────────────────────────────────────")
        ok, skip, err = reprocess_sleep(user_id)
        print(f"Resultado sueño: {ok} OK | {skip} saltados | {err} errores\n")

    print("Listo. Corre home_menu.py para ver el historial actualizado.")


if __name__ == "__main__":
    main()
