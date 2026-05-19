from datetime import datetime

from sleep_full_flow import run_sleep_full_flow
from sleep_history_engine import run_sleep_history_engine
from sleep_ai_chat import run_sleep_ai_chat
from sleep_backfill import run_sleep_backfill

from app_context import (
    get_current_user_id,
    get_sleep_dir,
    get_sleep_day_dir,
    get_sleep_analysis_path,
    get_sleep_findings_path,
    get_sleep_brief_path,
    get_sleep_trends_path,
    get_sleep_patterns_path,
    get_sleep_longitudinal_brief_path,
    get_sleep_history_dir,
)


def show_sleep_menu():
    print("\n===================================")
    print("MÓDULO DE SUEÑO Y RECOVERY")
    print("===================================")
    print("1. Noche anterior")
    print("2. Noche específica")
    print("3. Reprocesar últimas N noches")
    print("4. Correr Sleep History con IA")
    print("0. Volver")


def open_sleep_ai_chat_for_date(date_str, user_id=None):
    import os

    user_id = user_id or get_current_user_id()

    analysis_path = get_sleep_analysis_path(date_str, user_id)
    findings_path = get_sleep_findings_path(date_str, user_id)
    brief_path = get_sleep_brief_path(date_str, user_id)
    brief_ai_path = os.path.join(get_sleep_day_dir(date_str, user_id), "sleep_brief_ai.json")
    longitudinal_brief_path = get_sleep_longitudinal_brief_path(user_id)
    trends_path = get_sleep_trends_path(user_id)
    patterns_path = get_sleep_patterns_path(user_id)

    run_sleep_ai_chat(
        analysis_path=analysis_path,
        findings_path=findings_path,
        brief_path=brief_path,
        brief_ai_path=brief_ai_path,
        longitudinal_brief_path=longitudinal_brief_path,
        trends_path=trends_path,
        patterns_path=patterns_path
    )


def run_sleep_history_with_ai(user_id=None):
    import os
    from glob import glob
    from sleep_brief_ai import generate_sleep_ai_brief

    user_id = user_id or get_current_user_id()

    base_sleep_dir = get_sleep_dir(user_id)
    out_dir = get_sleep_history_dir(user_id)

    run_sleep_history_engine(base_sleep_dir, out_dir)

    analysis_files = sorted(glob(os.path.join(base_sleep_dir, "*", "sleep_analysis.json")))
    if not analysis_files:
        print("\nNo hay noches analizadas todavía.\n")
        return

    latest_analysis = analysis_files[-1]
    latest_day_dir = os.path.dirname(latest_analysis)

    findings_path = os.path.join(latest_day_dir, "sleep_findings.json")
    brief_path = os.path.join(latest_day_dir, "sleep_brief.json")

    print("\n[INFO] Recalculando AI brief de la última noche con history actualizado...")

    ai_result = generate_sleep_ai_brief(
        analysis_path=latest_analysis,
        findings_path=findings_path,
        brief_path=brief_path,
        longitudinal_brief_path=get_sleep_longitudinal_brief_path(user_id),
        trends_path=get_sleep_trends_path(user_id),
        patterns_path=get_sleep_patterns_path(user_id)
    )

    if ai_result:
        print("\n[OK] Sleep History con IA completado.\n")
    else:
        print("\n[WARNING] History se recalculó, pero la IA no generó brief.\n")


def sleep_module(client):
    user_id = get_current_user_id()

    while True:
        show_sleep_menu()
        option = input("Elige una opción: ").strip()

        if option == "1":
            date_str = datetime.now().date().isoformat()
            print(f"\nProcesando noche anterior: {date_str}")
            result = run_sleep_full_flow(client, date_str, user_id=user_id)

            if result and result.get("ai_ok"):
                open_chat = input("¿Quieres abrir Sleep AI Chat para esta noche? (s/n): ").strip().lower()
                if open_chat == "s":
                    open_sleep_ai_chat_for_date(date_str, user_id=user_id)

        elif option == "2":
            date_str = input("Fecha a analizar (YYYY-MM-DD): ").strip()
            result = run_sleep_full_flow(client, date_str, user_id=user_id)

            if result and result.get("ai_ok"):
                open_chat = input("¿Quieres abrir Sleep AI Chat para esta noche? (s/n): ").strip().lower()
                if open_chat == "s":
                    open_sleep_ai_chat_for_date(date_str, user_id=user_id)

        elif option == "3":
            days_back = input("\n¿Cuántas noches quieres reprocesar? (ej. 30): ")

            try:
                days_back = int(days_back)
            except:
                print("Número inválido")
                continue

            run_sleep_backfill(
                client,
                days_back=days_back,
                user_id=user_id
            )

        elif option == "4":
            run_sleep_history_with_ai(user_id=user_id)

        elif option == "0":
            break

        else:
            print("Opción no válida. Intenta de nuevo.\n")