from dataclasses import dataclass


@dataclass
class Finding:
    """One result of the system check."""

    level: str            # "error" blocks the run, "warning" does not
    message: str
    fixes: tuple = ()     # each fix is a tuple of component keys that would solve it


# components that need a capacity (fixed mode) or cost data (invest mode)
SIZED_COMPONENTS = ("pv", "battery", "heat_storage", "gas_boiler", "heat_pump")

# components that need an uploaded time series -> key in input_data
REQUIRED_PROFILES = {
    "demand": "electricity_demand",
    "heat_demand": "heat_demand",
    "pv": "pv",
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
    electricity_source = bool(chosen & {"grid", "pv"})
    heat_pump_works = "heat_pump" in chosen and electricity_source
    boiler_works = "gas_boiler" in chosen and "gas_import" in chosen
    heat_source = heat_pump_works or boiler_works

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
            f"{name('demand')} has no supply. Add a grid connection (or PV).",
            fixes(("grid",)),
        ))

    heat_error = "heat_demand" in chosen and not heat_source
    if heat_error:
        errors.append(Finding(
            "error",
            f"{name('heat_demand')} cannot be supplied. It needs a working heat source: "
            f"a gas boiler together with a gas import, or a heat pump together with "
            f"electricity from the grid or PV.",
            fixes(("gas_boiler", "gas_import"), ("heat_pump", "grid")),
        ))

    # prices: an obvious input mistake that makes the model unbounded
    grid_price = tech_inputs.get("grid", {}).get("variable_costs")
    tariff = tech_inputs.get("grid_feedin", {}).get("feedin_tariff")
    if (
        {"grid", "grid_feedin"} <= chosen
        and grid_price is not None
        and tariff is not None
        and tariff > grid_price
    ):
        errors.append(Finding(
            "error",
            f"The feed-in tariff ({tariff:g} €/kWh) is higher than the electricity "
            f"price ({grid_price:g} €/kWh). The model could buy and sell electricity "
            f"at the same time for unlimited profit and cannot be solved. "
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
    if (
        "pv" in chosen
        and "grid" not in chosen
        and chosen & {"demand", "heat_pump"}
    ):
        warnings.append(Finding(
            "warning",
            f"{name('pv')} alone cannot cover demand at night. Without a grid "
            f"connection (or enough storage) the model may be infeasible.",
            fixes(("grid",)),
        ))

    pv_mode = tech_inputs.get("pv", {}).get("mode")
    if "pv" in chosen and "grid_feedin" not in chosen and pv_mode in (None, "fixed"):
        warnings.append(Finding(
            "warning",
            f"Surplus electricity from {name('pv')} cannot be exported. With a fixed "
            f"PV capacity the model can become infeasible when PV produces more than "
            f"is used.",
            fixes(("grid_feedin",)),
        ))

    if "grid_feedin" in chosen and "pv" not in chosen:
        warnings.append(Finding(
            "warning",
            f"{name('grid_feedin')} is selected, but nothing feeds electricity into it.",
            fixes(("pv",)),
        ))

    if "gas_boiler" in chosen and "gas_import" not in chosen and not heat_error:
        warnings.append(Finding(
            "warning",
            f"{name('gas_boiler')} has no fuel supply and cannot run.",
            fixes(("gas_import",)),
        ))

    if "heat_pump" in chosen and not electricity_source and not heat_error:
        warnings.append(Finding(
            "warning",
            f"{name('heat_pump')} needs electricity and cannot run.",
            fixes(("grid",)),
        ))

    if "gas_import" in chosen and "gas_boiler" not in chosen:
        warnings.append(Finding(
            "warning",
            f"{name('gas_import')} is selected, but no component uses gas.",
            fixes(("gas_boiler",)),
        ))

    if "battery" in chosen and not electricity_source:
        warnings.append(Finding(
            "warning",
            f"{name('battery')} has nothing to charge from. Add a grid connection or PV.",
            fixes(("grid",), ("pv",)),
        ))

    if "heat_demand" not in chosen:
        for key in ("gas_boiler", "heat_pump", "heat_storage"):
            if key in chosen:
                warnings.append(Finding(
                    "warning",
                    f"{name(key)} is selected, but there is no heat demand.",
                    fixes(("heat_demand",)),
                ))

    return errors + warnings