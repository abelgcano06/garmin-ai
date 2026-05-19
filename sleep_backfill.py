from datetime import datetime, timedelta
from sleep_full_flow import run_sleep_full_flow
from sleep_history_engine import run_sleep_history_engine


def run_sleep_backfill(client, days_back=30, user_id=None):
    print("\n===================================")
    print("SLEEP BACKFILL ENGINE")
    print("===================================")
    print(f"Reprocesando últimas {days_back} noches")
    print("===================================\n")

    success = 0
    failed = 0

    today = datetime.today()

    for i in range(1, days_back + 1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")

        print(f"Procesando noche: {date_str}")

        try:
            run_sleep_full_flow(
                client,
                date_str,
                user_id=user_id,
                run_history=False,
                run_ai=False,
                verbose=False
            )
            success += 1
        except Exception as e:
            print("ERROR:", e)
            failed += 1

    print("\n===================================")
    print("BACKFILL TERMINADO")
    print("===================================")
    print("Noches procesadas:", success)
    print("Errores:", failed)

    base_sleep_dir = f"data/users/{user_id}/sleep"
    out_history_dir = f"data/users/{user_id}/sleep_history"

    print("\nReconstruyendo Sleep History completo...\n")
    run_sleep_history_engine(base_sleep_dir, out_history_dir)
    print("Sleep history reconstruido.\n")