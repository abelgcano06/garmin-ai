from garminconnect import Garmin
import json
import os

SESSION_FILE = "garmin_session.json"


def login_garmin(email, password):
    """
    Intenta iniciar sesión con Garmin.
    Si funciona, guarda la sesión local.
    """

    try:
        print("Conectando con Garmin...")

        client = Garmin(email, password)
        client.login()

        print("Login exitoso.")

        # Guardar sesión para reutilizar
        session_data = {
            "email": email
        }

        with open(SESSION_FILE, "w") as f:
            json.dump(session_data, f)

        return client

    except Exception as e:
        print("Error al iniciar sesión:", str(e))
        return None


def load_session():
    """
    Carga sesión guardada si existe
    """

    if not os.path.exists(SESSION_FILE):
        return None

    try:
        with open(SESSION_FILE) as f:
            session = json.load(f)

        email = session["email"]

        print("Sesión encontrada para:", email)

        return email

    except:
        return None


if __name__ == "__main__":

    print("===================================")
    print("GARMIN AUTH TEST")
    print("===================================")

    email = input("Correo Garmin: ")
    password = input("Contraseña Garmin: ")

    client = login_garmin(email, password)

    if client:
        print("Conectado correctamente a Garmin.")
    else:
        print("No se pudo iniciar sesión.")