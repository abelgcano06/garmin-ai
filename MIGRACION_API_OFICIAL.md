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

## Qué da y qué no da la API Personal (probado el 23 oct 2026)

**Sí:** perfil, resumen diario v2, sueño (resumen y score), HRV con lecturas cada 5 min,
FC intradía cada 2 min, Body Battery (con `chunks=288` → cada 5 min), estrés diario,
pasos, hidratación, peso, SpO₂ diario, fitness age, zonas de FC, actividades,
**detalle por segundo de cada actividad en JSON** (incluye stamina, grit, performance condition)
y el **.FIT original** (vueltas/laps).

**No (404):** fases de sueño minuto a minuto, estrés/respiración/SpO₂ intradía, training readiness,
training status, VO2max, endurance/hill score, FTP y umbral de lactato de Garmin, récords personales,
splits/zonas/clima/equipo por actividad, workouts al reloj.

Cómo lo compensa Apex:
- **Fases de sueño:** `sleep_engine` las infiere de los totales (su fallback de siempre).
- **Estrés y respiración del día:** `day_engine` usa los promedios del resumen diario.
- **Zonas por actividad:** vienen en la búsqueda de actividades (`powerTimeInZone_*`, `hrTimeInZone_*`).
- **FTP / VO2max:** los calcula Apex (`ftp_engine`) con tus datos de potencia.
- **Vueltas:** del .FIT.

## Multiusuario

Hoy cada usuario trae su propia Personal API key. Para abrir Apex a otros sin pedirles una key,
el siguiente paso es el tier **Starter** de Garmin (OAuth por usuario); `ApexGarminClient` solo
tendría que cambiar de dónde saca el token.
