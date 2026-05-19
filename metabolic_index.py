from statistics import mean


# Umbrales mínimos para considerar que sí hay esfuerzo fisiológico real
MIN_POWER_W = 80
MIN_HR_BPM = 100

# Para evitar explosiones raras del índice
MAX_REASONABLE_MSI = 2.5


def compute_msi_row(row, ftp, hr_max):
    power = row.get("power_w")
    hr = row.get("heart_rate_bpm")
    cadence = row.get("cadence_rpm")

    # Validaciones básicas
    if power is None or hr is None or cadence is None:
        return None

    if ftp is None or ftp <= 0:
        return None

    if hr_max is None or hr_max <= 0:
        return None

    # Filtrar momentos donde no hay esfuerzo real
    if power < MIN_POWER_W:
        return None

    if hr < MIN_HR_BPM:
        return None

    power_factor = power / ftp
    hr_factor = hr / hr_max

    # Protección extra
    if power_factor <= 0:
        return None

    # Penalización por cadencia baja
    cadence_factor = 1.0
    if cadence < 70:
        cadence_factor = 1.08
    elif cadence > 95:
        cadence_factor = 0.97

    msi = (hr_factor * cadence_factor) / power_factor

    # Evitar outliers absurdos
    if msi <= 0:
        return None

    if msi > MAX_REASONABLE_MSI:
        msi = MAX_REASONABLE_MSI

    return round(msi, 4)


def add_msi_to_rows(rows, ftp, hr_max):
    for r in rows:
        r["msi"] = compute_msi_row(r, ftp, hr_max)
    return rows


def summarize_msi(rows):
    values = [r["msi"] for r in rows if r.get("msi") is not None]

    if not values:
        return {
            "avg_msi": None,
            "max_msi": None,
            "high_msi_pct": None,
            "valid_msi_samples": 0,
        }

    avg_msi = mean(values)
    max_msi = max(values)

    # Consideramos "alto" arriba de 1.1
    high_count = len([v for v in values if v > 1.1])
    high_pct = (high_count / len(values)) * 100

    return {
        "avg_msi": round(avg_msi, 3),
        "max_msi": round(max_msi, 3),
        "high_msi_pct": round(high_pct, 2),
        "valid_msi_samples": len(values),
    }