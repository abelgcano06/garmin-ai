from datetime import datetime, timedelta

from day_full_flow import run_day_full_flow
from day_history_engine import run_day_history_engine


def run_day_backfill(client, days_back=30, user_id=None):
    print("\n===================================")
    print("DAY BACKFILL ENGINE")
    print("===================================")
    print(f"Reprocesando últimos {days_back} días")
    print("===================================\n")

    success = 0
    failed = 0

    today = datetime.today()

    for i in range(0, days_back):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")

        print(f"Procesando día: {date_str}")

        try:
            run_day_full_flow(
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
    print("Días procesados:", success)
    print("Errores:", failed)

    base_day_dir = f"data/users/{user_id}/day"
    out_history_dir = f"data/users/{user_id}/day_history"

    print("\nReconstruyendo Day History completo.\n")
    run_day_history_engine(base_day_dir, out_history_dir)
    print("Day history reconstruido.\n")


def main():
    from garmin_auth import login_garmin
    from app_context import set_current_garmin_email, get_current_user_id

    print("===================================")
    print("DAY BACKFILL")
    print("===================================")

    email = input("Correo Garmin: ").strip()
    password = input("Contraseña Garmin: ").strip()

    client = login_garmin(email, password)
    if not client:
        print("No se pudo iniciar sesión.")
        return

    set_current_garmin_email(email)
    user_id = get_current_user_id()

    try:
        days_back = int(input("¿Cuántos días quieres reprocesar? ").strip())
    except Exception:
        print("Número inválido.")
        return

    run_day_backfill(client, days_back=days_back, user_id=user_id)


if __name__ == "__main__":
    main()