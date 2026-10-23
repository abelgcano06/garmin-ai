"""
apex_app.py
===========
Punto de entrada en la nube: conector Apex (MCP + OAuth) y sync programado.

    uvicorn apex_app:app --host 0.0.0.0 --port $PORT

Variables de entorno:
    APEX_PUBLIC_URL        URL pública, p. ej. https://apex-production.up.railway.app   (obligatoria en la nube)
    APEX_INVITE_CODE       código para la beta; vacío = registro abierto
    APEX_SYNC_EVERY_HOURS  cada cuántas horas sincronizar a todos los usuarios (default 3; 0 = apagado)
    APEX_DB_PATH           SQLite de usuarios/tokens (default data/apex_auth.sqlite)
    ANTHROPIC_API_KEY      opcional, solo si usas los briefs con IA de los motores
"""

import os
import threading
import time
from contextlib import asynccontextmanager

os.chdir(os.path.dirname(os.path.abspath(__file__)))  # los motores usan rutas relativas a la raíz del repo

from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount  # noqa: E402

from apex_mcp import mcp  # noqa: E402

SYNC_EVERY_H = float(os.environ.get("APEX_SYNC_EVERY_HOURS", "3"))


def _scheduler():
    """Sincroniza a todos los usuarios cada N horas, uno a la vez."""
    from apex_auth import all_users
    from apex_tools import sincronizar, estado_sync
    time.sleep(60)
    while True:
        for uid, email in all_users():
            try:
                sincronizar(uid, email, days_back=3)
                while estado_sync(uid).get("estado") == "corriendo":
                    time.sleep(10)
            except Exception as e:
                print(f"[sync programado] {uid}: {e}")
        time.sleep(SYNC_EVERY_H * 3600)


@asynccontextmanager
async def lifespan(app):
    if SYNC_EVERY_H > 0:
        threading.Thread(target=_scheduler, daemon=True).start()
    async with mcp.session_manager.run():
        yield


_inner = mcp.streamable_http_app()
app = Starlette(routes=[Mount("/", app=_inner)], lifespan=lifespan)
