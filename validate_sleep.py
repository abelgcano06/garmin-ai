"""
validate_sleep.py -- Auditor?a de integridad de datos de sue?o

Verifica 3 capas:
  1. sleep_analysis.json  vs  f?rmulas del engine (recalcula in situ)
  2. sleep_analysis.json  vs  /api/sleep-full (passthrough del servidor)
  3. Valores de display (formateo que ve el usuario)

Uso:
    python validate_sleep.py [YYYY-MM-DD]
    python validate_sleep.py           # usa la noche m?s reciente
"""

import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone

# ??? Config ??????????????????????????????????????????????????????????????????

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "data", "users")
GARMIN_SESSION = os.path.join(BASE_DIR, "garmin_session.json")
SERVER_URL = "http://127.0.0.1:7845"

# ??? Helpers ?????????????????????????????????????????????????????????????????

OK   = "[OK] "
ERR  = "[!!] "
WARN = "[??] "

def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def ok(msg):    print(f"  {OK} {msg}")
def err(msg):   print(f"  {ERR} {msg}")
def warn(msg):  print(f"  {WARN} {msg}")
def info(msg):  print(f"       {msg}")

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def get_user_dir():
    sess = load_json(GARMIN_SESSION)
    email = sess.get("email", "")
    key = email.replace("@", "_at_").replace(".", "_")
    return os.path.join(USERS_DIR, key)

def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_error": str(e)}

def fmt_val(v):
    if v is None: return "null"
    if isinstance(v, float): return f"{v:.4f}"
    return str(v)

def compare(label, expected, got, tolerance=0.0001):
    """Compare two values, print result."""
    if expected is None and got is None:
        warn(f"{label}: ambos null")
        return
    if expected is None:
        warn(f"{label}: JSON=null, API={fmt_val(got)}")
        return
    if got is None:
        err(f"{label}: JSON={fmt_val(expected)}, API=null  <- FALTA EN API")
        return
    if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
        if abs(float(expected) - float(got)) <= tolerance:
            ok(f"{label}: {fmt_val(expected)}")
        else:
            err(f"{label}: JSON={fmt_val(expected)}, API={fmt_val(got)}  <- DIFERENTE")
    else:
        if str(expected) == str(got):
            ok(f"{label}: {expected}")
        else:
            err(f"{label}: JSON={expected!r}, API={got!r}  <- DIFERENTE")


# ??? CAPA 1: Verificaci?n de c?lculos del engine ?????????????????????????????

def mean(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None

def stddev(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 2: return 0.0
    m = mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))

def count_spikes(values, threshold_std=1.0):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals: return 0
    m = mean(vals)
    sd = stddev(vals)
    if sd == 0: return 0
    return sum(1 for v in vals if abs(v - m) > threshold_std * sd)

def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))

def verify_calculations(analysis, series):
    """Recalculate key Apex metrics from raw series and compare to stored values."""
    header("CAPA 1 -- Rec?lculo de m?tricas Apex")

    sa = analysis.get("sleep_architecture", {})
    sw = analysis.get("sleep_window", {})
    im = analysis.get("instability_markers", {})
    sr = analysis.get("stress_recovery", {})
    cr = analysis.get("cardiac_recovery", {})
    ar = analysis.get("autonomic_recovery", {})
    ox = analysis.get("oxygenation", {})
    rr = analysis.get("respiratory_recovery", {})
    er = analysis.get("energy_recharge", {})

    # ?? sleep_efficiency ??????????????????????????????????????????????????????
    sleep_time_s = sw.get("sleep_time_seconds") or 0
    tib_s        = sw.get("time_in_bed_seconds") or 0
    eff_calc     = sleep_time_s / tib_s if tib_s > 0 else None
    eff_stored   = sw.get("sleep_efficiency")
    print(f"\n  sleep_efficiency")
    info(f"  f?rmula: sleep_time({sleep_time_s}s) / time_in_bed({tib_s}s) = {fmt_val(eff_calc)}")
    if eff_calc is not None and eff_stored is not None:
        if abs(eff_calc - eff_stored) < 0.001:
            ok(f"almacenado={fmt_val(eff_stored)} <- correcto")
        else:
            err(f"calculado={fmt_val(eff_calc)}, almacenado={fmt_val(eff_stored)} <- DISCREPANCIA")
    else:
        warn(f"no se puede verificar (faltan datos base)")

    # ?? deep_ratio / rem_ratio ????????????????????????????????????????????????
    deep_s  = sa.get("deep_sleep_seconds") or 0
    rem_s   = sa.get("rem_sleep_seconds") or 0
    light_s = sa.get("light_sleep_seconds") or 0
    total_s = deep_s + rem_s + light_s
    print(f"\n  deep_ratio / rem_ratio")
    info(f"  deep={deep_s}s  rem={rem_s}s  light={light_s}s  total={total_s}s")
    if total_s > 0:
        dr_calc = deep_s / total_s
        rr_calc = rem_s  / total_s
        dr_stored = sa.get("deep_ratio")
        rr_stored = sa.get("rem_ratio")
        if dr_stored is not None and abs(dr_calc - dr_stored) < 0.001:
            ok(f"deep_ratio={fmt_val(dr_stored)} ({dr_stored*100:.1f}%) <- correcto")
        else:
            err(f"deep_ratio calc={fmt_val(dr_calc)}, almacenado={fmt_val(dr_stored)}")
        if rr_stored is not None and abs(rr_calc - rr_stored) < 0.001:
            ok(f"rem_ratio={fmt_val(rr_stored)} ({rr_stored*100:.1f}%) <- correcto")
        else:
            err(f"rem_ratio calc={fmt_val(rr_calc)}, almacenado={fmt_val(rr_stored)}")
    else:
        warn("no hay segundos de etapas para recalcular ratios")

    # ?? micro_arousal_score ???????????????????????????????????????????????????
    movement_vals = [x["value"] for x in series.get("movement", []) if isinstance(x, dict) and x.get("value") is not None]
    stress_vals   = [x["value"] for x in series.get("stress", [])   if isinstance(x, dict) and x.get("value") is not None and x["value"] >= 0]
    awake_count   = sa.get("awake_count") or 0
    mv_spikes     = count_spikes(movement_vals)
    st_spikes     = count_spikes(stress_vals)
    micro_calc    = clamp(awake_count * 10 + mv_spikes * 3 + st_spikes * 2)
    micro_stored  = im.get("micro_arousal_score")

    print(f"\n  micro_arousal_score")
    info(f"  f?rmula: awake_count({awake_count})x10 + mv_spikes({mv_spikes})x3 + st_spikes({st_spikes})x2 = {awake_count*10+mv_spikes*3+st_spikes*2} -> clamp-> {micro_calc}")
    info(f"  (movement samples={len(movement_vals)}, stress samples={len(stress_vals)})")
    if micro_stored is not None and abs(micro_calc - micro_stored) < 0.5:
        ok(f"almacenado={micro_stored} <- correcto")
    else:
        err(f"calculado={micro_calc}, almacenado={micro_stored} <- DISCREPANCIA")

    # ?? movement_spike_count ??????????????????????????????????????????????????
    mv_spike_stored = im.get("movement_spike_count")
    print(f"\n  movement_spike_count")
    info(f"  spikes detectados (std>1.0): {mv_spikes}")
    if mv_spike_stored is not None and mv_spikes == mv_spike_stored:
        ok(f"almacenado={mv_spike_stored} <- correcto")
    else:
        err(f"calculado={mv_spikes}, almacenado={mv_spike_stored} <- DISCREPANCIA")

    # avg_overnight_hrv
    # NOTA: el engine usa dto.get("avgOvernightHrv") directamente de Garmin
    # como fuente autoritativa. Nuestra media de la serie puede diferir
    # ligeramente (Garmin aplica su propio filtrado interno).
    hrv_vals  = [x["value"] for x in series.get("hrv", []) if isinstance(x, dict) and x.get("value") is not None]
    hrv_calc  = mean(hrv_vals)
    hrv_stored = ar.get("avg_overnight_hrv")
    print(f"\n  avg_overnight_hrv")
    info(f"  fuente: Garmin avgOvernightHrv (autoritativo) con fallback a media de serie")
    info(f"  serie: {len(hrv_vals)} samples, media serie={fmt_val(hrv_calc)}")
    info(f"  almacenado (Garmin): {hrv_stored}")
    if hrv_calc is not None and hrv_stored is not None:
        diff = abs(hrv_calc - hrv_stored)
        if diff < 1.0:
            ok(f"coincide con serie (diff={diff:.2f} ms)")
        elif diff < 5.0:
            warn(f"diff={diff:.1f} ms -- Garmin usa filtrado propio vs media bruta de serie (ESPERADO)")
        else:
            err(f"diff={diff:.1f} ms -- revisa si avgOvernightHrv llega del raw")

    # ?? avg_sleep_hr ?????????????????????????????????????????????????????????
    hr_vals  = [x["value"] for x in series.get("heart_rate", []) if isinstance(x, dict) and x.get("value") is not None]
    hr_calc  = mean(hr_vals)
    hr_stored = cr.get("avg_sleep_hr")
    print(f"\n  avg_sleep_hr")
    info(f"  samples FC={len(hr_vals)}, media calculada={fmt_val(hr_calc)}")
    if hr_calc is not None and hr_stored is not None and abs(hr_calc - hr_stored) < 1.0:
        ok(f"almacenado={hr_stored} <- correcto")
    else:
        err(f"calculado={fmt_val(hr_calc)}, almacenado={hr_stored} <- DISCREPANCIA")

    # ?? body_battery_change ???????????????????????????????????????????????????
    bb_start = er.get("body_battery_start")
    bb_end   = er.get("body_battery_end")
    bb_change_stored = er.get("body_battery_change")
    bb_change_calc = (bb_end - bb_start) if (bb_start is not None and bb_end is not None) else None
    print(f"\n  body_battery_change")
    info(f"  f?rmula: bb_end({bb_end}) - bb_start({bb_start}) = {fmt_val(bb_change_calc)}")
    if bb_change_calc is not None and bb_change_stored is not None and abs(bb_change_calc - bb_change_stored) < 0.5:
        ok(f"almacenado={bb_change_stored} <- correcto")
    elif bb_change_calc is None:
        warn("faltan bb_start o bb_end")
    else:
        err(f"calculado={fmt_val(bb_change_calc)}, almacenado={bb_change_stored} <- DISCREPANCIA")

    # avg_spo2 / min_spo2
    # NOTA: el engine usa dto.get("averageSpO2Value") / "lowestSpO2Value" de Garmin
    # directamente. La serie spo2 puede estar vacia si Garmin no genero
    # lecturas minuto a minuto esa noche (normal en noches sin datos continuos).
    spo2_vals  = [x["value"] for x in series.get("spo2", []) if isinstance(x, dict) and x.get("value") is not None]
    spo2_calc  = mean(spo2_vals)
    spo2_stored = ox.get("avg_spo2")
    min_spo2_stored = ox.get("min_spo2")
    min_spo2_calc = min(spo2_vals) if spo2_vals else None
    print(f"\n  avg_spo2 / min_spo2")
    info(f"  fuente: Garmin averageSpO2Value / lowestSpO2Value (autoritativo)")
    info(f"  serie: {len(spo2_vals)} samples (0 = Garmin no genero serie minuto a minuto)")
    info(f"  almacenado: avg={spo2_stored}, min={min_spo2_stored}")
    if not spo2_vals:
        warn(f"serie SpO2 vacia -- valores del DTO de Garmin directamente (ESPERADO)")
        ok(f"avg_spo2={spo2_stored} (fuente: Garmin DTO)")
        ok(f"min_spo2={min_spo2_stored} (fuente: Garmin DTO)")
    else:
        if spo2_calc is not None and spo2_stored is not None and abs(spo2_calc - spo2_stored) < 1.0:
            ok(f"avg_spo2={spo2_stored} <- correcto")
        else:
            err(f"avg_spo2 calc={fmt_val(spo2_calc)}, almacenado={spo2_stored}")
        if min_spo2_calc is not None and min_spo2_stored is not None and abs(min_spo2_calc - min_spo2_stored) < 1.0:
            ok(f"min_spo2={min_spo2_stored} <- correcto")
        else:
            err(f"min_spo2 calc={fmt_val(min_spo2_calc)}, almacenado={min_spo2_stored}")

    # ?? sleep_start_local timezone check ?????????????????????????????????????
    print(f"\n  sleep_start_local (timezone)")
    raw_local = sw.get("sleep_start_local", "")
    info(f"  valor almacenado: {raw_local}")
    info(f"  nota: Garmin usa +00:00 pero el valor es hora local, NO UTC")
    if raw_local and "+00:00" in raw_local:
        warn("sufijo +00:00 presente -- hora es local correcta pero el sufijo puede confundir")
        info(f"  hora correcta a mostrar: {raw_local[11:16]} (tomar chars 11-16 sin conversi?n)")
    else:
        ok("sin sufijo UTC problem?tico")


# ??? CAPA 2: JSON vs API passthrough ?????????????????????????????????????????

def verify_passthrough(analysis, date):
    header("CAPA 2 -- Passthrough garmin_server: JSON vs /api/sleep-full")

    url = f"{SERVER_URL}/api/sleep-full?date_param={date}"
    api = fetch_json(url)

    if "_error" in api:
        err(f"No se pudo conectar al servidor: {api['_error']}")
        info("Aseg?rate de que garmin_server.py est? corriendo")
        return

    api_date = api.get("date")
    if api_date != date:
        warn(f"El servidor retorn? fecha {api_date} (fallback), se esperaba {date}")
        date = api_date

    api_a = api.get("analysis") or {}
    ok(f"Servidor respondi? con fecha: {api_date}")

    # Todos los campos que el servidor debe exponer
    fields_to_check = [
        # sleep window
        ("sleep_window.sleep_time_seconds",  analysis.get("sleep_window", {}).get("sleep_time_seconds"),  api_a.get("sleep_time_seconds")),
        ("sleep_window.time_in_bed_seconds", analysis.get("sleep_window", {}).get("time_in_bed_seconds"), api_a.get("time_in_bed_seconds")),
        ("sleep_window.sleep_efficiency",    analysis.get("sleep_window", {}).get("sleep_efficiency"),    api_a.get("sleep_efficiency")),
        ("sleep_window.sleep_start_local",   analysis.get("sleep_window", {}).get("sleep_start_local"),   api_a.get("sleep_start_local")),
        ("sleep_window.sleep_end_local",     analysis.get("sleep_window", {}).get("sleep_end_local"),     api_a.get("sleep_end_local")),
        # architecture
        ("sleep_architecture.deep_ratio",    analysis.get("sleep_architecture", {}).get("deep_ratio"),    api_a.get("deep_ratio")),
        ("sleep_architecture.rem_ratio",     analysis.get("sleep_architecture", {}).get("rem_ratio"),     api_a.get("rem_ratio")),
        ("sleep_architecture.awake_count",   analysis.get("sleep_architecture", {}).get("awake_count"),   api_a.get("awake_count")),
        ("sleep_architecture.fragmentation_index", analysis.get("sleep_architecture", {}).get("fragmentation_index"), api_a.get("fragmentation_index")),
        # cardiac
        ("cardiac_recovery.avg_sleep_hr",    analysis.get("cardiac_recovery", {}).get("avg_sleep_hr"),    api_a.get("avg_sleep_hr")),
        ("cardiac_recovery.resting_hr",      analysis.get("cardiac_recovery", {}).get("resting_hr"),      api_a.get("resting_hr")),
        ("cardiac_recovery.hr_drop",         analysis.get("cardiac_recovery", {}).get("hr_drop"),         api_a.get("hr_drop")),
        # autonomic
        ("autonomic_recovery.avg_overnight_hrv",  analysis.get("autonomic_recovery", {}).get("avg_overnight_hrv"),  api_a.get("avg_overnight_hrv")),
        ("autonomic_recovery.hrv_recovery_score", analysis.get("autonomic_recovery", {}).get("hrv_recovery_score"), api_a.get("hrv_recovery_score")),
        ("autonomic_recovery.hrv_ramp_score",     analysis.get("autonomic_recovery", {}).get("hrv_ramp_score"),     api_a.get("hrv_ramp_score")),
        # stress
        ("stress_recovery.avg_sleep_stress",  analysis.get("stress_recovery", {}).get("avg_sleep_stress"),  api_a.get("avg_sleep_stress")),
        ("stress_recovery.stress_spike_count",analysis.get("stress_recovery", {}).get("stress_spike_count"),api_a.get("stress_spike_count")),
        # respiratory
        ("respiratory_recovery.avg_respiration",          analysis.get("respiratory_recovery", {}).get("avg_respiration"),          api_a.get("avg_respiration")),
        ("respiratory_recovery.respiratory_stability_score", analysis.get("respiratory_recovery", {}).get("respiratory_stability_score"), api_a.get("respiratory_stability_score")),
        ("respiratory_recovery.breathing_disruption_severity", analysis.get("respiratory_recovery", {}).get("breathing_disruption_severity"), api_a.get("breathing_disruption_severity")),
        # oxygenation
        ("oxygenation.avg_spo2",             analysis.get("oxygenation", {}).get("avg_spo2"),             api_a.get("avg_spo2")),
        ("oxygenation.min_spo2",             analysis.get("oxygenation", {}).get("min_spo2"),             api_a.get("min_spo2")),
        ("oxygenation.max_spo2",             analysis.get("oxygenation", {}).get("max_spo2"),             api_a.get("max_spo2")),
        ("oxygenation.spo2_drop_count",      analysis.get("oxygenation", {}).get("spo2_drop_count"),      api_a.get("spo2_drop_count")),
        # energy
        ("energy_recharge.body_battery_start",  analysis.get("energy_recharge", {}).get("body_battery_start"),  api_a.get("body_battery_start")),
        ("energy_recharge.body_battery_end",    analysis.get("energy_recharge", {}).get("body_battery_end"),    api_a.get("body_battery_end")),
        ("energy_recharge.body_battery_change", analysis.get("energy_recharge", {}).get("body_battery_change"), api_a.get("body_battery_change")),
        ("energy_recharge.recharge_efficiency", analysis.get("energy_recharge", {}).get("recharge_efficiency"), api_a.get("recharge_efficiency")),
        # sleep need
        ("sleep_need.sleep_need_gap_minutes",   analysis.get("sleep_need", {}).get("sleep_need_gap_minutes"),   api_a.get("sleep_need_gap_minutes")),
        ("sleep_need.feedback",                 analysis.get("sleep_need", {}).get("feedback"),                 api_a.get("sleep_need_feedback")),
        # circadian
        ("circadian_alignment.circadian_alignment_score", analysis.get("circadian_alignment", {}).get("circadian_alignment_score"), api_a.get("circadian_alignment_score")),
        ("circadian_alignment.sleep_alignment_status",    analysis.get("circadian_alignment", {}).get("sleep_alignment_status"),    api_a.get("sleep_alignment_status")),
        # instability
        ("instability_markers.micro_arousal_score",       analysis.get("instability_markers", {}).get("micro_arousal_score"),       api_a.get("micro_arousal_score")),
        ("instability_markers.overnight_instability_score",analysis.get("instability_markers", {}).get("overnight_instability_score"),api_a.get("overnight_instability_score")),
        ("instability_markers.movement_spike_count",       analysis.get("instability_markers", {}).get("movement_spike_count"),       api_a.get("movement_spike_count")),
        # recovery summary
        ("recovery_summary.overall_recovery_score",  analysis.get("recovery_summary", {}).get("overall_recovery_score"),  api_a.get("overall_recovery_score")),
        ("recovery_summary.physical_recovery_score", analysis.get("recovery_summary", {}).get("physical_recovery_score"), api_a.get("physical_recovery_score")),
        ("recovery_summary.neural_recovery_score",   analysis.get("recovery_summary", {}).get("neural_recovery_score"),   api_a.get("neural_recovery_score")),
    ]

    print()
    for label, json_val, api_val in fields_to_check:
        compare(label, json_val, api_val)


# ??? CAPA 3: Verificaci?n del formateo UI ????????????????????????????????????

def verify_display(analysis, series):
    header("CAPA 3 -- Verificaci?n de formateo UI")

    sw = analysis.get("sleep_window", {})
    sa = analysis.get("sleep_architecture", {})
    ox = analysis.get("oxygenation", {})
    er = analysis.get("energy_recharge", {})

    # sleep_start_local -- ?se muestra bien?
    raw_start = sw.get("sleep_start_local", "")
    raw_end   = sw.get("sleep_end_local", "")
    print(f"\n  Horas de sue?o (sin conversi?n de timezone)")
    if raw_start and len(raw_start) >= 16:
        time_str = raw_start[11:16]
        h, m = map(int, time_str.split(":"))
        ampm = "PM" if h >= 12 else "AM"
        h12 = h % 12 or 12
        ui_time = f"{h12}:{m:02d} {ampm}"
        ok(f"sleep_start -> '{raw_start}' -> UI muestra: {ui_time}")
    else:
        warn(f"sleep_start_local vac?o o mal formado: {raw_start!r}")

    if raw_end and len(raw_end) >= 16:
        time_str = raw_end[11:16]
        h, m = map(int, time_str.split(":"))
        ampm = "PM" if h >= 12 else "AM"
        h12 = h % 12 or 12
        ui_time = f"{h12}:{m:02d} {ampm}"
        ok(f"sleep_end   -> '{raw_end}' -> UI muestra: {ui_time}")

    # sleep_efficiency -- ?se formatea como porcentaje?
    eff = sw.get("sleep_efficiency")
    print(f"\n  sleep_efficiency (debe ser <=1.0, se muestra como %)")
    if eff is not None:
        if eff <= 1.0:
            ok(f"valor={eff} -> UI muestra: {round(eff*100)}%")
        else:
            err(f"valor={eff} -- ya es porcentaje, UI lo multiplicar?a por 100 -> ERROR de escala")

    # min_spo2 -- umbral de alerta
    min_spo2 = ox.get("min_spo2")
    print(f"\n  min_spo2 (alerta si < 88)")
    if min_spo2 is not None:
        if min_spo2 < 88:
            warn(f"min_spo2={min_spo2}% -> ALERTA SpO2 activa en UI")
        else:
            ok(f"min_spo2={min_spo2}% -> sin alerta")

    # body_battery_change -- signo
    bbc = er.get("body_battery_change")
    print(f"\n  body_battery_change (signo)")
    if bbc is not None:
        prefix = f"+{round(bbc)}" if bbc >= 0 else str(round(bbc))
        ok(f"valor={bbc} -> UI muestra: {prefix} pts")

    # deep_ratio / rem_ratio -- escala
    dr = sa.get("deep_ratio")
    rr = sa.get("rem_ratio")
    print(f"\n  deep_ratio / rem_ratio (escala 0-1, UI muestra %)")
    if dr is not None:
        ok(f"deep_ratio={dr} -> UI: {dr*100:.1f}%")
    if rr is not None:
        ok(f"rem_ratio={rr} -> UI: {rr*100:.1f}%")

    # micro_arousal_score -- direcci?n (alto = malo)
    micro = analysis.get("instability_markers", {}).get("micro_arousal_score")
    print(f"\n  micro_arousal_score (^ peor -- 100 = m?xima carga)")
    if micro is not None:
        dot_color = "ROJO" if (100 - micro) < 40 else ("AMBAR" if (100 - micro) < 70 else "VERDE")
        ok(f"valor={micro}/100 -> punto indicador: {dot_color} (inverted: {100 - micro})")


# ??? MAIN ????????????????????????????????????????????????????????????????????

def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None

    user_dir = get_user_dir()
    sleep_root = os.path.join(user_dir, "sleep")

    # Resolver fecha
    if date_arg:
        date = date_arg
    else:
        available = sorted([
            e for e in os.listdir(sleep_root)
            if os.path.isfile(os.path.join(sleep_root, e, "sleep_analysis.json"))
        ])
        if not available:
            print("No se encontraron datos de sue?o.")
            sys.exit(1)
        date = available[-1]

    base = os.path.join(sleep_root, date)
    analysis_path = os.path.join(base, "sleep_analysis.json")
    series_path   = os.path.join(base, "sleep_series.json")

    if not os.path.exists(analysis_path):
        print(f"No existe sleep_analysis.json para {date}")
        sys.exit(1)

    analysis = load_json(analysis_path)
    series   = load_json(series_path) if os.path.exists(series_path) else {}

    print(f"\n  Auditando noche: {date}")
    print(f"  Usuario: {user_dir.split(os.sep)[-1]}")

    verify_calculations(analysis, series)
    verify_passthrough(analysis, date)
    verify_display(analysis, series)

    header("RESUMEN")
    print("  Ejecuta este script despu?s de cada sincronizaci?n para")
    print("  verificar que los datos son correctos en las 3 capas.\n")


if __name__ == "__main__":
    main()
