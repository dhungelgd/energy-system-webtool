"""A scenario and a result by hand for the tests of the PDF report (no solver needed): a year of flows if wanted."""

import math
from datetime import datetime

from backend.results import (
    BusSummary,
    FlowTable,
    KeyFigure,
    ScenarioResult,
    SolverInfo,
    Table,
)
from backend.scenario_v2 import SeriesData, SeriesSource
from backend.series_input import has_series
from frontend_nicegui.draft import ScenarioDraft

START = datetime(2021, 1, 1)
ENERGY = ["Component", "Energy (kWh)", "Share (%)"]


def sample_scenario(hours=24, name="PV, battery and heat, test"):
    """A scenario of the full system with a time series for each component that has one."""

    draft = ScenarioDraft(name=name, steps=hours)
    draft.apply_template("Full system")
    for component in draft.components():
        if has_series(component):
            draft.set_series(component.id, SeriesData(
                unit="kW", source=SeriesSource(file="profiles.csv", column=component.id.upper()),
                values=[0.5 + 0.4 * math.sin(i / 24 * 2 * math.pi) for i in range(hours)]))

    return draft.scenario()


def _wave(i, shift=0.0, scale=1.0, base=0.0):
    return max(0.0, base + scale * math.sin((i % 24 - 6 + shift) / 12 * math.pi))


def sample_result(hours=24, with_flows=True, costs=True, capacities=True, built=True):
    """A result by hand: electricity (grid, PV, demand, heating rod, feed-in), heat and a gas carrier through which
    nothing flows. `hours` is the length of the period."""

    def table(rows):
        return Table(columns=ENERGY, rows=rows)

    def flows(columns):
        names = list(columns)
        if not with_flows:
            return None
        return FlowTable(start=START, step_hours=1.0, columns=names, values=[[col(i) for i in range(hours)] for col in columns.values()])

    electricity = BusSummary(
        energy_sums={}, flows=flows({
            "grid_import-->electricity": lambda i: 3.0 + _wave(i + 12, scale=2.0),
            "pv-->electricity": lambda i: _wave(i, scale=6.0),
            "electricity-->demand": lambda i: 4.0 + _wave(i, scale=1.5),
            "electricity-->heating_rod": lambda i: 1.0 + _wave(i, scale=1.0),
            "electricity-->grid_feedin": lambda i: _wave(i, scale=2.0),
        }),
        supply=table([["Grid import", 61200.0, 62.0], ["PV", 37500.0, 38.0]]),
        use=table([["Electricity demand", 52000.0, 52.5], ["Heating rod", 12000.0, 12.1], ["Grid feed-in", 34700.0, 35.4]]),
    )
    heat = BusSummary(
        energy_sums={}, flows=flows({
            "heating_rod-->heat": lambda i: 1.0 + _wave(i, scale=1.0),
            "heat-->heat_demand": lambda i: 1.0 + _wave(i, scale=1.0),
        }),
        supply=table([["Heating rod", 12000.0, 100.0]]), use=table([["Heat demand", 12000.0, 100.0]]),
    )
    gas = BusSummary(
        energy_sums={}, flows=flows({"gas_import-->gas": lambda i: 0.0, "gas-->chp": lambda i: 0.0}),
        supply=table([["Gas import", 0.0, 0.0]]), use=table([["CHP plant", 0.0, 0.0]]),
    )

    return ScenarioResult(
        objective=55353.0, horizon_hours=float(hours),
        solver=SolverInfo(status="ok", termination="optimal", seconds=1.5, name="highs"),
        key_figures=[
            KeyFigure(label="System cost (simulated period)", value=55353.0, unit="€",
                      help="Objective of the optimization: annualised investment and fixed O&M plus energy costs, "
                           "minus feed-in revenue. Negative means a net revenue."),
            KeyFigure(label="Grid import", value=61200.0, unit="kWh", help="Electricity bought from the grid."),
            KeyFigure(label="Electricity consumption", value=64000.0, unit="kWh", help="Demand plus heating rod."),
        ],
        cost_breakdown=Table(columns=["Item", "Category", "Cost (€)"], rows=[
            ["Heating rod", "Investment and fixed O&M", 19080.3], ["PV", "Investment and fixed O&M", 8400.0],
            ["Grid import", "Energy purchase", 36272.7], ["Grid feed-in", "Revenue", -8400.0]] if costs else []),
        capacities=Table(columns=["Component", "Mode", "Capacity", "Unit", "Annualised cost (€/a)"], rows=[
            ["PV", "fixed (input)" if not built else "optimized", 5.0 if not built else 41.7, "kW", 8400.0],
            ["Heating rod", "optimized", 2471.04 if built else 0.0, "kW (heat)", 19080.3 if built else 0.0],
            ["Battery", "optimized", 0.0, "kWh", 0.0]] if capacities else []),
        buses={"electricity": electricity, "heat": heat, "gas": gas},
    )