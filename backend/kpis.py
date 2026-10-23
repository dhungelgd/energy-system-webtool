"""Figures derived from the optimization results.

Key figures, cost breakdown and capacity table. Only pandas and numpy are used
(no Streamlit), so any frontend can reuse this module.

Energies are in kWh, powers in kW and costs in EUR.
"""

import numpy as np
import pandas as pd

from backend.oemof_components import calculate_epc
from backend.plotting import NODE_NAMES
from backend.postprocessing import get_investment_capacities
from backend.price_units import price_series_in_eur_per_kwh, DEFAULT_PRICE_UNIT

# unit of the installed capacity of each sized component
CAPACITY_UNITS = {
    "pv": "kW",
    "wind": "kW",
    "gas_boiler": "kW (heat)",
    "heat_pump": "kW (heat)",
    "heating_rod": "kW (heat)",
    "chp": "kW (electric)",
    "battery": "kWh",
    "heat_storage": "kWh",
}

CATEGORY_INVEST = "Investment and fixed O&M"
CATEGORY_ENERGY = "Energy purchase"
CATEGORY_REVENUE = "Revenue"


def readable(label):
    return NODE_NAMES.get(label, label)


def _split_flows(energy_sums, bus):
    """Energy per partner component: (supply to the bus, use from the bus)."""

    supply, use = {}, {}

    for flow, value in energy_sums.items():
        source, target = flow.split("-->")

        if target == bus:
            supply[source] = float(value)
        elif source == bus:
            use[target] = float(value)

    return supply, use


def _share_table(values):

    series = pd.Series(values, dtype=float)
    total = series.sum()

    return pd.DataFrame({
        "Component": [readable(name) for name in series.index],
        "Energy (kWh)": series.values,
        "Share (%)": series.values / total * 100 if total > 0 else 0.0,
    })


def supply_and_use(energy_sums, bus):
    """Two tables for one bus: who supplies the energy and where it goes."""

    supply, use = _split_flows(energy_sums, bus)

    return _share_table(supply), _share_table(use)


def compute_key_figures(buses, objective, horizon_hours):
    """List of headline numbers: {"label", "value", "unit", "help"}."""

    full_year = horizon_hours >= 8700

    figures = [{
        "label": "Annual system cost" if full_year else "System cost (simulated period)",
        "value": objective,
        "unit": "€",
        "help": (
            "Objective of the optimization: annualised investment and fixed O&M "
            "plus energy costs, minus feed-in revenue. Negative means a net revenue."
        ),
    }]

    electricity = buses.get("electricity")

    if electricity is not None:

        supply, use = _split_flows(electricity["energy_sums"], "electricity")

        generation = sum(supply.get(name, 0.0) for name in ("pv", "wind", "chp"))
        grid_import = supply.get("grid_import")
        feedin = use.get("grid_feedin")

        # consumption = everything that really uses electricity
        # (not the feed-in and not the charging of the battery)
        consumption = sum(
            value for name, value in use.items()
            if name not in ("grid_feedin", "battery")
        )

        if consumption > 0:
            figures.append({
                "label": "Electricity consumption", "value": consumption, "unit": "kWh",
                "help": "Electricity demand plus electricity used by heat pump and heating rod.",
            })

        if grid_import is not None:
            figures.append({
                "label": "Grid import", "value": grid_import, "unit": "kWh",
                "help": "Electricity bought from the grid.",
            })

            peak = _flow(buses, "electricity", "grid_import-->electricity")
            if peak is not None:
                figures.append({
                    "label": "Peak grid import", "value": float(peak.max()), "unit": "kW",
                    "help": "Highest power drawn from the grid in a single time step.",
                })

        if feedin is not None:
            figures.append({
                "label": "Grid feed-in", "value": feedin, "unit": "kWh",
                "help": "Electricity sold to the grid.",
            })

        if generation > 0:
            figures.append({
                "label": "Own generation", "value": generation, "unit": "kWh",
                "help": "Electricity from PV, wind and CHP.",
            })
            figures.append({
                "label": "Self-consumption", "unit": "%",
                "value": float(np.clip((generation - (feedin or 0.0)) / generation, 0, 1)) * 100,
                "help": "Share of the own generation that is not fed into the grid.",
            })

        if grid_import is not None and consumption > 0:
            figures.append({
                "label": "Self-sufficiency", "unit": "%",
                "value": float(np.clip(1 - grid_import / consumption, 0, 1)) * 100,
                "help": "Share of the electricity consumption that is not bought from the grid.",
            })

    heat = buses.get("heat")

    if heat is not None:

        _, heat_use = _split_flows(heat["energy_sums"], "heat")

        if heat_use.get("heat_demand"):
            figures.append({
                "label": "Heat demand", "value": heat_use["heat_demand"], "unit": "kWh",
                "help": "Heat that has to be supplied.",
            })

    return figures


def _flow(buses, bus, flow_name):
    """Power time series (kW) of one flow, or None if it is not in the results."""

    data = buses.get(bus)

    if data is None or flow_name not in data["flows"].columns:
        return None

    # oemof adds an empty row for the end of the last time step
    return data["flows"][flow_name].dropna().values


def compute_cost_breakdown(results, config, buses, objective, step_hours):
    """Where the system cost comes from: one row per cost or revenue item.

    Columns: Item, Category, Cost (€). Revenues are negative. The rows add up
    to the objective; a difference (if any) is shown as "Other".
    """

    techs = config["technologies"]
    rows = []

    # annualised capital cost + fixed O&M of the optimized capacities
    for label, invested in get_investment_capacities(results).items():

        cfg = techs.get(label)

        if not cfg or cfg.get("mode") != "invest":
            continue

        epc = calculate_epc(
            capex=cfg["capex"], opex=cfg["opex"],
            lifetime=cfg["lifetime"], interest_rate=cfg["interest_rate"],
        )
        rows.append((readable(label), CATEGORY_INVEST, epc * invested))

    # grid import (constant price or time series)
    power = _flow(buses, "electricity", "grid_import-->electricity")

    if power is not None:

        grid = techs.get("grid", {})

        if grid.get("price_mode") == "timeseries":
            price = np.array(price_series_in_eur_per_kwh(
                grid["price_series"], grid.get("price_unit", DEFAULT_PRICE_UNIT)
            )[:len(power)])
        else:
            price = grid.get("variable_costs") or 0.0

        rows.append((readable("grid_import"), CATEGORY_ENERGY,
                     float((power * price).sum() * step_hours)))

    # feed-in revenue
    power = _flow(buses, "electricity", "electricity-->grid_feedin")

    if power is not None:

        tariff = techs.get("grid_feedin", {}).get("feedin_tariff") or 0.0

        rows.append((readable("grid_feedin"), CATEGORY_REVENUE,
                     -float(power.sum() * step_hours * tariff)))

    # gas purchase
    power = _flow(buses, "gas", "gas_import-->gas")

    if power is not None:

        price = techs.get("gas_import", {}).get("variable_costs") or 0.0

        rows.append((readable("gas_import"), CATEGORY_ENERGY,
                     float(power.sum() * step_hours * price)))

    table = pd.DataFrame(rows, columns=["Item", "Category", "Cost (€)"])

    # anything the items above do not explain
    difference = objective - table["Cost (€)"].sum()

    if abs(difference) > 0.01 + 1e-6 * abs(objective):
        table.loc[len(table)] = ["Other", "Other", difference]

    return table


def build_capacity_table(results, config):
    """Installed capacity of every sized component (input or optimized)."""

    invested = get_investment_capacities(results)
    rows = []

    for key, cfg in config["technologies"].items():

        if key not in CAPACITY_UNITS:
            continue

        if cfg.get("mode") == "invest":

            capacity = invested.get(key)
            epc = calculate_epc(
                capex=cfg["capex"], opex=cfg["opex"],
                lifetime=cfg["lifetime"], interest_rate=cfg["interest_rate"],
            )
            rows.append((readable(key), "optimized", capacity, CAPACITY_UNITS[key],
                         None if capacity is None else epc * capacity))

        else:
            # fixed capacity: no capital cost is part of the optimization
            rows.append((readable(key), "fixed (input)", cfg.get("capacity"),
                         CAPACITY_UNITS[key], None))

    table = pd.DataFrame(
        rows,
        columns=["Component", "Mode", "Capacity", "Unit", "Annualised cost (€/a)"],
    )

    # empty cells (fixed mode) must not turn the number columns into text
    for column in ("Capacity", "Annualised cost (€/a)"):
        table[column] = pd.to_numeric(table[column], errors="coerce")

    return table