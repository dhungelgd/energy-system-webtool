"""One-time merge of the texts of step 6 into the two catalogs (adds and changes keys, keeps them sorted)."""
import json
from pathlib import Path

TEXTS = {
    # the help text of the size choice says what a fixed size means for the costs
    "field.capacity.mode.help": (
        "Fixed: the size you enter is used. With a fixed size the investment settings are not needed, and the cost "
        "of the plant is not part of the system cost. Invest: the optimizer chooses the size that gives the lowest "
        "total cost, within the maximum you set.",
        "Fest: Die Größe, die Sie eingeben, wird verwendet. Bei fester Größe werden die Investitionseinstellungen "
        "nicht gebraucht, und die Kosten der Anlage sind nicht Teil der Systemkosten. Investition: Der Optimierer "
        "wählt die Größe mit den niedrigsten Gesamtkosten, innerhalb des Maximums, das Sie festlegen."),
    # the page says which forms there are
    "builder.wip": (
        "Work in progress: settings forms exist for the demands, the grid, the feed-in, the gas import, the PV "
        "system and the wind turbine so far; the other components and the upload of time series follow. Until then "
        "you can see below what is still missing, and open a complete scenario file further down.",
        "In Arbeit: Einstellungsformulare gibt es bisher für die Bedarfe, das Netz, die Einspeisung, den Gasbezug, "
        "die PV-Anlage und die Windkraftanlage; die anderen Komponenten und das Hochladen von Zeitreihen folgen. "
        "Bis dahin sehen Sie unten, was noch fehlt, und können weiter unten eine vollständige Szenariodatei öffnen."),
    # words of their own for a component (the part after @ is the component)
    "field.costs.variable_costs.label@grid": ("Electricity price", "Strompreis"),
    "field.costs.variable_costs.help@grid": ("What one kWh from the grid costs.", "Was eine kWh aus dem Netz kostet."),
    "field.costs.revenue.label@grid_feedin": ("Feed-in tariff", "Einspeisevergütung"),
    "field.costs.revenue.help@grid_feedin": (
        "What you get for every kWh that you feed into the grid.",
        "Was Sie für jede kWh bekommen, die Sie ins Netz einspeisen."),
    "field.costs.variable_costs.label@gas_import": ("Gas price", "Gaspreis"),
    "field.costs.variable_costs.help@gas_import": ("What one kWh of gas costs.", "Was eine kWh Gas kostet."),
    "field.demand.annual_demand.label@demand": ("Annual electricity demand", "Jahresstrombedarf"),
    "field.demand.annual_demand.help@demand": (
        "The electricity per year. Every hour gets its share of it.",
        "Der Strom pro Jahr. Jede Stunde bekommt ihren Anteil daran."),
    "field.demand.annual_demand.label@heat_demand": ("Annual heat demand", "Jahreswärmebedarf"),
    "field.demand.annual_demand.help@heat_demand": (
        "The heat per year. Every hour gets its share of it.",
        "Die Wärme pro Jahr. Jede Stunde bekommt ihren Anteil daran."),
    "field.capacity.capacity.help@wind": ("The rated power of the wind turbine.", "Die Nennleistung der Windkraftanlage."),
}

folder = Path(__file__).resolve().parent / "backend" / "i18n"
for index, language in enumerate(("en", "de")):
    path = folder / f"{language}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, texts in TEXTS.items():
        data[key] = texts[index]
    path.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(language, len(data), "texts")