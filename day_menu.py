from datetime import datetime, timedelta

from day_full_flow import run_day_full_flow
from day_history_engine import run_day_history_engine
from day_ai_chat import run_day_ai_chat
from day_backfill import run_day_backfill

from app_context import (
    get_current_user_id,
    get_day_dir,
    get_day_day_dir,
    get_day_analysis_path,
    get_day_findings_path,
    get_day_brief_path,
    get_day_trends_path,
    get_day_patterns_path,
    get_day_longitudinal_brief_path,
    get_day_history_dir,
)


def show_day_menu():
    print("\n===================================")
    print("MÓDULO DE DÍA Y ESTADO FISIOLÓGICO")
    print("===================================")
    print("1. Hoy")
    print("2. Día específico")
    print("3. Reprocesar últimos N días")
    print("4. Correr Day History con IA")
    print("0. Volver")


def open_day_ai_chat_for_date(date_str, user_id=None):
    import os

    user_id = user_id or get_current_user_id()

    analysis_path = get_day_analysis_path(date_str, user_id)
    findings_path = get_day_findings_path(date_str, user_id)
    brief_path = get_day_brief_path(date_str, user_id)
    brief_ai_path = os.path.join(get_day_day_dir(date_str, user_id), "day_brief_ai.json")
    longitudinal_brief_path = get_day_longitudinal_brief_path(user_id)
    trends_path = get_day_trends_path(user_id)
    patterns_path = get_day_patterns_path(user_id)

    run_day_ai_chat(
        analysis_path=analysis_path,
        findings_path=findings_path,
        brief_path=brief_path,
        brief_ai_path=brief_ai_path,
        longitudinal_brief_path=longitudinal_brief_path,
        trends_path=trends_path,
        patterns_path=patterns_path
    )


def run_day_history_with_ai(client=None, user_id=None):
    import os
    from glob import glob
    from day_brief_ai import generate_day_ai_brief

    user_id = user_id or get_current_user_id()

    base_day_dir = get_day_dir(user_id)
    out_dir = get_day_history_dir(user_id)

    run_day_history_engine(base_day_dir, out_dir)

    analysis_files = sorted(glob(os.path.join(base_day_dir, "*", "day_analysis.json")))
    if not analysis_files:
        print("\nNo hay días analizados todavía.\n")
        return

    latest_analysis = analysis_files[-1]
    latest_day_dir = os.path.dirname(latest_analysis)

    findings_path = os.path.join(latest_day_dir, "day_findings.json")
    brief_path = os.path.join(latest_day_dir, "day_brief.json")

    print("\n[INFO] Recalculando AI brief del último día con history actualizado...")

    ai_result = generate_day_ai_brief(
        analysis_path=latest_analysis,
        findings_path=findings_path,
        brief_path=brief_path,
        longitudinal_brief_path=get_day_longitudinal_brief_path(user_id),
        trends_path=get_day_trends_path(user_id),
        patterns_path=get_day_patterns_path(user_id)
    )

    if ai_result:
        print("\n[OK] Day History con IA completado.\n")
    else:
        print("\n[WARNING] History se recalculó, pero la IA no generó brief.\n")


def day_module(client):
    user_id = get_current_user_id()

    while True:
        show_day_menu()
        option = input("Elige una opción: ").strip()

        if option == "1":
            date_str = datetime.now().date().isoformat()
            print(f"\nProcesando día actual: {date_str}")
            result = run_day_full_flow(client, date_str, user_id=user_id)

            if result and result.get("ai_ok"):
                open_chat = input("¿Quieres abrir Day AI Chat para este día? (s/n): ").strip().lower()
                if open_chat == "s":
                    open_day_ai_chat_for_date(date_str, user_id=user_id)

        elif option == "2":
            date_str = input("Fecha a analizar (YYYY-MM-DD): ").strip()
            result = run_day_full_flow(client, date_str, user_id=user_id)

            if result and result.get("ai_ok"):
                open_chat = input("¿Quieres abrir Day AI Chat para este día? (s/n): ").strip().lower()
                if open_chat == "s":
                    open_day_ai_chat_for_date(date_str, user_id=user_id)

        elif option == "3":
            try:
                days_back = int(input("¿Cuántos días quieres reprocesar? ").strip())
            except Exception:
                print("Número inválido.\n")
                continue

            run_day_backfill(client, days_back=days_back, user_id=user_id)

        elif option == "4":
            run_day_history_with_ai(client=client, user_id=user_id)

        elif option == "0":
            break

        else:
            print("Opción no válida. Intenta de nuevo.\n")