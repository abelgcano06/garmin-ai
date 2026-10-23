"""
Prueba rápida de la API oficial contra tus datos reales.

    python tools/smoke_test_official.py --email tu@correo.com [--date 2026-10-21]

Usa la key de data/users/<id>/garmin_api_key; si no existe, la de
~/.config/garmin/connect-personal-api-key (la que guarda garmin-personal-mcp).
No escribe nada en data/ salvo el caché del bearer token.
"""

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # redes corporativas que inspeccionan HTTPS
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from app_context import email_to_user_id  # noqa: E402
from garmin_official import ApexGarminClient  # noqa: E402
from sleep_engine_v1 import build_sleep_series, compute_analysis  # noqa: E402
from day_engine_v1 import build_day_series, compute_day_analysis  # noqa: E402
from activity_pipeline import build_activity_series_csv  # noqa: E402


def ok(label, value):
    print(f"  [OK] {label}: {value}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--date", default=(date.today() - timedelta(days=1)).isoformat())
    a = ap.parse_args()
    uid = email_to_user_id(a.email)
    c = ApexGarminClient.for_user(uid)

    print(f"\nUsuario {uid} · fecha {a.date}")
    ok("perfil", c.get_full_name())

    st = c.get_stats(a.date)
    ok("stats", {k: st.get(k) for k in ("restingHeartRate", "averageStressLevel", "bodyBatteryHighestValue", "totalSteps")})

    sd = c.get_sleep_data(a.date)
    raw = {"meta": {"date": a.date}, "calls": {"get_stats": {"ok": True, "data": st}, "get_sleep_data": {"ok": True, "data": sd}}}
    ser = build_sleep_series(raw)
    ok("serie de sueño", {k: len(v) for k, v in ser.items() if isinstance(v, list)})
    ok("sleep_engine", compute_analysis(raw, ser).get("recovery_summary"))

    hr, bb, hrv = c.get_heart_rates(a.date), c.get_body_battery(a.date), c.get_hrv_data(a.date)
    rawd = {"meta": {"date": a.date}, "calls": {
        "get_stats": {"ok": True, "data": st}, "get_heart_rates": {"ok": True, "data": hr},
        "get_stress_data": {"ok": True, "data": None}, "get_body_battery": {"ok": True, "data": bb},
        "get_respiration_data": {"ok": True, "data": None}, "get_hrv_data": {"ok": True, "data": hrv}}}
    ok("day_engine", compute_day_analysis(rawd, build_day_series(rawd)).get("recovery_summary"))

    acts = c.get_activities_by_date((date.fromisoformat(a.date) - timedelta(days=14)).isoformat(), a.date)
    ok("actividades 14 d", len(acts))
    with_power = next((x for x in acts if x.get("avgPower")), None)
    if with_power:
        det = c.get_activity_details(with_power["activityId"])
        ok("FIT → serie", f"{with_power['activityName']}: {det['metricsCount']} puntos")
        path = build_activity_series_csv(det, with_power["activityId"], user_id=uid)
        ok("CSV", path)
    print("\nTodo bien: la API oficial alimenta los motores de Apex.\n")


if __name__ == "__main__":
    main()
