"""
reanalyze_all.py
================
Re-calcula derived_summary para todas las actividades existentes usando
la lógica actualizada (compute_np con ventanas 30s reales + estimated_tss).
NO toca garmin_summary ni ningún otro campo — solo reemplaza derived_summary.

Uso:
    python reanalyze_all.py
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from activity_analyzer import (
    read_activity_series,
    build_derived_summary,
    add_msi_to_rows,
)
from fatigue_analysis_v2 import build_fatigue_report
from metabolic_index import summarize_msi
from performance_scores import build_performance_scores
from app_context import get_user_root


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def reanalyze_all(user_dir: str):
    idx_path = os.path.join(user_dir, "activity_index.json")
    idx = load_json(idx_path)
    if not idx:
        print("No activity_index.json found")
        return

    activities = idx.get("activities", [])

    profile = load_json(os.path.join(user_dir, "profile.json")) or {}
    ftp = float(profile.get("ftp_apex") or profile.get("ftp") or 230.0)
    max_hr = float(profile.get("max_hr") or 185.0)
    print(f"FTP={ftp}W  max_hr={max_hr}  |  {len(activities)} actividades a procesar\n")

    ok = 0
    skipped = 0
    errors = 0

    for a in activities:
        aid = str(a.get("activity_id", ""))
        name = a.get("name", aid)
        date = a.get("date", "")[:10]
        act_dir = os.path.join(user_dir, "activities", aid)

        # Prefer clean CSV, fall back to raw
        csv_path = os.path.join(act_dir, "activity_series_clean.csv")
        if not os.path.exists(csv_path):
            csv_path = os.path.join(act_dir, "activity_series.csv")
        json_path = os.path.join(act_dir, "activity_analysis.json")

        if not os.path.exists(csv_path):
            print(f"  SKIP  [{date}] {name} — sin CSV")
            skipped += 1
            continue

        if not os.path.exists(json_path):
            print(f"  SKIP  [{date}] {name} — sin analysis.json")
            skipped += 1
            continue

        try:
            rows = read_activity_series(csv_path)
            if not rows:
                print(f"  SKIP  [{date}] {name} — CSV vacío")
                skipped += 1
                continue

            rows = add_msi_to_rows(rows, ftp, max_hr)
            new_derived = build_derived_summary(rows, ftp)
            new_metabolic = summarize_msi(rows)
            new_fatigue = build_fatigue_report(rows)

            analysis = load_json(json_path)
            if not analysis:
                print(f"  ERROR [{date}] {name} — no se pudo leer analysis.json")
                errors += 1
                continue

            old_np  = (analysis.get("derived_summary") or {}).get("estimated_np")
            old_tss = (analysis.get("derived_summary") or {}).get("estimated_tss")
            new_np  = new_derived.get("estimated_np")
            new_tss = new_derived.get("estimated_tss")

            analysis["derived_summary"] = new_derived
            analysis["metabolic_index"] = new_metabolic
            analysis["fatigue"] = new_fatigue

            # Rebuild performance scores with updated data
            new_scores = build_performance_scores(analysis)
            analysis["performance_scores"] = new_scores

            save_json(json_path, analysis)

            old_eff = None  # will be recalculated
            new_eff_drop = new_fatigue.get("efficiency_drop_pct")
            new_mls = (new_scores.get("muscular_load_score") or {}).get("score")
            new_pcs = (new_scores.get("pacing_score") or {}).get("score")

            print(f"  OK    [{date}] {name}")
            print(f"         NP:  {old_np} -> {new_np}  |  TSS: {old_tss} -> {new_tss}")
            print(f"         eff_drop: {new_eff_drop}%  |  muscular_load: {new_mls}  |  pacing: {new_pcs}")
            ok += 1

        except Exception as e:
            print(f"  ERROR [{date}] {name} — {e}")
            errors += 1

    print(f"\nCompletado: {ok} OK / {skipped} saltados / {errors} errores")


if __name__ == "__main__":
    from app_context import get_current_user_id, get_user_root
    import json as _json

    session_path = os.path.join(BASE_DIR, "data", "session.json")
    if os.path.exists(session_path):
        session = _json.load(open(session_path, encoding="utf-8"))
        email = session.get("email", "")
        slug = email.replace("@", "_at_").replace(".", "_")
        user_dir = os.path.join(BASE_DIR, "data", "users", slug)
    else:
        # Fallback: solo usuario conocido
        user_dir = os.path.join(BASE_DIR, "data", "users", "abelgcanofuentes_at_hotmail_com")

    reanalyze_all(user_dir)
