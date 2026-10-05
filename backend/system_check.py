from dataclasses import dataclass

from backend.price_units import PRICE_UNIT_FACTORS, price_series_in_eur_per_kwh


@dataclass
class Finding:
    """One result of the system check."""

    level: str            # "error" blocks the run, "warning" does not
    message: str
    fixes: tuple = ()     # each fix is a tuple of component keys that would solve it


# components that need a capacity (fixed mode) or cost data (invest mode)
SIZED_COMPONENTS = (
    "pv", "wind", "battery", "heat_storage",
    "gas_boiler", "heat_pump", "heating_rod", "chp",
)

# efficiencies that must be entered (greater than 0)
EFFICIENCY_LABELS = {
    "efficiency": "efficiency",
    "efficiency_el": "electrical efficiency",
    "efficiency_th": "thermal efficiency",
}
EFFICIENCY_FIELDS = {
    "heating_rod": ("efficiency",),
    "chp": ("efficiency_el", "efficiency_th"),
}

# components that need an uploaded time series -> key in input_data
REQUIRED_PROFILES = {
    "demand": "electricity_demand",
    "heat_demand": "heat_demand",
    "pv": "pv",
    "wind": "wind",
}

INVEST_FIELDS = ("capex", "opex", "lifetime", "interest_rate")


def check_system(selected, tech_inputs=None, input_data=None, labels=None):
    """Check a system definition before the optimization is started.

    Returns a list of Finding objects, errors first. Errors describe cases where
    the model cannot be solved (or cannot even be built). Warnings describe
    combinations that are probably not what the user wants, or that can make the
    model infeasible.

    This module does not use Streamlit, so any frontend can call it.

    selected     list of component keys, e.g. ["demand", "grid", "pv"]
    tech_inputs  values entered by the user, e.g. {"pv": {"mode": "fixed", ...}}
    input_data   uploaded time series, e.g. {"pv": [...], "electricity_demand": [...]}
    labels       readable names for the messages, e.g. {"pv": "PV System"}
    """

    chosen = set(selected)
    tech_inputs = tech_inputs or {}
    input_data = input_data or {}
    labels = labels or {}

    def name(key):
        return labels.get(key, key)

    def fixes(*options):
        # keep only what is still missing; drop options that are already complete
        result = []
        for option in options:
            missing = tuple(k for k in option if k not in chosen)
            if missing:
                result.append(missing)
        return tuple(result)

    errors = []
    warnings = []

    # what can actually supply energy in the selected system
    renewables = [k for k in ("pv", "wind") if k in chosen]
    # a CHP plant only runs when its gas is supplied and its heat can be used
    chp_works = {"chp", "gas_import", "heat_demand"} <= chosen
    electricity_source = "grid" in chosen or bool(renewables) or chp_works
    heat_pump_works = "heat_pump" in chosen and electricity_source
    heating_rod_works = "heating_rod" in chosen and electricity_source
    boiler_works = "gas_boiler" in chosen and "gas_import" in chosen
    chp_heat_works = "chp" in chosen and "gas_import" in chosen
    heat_source = (
        heat_pump_works or heating_rod_works or boiler_works or chp_heat_works
    )

    # structure: errors (the model cannot be solved)
    if not chosen & {"demand", "heat_demand"}:
        errors.append(Finding(
            "error",
            "No demand selected. Add an electricity demand or a heat demand.",
            fixes(("demand",), ("heat_demand",)),
        ))

    if "demand" in chosen and not electricity_source:
        errors.append(Finding(
            "error",
            f"{name('demand')} has no supply. Add a grid connection (or PV or wind).",
            fixes(("grid",)),
        ))

    heat_error = "heat_demand" in chosen and not heat_source
    if heat_error:
        errors.append(Finding(
            "error",
            f"{name('heat_demand')} cannot be supplied. It needs a working heat source: "
            f"a gas boiler or CHP plant together with a gas import, or a heat pump "
            f"or heating rod together with electricity from the grid or PV.",
            fixes(
                ("gas_boiler", "gas_import"),
                ("chp", "gas_import"),
                ("heat_pump", "grid"),
                ("heating_rod", "grid"),
            ),
        ))

    # electricity price: constant value or uploaded time series
    grid = tech_inputs.get("grid", {})
    price_is_series = "grid" in chosen and grid.get("price_mode") == "timeseries"
    lowest_price = None          # lowest electricity price in EUR/kWh (for the feed-in check)
    price_label = "electricity price"

    if price_is_series:
        series = input_data.get("grid_price")
        horizon = len(input_data["timeindex"]) if input_data.get("timeindex") is not None else None

        if series is None:
            errors.append(Finding(
                "error",
                f"{name('grid')}: no price time series uploaded. Upload a CSV file "
                f"or switch the electricity price to 'constant'.",
            ))
        elif grid.get("price_unit", "€/kWh") not in PRICE_UNIT_FACTORS:
            errors.append(Finding(
                "error",
                f"{name('grid')}: unknown price unit '{grid.get('price_unit')}'.",
            ))
        else:
            prices = price_series_in_eur_per_kwh(series, grid.get("price_unit", "€/kWh"))
            if any(p != p for p in prices):
                errors.append(Finding(
                    "error",
                    f"{name('grid')}: the price series contains empty values. "
                    f"Please check the selected column.",
                ))
            elif horizon is not None and len(prices) < horizon:
                errors.append(Finding(
                    "error",
                    f"{name('grid')}: the price series has {len(prices)} values, but the "
                    f"selected time range needs {horizon}. Upload a longer series or "
                    f"shorten the time range.",
                ))
            else:
                lowest_price = min(prices)
                price_label = f"lowest electricity price in the series"
    else:
        lowest_price = grid.get("variable_costs")

    # prices: an obvious input mistake that makes the model unbounded
    tariff = tech_inputs.get("grid_feedin", {}).get("feedin_tariff")
    if (
        {"grid", "grid_feedin"} <= chosen
        and lowest_price is not None
        and tariff is not None
        and tariff > lowest_price
    ):
        errors.append(Finding(
            "error",
            f"The feed-in tariff ({tariff:g} €/kWh) is higher than the "
            f"{price_label} ({lowest_price:g} €/kWh). The model could buy and sell "
            f"electricity at the same time for unlimited profit and cannot be solved. "
            f"Please check the prices and their units.",
        ))

    # inputs: errors (missing values that would stop the run)
    for key, profile in REQUIRED_PROFILES.items():
        if key in chosen and input_data.get(profile) is None:
            errors.append(Finding(
                "error",
                f"{name(key)}: no time series uploaded. Upload a CSV file in its tab.",
            ))

    heat_pump = tech_inputs.get("heat_pump", {})
    if "heat_pump" in chosen:
        if heat_pump.get("cop_mode") == "timeseries":
            if input_data.get("cop_series") is None:
                errors.append(Finding(
                    "error",
                    f"{name('heat_pump')}: no COP time series uploaded. Upload a CSV "
                    f"file or switch the COP mode to 'constant'.",
                ))
        else:
            cop = heat_pump.get("cop_value")
            if cop is None or cop <= 0:
                errors.append(Finding(
                    "error",
                    f"{name('heat_pump')}: the constant COP must be greater than 0.",
                ))

    for key, fields in EFFICIENCY_FIELDS.items():
        if key not in chosen:
            continue
        values = tech_inputs.get(key, {})
        for field in fields:
            value = values.get(field)
            if value is None or value <= 0:
                errors.append(Finding(
                    "error",
                    f"{name(key)}: the {EFFICIENCY_LABELS[field]} must be greater than 0.",
                ))

    if "chp" in chosen:
        chp = tech_inputs.get("chp", {})
        eta_el, eta_th = chp.get("efficiency_el"), chp.get("efficiency_th")
        if eta_el and eta_th and eta_el + eta_th > 1:
            errors.append(Finding(
                "error",
                f"{name('chp')}: electrical + thermal efficiency "
                f"({eta_el + eta_th:g}) cannot be greater than 1.",
            ))

    for key in SIZED_COMPONENTS:
        if key not in chosen or key not in tech_inputs:
            continue

        values = tech_inputs[key]
        mode = values.get("mode")

        if mode in (None, "fixed"):
            capacity = values.get("capacity")
            if capacity is None or capacity <= 0:
                errors.append(Finding(
                    "error",
                    f"{name(key)}: fixed mode needs a capacity greater than 0 "
                    f"(or set the mode to 'invest').",
                ))

        elif mode == "invest":
            missing = [f for f in INVEST_FIELDS if values.get(f) is None]
            if missing:
                errors.append(Finding(
                    "error",
                    f"{name(key)}: invest mode needs values for {', '.join(missing)}.",
                ))

    # structure: warnings (the model may still run)
    if renewables and "grid" not in chosen and chosen & {"demand", "heat_pump", "heating_rod"}:
        names = " and ".join(name(k) for k in renewables)
        warnings.append(Finding(
            "warning",
            f"{names} alone cannot cover demand at all times. Without a grid "
            f"connection (or enough storage) the model may be infeasible.",
            fixes(("grid",)),
        ))

    fixed_renewables = [
        k for k in renewables
        if tech_inputs.get(k, {}).get("mode") in (None, "fixed")
    ]
    if fixed_renewables and "grid_feedin" not in chosen:
        names = " and ".join(name(k) for k in fixed_renewables)
        warnings.append(Finding(
            "warning",
            f"Surplus electricity from {names} cannot be exported. With a fixed "
            f"capacity the model can become infeasible when production is higher "
            f"than what is used.",
            fixes(("grid_feedin",)),
        ))

    if "grid_feedin" in chosen and not (renewables or chp_works):
        warnings.append(Finding(
            "warning",
            f"{name('grid_feedin')} is selected, but nothing feeds electricity into it.",
            fixes(("pv",), ("wind",), ("chp", "gas_import")),
        ))

    # a CHP plant always produces heat and electricity together
    other_heat = heat_pump_works or heating_rod_works or boiler_works
    if "chp" in chosen and "gas_import" not in chosen and not heat_error:
        warnings.append(Finding(
            "warning",
            f"{name('chp')} has no fuel supply and cannot run.",
            fixes(("gas_import",)),
        ))
    if "chp" in chosen and "heat_demand" not in chosen:
        warnings.append(Finding(
            "warning",
            f"{name('chp')} always produces heat as well. Without a heat demand "
            f"the heat cannot be used and the plant will not run.",
            fixes(("heat_demand",)),
        ))
    if chp_works and "grid_feedin" not in chosen and not other_heat:
        warnings.append(Finding(
            "warning",
            f"{name('chp')} is the only heat source and its electricity cannot be "
            f"exported. If heat demand is high compared to electricity demand "
            f"the model can become infeasible.",
            fixes(("grid_feedin",)),
        ))

    if "gas_boiler" in chosen and "gas_import" not in chosen and not heat_error:
        warnings.append(Finding(
            "warning",
            f"{name('gas_boiler')} has no fuel supply and cannot run.",
            fixes(("gas_import",)),
        ))

    for key in ("heat_pump", "heating_rod"):
        if key in chosen and not electricity_source and not heat_error:
            warnings.append(Finding(
                "warning",
                f"{name(key)} needs electricity and cannot run.",
                fixes(("grid",)),
            ))

    if "gas_import" in chosen and not chosen & {"gas_boiler", "chp"}:
        warnings.append(Finding(
            "warning",
            f"{name('gas_import')} is selected, but no component uses gas.",
            fixes(("gas_boiler",), ("chp",)),
        ))

    if "battery" in chosen and not electricity_source:
        warnings.append(Finding(
            "warning",
            f"{name('battery')} has nothing to charge from. Add a grid connection, PV or wind.",
            fixes(("grid",), ("pv",), ("wind",)),
        ))

    if "heat_demand" not in chosen:
        for key in ("gas_boiler", "heat_pump", "heating_rod", "heat_storage"):
            if key in chosen:
                warnings.append(Finding(
                    "warning",
                    f"{name(key)} is selected, but there is no heat demand.",
                    fixes(("heat_demand",)),
                ))

    return errors + warnings