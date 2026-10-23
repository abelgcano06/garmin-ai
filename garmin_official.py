"""
garmin_official.py
==================
Cliente de Garmin para Apex basado en la API oficial (Garmin Connect Personal API).

Reemplaza a garminconnect/garth. Expone los mismos métodos que usaban los
pipelines de Apex (get_stats, get_sleep_data, get_activities_by_date, ...)
y devuelve datos con la misma forma que esperan los motores, así que
sleep_engine, day_engine, activity_analyzer y master_engine no cambian.

Multiusuario desde el inicio: cada instancia representa a UN usuario y lleva
su propia API key y su propio caché de bearer token.

Uso:
    from garmin_official import ApexGarminClient
    client = ApexGarminClient.for_user("abel")          # busca la key del usuario
    client = ApexGarminClient(api_key="GCDC_...")       # key explícita

Orden para encontrar la API key (resolve_user_api_key):
    1. api_key explícita
    2. variable de entorno GARMIN_PERSONAL_API_KEY__<USER_ID> (mayúsculas, no alfanum -> _)
    3. archivo data/users/<user_id>/garmin_api_key   (data/ está en .gitignore)
    4. variable de entorno GARMIN_PERSONAL_API_KEY
    5. ~/.config/garmin/connect-personal-api-key      (lo que crea `garmin-personal-mcp auth`)

Limitaciones de la API Personal frente a la puerta no oficial:
    - No hay serie intradía de estrés ni de respiración: get_stress_data y
      get_respiration_data regresan None y los motores usan su fallback.
    - No hay "activity details" en JSON: get_activity_details descarga el .FIT
      original y lo convierte al mismo formato (metricDescriptors +
      activityDetailMetrics). Es igual o más detallado (1 punto por segundo).
    - No hay Training API (subir workouts): upload_workout lanza
      FeatureNotAvailable. Requiere el tier Starter/Enterprise.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from garmin_personal_api import (
    GarminPersonalApiClient,
    GarminPersonalApiError,
    HttpError,
    PersonalApiAuthenticator,
    resolve_api_key,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "data", "users")

UNAUTHORIZED = 401
KEY_REJECTED = {400, 401, 403}
KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken"


class GarminKeyError(RuntimeError):
    """La API key no existe, expiró o Garmin la rechazó."""


class FeatureNotAvailable(RuntimeError):
    """La API Personal no ofrece esta función."""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _iso(d: str | date) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


def _env_name(user_id: str) -> str:
    return "GARMIN_PERSONAL_API_KEY__" + re.sub(r"[^A-Za-z0-9]", "_", user_id).upper()


def user_key_path(user_id: str) -> str:
    return os.path.join(USERS_DIR, user_id, "garmin_api_key")


def user_token_cache_path(user_id: str | None) -> Path:
    if not user_id:
        return Path("~/.config/garmin/connect-personal-api-bearer-token.json").expanduser()
    return Path(USERS_DIR) / user_id / "garmin_bearer_token.json"


def resolve_user_api_key(user_id: str | None = None, api_key: str | None = None) -> str:
    if api_key:
        return api_key.strip()
    if user_id:
        v = os.environ.get(_env_name(user_id))
        if v:
            return v.strip()
        p = user_key_path(user_id)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                v = f.read().strip()
            if v:
                return v
    try:
        return resolve_api_key()
    except GarminPersonalApiError as exc:
        raise GarminKeyError(
            f"No encontré una Personal API key de Garmin"
            f"{' para ' + user_id if user_id else ''}. Créala en {KEY_PAGE} y "
            f"guárdala con save_user_api_key()."
        ) from exc


def save_user_api_key(user_id: str, api_key: str) -> str:
    """Guarda la key del usuario en data/users/<id>/garmin_api_key con permisos 600."""
    path = user_key_path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(api_key.strip())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _ms(ts: Any) -> int | None:
    """Timestamps de Garmin → epoch ms."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    s = str(ts).replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
    return None


def _between(pairs: list, start_ms: int, end_ms: int) -> list:
    return [p for p in pairs or [] if isinstance(p, (list, tuple)) and len(p) >= 2
            and p[0] is not None and p[1] is not None and start_ms <= p[0] <= end_ms]


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class ApexGarminClient:
    """Un usuario = una instancia. Compatible con los métodos de garminconnect que usa Apex."""

    def __init__(self, api_key: str | None = None, user_id: str | None = None, timeout: float = 30.0):
        self.user_id = user_id
        self._api_key = resolve_user_api_key(user_id, api_key)
        cache = user_token_cache_path(user_id)
        cache.parent.mkdir(parents=True, exist_ok=True)
        self._auth = PersonalApiAuthenticator(timeout=timeout, bearer_token_cache_file=cache)
        self._timeout = timeout
        self._client: GarminPersonalApiClient | None = None

    @classmethod
    def for_user(cls, user_id: str, **kw) -> "ApexGarminClient":
        return cls(user_id=user_id, **kw)

    # ── auth / transporte ────────────────────────────────────────────────────
    def _token(self, force: bool = False) -> str:
        try:
            return self._auth.obtain_token(self._api_key, force_refresh=force).access_token
        except HttpError as exc:
            if exc.status_code in KEY_REJECTED:
                raise GarminKeyError(
                    f"Garmin rechazó la Personal API key (HTTP {exc.status_code}). "
                    f"Puede haber expirado o sido borrada. Crea otra en {KEY_PAGE}."
                ) from exc
            raise

    def _api(self) -> GarminPersonalApiClient:
        if self._client is None:
            self._client = GarminPersonalApiClient(self._token(), timeout=self._timeout)
        return self._client

    def _call(self, fn):
        """Ejecuta fn(client); si el bearer fue revocado (401) lo renueva y reintenta una vez."""
        try:
            return fn(self._api())
        except HttpError as exc:
            if exc.status_code != UNAUTHORIZED:
                raise
            self._api().update_bearer_token(self._token(force=True))
            return fn(self._api())

    def close(self):
        if self._client:
            self._client.close()
        self._auth.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def login(self, *a, **k):
        """Compatibilidad: valida la key pidiendo el perfil."""
        self.get_profile_settings()
        return True

    # ── perfil ───────────────────────────────────────────────────────────────
    def get_profile_settings(self):
        return self._call(lambda c: c.get_user_profile_settings())

    def get_full_name(self):
        p = self.get_profile_settings() or {}
        return p.get("displayName") or p.get("fullName") or ""

    def get_heart_rate_zones(self):
        return self._call(lambda c: c.get_heart_rate_zones())

    # ── actividades ──────────────────────────────────────────────────────────
    def get_activities_by_date(self, start: str | date, end: str | date, activitytype: str | None = None) -> list:
        out, page, size = [], 0, 100
        while True:
            res = self._call(lambda c: c.search_activities(
                start=page * size, limit=size, start_date=_iso(start), end_date=_iso(end),
                activity_type=activitytype))
            items = res if isinstance(res, list) else (res or {}).get("results") or (res or {}).get("activityList") or []
            out.extend(items)
            if len(items) < size:
                return out
            page += 1

    def get_activities(self, start: int = 0, limit: int = 20) -> list:
        res = self._call(lambda c: c.search_activities(start=start, limit=limit))
        return res if isinstance(res, list) else (res or {}).get("results", [])

    def get_activity(self, activity_id: int | str) -> dict:
        return self._call(lambda c: c.get_activity(activity_id))

    def download_activity_fit(self, activity_id: int | str) -> bytes:
        """Bytes del .FIT original (descomprimido del ZIP)."""
        raw = self._call(lambda c: c.download_activity(activity_id))
        if raw[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                name = next((n for n in z.namelist() if n.lower().endswith(".fit")), None)
                if not name:
                    raise GarminPersonalApiError("El ZIP de la actividad no trae un .fit")
                return z.read(name)
        return raw

    def get_activity_details(self, activity_id: int | str, maxchart: int | None = None, maxpoly: int | None = None) -> dict:
        """Convierte el .FIT al formato de activity details de Connect que lee activity_pipeline."""
        return fit_to_activity_details(self.download_activity_fit(activity_id), activity_id)

    def upload_workout(self, *a, **k):
        raise FeatureNotAvailable(
            "La API Personal de Garmin no permite enviar workouts al reloj. "
            "Se necesita el Training API (tier Starter o Enterprise).")

    # ── día ──────────────────────────────────────────────────────────────────
    def get_daily_summary_v2(self, d: str | date) -> dict:
        res = self._call(lambda c: c.get_daily_summaries(_iso(d), _iso(d))) or {}
        data = res.get("data") if isinstance(res, dict) else res
        return (data or [{}])[0] or {}

    def get_stats(self, d: str | date) -> dict:
        """Mapea el resumen diario v2 al formato legacy de get_stats que leen los motores."""
        x = self.get_daily_summary_v2(d)
        if not x:
            return {}
        mv, hr, st = x.get("movement") or {}, x.get("heartRate") or {}, x.get("stress") or {}
        bb, rs, ox = x.get("bodyBattery") or {}, x.get("respiration") or {}, x.get("pulseOx") or {}
        im, cal, wc = x.get("intensityMinutes") or {}, x.get("calories") or {}, x.get("wellnessChronology") or {}
        steps = (mv.get("steps") or {}).get("value")
        sleep_evt = next((e for e in bb.get("activityEvents") or [] if e.get("eventType") == "SLEEP"), None)
        total_ms = st.get("totalDurationInMillis")
        hi_ms = st.get("highStressDurationInMillis")
        stats = {
            "calendarDate": x.get("calendarDate") or _iso(d),
            "wellnessStartTimeGmt": wc.get("startTimestampGmt"),
            "wellnessEndTimeGmt": wc.get("endTimestampGmt"),
            "durationInMilliseconds": wc.get("totalDurationInMillis"),
            "totalSteps": steps, "steps": steps,
            "dailyStepGoal": (mv.get("steps") or {}).get("goal"),
            "activeKilocalories": cal.get("burnedActive"),
            "wellnessActiveKilocalories": cal.get("burnedActive"),
            "bmrKilocalories": cal.get("burnedResting"),
            "totalKilocalories": cal.get("burnedTotal"),
            "restingHeartRate": hr.get("restingValue"),
            "minHeartRate": hr.get("minValue"), "maxHeartRate": hr.get("maxValue"),
            "minAvgHeartRate": hr.get("minValue"), "maxAvgHeartRate": hr.get("maxValue"),
            "averageStressLevel": st.get("avgLevel") if (st.get("avgLevel") or -1) >= 0 else None,
            "maxStressLevel": st.get("maxLevel"),
            "stressQualifier": st.get("qualifier"),
            "highStressPercentage": round(hi_ms / total_ms * 100, 1) if hi_ms is not None and total_ms else None,
            "restStressDuration": (st.get("restDurationInMillis") or 0) / 1000 or None,
            "lowStressDuration": (st.get("lowStressDurationInMillis") or 0) / 1000 or None,
            "mediumStressDuration": (st.get("mediumStressDurationInMillis") or 0) / 1000 or None,
            "highStressDuration": (hi_ms or 0) / 1000 or None,
            "activityStressDuration": (st.get("activityDurationInMillis") or 0) / 1000 or None,
            "sedentarySeconds": None,
            "moderateIntensityMinutes": im.get("moderate"),
            "vigorousIntensityMinutes": im.get("vigorous"),
            "intensityMinutesGoal": im.get("goal"),
            "bodyBatteryHighestValue": bb.get("maxValue"),
            "bodyBatteryLowestValue": bb.get("minValue"),
            "bodyBatteryMostRecentValue": bb.get("latestValue"),
            "bodyBatteryChargedValue": bb.get("chargedValue"),
            "bodyBatteryDrainedValue": bb.get("drainedValue"),
            "bodyBatteryDuringSleep": (sleep_evt or {}).get("bodyBatteryImpact"),
            "bodyBatteryAtWakeTime": None,
            "avgWakingRespirationValue": rs.get("avgValue"),
            "lowestRespirationValue": rs.get("minValue"),
            "highestRespirationValue": rs.get("maxValue"),
            "averageSpo2": ox.get("avgValue"), "lowestSpo2": ox.get("minValue"),
            "_source": "garmin_personal_api_v2",
        }
        # Body Battery al despertar = valor al final del evento de sueño
        if sleep_evt:
            try:
                bbd = self.get_body_battery(d, d) or []
                arr = (bbd[0] if bbd else {}).get("bodyBatteryValuesArray") or []
                wake = (_ms(sleep_evt.get("eventStartTimeGmt") + "Z") or 0) + int(sleep_evt.get("durationInMilliseconds") or 0)
                before = [p for p in arr if p[1] is not None and p[0] <= wake]
                if before:
                    stats["bodyBatteryAtWakeTime"] = before[-1][1]
            except Exception:
                pass
        return stats

    def get_user_summary(self, d):
        return self.get_stats(d)

    def get_heart_rates(self, d: str | date) -> dict:
        return self._call(lambda c: c.get_daily_heart_rate(_iso(d))) or {}

    def get_rhr_day(self, d: str | date) -> dict:
        hr = self.get_heart_rates(d)
        return {"restingHeartRate": hr.get("restingHeartRate"),
                "lastSevenDaysAvgRestingHeartRate": hr.get("lastSevenDaysAvgRestingHeartRate")}

    def get_body_battery(self, start: str | date, end: str | date | None = None) -> list:
        res = self._call(lambda c: c.get_daily_body_battery(_iso(start), _iso(end or start)))
        return res if isinstance(res, list) else (res or {}).get("results", [res] if res else [])

    def get_hrv_data(self, d: str | date) -> dict:
        return self._call(lambda c: c.get_daily_hrv(_iso(d))) or {}

    def get_hrv_summaries(self, start, end) -> dict:
        return self._call(lambda c: c.get_daily_hrv_summaries(_iso(start), _iso(end))) or {}

    def get_spo2_data(self, d: str | date) -> dict:
        return self._call(lambda c: c.get_daily_spo2(_iso(d))) or {}

    def get_stress_data(self, d):
        """Sin serie intradía en la API Personal; los motores usan el promedio de get_stats."""
        return None

    def get_respiration_data(self, d):
        """Sin serie intradía en la API Personal; los motores usan los valores de get_stats."""
        return None

    # ── sueño ────────────────────────────────────────────────────────────────
    def get_sleep_summary(self, d: str | date) -> dict:
        return self._call(lambda c: c.get_daily_sleep(_iso(d))) or {}

    def get_sleep_summaries(self, start, end):
        return self._call(lambda c: c.get_daily_sleep_summaries(_iso(start), _iso(end)))

    def get_sleep_data(self, d: str | date) -> dict:
        """
        Arma la estructura de dailySleepData de Connect a partir de piezas oficiales:
        resumen de sueño + FC (día anterior y actual) + HRV + Body Battery recortados
        a la ventana de sueño. sleepLevels/sleepStress no existen en la API Personal;
        sleep_engine infiere las fases desde el DTO.
        """
        dto = self.get_sleep_summary(d)
        if not dto or not dto.get("sleepTimeSeconds"):
            return {"dailySleepDTO": dto or {}}
        s, e = _ms(dto.get("sleepStartTimestampGMT")), _ms(dto.get("sleepEndTimestampGMT"))
        prev = (datetime.strptime(_iso(d), "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
        out: dict[str, Any] = {"dailySleepDTO": dto, "sleepLevels": [], "sleepStress": [], "sleepMovement": []}

        try:
            hr_vals = []
            for day in (prev, _iso(d)):
                hr_vals += (self.get_heart_rates(day) or {}).get("heartRateValues") or []
            out["sleepHeartRate"] = [{"startGMT": t, "value": v} for t, v in _between(hr_vals, s, e)]
            rhr = self.get_heart_rates(d) or {}
            out["restingHeartRate"] = rhr.get("restingHeartRate")
        except Exception:
            out["sleepHeartRate"] = []

        try:
            hrv = self.get_hrv_data(d) or {}
            out["hrvData"] = [{"startGMT": r.get("readingTimeGMT"), "value": r.get("hrvValue")}
                              for r in hrv.get("hrvReadings") or []]
            summ = hrv.get("hrvSummary") or {}
            out["avgOvernightHrv"] = summ.get("lastNightAvg")
            out["hrvStatus"] = summ.get("status")
        except Exception:
            out["hrvData"] = []

        try:
            arr = []
            for day in (prev, _iso(d)):
                for item in self.get_body_battery(day, day) or []:
                    arr += item.get("bodyBatteryValuesArray") or []
                    for ev in item.get("bodyBatteryActivityEvent") or []:
                        if ev.get("eventType") == "SLEEP" and day == _iso(d):
                            out["bodyBatteryChange"] = ev.get("bodyBatteryImpact")
            out["sleepBodyBattery"] = [{"startGMT": t, "value": v} for t, v in _between(arr, s, e)]
        except Exception:
            out["sleepBodyBattery"] = []

        out["wellnessEpochRespirationDataDTOList"] = []
        out["wellnessEpochSPO2DataDTOList"] = []
        return out


# ─────────────────────────────────────────────────────────────────────────────
# FIT → activity details (formato Connect)
# ─────────────────────────────────────────────────────────────────────────────

_FIT_FIELDS = [
    # (clave Connect,         campos FIT en orden de preferencia,         conversión)
    ("directTimestamp",       ["timestamp"],                               "ts"),
    ("sumElapsedDuration",    [],                                          "elapsed"),
    ("sumDistance",           ["distance"],                                None),
    ("directElevation",       ["enhanced_altitude", "altitude"],           None),
    ("directSpeed",           ["enhanced_speed", "speed"],                 None),
    ("directBikeCadence",     ["cadence"],                                 None),
    ("directHeartRate",       ["heart_rate"],                              None),
    ("directPower",           ["power"],                                   None),
    ("directRespirationRate", ["enhanced_respiration_rate", "respiration_rate"], None),
    ("directVerticalSpeed",   [],                                          "vspeed"),
    ("directGrit",            ["grit"],                                    None),
    ("directAvailableStamina", [],                                         None),
    ("directPotentialStamina", [],                                         None),
    ("directPerformanceCondition", [],                                     None),
    ("directLatitude",        ["position_lat"],                            "semicircles"),
    ("directLongitude",       ["position_long"],                           "semicircles"),
    ("directAirTemperature",  ["temperature"],                             None),
]


FIT_EPOCH_OFFSET = 631065600  # segundos entre 1970-01-01 y 1989-12-31


def fit_to_activity_details(fit_bytes: bytes, activity_id: int | str | None = None) -> dict:
    from garmin_fit_sdk import Decoder, Stream

    decoder = Decoder(Stream.from_byte_array(bytearray(fit_bytes)))
    messages, errors = decoder.read(convert_datetimes_to_dates=False, convert_types_to_strings=True)
    records = messages.get("record_mesgs") or []

    descriptors = [{"metricsIndex": i, "key": k} for i, (k, _, _) in enumerate(_FIT_FIELDS)]
    rows, t0, prev = [], None, None
    for rec in records:
        r = rec
        ts = r.get("timestamp")
        if ts is None:
            continue
        # convert_datetimes_to_dates=False → segundos desde la época FIT (1989-12-31)
        ts_ms = int((ts + FIT_EPOCH_OFFSET) * 1000) if isinstance(ts, (int, float)) else _ms(str(ts))
        if t0 is None:
            t0 = ts_ms
        metrics = []
        for key, fields, conv in _FIT_FIELDS:
            val = next((r.get(f) for f in fields if r.get(f) is not None), None)
            if conv == "ts":
                val = ts_ms
            elif conv == "elapsed":
                val = (ts_ms - t0) / 1000.0
            elif conv == "semicircles" and val is not None:
                val = val * (180.0 / 2 ** 31)
            elif conv == "vspeed":
                alt = next((r.get(f) for f in ("enhanced_altitude", "altitude") if r.get(f) is not None), None)
                if prev and alt is not None and prev[1] is not None and ts_ms > prev[0]:
                    val = (alt - prev[1]) / ((ts_ms - prev[0]) / 1000.0)
                prev = (ts_ms, alt)
            metrics.append(val)
        rows.append({"metrics": metrics})

    return {
        "activityId": activity_id,
        "measurementCount": len(descriptors),
        "metricsCount": len(rows),
        "metricDescriptors": descriptors,
        "activityDetailMetrics": rows,
        "_source": "fit_file",
        "_fit_errors": [str(e) for e in errors] if errors else [],
        "_sessions": messages.get("session_mesgs") or [],
        "_laps": messages.get("lap_mesgs") or [],
    }
