"""
master_full_flow.py
===================
Orquesta el flujo completo del motor maestro:
  1. Corre master_engine   → calcula readiness, correlaciones, pesos dinámicos
  2. Corre master_ai_brief → genera Quick Brief + Deep Brief con Claude

Uso desde home_menu:
    from master_full_flow import run_master_full_flow
    run_master_full_flow(user_id=user_id, date_str="2026-03-17")

Uso directo desde terminal:
    python master_full_flow.py --date 2026-03-17
"""

import os
from datetime import date, timedelta

from app_context import get_current_user_id, get_user_root
from master_engine import run_master_engine
from master_ai_brief import run_master_ai_brief


def run_master_full_flow(user_id=None, date_str=None):
    user_id  = user_id or get_current_user_id()
    user_dir = get_user_root(user_id)

    if date_str is None:
        # por defecto: ayer, igual que sleep y day
        date_str = (date.today() - timedelta(days=1)).isoformat()

    print("\n" + "=" * 50)
    print("MASTER FULL FLOW")
    print(f"Usuario: {user_id}")
    print(f"Fecha:   {date_str}")
    print("=" * 50)

    # 1) Motor maestro — readiness, correlaciones, pesos
    print("\n[1/2] Corriendo Master Engine...")
    engine_result = run_master_engine(user_dir, target_date=date_str)

    if not engine_result:
        print("[ERROR] Master Engine no retornó resultados. Abortando.")
        return None

    brief = engine_result.get("master_brief")
    if brief:
        score = brief.get("readiness_score")
        label = brief.get("readiness_label")
        print(f"\n  Readiness del {date_str}: {score}/100 — {label}")
    else:
        print("\n  [AVISO] No se generó master_brief para esta fecha.")

    # 2) AI Brief — Quick + Deep con Claude
    print("\n[2/2] Generando AI Briefs (Quick + Deep)...")
    ai_results = run_master_ai_brief(user_dir, target_date=date_str)

    print("\n" + "=" * 50)
    print("MASTER FULL FLOW TERMINADO")
    print("=" * 50)

    pi_dir = os.path.join(user_dir, "performance_intelligence")
    print(f"\nArchivos generados en: {pi_dir}")
    print("  master_brief.json")
    print("  master_brief_quick.json")
    print("  master_brief_deep.json")
    print("  readiness_history.json")
    print("  performance_correlations.json")
    print()

    return {
        "engine": engine_result,
        "ai":     ai_results,
    }


if __name__ == "__main__":
    import argparse
    from app_context import set_current_garmin_email, ensure_current_user_profile

    parser = argparse.ArgumentParser(description="Master Full Flow")
    parser.add_argument("--email", type=str, default=None, help="Email Garmin del usuario")
    parser.add_argument("--date",  type=str, default=None, help="Fecha YYYY-MM-DD (default: ayer)")
    args = parser.parse_args()

    if args.email:
        set_current_garmin_email(args.email)
        ensure_current_user_profile(garmin_email=args.email)
    else:
        # Si no hay email, intenta leer el usuario actual del contexto
        try:
            get_current_user_id()
        except ValueError:
            print("[ERROR] Necesitas pasar --email o tener un usuario activo en el contexto.")
            exit(1)

    run_master_full_flow(date_str=args.date)