"""Muestra la forma cruda de Body Battery para depurar.  python tools/debug_body_battery.py --email X --date YYYY-MM-DD"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
from app_context import email_to_user_id
from garmin_official import ApexGarminClient

ap = argparse.ArgumentParser(); ap.add_argument("--email", required=True); ap.add_argument("--date", required=True)
a = ap.parse_args()
c = ApexGarminClient.for_user(email_to_user_id(a.email))
raw = c._call(lambda cl: cl.get_daily_body_battery(a.date, a.date))
print("tipo:", type(raw).__name__)
items = raw if isinstance(raw, list) else [raw]
for it in items[:2]:
    print("llaves:", list(it.keys()) if isinstance(it, dict) else it)
    arr = (it or {}).get("bodyBatteryValuesArray") or []
    print("lecturas:", len(arr), "| primeras:", arr[:3], "| últimas:", arr[-2:])
    print("descriptores:", it.get("bodyBatteryValueDescriptorDTOList"))
sd = c.get_sleep_summary(a.date)
print("sueño GMT:", sd.get("sleepStartTimestampGMT"), "->", sd.get("sleepEndTimestampGMT"))
