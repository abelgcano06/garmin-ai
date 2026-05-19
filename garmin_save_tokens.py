"""
garmin_save_tokens.py
=====================
Login único con email+password y guarda los tokens de garth en
data/garth_tokens/ para que garmin_server.py no pida contraseña.

Uso (una sola vez, o cuando expiren los tokens):
    python garmin_save_tokens.py
"""

import json
import os
import getpass
from garminconnect import Garmin

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, "garmin_session.json")
TOKENSTORE   = os.path.join(BASE_DIR, "data", "garth_tokens")


def main():
    # Read saved email
    email = None
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, encoding="utf-8") as f:
            email = json.load(f).get("email", "")

    if not email:
        email = input("Correo Garmin: ").strip()

    password = getpass.getpass(f"Contraseña para {email}: ")

    print("Iniciando sesión...")
    client = Garmin(email, password)
    client.login()
    print("[OK] Login exitoso")

    # Save garth tokens
    os.makedirs(TOKENSTORE, exist_ok=True)
    client.garth.dump(TOKENSTORE)
    print(f"[OK] Tokens guardados en: {TOKENSTORE}")
    print(f"     Archivos: {os.listdir(TOKENSTORE)}")
    print("\nYa puedes iniciar garmin_server.py sin necesidad de contraseña.")


if __name__ == "__main__":
    main()
