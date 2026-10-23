# Migración a la API oficial de Garmin

Apex ya no usa `garminconnect`/`garth` (usuario y contraseña). Ahora usa la
**Garmin Connect Personal API** con una Personal API key por usuario.

## Qué cambió

| Archivo | Cambio |
|---|---|
| `garmin_official.py` | **Nuevo.** `ApexGarminClient`: un usuario = una instancia, con su key y su caché de token. Mismos métodos que usaban los pipelines (`get_stats`, `get_sleep_data`, `get_activities_by_date`, `get_activity_details`, …) y misma forma de datos, así que los motores no cambian. |
| `garmin_auth.py` | `login_garmin(email, api_key=...)` ya no usa contraseña. CLI para guardar la key de un usuario. |
| `run_sync.py` | Solo necesita el correo; acepta `api_key` opcional en `session.json` (la guarda y la valida). |
| `garmin_server.py` | Un cliente por usuario (header `X-Apex-Email` o `garmin_session.json`). Los endpoints de workouts responden 501. |
| `historical_import.py` | Usa el cliente oficial; `--password` queda obsoleto. |
| `requirements.txt` | **Nuevo.** |
| `tools/smoke_test_official.py` | **Nuevo.** Prueba contra tus datos reales. |

## Configurar un usuario

```bash
pip install -r requirements.txt
python garmin_auth.py --email tu@correo.com      # pega la key; se guarda en data/users/<id>/garmin_api_key
python tools/smoke_test_official.py --email tu@correo.com
python run_sync.py                                # igual que antes
```

Crear la key: https://connect.garmin.com/app/settings/personalApiToken

En la nube, en vez del archivo, define la variable
`GARMIN_PERSONAL_API_KEY__<USER_ID>` (ej. `GARMIN_PERSONAL_API_KEY__ABELGCANOFUENTES_AT_HOTMAIL_COM`).

## Diferencias de datos

- **Actividades:** las series por segundo salen del `.FIT` original (lector oficial `garmin-fit-sdk`).
  Trae potencia, FC, cadencia, altitud, velocidad, respiración, GPS y temperatura.
  Stamina, grit y performance condition no vienen en el FIT y quedan vacíos.
- **Sueño:** la API Personal no trae fases minuto a minuto ni estrés nocturno.
  `get_sleep_data` arma la estructura con FC, HRV y Body Battery recortados a la ventana de sueño;
  `sleep_engine` infiere las fases desde los totales (su fallback de siempre).
- **Día:** no hay serie intradía de estrés ni respiración; `day_engine` usa los promedios del resumen diario.
- **Workouts al reloj:** no disponible en la API Personal (requiere Training API, tier Starter/Enterprise).

## Multiusuario

Hoy cada usuario trae su propia Personal API key. Para abrir Apex a otros sin pedirles una key,
el siguiente paso es el tier **Starter** de Garmin (OAuth por usuario); `ApexGarminClient` solo
tendría que cambiar de dónde saca el token.
