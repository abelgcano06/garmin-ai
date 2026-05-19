from datetime import datetime, timedelta

from garmin_auth import login_garmin
from auto_sync import run_auto_sync
from activity_menu import activity_module
from sleep_menu import sleep_module
from day_menu import day_module
from master_full_flow import run_master_full_flow
from app_context import set_current_garmin_email, get_current_user_id, ensure_current_user_profile


def show_home_menu():
    print("\n===================================")
    print("BIENVENIDO A TU APP DE ANÁLISIS")
    print("===================================")
    print("1. Mi Noche")
    print("2. Mi Día")
    print("3. Mi Actividad")
    print("4. Master Intelligence")
    print("0. Salir")


def master_module(user_id):
    print("\n===================================")
    print("MASTER INTELLIGENCE")
    print("===================================")
    print("1. Análisis de ayer")
    print("2. Fecha específica")
    print("0. Volver")

    option = input("\nElige una opción: ").strip()

    if option == "0":
        return
    elif option == "1":
        date_str = (datetime.now().date() - timedelta(days=1)).isoformat()
        run_master_full_flow(user_id=user_id, date_str=date_str)
    elif option == "2":
        date_str = input("Fecha (YYYY-MM-DD): ").strip()
        if date_str:
            run_master_full_flow(user_id=user_id, date_str=date_str)
    else:
        print("Opción no válida.")


def main():
    print("===================================")
    print("LOGIN GARMIN")
    print("===================================")

    email    = input("Correo Garmin: ").strip()
    password = input("Contraseña Garmin: ").strip()

    client = login_garmin(email, password)

    if not client:
        print("No se pudo iniciar sesión. Cerrando app.")
        return

    set_current_garmin_email(email)
    ensure_current_user_profile(garmin_email=email)

    user_id = get_current_user_id()
    print(f"\nSesión iniciada para: {email}")
    print(f"user_id: {user_id}\n")

    # AUTO SYNC — corre solo, sin preguntar
    run_auto_sync(client, user_id=user_id)

    while True:
        show_home_menu()
        option = input("Elige una opción: ").strip()

        if option == "1":
            sleep_module(client)
        elif option == "2":
            day_module(client)
        elif option == "3":
            activity_module(client)
        elif option == "4":
            master_module(user_id)
        elif option == "0":
            print("Saliendo de la app.")
            break
        else:
            print("Opción no válida. Intenta de nuevo.\n")


if __name__ == "__main__":
    main()