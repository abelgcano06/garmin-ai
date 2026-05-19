import json
import os

DATA_FOLDER = "data"


def load_analysis(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def add_insight(insights, title, what_happened, what_it_means, what_to_do, priority="medium"):
    insights.append({
        "title": title,
        "what_happened": what_happened,
        "what_it_means": what_it_means,
        "what_to_do": what_to_do,
        "priority": priority,
    })


def build_repeatability_insight(analysis, insights):
    fatigue = analysis.get("fatigue", {})
    repeatability = fatigue.get("climb_repeatability_pct")

    if repeatability is None:
        return

    if repeatability <= -6:
        add_insight(
            insights,
            title="Te faltó repeatability en subidas",
            what_happened=f"Tu rendimiento en subidas cayó {abs(repeatability):.2f}% entre el inicio y el final de la sesión.",
            what_it_means="Tus primeras subidas fueron fuertes, pero te costó sostener ese nivel cuando las subidas se repitieron. Esto suele indicar fatiga acumulada, pacing agresivo al inicio o falta de durabilidad específica en subida.",
            what_to_do="Trabaja repeticiones de subida de 3 a 5 minutos con recuperación incompleta, buscando que la última repetición no caiga más de 3 a 5% respecto a la primera.",
            priority="high",
        )


def build_efficiency_insight(analysis, insights):
    fatigue = analysis.get("fatigue", {})
    eff_drop = fatigue.get("efficiency_drop_pct")

    if eff_drop is None:
        return

    if eff_drop <= -6:
        add_insight(
            insights,
            title="Tu eficiencia potencia/FC se deterioró",
            what_happened=f"La relación entre potencia y frecuencia cardiaca cayó {abs(eff_drop):.2f}% a lo largo de la sesión.",
            what_it_means="Con el paso de los minutos, tu cuerpo necesitó más costo cardiovascular para sostener una potencia similar o menor. Esto suele reflejar deriva cardiaca, fatiga periférica o un gasto energético alto en la primera parte de la actividad.",
            what_to_do="Mejora tu base aeróbica y tu pacing. Incluye sesiones Z2 largas con objetivo de desacople bajo, además de trabajo sweet spot y over-unders para sostener mejor el esfuerzo cuando ya vienes fatigado.",
            priority="high",
        )


def build_profile_insight(analysis, insights):
    profile = analysis.get("athlete_profile", {})
    primary = profile.get("primary_type")
    secondary = profile.get("secondary_type")
    strengths = profile.get("strengths", [])
    limiters = profile.get("limiters", [])

    if not primary:
        return

    strengths_text = ", ".join(strengths[:3]) if strengths else "sin fortalezas claras detectadas"
    limiters_text = ", ".join(limiters[:3]) if limiters else "sin limitantes claras detectadas"

    add_insight(
        insights,
        title="Tu perfil de ciclista está bastante definido",
        what_happened=f"El motor te clasificó como {primary} con componente secundaria {secondary}. Tus fortalezas principales apuntan a {strengths_text}.",
        what_it_means="Tu patrón de potencia y de subida indica que tienes un estilo más orientado a esfuerzos intensos y cambios de ritmo que a potencia sostenida tipo diesel. Eso ayuda a entender por qué algunas sesiones se te dan muy bien y otras se te hacen más pesadas.",
        what_to_do=f"Entrena manteniendo tu identidad de rider, pero trabajando tus limitantes principales: {limiters_text}. La idea no es perder tu punch, sino hacerlo más durable.",
        priority="high",
    )


def build_climb_insight(analysis, insights):
    climbs = analysis.get("climbs", [])
    if not climbs:
        return

    top_climb = sorted(climbs, key=lambda x: x.get("climb_score", 0), reverse=True)[0]
    climb_type = top_climb.get("climb_type")
    duration = top_climb.get("duration_min")
    gain = top_climb.get("elevation_gain_m")
    power = top_climb.get("avg_power")
    grade = top_climb.get("avg_grade_pct")

    add_insight(
        insights,
        title="Tu mejor rendimiento apareció en una subida específica",
        what_happened=f"Tu subida más exigente fue una {climb_type} de {duration} min, {gain} m de ganancia, {grade}% de pendiente media y {power} W promedio.",
        what_it_means="Esto ayuda a aterrizar en qué tipo de subida expresas mejor tu rendimiento real. No solo importa tu potencia máxima, sino dónde la puedes aplicar mejor en el terreno que realmente ruedas.",
        what_to_do="Usa esta subida como referencia de entrenamiento. Compárate contra esfuerzos futuros en subidas de duración y pendiente parecidas para medir progreso real y no solo números aislados.",
        priority="medium",
    )


def build_pacing_insight(analysis, insights):
    derived = analysis.get("derived_summary", {})
    vi = derived.get("vi")
    ride_class = derived.get("ride_classification")

    if vi is None:
        return

    if vi >= 1.2:
        add_insight(
            insights,
            title="Tu pacing fue bastante variable",
            what_happened=f"El ride tuvo un VI de {vi}, lo que indica una sesión con muchos cambios de ritmo. El sistema también la clasificó como: {ride_class}.",
            what_it_means="Esto es típico de MTB o trail técnico, pero también puede volverse costoso si haces demasiados picos al inicio y luego pagas esa agresividad más adelante en la sesión.",
            what_to_do="Trabaja pacing en subida y en bloques de 8 a 15 minutos. La meta es evitar picos demasiado altos en el primer minuto y sostener mejor la potencia útil durante todo el esfuerzo.",
            priority="medium",
        )


def build_power_durability_insight(analysis, insights):
    fatigue = analysis.get("fatigue", {})
    power_drop = fatigue.get("power_drop_pct")

    if power_drop is None:
        return

    if power_drop <= -6:
        add_insight(
            insights,
            title="La potencia útil cayó con el paso de la sesión",
            what_happened=f"Tu potencia útil cayó {abs(power_drop):.2f}% entre la primera y la segunda mitad de la actividad.",
            what_it_means="Eso sugiere que no fue solo una sesión dura, sino una sesión donde el rendimiento fue perdiendo calidad conforme acumulaste carga. Esto afecta especialmente en actividades con muchas subidas o esfuerzos encadenados.",
            what_to_do="Incluye sesiones de calidad al final de rodadas largas: por ejemplo, 90 a 120 min suaves y luego 2 a 3 bloques de 8 a 10 min fuertes. Eso construye durabilidad real bajo fatiga.",
            priority="high",
        )


def build_cadence_climb_insight(analysis, insights):
    climbs = analysis.get("climbs", [])
    if not climbs:
        return

    avg_cad = [c.get("avg_cadence") for c in climbs if c.get("avg_cadence") is not None]
    if not avg_cad:
        return

    cadence_mean = sum(avg_cad) / len(avg_cad)

    if cadence_mean < 68:
        add_insight(
            insights,
            title="Tu cadencia en subidas fue baja",
            what_happened=f"La cadencia media en las subidas detectadas estuvo alrededor de {round(cadence_mean, 1)} rpm.",
            what_it_means="Eso puede indicar que estás resolviendo las subidas más por torque que por fluidez. En MTB puede funcionar, pero también aumenta el costo muscular y puede acelerar la fatiga en sesiones largas o con muchas subidas.",
            what_to_do="Prueba bloques de subida buscando 70 a 85 rpm en pendientes medias. No se trata de pedalear rápido por pedalear rápido, sino de encontrar una cadencia que sostenga potencia con menos castigo muscular.",
            priority="medium",
        )


def build_top_insights(analysis):
    insights = []

    build_repeatability_insight(analysis, insights)
    build_efficiency_insight(analysis, insights)
    build_profile_insight(analysis, insights)
    build_climb_insight(analysis, insights)
    build_pacing_insight(analysis, insights)
    build_power_durability_insight(analysis, insights)
    build_cadence_climb_insight(analysis, insights)

    # Orden por prioridad
    priority_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: priority_order.get(x["priority"], 99))

    return insights[:5]


def save_insights_json(analysis_path, insights):
    base_name = os.path.basename(analysis_path)
    new_name = base_name.replace("activity_analysis_", "activity_insights_")
    output_path = os.path.join(DATA_FOLDER, new_name)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"top_insights": insights}, f, indent=2, ensure_ascii=False)

    return output_path


def main():
    analysis_path = input("Ruta del archivo activity_analysis.json: ").strip()

    if not os.path.exists(analysis_path):
        print("No se encontró el archivo.")
        return

    analysis = load_analysis(analysis_path)
    insights = build_top_insights(analysis)
    output_path = save_insights_json(analysis_path, insights)

    print("\n==========================")
    print("TOP INSIGHTS DE LA ACTIVIDAD")
    print("==========================")

    if not insights:
        print("No se generaron insights.")
        return

    for i, ins in enumerate(insights, start=1):
        print(f"\nInsight #{i} [{ins['priority']}]")
        print(f"Título: {ins['title']}")
        print(f"Qué pasó: {ins['what_happened']}")
        print(f"Qué significa: {ins['what_it_means']}")
        print(f"Qué hacer: {ins['what_to_do']}")

    print(f"\nArchivo guardado en: {output_path}")


if __name__ == "__main__":
    main()