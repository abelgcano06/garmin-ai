"""
Prueba qué endpoints extra de Garmin Connect responde la API Personal con tu key.
    python tools/probe_endpoints.py --email X --date YYYY-MM-DD
Solo lee. Imprime estado, tamaño y llaves principales de cada uno.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from app_context import email_to_user_id
from garmin_official import ApexGarminClient

ap = argparse.ArgumentParser(); ap.add_argument("--email", required=True); ap.add_argument("--date", required=True)
a = ap.parse_args(); d = a.date
c = ApexGarminClient.for_user(email_to_user_id(a.email))
prof = c.get_profile_settings() or {}
dn = prof.get("displayName", "")
acts = c.get_activities_by_date(d, d) or c.get_activities(0, 1)
aid = acts[0]["activityId"] if acts else 0

CANDIDATES = [
    ("estrés intradía", f"/wellness-service/wellness/dailyStress/{d}", None),
    ("respiración intradía", f"/wellness-service/wellness/daily/respiration/{d}", None),
    ("SpO2 intradía", f"/wellness-service/wellness/daily/spo2/{d}", None),
    ("sueño completo (fases)", f"/wellness-service/wellness/dailySleepData/{dn}", {"date": d, "nonSleepBufferMinutes": 60}),
    ("sueño completo v2", "/sleep-service/sleep/dailySleepData", {"date": d, "nonSleepBufferMinutes": 60}),
    ("épocas/movimiento", f"/wellness-service/wellness/dailyMovement/{dn}", {"calendarDate": d}),
    ("training readiness", f"/metrics-service/metrics/trainingreadiness/{d}", None),
    ("training status", f"/metrics-service/metrics/trainingstatus/aggregated/{d}", None),
    ("VO2max", f"/metrics-service/metrics/maxmet/daily/{d}/{d}", None),
    ("endurance score", "/metrics-service/metrics/endurancescore", {"calendarDate": d}),
    ("hill score", "/metrics-service/metrics/hillscore", {"calendarDate": d}),
    ("FTP biométrico", "/biometric-service/biometric/latestFunctionalThresholdPower/CYCLING", None),
    ("lactate threshold", "/biometric-service/biometric/latestLactateThreshold", None),
    ("récords personales", f"/personalrecord-service/personalrecord/prs/{dn}", None),
    ("resumen diario legacy", f"/usersummary-service/usersummary/daily/{dn}", {"calendarDate": d}),
    ("actividad: detalle JSON", f"/activity-service/activity/{aid}/details", {"maxChartSize": 100000}),
    ("actividad: splits/laps", f"/activity-service/activity/{aid}/splits", None),
    ("actividad: zonas FC", f"/activity-service/activity/{aid}/hrTimeInZones", None),
    ("actividad: zonas potencia", f"/activity-service/activity/{aid}/powerTimeInZones", None),
    ("actividad: clima", f"/activity-service/activity/{aid}/weather", None),
    ("actividad: equipo", f"/gear-service/gear/filterGear", {"activityId": aid}),
]

def shape(x):
    if isinstance(x, dict): return "dict " + ",".join(list(x.keys())[:12])
    if isinstance(x, list): return f"list[{len(x)}] " + (shape(x[0]) if x else "")
    return type(x).__name__

print(f"displayName={dn} actividad={aid}\n")
for name, path, params in CANDIDATES:
    try:
        r = c._call(lambda cl: cl.get(path, params=params))
        size = len(json.dumps(r)) if r is not None else 0
        print(f"[SÍ] {name:26} {size:>8} B  {shape(r)[:110]}")
    except Exception as e:
        code = getattr(e, "status_code", "")
        print(f"[NO] {name:26} {code} {str(e)[:60]}")
