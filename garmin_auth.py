"""
garmin_auth.py
==============
Conexión a Garmin con la API oficial (Personal API). Ya no usa usuario/contraseña.

Cada usuario de Apex se identifica por su correo de Garmin y tiene su propia
Personal API key guardada en data/users/<user_id>/garmin_api_key.

Configurar la key de un usuario (una vez):
    python garmin_auth.py --email tu@correo.com
    (pide la key oculta, la valida contra Garmin y la guarda)

Crear la key: https://connect.garmin.com/app/settings/personalApiToken
"""

import argparse
import getpass
import json
import os
import sys

from app_context import email_to_user_id
from garmin_official import (
    ApexGarminClient,
    GarminKeyError,
    KEY_PAGE,
    save_user_api_key,
)

SESSION_FILE = "garmin_session.json"


def get_garmin_client(email: str, api_key: str | None = None) -> ApexGarminClient:
    """Cliente oficial para el usuario de ese correo. Si viene api_key, la guarda primero."""
    user_id = email_to_user_id(email)
    if api_key:
        save_user_api_key(user_id, api_key)
    return ApexGarminClient.for_user(user_id)


def login_garmin(email, password=None, api_key=None):
    """
    Compatibilidad con el flujo anterior. `password` se ignora: la API oficial
    usa la Personal API key del usuario. Regresa el cliente o None si falla.
    """
    try:
        print("Conectando con Garmin (API oficial)...")
        client = get_garmin_client(email, api_key)
        client.login()
        print("Conexión exitosa.")
        with open(SESSION_FILE, "w") as f:
            json.dump({"email": email}, f)
        return client
    except GarminKeyError as e:
        print("Error de API key:", str(e))
        return None
    except Exception as e:
        print("Error al conectar con Garmin:", str(e))
        return None


def load_session():
    """Carga el correo de la sesión guardada si existe."""
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE) as f:
            email = json.load(f)["email"]
        print("Sesión encontrada para:", email)
        return email
    except Exception:
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Configura la Personal API key de Garmin para un usuario de Apex")
    ap.add_argument("--email", required=True, help="Correo de Garmin del usuario")
    args = ap.parse_args()

    print(f"Crea tu Personal API key en: {KEY_PAGE}")
    key = getpass.getpass("Pega la key (no se muestra): ").strip()
    if not key:
        sys.exit("No pegaste ninguna key.")

    client = login_garmin(args.email, api_key=key)
    if client:
        print(f"Listo. Key guardada para {args.email} ({client.get_full_name()}).")
    else:
        sys.exit("Garmin no aceptó la key. Revisa que esté activa y vuelve a intentar.")
