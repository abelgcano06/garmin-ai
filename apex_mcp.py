"""
apex_mcp.py
===========
Conector Apex para Claude (servidor MCP remoto, streamable HTTP, OAuth por usuario).

Herramientas: apex_hoy, apex_sueno, apex_dia, apex_carga, apex_actividades,
apex_actividad, apex_tendencias, apex_guardar_nota, apex_sincronizar, apex_estado_sync.

Cada llamada sabe quién es el ciclista por su token; nunca ve datos de otro.
"""

from __future__ import annotations

import os
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import apex_tools as T
from apex_auth import SCOPE, ApexOAuthProvider, user_email

PUBLIC_URL = os.environ.get("APEX_PUBLIC_URL", "http://localhost:8000").rstrip("/")
_host = urlparse(PUBLIC_URL).netloc

provider = ApexOAuthProvider(PUBLIC_URL)

INSTRUCTIONS = """Apex Performance Intelligence: análisis de rendimiento y recuperación para ciclistas,
calculado con los datos oficiales de Garmin del usuario (sueño, HRV, Body Battery, FC, actividades con potencia).

Cómo usarlo:
- Para "¿qué entreno hoy?", "¿cómo amanecí?" o "¿estoy listo?": apex_hoy primero.
- Para una noche o un día específico: apex_sueno / apex_dia con la fecha (YYYY-MM-DD; para sueño, la mañana en que despertó).
- Para forma, fatiga, FTP o curva de potencia: apex_carga.
- Para rides: apex_actividades para encontrarlos y apex_actividad con el id para el análisis completo.
- Para patrones (qué le afecta más, cómo evoluciona): apex_tendencias.
- Si los datos se ven viejos o falta un día, apex_sincronizar y luego apex_estado_sync.
Responde en el idioma del usuario, con números concretos, y explica los términos técnicos (CTL, TSB, VI) la primera vez.
Readiness: ≥80 carga alta, 65–79 normal, 50–64 precaución, 35–49 recuperación activa, <35 descanso."""

mcp = FastMCP(
    name="Apex",
    instructions=INSTRUCTIONS,
    website_url=PUBLIC_URL,
    auth_server_provider=provider,
    auth=AuthSettings(
        issuer_url=PUBLIC_URL,
        resource_server_url=f"{PUBLIC_URL}/mcp",
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=[SCOPE],
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[h for h in (_host, "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*") if h],
        allowed_origins=[PUBLIC_URL, "https://claude.ai", "https://claude.com", "http://localhost:*"],
    ),
    stateless_http=True,
)


def _uid() -> str:
    tok = get_access_token()
    if not tok or not tok.subject:
        raise PermissionError("Sesión de Apex no válida. Vuelve a conectar el conector.")
    return tok.subject


Fecha = Annotated[str | None, Field(description="Fecha YYYY-MM-DD. Vacía = la más reciente con datos.")]
RO = {"readOnlyHint": True, "openWorldHint": False}


@mcp.tool(annotations=RO)
def apex_hoy() -> dict:
    """Readiness de hoy (0-100) con recomendación de entrenamiento, limitantes, alertas,
    readiness de los últimos 7 días, la última noche con datos, la carga actual (CTL/ATL/TSB)
    y el perfil del atleta (FTP, peso, objetivo y días que faltan)."""
    return T.hoy(_uid())


@mcp.tool(annotations=RO)
def apex_sueno(fecha: Fecha = None, resumen: Annotated[bool, Field(description="True = solo lo esencial")] = False) -> dict:
    """Análisis Apex de una noche: recuperación física, neural y total, ventana, arquitectura
    (profundo, REM, despertares, fragmentación), curva autonómica (FC, HRV, Body Battery) y hallazgos.
    La fecha es la mañana en que despertó."""
    return T.sueno(_uid(), fecha, resumen=resumen)


@mcp.tool(annotations=RO)
def apex_dia(fecha: Fecha = None) -> dict:
    """Análisis Apex de un día: capacidad, tensión del sistema, energía (Body Battery),
    estrés, carga física y cognitiva, recuperación intradía, hallazgos y limitantes."""
    return T.dia(_uid(), fecha)


@mcp.tool(annotations=RO)
def apex_carga() -> dict:
    """Carga de entrenamiento: CTL (forma, 42 d), ATL (fatiga, 7 d), TSB (frescura), ramp rate,
    TSS por semana (12 semanas), PMC de 28 días, FTP estimado por Apex y mejor curva de potencia."""
    return T.carga(_uid())


@mcp.tool(annotations=RO)
def apex_actividades(
    desde: Fecha = None, hasta: Fecha = None,
    tipo: Annotated[str | None, Field(description="road_biking, mountain_biking, gravel_cycling, indoor_cycling, running…")] = None,
    etiqueta: Annotated[str | None, Field(description="Etiqueta que puso el usuario, p. ej. Intervalos")] = None,
    limite: Annotated[int, Field(ge=1, le=60)] = 20,
) -> dict:
    """Lista de actividades (más recientes primero) con distancia, tiempo, desnivel, FC, potencia,
    NP, VI, TSS, clasificación, limitante principal y la etiqueta/RPE del usuario.
    Regresa {"total": n, "actividades": [...]}."""
    acts = T.actividades(_uid(), desde, hasta, tipo, etiqueta, limite)
    return {"total": len(acts), "actividades": acts}


@mcp.tool(annotations=RO)
def apex_actividad(id: Annotated[int, Field(description="id de apex_actividades")]) -> dict:
    """Análisis Apex completo de una actividad: resumen Garmin y Apex, scores de rendimiento,
    perfil de potencia, zonas, esfuerzos, subidas, fatiga, índice metabólico, hallazgos y nota del usuario."""
    return T.actividad(_uid(), id)


@mcp.tool(annotations=RO)
def apex_tendencias(dias: Annotated[int, Field(ge=7, le=120)] = 30) -> dict:
    """Tendencias: readiness y sueño por día, correlaciones personales aprendidas de sus datos
    (qué afecta su rendimiento) y los pesos que usa su readiness."""
    return T.tendencias(_uid(), dias)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
def apex_guardar_nota(
    id: Annotated[int, Field(description="id de la actividad")],
    etiqueta: Annotated[str | None, Field(description="Fondo, Intervalos, Tempo, Recuperación, Grupo, Carrera, Indoor u otra")] = None,
    rpe: Annotated[int | None, Field(ge=1, le=10, description="Esfuerzo percibido 1-10")] = None,
    texto: Annotated[str | None, Field(description="Cómo se sintió, qué comió, objetivo del ride")] = None,
) -> dict:
    """Guarda etiqueta, RPE y notas del usuario en una actividad."""
    return T.guardar_nota(_uid(), id, etiqueta, rpe, texto)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
def apex_actualizar_perfil(
    nombre: str | None = None,
    peso_kg: Annotated[float | None, Field(gt=30, lt=200)] = None,
    estatura_cm: Annotated[float | None, Field(gt=100, lt=230)] = None,
    edad: Annotated[int | None, Field(gt=10, lt=100)] = None,
    ftp: Annotated[int | None, Field(gt=50, lt=600, description="FTP en watts si el atleta lo conoce")] = None,
    fc_max: Annotated[int | None, Field(gt=120, lt=230)] = None,
    horas_semana: Annotated[float | None, Field(ge=0, le=40)] = None,
    objetivo: Annotated[str | None, Field(description="Evento objetivo, p. ej. Carrera de 100 km XC")] = None,
    fecha_objetivo: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    anios_experiencia: Annotated[float | None, Field(ge=0, le=60)] = None,
) -> dict:
    """Actualiza el perfil del atleta (peso, FTP, FC máx, objetivo y fecha, etc.). Solo cambia lo que se manda.
    Úsalo cuando el usuario diga sus datos; mejora W/kg, zonas y la planeación hacia su objetivo."""
    return T.actualizar_perfil(_uid(), nombre=nombre, peso_kg=peso_kg, estatura_cm=estatura_cm, edad=edad, ftp=ftp,
                               fc_max=fc_max, horas_semana=horas_semana, objetivo=objetivo,
                               fecha_objetivo=fecha_objetivo, anios_experiencia=anios_experiencia)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True})
def apex_sincronizar(dias: Annotated[int, Field(ge=1, le=90)] = 7) -> dict:
    """Trae de Garmin lo nuevo (actividades de los últimos `dias`, noches y días faltantes) y recalcula
    readiness, carga y FTP. Corre en segundo plano (1-5 min); consulta con apex_estado_sync."""
    uid = _uid()
    email = user_email(uid)
    if not email:
        raise PermissionError("No encontré tu correo de Garmin. Vuelve a conectar Apex.")
    return T.sincronizar(uid, email, dias)


@mcp.tool(annotations=RO)
def apex_cobertura() -> dict:
    """Cuántas noches, días y actividades tiene Apex del usuario, desde cuándo, qué falta en los
    últimos 30 días, qué le falta al perfil y cuándo fue el último sync."""
    return T.cobertura(_uid())


@mcp.tool(annotations=RO)
def apex_estado_sync() -> dict:
    """Avance del último sync con Garmin."""
    return T.estado_sync(_uid())


@mcp.custom_route("/apex/login", methods=["GET", "POST"])
async def apex_login(request):
    return await provider.login_page(request)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"ok": True, "service": "apex"})
