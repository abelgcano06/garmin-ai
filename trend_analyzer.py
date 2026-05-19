import json
import os

from app_context import get_activity_history_path, get_current_user_id


def load_history(user_id=None):
    user_id = user_id or get_current_user_id()
    history_file = get_activity_history_path(user_id)

    if not os.path.exists(history_file):
        return {"activities": []}

    with open(history_file, "r", encoding="utf-8") as f:
        return json.load(f)


def avg(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def trend_direction(old, new, higher_is_better=True):
    if old is None or new is None:
        return None, None

    delta = new - old
    pct = (delta / old * 100) if old != 0 else None

    if higher_is_better:
        direction = "mejorando" if delta > 0 else "empeorando" if delta < 0 else "estable"
    else:
        direction = "mejorando" if delta < 0 else "empeorando" if delta > 0 else "estable"

    return direction, pct


def analyze_trends(history):
    activities = history.get("activities", [])

    if len(activities) < 4:
        return {
            "error": "Se necesitan al menos 4 actividades en el historial del usuario para detectar tendencias."
        }

    recent = activities[-4:]
    previous = activities[-8:-4] if len(activities) >= 8 else activities[:-4]

    if not previous:
        return {
            "error": "Todavía no hay suficientes actividades anteriores para comparar tendencias."
        }

    metrics = {
        "top_climb_power": {"higher_is_better": True, "label": "potencia en tu mejor subida"},
        "climb_repeatability_pct": {"higher_is_better": False, "label": "repeatability en subidas"},
        "power_drop_pct": {"higher_is_better": False, "label": "caída de potencia"},
        "efficiency_drop_pct": {"higher_is_better": False, "label": "eficiencia potencia/FC"},
        "estimated_np": {"higher_is_better": True, "label": "Normalized Power estimada"},
        "energy_kj": {"higher_is_better": False, "label": "costo energético"},
        "avg_msi": {"higher_is_better": False, "label": "MSI promedio"},
        "high_msi_pct": {"higher_is_better": False, "label": "% de tiempo en MSI alto"},
    }

    results = []

    for key, meta in metrics.items():
        old_avg = avg([a.get(key) for a in previous])
        new_avg = avg([a.get(key) for a in recent])

        direction, pct = trend_direction(old_avg, new_avg, meta["higher_is_better"])

        results.append({
            "metric": key,
            "label": meta["label"],
            "previous_avg": round(old_avg, 2) if old_avg is not None else None,
            "recent_avg": round(new_avg, 2) if new_avg is not None else None,
            "direction": direction,
            "pct_change": round(pct, 2) if pct is not None else None,
        })

    return {
        "recent_count": len(recent),
        "previous_count": len(previous),
        "trends": results,
    }


def print_trends(report):
    if report.get("error"):
        print(report["error"])
        return

    print("\n==========================")
    print("TREND ANALYZER")
    print("==========================")
    print(f"Sesiones recientes analizadas: {report['recent_count']}")
    print(f"Sesiones previas analizadas: {report['previous_count']}")

    for t in report["trends"]:
        print(f"\nMétrica: {t['label']}")
        print(f"Promedio previo: {t['previous_avg']}")
        print(f"Promedio reciente: {t['recent_avg']}")
        print(f"Tendencia: {t['direction']}")
        print(f"Cambio %: {t['pct_change']}")


def main():
    user_id = input("user_id (Enter para usar actual): ").strip() or None
    history = load_history(user_id=user_id)
    report = analyze_trends(history)
    print_trends(report)


if __name__ == "__main__":
    main()