import json
import os
from datetime import datetime, timedelta

from garmin_auth import login_garmin


def safe_call(name, fn):
    try:
        data = fn()
        return {
            "ok": True,
            "data": data,
            "error": None
        }
    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error": str(e)
        }


def preview_data(obj, max_items=10):
    if isinstance(obj, list):
        return obj[:max_items]

    if isinstance(obj, dict):
        preview = {}
        for k, v in list(obj.items())[:30]:
            if isinstance(v, list):
                preview[k] = v[:max_items]
            else:
                preview[k] = v
        return preview

    return obj


def summarize_structure(obj, max_depth=4, _depth=0):
    if _depth >= max_depth:
        return type(obj).__name__

    if isinstance(obj, dict):
        out = {
            "_type": "dict",
            "_keys": list(obj.keys())[:80],
            "_children": {}
        }
        for k, v in list(obj.items())[:40]:
            out["_children"][k] = summarize_structure(v, max_depth=max_depth, _depth=_depth + 1)
        return out

    if isinstance(obj, list):
        sample = obj[:5]
        return {
            "_type": "list",
            "_len": len(obj),
            "_sample": [summarize_structure(x, max_depth=max_depth, _depth=_depth + 1) for x in sample]
        }

    return type(obj).__name__


def extract_pair_series(items):
    out = []
    if not isinstance(items, list):
        return out

    for row in items:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            ts = row[0]
            value = row[1]
            out.append({"raw_ts": ts, "raw_value": value})
    return out


def extract_dict_series(items):
    out = []
    if not isinstance(items, list):
        return out

    for row in items:
        if isinstance(row, dict):
            out.append(row)
    return out


def find_candidate_paths(obj, path="root", results=None):
    if results is None:
        results = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}"

            if isinstance(v, list) and v:
                first = v[0]

                if isinstance(first, (list, tuple)) and len(first) >= 2:
                    results.append({
                        "path": child_path,
                        "shape": "pair_list",
                        "len": len(v),
                        "preview": v[:5]
                    })

                elif isinstance(first, dict):
                    results.append({
                        "path": child_path,
                        "shape": "dict_list",
                        "len": len(v),
                        "preview": v[:3]
                    })

            elif isinstance(v, dict):
                find_candidate_paths(v, child_path, results)

    elif isinstance(obj, list):
        for i, item in enumerate(obj[:10]):
            find_candidate_paths(item, f"{path}[{i}]", results)

    return results


def build_body_battery_debug(date_str, bb_result, stats_result):
    stats = stats_result.get("data") if stats_result.get("ok") else {}
    bb = bb_result.get("data") if bb_result.get("ok") else None

    debug = {
        "calendar_date": date_str,
        "body_battery_call_ok": bb_result.get("ok", False),
        "body_battery_error": bb_result.get("error"),
        "stats_call_ok": stats_result.get("ok", False),
        "stats_summary": {
            "bodyBatteryAtWakeTime": stats.get("bodyBatteryAtWakeTime"),
            "bodyBatteryMostRecentValue": stats.get("bodyBatteryMostRecentValue"),
            "bodyBatteryHighestValue": stats.get("bodyBatteryHighestValue"),
            "bodyBatteryLowestValue": stats.get("bodyBatteryLowestValue"),
            "bodyBatteryChargedValue": stats.get("bodyBatteryChargedValue"),
            "bodyBatteryDrainedValue": stats.get("bodyBatteryDrainedValue"),
            "bodyBatteryDuringSleep": stats.get("bodyBatteryDuringSleep"),
        } if isinstance(stats, dict) else {},
        "body_battery_type": type(bb).__name__,
        "body_battery_preview": preview_data(bb),
        "body_battery_structure": summarize_structure(bb),
        "candidate_paths": find_candidate_paths(bb, path="body_battery"),
    }

    # Intenta sacar ejemplos de series candidatas
    extracted_examples = []

    if isinstance(bb, list):
        pair_series = extract_pair_series(bb)
        dict_series = extract_dict_series(bb)

        if pair_series:
            extracted_examples.append({
                "source": "top_level_list_as_pairs",
                "count": len(pair_series),
                "preview": pair_series[:10]
            })

        if dict_series:
            extracted_examples.append({
                "source": "top_level_list_as_dicts",
                "count": len(dict_series),
                "preview": dict_series[:5]
            })

    elif isinstance(bb, dict):
        for key, value in bb.items():
            if isinstance(value, list):
                pair_series = extract_pair_series(value)
                dict_series = extract_dict_series(value)

                if pair_series:
                    extracted_examples.append({
                        "source": f"dict_key:{key}:pair_list",
                        "count": len(pair_series),
                        "preview": pair_series[:10]
                    })

                if dict_series:
                    extracted_examples.append({
                        "source": f"dict_key:{key}:dict_list",
                        "count": len(dict_series),
                        "preview": dict_series[:5]
                    })

    debug["extracted_examples"] = extracted_examples
    return debug


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    print("===================================")
    print("BODY BATTERY EXPLORER")
    print("===================================")

    email = input("Correo Garmin: ").strip()
    password = input("Contraseña Garmin: ").strip()
    date_str = input("Fecha (YYYY-MM-DD): ").strip()

    client = login_garmin(email, password)
    if not client:
        print("No se pudo iniciar sesión.")
        return

    out_dir = os.path.join("data", f"body_battery_explorer_{date_str}")
    os.makedirs(out_dir, exist_ok=True)

    # principal
    bb_result = safe_call("get_body_battery", lambda: client.get_body_battery(date_str, date_str))
    stats_result = safe_call("get_stats", lambda: client.get_stats(date_str))

    # opcionales útiles para comparar
    bb_events_result = (
        safe_call("get_body_battery_events", lambda: client.get_body_battery_events(date_str))
        if hasattr(client, "get_body_battery_events") else
        {"ok": False, "data": None, "error": "Method not available"}
    )

    all_day_events_result = (
        safe_call("get_all_day_events", lambda: client.get_all_day_events(date_str))
        if hasattr(client, "get_all_day_events") else
        {"ok": False, "data": None, "error": "Method not available"}
    )

    raw_dump = {
        "meta": {
            "date": date_str,
            "output_dir": out_dir
        },
        "calls": {
            "get_body_battery": bb_result,
            "get_stats": stats_result,
            "get_body_battery_events": bb_events_result,
            "get_all_day_events": all_day_events_result,
        }
    }

    debug_summary = build_body_battery_debug(
        date_str=date_str,
        bb_result=bb_result,
        stats_result=stats_result
    )

    save_json(os.path.join(out_dir, "body_battery_raw_dump.json"), raw_dump)
    save_json(os.path.join(out_dir, "body_battery_debug_summary.json"), debug_summary)

    print("\n===================================")
    print("RESULTADO")
    print("===================================")
    print(f"Carpeta: {out_dir}")
    print(f"get_body_battery ok: {bb_result['ok']}")
    print(f"Tipo devuelto: {debug_summary['body_battery_type']}")
    print(f"Candidatos encontrados: {len(debug_summary['candidate_paths'])}")
    print(f"Ejemplos extraídos: {len(debug_summary['extracted_examples'])}")

    if debug_summary["stats_summary"]:
        print("\nStats summary:")
        for k, v in debug_summary["stats_summary"].items():
            print(f"- {k}: {v}")

    if debug_summary["candidate_paths"]:
        print("\nCandidate paths:")
        for item in debug_summary["candidate_paths"][:10]:
            print(f"- {item['path']} | {item['shape']} | len={item['len']}")

    if debug_summary["extracted_examples"]:
        print("\nExtracted examples:")
        for item in debug_summary["extracted_examples"][:5]:
            print(f"- {item['source']} | count={item['count']}")

    print("\nArchivos generados:")
    print("- body_battery_raw_dump.json")
    print("- body_battery_debug_summary.json")


if __name__ == "__main__":
    main()