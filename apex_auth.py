"""
apex_auth.py
============
OAuth 2.1 para el conector Apex (lo que pide claude.ai para conectores remotos).

Flujo para el ciclista:
  1. En Claude agrega el conector Apex → Claude abre /apex/login.
  2. Escribe su correo de Garmin, su Personal API key y el código de invitación
     (si APEX_INVITE_CODE está definido). Si ya se registró antes, basta el correo
     y el código.
  3. Apex valida la key contra Garmin, la guarda para ese usuario y regresa a Claude.

Persistencia: SQLite en APEX_DB_PATH (por defecto data/apex_auth.sqlite). En Railway,
monta un volumen en /app/data para que sobreviva a los despliegues.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import threading
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app_context import email_to_user_id

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("APEX_DB_PATH", os.path.join(BASE_DIR, "data", "apex_auth.sqlite"))
INVITE_CODE = os.environ.get("APEX_INVITE_CODE", "").strip()
SCOPE = "apex"

ACCESS_TTL = 60 * 60 * 24          # 1 día
REFRESH_TTL = 60 * 60 * 24 * 90    # 90 días
CODE_TTL = 60 * 10                 # 10 min
PENDING_TTL = 60 * 30              # 30 min para llenar el login

_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS clients (client_id TEXT PRIMARY KEY, info TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, client_id TEXT, params TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS codes (code TEXT PRIMARY KEY, data TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS tokens (hash TEXT PRIMARY KEY, kind TEXT, client_id TEXT, user_id TEXT,
                                           scopes TEXT, expires_at INTEGER, resource TEXT);
        CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, email TEXT, created REAL, last_login REAL);
    """)
    return con


_con = _db()


def _h(token: str) -> str:
    """Los tokens se guardan hasheados: una copia de la base no sirve para entrar."""
    return hashlib.sha256(token.encode()).hexdigest()


def _q(sql: str, args: tuple = (), one: bool = False):
    with _lock:
        cur = _con.execute(sql, args)
        _con.commit()
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


# ─────────────────────────────────────────────────────────────────────────────
# Usuarios
# ─────────────────────────────────────────────────────────────────────────────

def user_email(user_id: str) -> str | None:
    r = _q("SELECT email FROM users WHERE user_id=?", (user_id,), one=True)
    return r[0] if r else None


def all_users() -> list[tuple[str, str]]:
    return [(u, e) for u, e in _q("SELECT user_id, email FROM users")]


def _upsert_user(email: str) -> str:
    uid = email_to_user_id(email)
    now = time.time()
    _q("INSERT INTO users(user_id,email,created,last_login) VALUES(?,?,?,?) "
       "ON CONFLICT(user_id) DO UPDATE SET last_login=excluded.last_login, email=excluded.email",
       (uid, email.strip().lower(), now, now))
    return uid


# ─────────────────────────────────────────────────────────────────────────────
# Provider
# ─────────────────────────────────────────────────────────────────────────────

class ApexOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):

    def __init__(self, public_url: str):
        self.public_url = public_url.rstrip("/")

    # clientes (registro dinámico, lo usa claude.ai)
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        r = _q("SELECT info FROM clients WHERE client_id=?", (client_id,), one=True)
        return OAuthClientInformationFull.model_validate_json(r[0]) if r else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        _q("INSERT OR REPLACE INTO clients(client_id, info) VALUES(?,?)",
           (client_info.client_id, client_info.model_dump_json()))

    # autorización → pantalla de login de Apex
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        pid = secrets.token_urlsafe(24)
        _q("INSERT INTO pending(id, client_id, params, created) VALUES(?,?,?,?)",
           (pid, client.client_id, params.model_dump_json(), time.time()))
        return f"{self.public_url}/apex/login?req={pid}"

    async def load_authorization_code(self, client, authorization_code: str) -> AuthorizationCode | None:
        r = _q("SELECT data, created FROM codes WHERE code=?", (_h(authorization_code),), one=True)
        if not r:
            return None
        code = AuthorizationCode.model_validate_json(r[0])
        return code if code.client_id == client.client_id else None

    async def exchange_authorization_code(self, client, authorization_code: AuthorizationCode) -> OAuthToken:
        _q("DELETE FROM codes WHERE code=?", (_h(authorization_code.code),))
        return self._issue(client.client_id, authorization_code.subject, authorization_code.scopes,
                           str(authorization_code.resource) if authorization_code.resource else None)

    async def load_refresh_token(self, client, refresh_token: str) -> RefreshToken | None:
        r = _q("SELECT client_id,user_id,scopes,expires_at FROM tokens WHERE hash=? AND kind='refresh'",
               (_h(refresh_token),), one=True)
        if not r or r[0] != client.client_id or r[3] < time.time():
            return None
        return RefreshToken(token=refresh_token, client_id=r[0], scopes=json.loads(r[2]), expires_at=r[3], subject=r[1])

    async def exchange_refresh_token(self, client, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        _q("DELETE FROM tokens WHERE hash=?", (_h(refresh_token.token),))
        return self._issue(client.client_id, refresh_token.subject, scopes or refresh_token.scopes, None)

    async def load_access_token(self, token: str) -> AccessToken | None:
        r = _q("SELECT client_id,user_id,scopes,expires_at,resource FROM tokens WHERE hash=? AND kind='access'",
               (_h(token),), one=True)
        if not r or r[3] < time.time():
            return None
        return AccessToken(token=token, client_id=r[0], scopes=json.loads(r[2]), expires_at=r[3],
                           resource=r[4], subject=r[1])

    async def revoke_token(self, token) -> None:
        _q("DELETE FROM tokens WHERE hash=?", (_h(token.token),))

    def _issue(self, client_id: str, user_id: str | None, scopes: list[str], resource: str | None) -> OAuthToken:
        access, refresh = "apx_" + secrets.token_urlsafe(32), "apr_" + secrets.token_urlsafe(40)
        now = int(time.time())
        _q("INSERT INTO tokens VALUES(?,?,?,?,?,?,?)",
           (_h(access), "access", client_id, user_id, json.dumps(scopes), now + ACCESS_TTL, resource))
        _q("INSERT INTO tokens VALUES(?,?,?,?,?,?,?)",
           (_h(refresh), "refresh", client_id, user_id, json.dumps(scopes), now + REFRESH_TTL, resource))
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL,
                          scope=" ".join(scopes), refresh_token=refresh)

    # ── pantalla de login ────────────────────────────────────────────────────
    async def login_page(self, request: Request) -> Response:
        form = await request.form() if request.method == "POST" else None
        pid = (form.get("req") if form else None) or request.query_params.get("req")
        row = _q("SELECT client_id, params, created FROM pending WHERE id=?", (pid or "",), one=True)
        if not row or row[2] < time.time() - PENDING_TTL:
            return HTMLResponse(_page("La solicitud expiró. Vuelve a conectar Apex desde Claude.", error=True), status_code=400)

        if request.method == "GET":
            return HTMLResponse(_page(form=_form(pid)))

        email = (form.get("email") or "").strip().lower()
        key = (form.get("api_key") or "").strip()
        invite = (form.get("invite") or "").strip()

        def again(msg):
            return HTMLResponse(_page(form=_form(pid, email, msg)), status_code=400)

        if INVITE_CODE and not hmac.compare_digest(invite, INVITE_CODE):
            return again("El código de invitación no es correcto.")
        if "@" not in email:
            return again("Escribe el correo de tu cuenta de Garmin.")

        uid = email_to_user_id(email)
        from garmin_official import ApexGarminClient, GarminKeyError, save_user_api_key, user_key_path
        dev_skip = os.environ.get("APEX_DEV_SKIP_GARMIN") == "1" and self.public_url.startswith("http://localhost")
        try:
            if key and dev_skip:
                save_user_api_key(uid, key)
            elif key:
                ApexGarminClient(api_key=key, user_id=uid).get_profile_settings()
                save_user_api_key(uid, key)
            elif not (os.path.exists(user_key_path(uid)) or os.environ.get("GARMIN_PERSONAL_API_KEY__" + uid.upper())):
                return again("Pega tu Personal API key de Garmin (la primera vez es obligatoria).")
        except GarminKeyError:
            return again("Garmin no aceptó esa API key. Revisa que esté activa.")
        except Exception as e:
            return again(f"No pude validar la key con Garmin ({type(e).__name__}). Intenta otra vez.")

        _upsert_user(email)
        params = AuthorizationParams.model_validate_json(row[1])
        code = secrets.token_urlsafe(32)
        ac = AuthorizationCode(
            code=code, scopes=params.scopes or [SCOPE], expires_at=time.time() + CODE_TTL, client_id=row[0],
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject=uid)
        _q("INSERT INTO codes(code, data, created) VALUES(?,?,?)", (_h(code), ac.model_dump_json(), time.time()))
        _q("DELETE FROM pending WHERE id=?", (pid,))

        # Primer sync en segundo plano para que haya datos cuando Claude pregunte
        try:
            if not dev_skip:
                from apex_tools import sincronizar
                sincronizar(uid, email, days_back=120)  # 120 d: CTL necesita 42+ días de historia
        except Exception:
            pass
        return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state), status_code=302)


# ─────────────────────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────────────────────

def _form(pid: str, email: str = "", error: str = "") -> str:
    e = html.escape
    inv = '<label>Código de invitación<input name="invite" autocomplete="off" required></label>' if INVITE_CODE else ""
    return f"""
    {f'<p class="err">{e(error)}</p>' if error else ''}
    <form method="post">
      <input type="hidden" name="req" value="{e(pid)}">
      <label>Correo de tu cuenta de Garmin<input name="email" type="email" value="{e(email)}" required autocomplete="email"></label>
      <label>Personal API key de Garmin
        <input name="api_key" type="password" autocomplete="off" placeholder="GCDC_…">
        <small>Créala en <a href="https://connect.garmin.com/app/settings/personalApiToken" target="_blank" rel="noopener">connect.garmin.com → Settings → Personal API Key</a>. Si ya te conectaste antes, déjala vacía.</small>
      </label>
      {inv}
      <button type="submit">Conectar Apex</button>
    </form>"""


def _page(body: str = "", form: str = "", error: bool = False) -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Conectar Apex</title>
<style>
:root{{--bg:#0e1622;--panel:#152131;--ink:#e6ecf5;--muted:#8e9db3;--line:#24344a;--accent:#f0a23e;--bad:#ef6a5a;color-scheme:dark}}
@media (prefers-color-scheme:light){{:root{{--bg:#f3f5f8;--panel:#fff;--ink:#152033;--muted:#5d6b80;--line:#dde3ec;--accent:#d9831a;--bad:#d04a3a;color-scheme:light}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
padding:32px max(16px,env(safe-area-inset-left))}}
main{{max-width:440px;margin:0 auto;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:24px}}
h1{{font:700 30px/1 "Arial Narrow",system-ui;letter-spacing:.06em;margin:0 0 4px}}h1 span{{color:var(--accent)}}
p.sub{{color:var(--muted);margin:0 0 18px}}label{{display:block;margin:0 0 14px;font-weight:500}}
input{{display:block;width:100%;margin-top:4px;padding:10px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:inherit}}
small{{display:block;color:var(--muted);font-weight:400;margin-top:4px}}a{{color:var(--accent)}}
button{{width:100%;padding:11px;border:0;border-radius:6px;background:var(--accent);color:#1b1206;font:600 16px system-ui;cursor:pointer}}
.err{{color:var(--bad);font-weight:500}}
</style></head><body><main>
<h1>APEX<span>/</span>PI</h1><p class="sub">Conecta tu Garmin para que Claude use tus análisis de Apex.</p>
{f'<p class="{"err" if error else ""}">{html.escape(body)}</p>' if body else ''}{form}
</main></body></html>"""
