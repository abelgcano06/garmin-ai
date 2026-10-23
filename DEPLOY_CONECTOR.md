# Conector Apex en Railway

El conector es `apex_app.py`: un servidor MCP remoto (lo que Claude llama "conector personalizado")
con login por usuario, más un sync automático con Garmin cada pocas horas.

```
Claude (celular/web/desktop) ──OAuth──► Apex en Railway ──API oficial──► Garmin
                                         └─ data/ en volumen (keys, tokens, análisis)
```

## 1. Crear el servicio

1. En Railway: **New Project → Deploy from GitHub repo → `abelgcano06/garmin-ai`**, rama `feature/api-oficial`
   (cuando la juntes a `main`, cambia la rama).
2. Railway detecta `railway.json` y construye con el `Dockerfile`.
3. **Settings → Networking → Generate Domain.** Copia la URL, p. ej. `https://apex-production.up.railway.app`.

## 2. Volumen (obligatorio)

**Settings → Volumes → New Volume**, montado en **`/app/data`**.
Ahí viven las keys de Garmin, los tokens y todos los análisis. Sin volumen se borran en cada despliegue.

## 3. Variables

| Variable | Valor |
|---|---|
| `APEX_PUBLIC_URL` | la URL del paso 1, sin `/` al final |
| `APEX_INVITE_CODE` | un código para tu beta, p. ej. `NHBC2026` (vacío = cualquiera puede registrarse) |
| `APEX_SYNC_EVERY_HOURS` | `3` |
| `ANTHROPIC_API_KEY` | opcional, solo para los briefs con IA de los motores |

Railway reinicia solo. Prueba `https://TU-URL/health` → `{"ok": true}`.

## 4. Conectarlo en Claude

claude.ai → **Ajustes → Conectores → Agregar conector personalizado**
- Nombre: `Apex`
- URL: `https://TU-URL/mcp`

Claude abre la pantalla de Apex: correo de Garmin + Personal API key + código de invitación.
Al entrar arranca el primer sync (30 días; tarda unos minutos).

Aparece en el celular y en Desktop automáticamente.

## 5. Para tus ciclistas

Cada uno:
1. Crea su key en https://connect.garmin.com/app/settings/personalApiToken
2. Agrega el conector con la misma URL y el código de invitación.

Cada quien ve solo sus datos (el token de Claude identifica al usuario).

## Herramientas que ve Claude

| Herramienta | Para qué |
|---|---|
| `apex_hoy` | readiness, recomendación, limitantes, carga, perfil y objetivo |
| `apex_sueno` | análisis de una noche |
| `apex_dia` | análisis de un día |
| `apex_carga` | CTL/ATL/TSB, ramp rate, TSS semanal, FTP, curva de potencia |
| `apex_actividades` / `apex_actividad` | lista y análisis completo de rides |
| `apex_tendencias` | readiness y sueño en el tiempo, correlaciones personales |
| `apex_guardar_nota` | etiqueta, RPE y notas por ride |
| `apex_sincronizar` / `apex_estado_sync` | traer lo nuevo de Garmin |

## Probar en local

```bash
pip install -r requirements.txt
APEX_PUBLIC_URL=http://localhost:8000 uvicorn apex_app:app --port 8000
```
