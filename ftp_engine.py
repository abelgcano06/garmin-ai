"""
ftp_engine.py
Calcula FTP estimado a partir de power_profile de actividades.
- Con potenciómetro: 95% del mejor 20min ponderado estadísticamente
- Sin potenciómetro: estimación VAM-based cuando hay datos de ascensos
Guarda resultado en performance_intelligence/ftp_profile.json
"""

import json
import os
import statistics
from datetime import datetime

# ── helpers ────────────────────────────────────────────────────────────────

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip().strip("\x00")
            if not content:
                return None
            return json.loads(content)
    except Exception:
        return None

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── main ──────────────────────────────────────────────────────────────────

def run_ftp_engine(user_dir: str):
    idx_path = os.path.join(user_dir, "activity_index.json")
    idx_raw = load_json(idx_path)
    if not idx_raw:
        print("[ftp] No activity index found")
        return None

    activities = idx_raw.get("activities", [])

    power_records = []    # activities with real power data
    vam_records   = []    # activities with climbs (no power)

    for a in activities:
        af = a.get("analysis_file", "").replace("\\", "/")
        full = af if af.startswith("c:") else f"c:/garmin-ai/{af}"
        an = load_json(full)
        if not an:
            continue

        date = a.get("date", "")[:10]
        gs = an.get("garmin_summary", {}) or {}
        pp = an.get("power_profile", {}) or {}
        climbs = an.get("climbs", []) or []

        avg_power = gs.get("avg_power")
        garmin_np = gs.get("garmin_np")
        p20 = pp.get("20min")
        p5  = pp.get("5min")
        p60 = pp.get("60min")

        # ── power-based record ─────────────────────────────────────────────
        if p20 and isinstance(p20, dict) and p20.get("avg_power"):
            power_20 = float(p20["avg_power"])
            hr_20    = p20.get("avg_hr")
            power_5  = float(p5["avg_power"]) if p5 and p5.get("avg_power") else None
            power_60 = float(p60["avg_power"]) if p60 and p60.get("avg_power") else None

            # FTP estimate for this session
            ftp_est = round(power_20 * 0.95, 1)

            # Confidence based on duration of ride
            elapsed = gs.get("elapsed_minutes", 0) or 0
            if elapsed >= 60:
                confidence = "high"
            elif elapsed >= 40:
                confidence = "medium"
            else:
                confidence = "low"

            power_records.append({
                "date": date,
                "ftp_estimate": ftp_est,
                "power_20min": power_20,
                "power_5min": power_5,
                "power_60min": power_60,
                "avg_power": avg_power,
                "garmin_np": garmin_np,
                "hr_at_20min": hr_20,
                "confidence": confidence,
            })

        # ── VAM-based record (no power) ────────────────────────────────────
        elif climbs:
            long_climbs = [c for c in climbs if c.get("duration_min", 0) >= 3]
            if long_climbs:
                # Best VAM across climbs of this activity
                best_vam = max(c["vam"] for c in long_climbs if c.get("vam"))
                # Conservative FTP proxy: VAM / 9.5 * 75 (rough empirical for MTB)
                # This is an estimation, not a real FTP
                vam_records.append({
                    "date": date,
                    "best_vam": best_vam,
                    "ftp_proxy": round(best_vam / 9.5, 1),
                    "climb_count": len(long_climbs),
                    "method": "vam_proxy",
                })

    # ── Statistical FTP from power records ───────────────────────────────
    result = {
        "generated_at": datetime.now().isoformat(),
        "has_power_meter": len(power_records) > 0,
        "power_activity_count": len(power_records),
        "power_records": sorted(power_records, key=lambda x: x["date"]),
        "vam_records": sorted(vam_records, key=lambda x: x["date"]),
        "ftp_current": None,
        "ftp_method": None,
        "ftp_confidence": None,
        "ftp_trend": [],
        "power_curve_best": {},
    }

    if power_records:
        estimates = [r["ftp_estimate"] for r in power_records]
        p20_values = [r["power_20min"] for r in power_records]

        # Remove outliers: values > 1.5 IQR above Q3
        sorted_est = sorted(estimates)
        n = len(sorted_est)
        if n >= 4:
            q1 = sorted_est[n // 4]
            q3 = sorted_est[(3 * n) // 4]
            iqr = q3 - q1
            upper_fence = q3 + 1.5 * iqr
            filtered = [e for e in estimates if e <= upper_fence]
            if not filtered:
                filtered = estimates
        else:
            filtered = estimates

        # Use the 90th percentile of filtered estimates (not max, to be robust)
        filtered_sorted = sorted(filtered)
        p90_idx = max(0, int(len(filtered_sorted) * 0.9) - 1)
        ftp_best = filtered_sorted[p90_idx]

        # High-confidence if any record has high confidence
        high_conf = [r for r in power_records if r["confidence"] == "high"]
        med_conf  = [r for r in power_records if r["confidence"] == "medium"]
        n_records = len(power_records)

        if n_records >= 3 and high_conf:
            ftp_confidence = "alta"
            ftp_method = f"percentil 90 de {n_records} sesiones con potenciómetro"
        elif n_records >= 2:
            ftp_confidence = "media"
            ftp_method = f"mejor estimación de {n_records} sesiones con potenciómetro"
        else:
            ftp_confidence = "baja"
            ftp_method = "estimación de 1 sesión — necesitas más rides para confirmar"

        result["ftp_current"] = round(ftp_best, 1)
        result["ftp_method"] = ftp_method
        result["ftp_confidence"] = ftp_confidence

        # Trend: FTP estimate per date
        result["ftp_trend"] = [
            {"date": r["date"], "ftp_estimate": r["ftp_estimate"], "confidence": r["confidence"]}
            for r in sorted(power_records, key=lambda x: x["date"])
        ]

        # Best power curve across all power sessions
        durations = ["1s","5s","10s","30s","1min","3min","5min","8min","10min","20min","30min","60min"]
        best_curve = {}
        for r in power_records:
            af = None
            # Re-read from disk to get full power profile
            for a in activities:
                if a.get("date", "")[:10] == r["date"]:
                    af_raw = a.get("analysis_file","").replace("\\", "/")
                    af = af_raw if af_raw.startswith("c:") else f"c:/garmin-ai/{af_raw}"
                    break
            if af:
                an = load_json(af)
                pp = (an or {}).get("power_profile", {})
                for dur in durations:
                    val = pp.get(dur)
                    if val and isinstance(val, dict):
                        pw = val.get("avg_power")
                        if pw and (dur not in best_curve or pw > best_curve[dur]["power"]):
                            best_curve[dur] = {
                                "power": round(float(pw), 1),
                                "date": r["date"],
                                "hr": val.get("avg_hr"),
                            }
        result["power_curve_best"] = best_curve

        # W/kg (if we had weight — placeholder)
        result["note"] = "Agrega tu peso en el perfil para calcular W/kg"

    # VAM fallback removed: without a power meter FTP cannot be reliably estimated.
    # vam_records are still collected above for potential future use.

    # Save ftp_profile.json
    out_path = os.path.join(user_dir, "performance_intelligence", "ftp_profile.json")
    save_json(out_path, result)

    if result["ftp_current"]:
        print(f"[ftp] FTP estimado: {result['ftp_current']} W | confianza: {result['ftp_confidence']} | método: {result['ftp_method']}")
    else:
        print("[ftp] Sin datos suficientes para estimar FTP")

    # ── Update profile.json with ftp_apex + detect achievements ──────────────
    profile_path = os.path.join(user_dir, "profile.json")
    profile = load_json(profile_path) or {}

    prev_ftp_apex = float(profile.get("ftp_apex") or 0)
    new_ftp = result.get("ftp_current")
    achievements = []

    if new_ftp:
        ftp_improved = new_ftp > prev_ftp_apex

        if ftp_improved and prev_ftp_apex > 0:
            delta = round(new_ftp - prev_ftp_apex, 1)
            pct = round(delta / prev_ftp_apex * 100, 1)
            achievements.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "type": "ftp_pr",
                "title": "¡Nuevo FTP personal!",
                "message": f"Tu FTP subió de {prev_ftp_apex}W a {round(new_ftp, 1)}W (+{delta}W, +{pct}%)",
                "value": round(new_ftp, 1),
                "previous": prev_ftp_apex,
            })
            print(f"[ftp] ** FTP RECORD: {prev_ftp_apex}W -> {round(new_ftp, 1)}W (+{delta}W)")
        elif not prev_ftp_apex:
            achievements.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "type": "ftp_first",
                "title": "FTP establecido por primera vez",
                "message": f"Tu FTP Apex: {round(new_ftp, 1)}W",
                "value": round(new_ftp, 1),
                "previous": None,
            })

        # Check power curve PRs (5min, 20min)
        best_curve = result.get("power_curve_best", {})
        prev_curve = profile.get("power_curve_best", {})
        for dur in ["5min", "20min", "60min"]:
            entry = best_curve.get(dur) or {}
            new_val = entry.get("power")
            prev_entry = prev_curve.get(dur) or {}
            prev_val = prev_entry.get("power")
            if new_val and (not prev_val or new_val > prev_val):
                delta_p = round(new_val - (prev_val or 0), 1)
                label = f"Récord de potencia {dur}"
                msg = (f"{dur}: {prev_val}W → {new_val}W (+{delta_p}W)"
                       if prev_val else f"Primer récord {dur}: {new_val}W")
                achievements.append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": f"power_pr_{dur.replace('min','m')}",
                    "title": label,
                    "message": msg,
                    "value": new_val,
                    "previous": prev_val,
                })
                print(f"[ftp] ** RECORD {dur}: {prev_val or '-'}W -> {new_val}W")

        # Update profile.json
        profile["ftp_apex"] = round(new_ftp, 1)
        profile["power_curve_best"] = best_curve
        save_json(profile_path, profile)

        # Persist achievements
        if achievements:
            ach_path = os.path.join(user_dir, "performance_intelligence", "achievements.json")
            existing = load_json(ach_path) or {"achievements": []}
            existing["achievements"] = achievements + existing.get("achievements", [])
            existing["achievements"] = existing["achievements"][:100]
            save_json(ach_path, existing)

    result["achievements"] = achievements
    result["ftp_previous"] = prev_ftp_apex
    result["ftp_improved"] = new_ftp is not None and new_ftp > prev_ftp_apex

    return result


if __name__ == "__main__":
    import sys
    email = sys.argv[1] if len(sys.argv) > 1 else "abelgcanofuentes@hotmail.com"
    slug = email.replace("@", "_at_").replace(".", "_")
    user_dir = f"c:/garmin-ai/data/users/{slug}"
    run_ftp_engine(user_dir)
