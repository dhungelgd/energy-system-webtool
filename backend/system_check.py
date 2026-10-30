from backend.findings import ComponentRef, Finding, coded  # noqa: F401 - Finding is re-exported
from backend.price_units import PRICE_UNIT_FACTORS, price_series_in_eur_per_kwh

# components that need a capacity (fixed mode) or cost data (invest mode)
SIZED_COMPONENTS = (
    "pv", "wind", "battery", "heat_storage",
    "gas_boiler", "heat_pump", "heating_rod", "chp",
)

# efficiencies that must be entered (greater than 0), and the finding for each
EFFICIENCY_CODES = {
    "efficiency": "efficiency",
    "efficiency_el": "efficiency_electrical",
    "efficiency_th": "efficiency_thermal",
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


def _has_invalid_values(values):
    """True if a series contains empty (NaN) or non-numeric values."""

    for v in values:
        try:
            if float(v) != float(v):   # NaN
                return True
        except (TypeError, ValueError):
            return True
    return False


def check_system(selected, tech_inputs=None, input_data=None, labels=None):
    """Check a system definition before the optimization is started.

    Returns a list of Finding objects, errors first. Errors describe cases where
    the model cannot be solved (or cannot even be built). Warnings describe
    combinations that are probably not what the user wants, or that can make the
    model infeasible.

    A finding is a code plus parameters (see findings.py); the sentences are in the
    catalogs of backend/i18n. Its English wording is in `message`.

    This module does not use Streamlit, so any frontend can call it.

    selected     list of component keys, e.g. ["demand", "grid", "pv"]
    tech_inputs  values entered by the user, e.g. {"pv": {"mode": "fixed", ...}}
    input_data   uploaded time series, e.g. {"pv": [...], "electricity_demand": [...]}
    labels       readable names for the English wording, e.g. {"pv": "PV System"}
    """

    chosen = set(selected)
    tech_inputs = tech_inputs or {}
    input_data = input_data or {}
    labels = labels or {}

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

    def error(code, fix=(), **params):
        errors.append(coded("error", code, labels, fix, **params))

    def warning(code, fix=(), **params):
        warnings.append(coded("warning", code, labels, fix, **params))

    ref = ComponentRef

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
        error("no_demand", fixes(("demand",), ("heat_demand",)))

    if "demand" in chosen and not electricity_source:
        error("demand_no_supply", fixes(("grid",)), component=ref("demand"))

    heat_error = "heat_demand" in chosen and not heat_source
    if heat_error:
        error(
            "heat_not_supplied",
            fixes(
                ("gas_boiler", "gas_import"),
                ("chp", "gas_import"),
                ("heat_pump", "grid"),
                ("heating_rod", "grid"),
            ),
            component=ref("heat_demand"),
        )

    # electricity price: constant value or uploaded time series
    grid = tech_inputs.get("grid", {})
    price_is_series = "grid" in chosen and grid.get("price_mode") == "timeseries"
    lowest_price = None          # lowest electricity price in EUR/kWh (for the feed-in check)
    price_from_series = False

    if price_is_series:
        series = input_data.get("grid_price")
        horizon = len(input_data["timeindex"]) if input_data.get("timeindex") is not None else None

        if series is None:
            error("grid_price_missing", component=ref("grid"))
        elif grid.get("price_unit", "€/kWh") not in PRICE_UNIT_FACTORS:
            error("grid_price_unit", component=ref("grid"), unit=grid.get("price_unit"))
        else:
            prices = price_series_in_eur_per_kwh(series, grid.get("price_unit", "€/kWh"))
            if any(p != p for p in prices):
                error("grid_price_empty", component=ref("grid"))
            elif horizon is not None and len(prices) < horizon:
                error("grid_price_short", component=ref("grid"), count=len(prices), needed=horizon)
            else:
                lowest_price = min(prices)
                price_from_series = True
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
        error(
            "feedin_above_lowest_price" if price_from_series else "feedin_above_price",
            tariff=tariff, price=lowest_price,
        )

    # inputs: errors (missing values that would stop the run)
    for key, profile in REQUIRED_PROFILES.items():
        if key in chosen and input_data.get(profile) is None:
            error("profile_missing", component=ref(key))

    heat_pump = tech_inputs.get("heat_pump", {})
    if "heat_pump" in chosen:
        if heat_pump.get("cop_mode") == "timeseries":
            if input_data.get("cop_series") is None:
                error("cop_missing", component=ref("heat_pump"))
        else:
            cop = heat_pump.get("cop_value")
            if cop is None or cop <= 0:
                error("cop_not_positive", component=ref("heat_pump"))

    # time series: complete values, and long enough for the selected time range
    n_steps = len(input_data["timeindex"]) if input_data.get("timeindex") is not None else None

    series_to_check = [
        (key, profile) for key, profile in REQUIRED_PROFILES.items() if key in chosen
    ]
    if "heat_pump" in chosen and heat_pump.get("cop_mode") == "timeseries":
        series_to_check.append(("heat_pump", "cop_series"))

    for key, profile in series_to_check:
        values = input_data.get(profile)
        if values is None:
            continue    # a missing upload is already reported above

        if _has_invalid_values(values):
            error("series_invalid", component=ref(key))
        elif n_steps is not None and len(values) < n_steps:
            error("series_short", component=ref(key), count=len(values), needed=n_steps)
        elif n_steps is not None and len(values) > n_steps:
            warning("series_long", component=ref(key), count=len(values), needed=n_steps)

    for key, fields in EFFICIENCY_FIELDS.items():
        if key not in chosen:
            continue
        values = tech_inputs.get(key, {})
        for field in fields:
            value = values.get(field)
            if value is None or value <= 0:
                error(EFFICIENCY_CODES[field], component=ref(key))

    for key in ("battery", "heat_storage"):
        if key not in chosen:
            continue
        c_rate = tech_inputs.get(key, {}).get("c_rate")
        if c_rate is None or c_rate <= 0:
            error("c_rate", component=ref(key))

    if "chp" in chosen:
        chp = tech_inputs.get("chp", {})
        eta_el, eta_th = chp.get("efficiency_el"), chp.get("efficiency_th")
        if eta_el and eta_th and eta_el + eta_th > 1:
            error("chp_efficiency_sum", component=ref("chp"), total=eta_el + eta_th)

    for key in SIZED_COMPONENTS:
        if key not in chosen or key not in tech_inputs:
            continue

        values = tech_inputs[key]
        mode = values.get("mode")

        if mode in (None, "fixed"):
            capacity = values.get("capacity")
            if capacity is None or capacity <= 0:
                error("fixed_needs_capacity", component=ref(key))

        elif mode == "invest":
            missing = [f for f in INVEST_FIELDS if values.get(f) is None]
            if missing:
                error("invest_needs_values", component=ref(key), fields=", ".join(missing))

    # structure: warnings (the model may still run)
    if renewables and "grid" not in chosen and chosen & {"demand", "heat_pump", "heating_rod"}:
        warning(
            "renewables_alone", fixes(("grid",)),
            components=[ref(k) for k in renewables], n=len(renewables),
        )

    fixed_renewables = [
        k for k in renewables
        if tech_inputs.get(k, {}).get("mode") in (None, "fixed")
    ]
    if fixed_renewables and "grid_feedin" not in chosen:
        warning(
            "surplus_not_exported", fixes(("grid_feedin",)),
            components=[ref(k) for k in fixed_renewables],
        )

    if "grid_feedin" in chosen and not (renewables or chp_works):
        warning(
            "feedin_unused", fixes(("pv",), ("wind",), ("chp", "gas_import")),
            component=ref("grid_feedin"),
        )

    # a CHP plant always produces heat and electricity together
    other_heat = heat_pump_works or heating_rod_works or boiler_works
    if "chp" in chosen and "gas_import" not in chosen and not heat_error:
        warning("no_fuel", fixes(("gas_import",)), component=ref("chp"))
    if "chp" in chosen and "heat_demand" not in chosen:
        warning("chp_no_heat_demand", fixes(("heat_demand",)), component=ref("chp"))
    if chp_works and "grid_feedin" not in chosen and not other_heat:
        warning("chp_only_heat_source", fixes(("grid_feedin",)), component=ref("chp"))

    if "gas_boiler" in chosen and "gas_import" not in chosen and not heat_error:
        warning("no_fuel", fixes(("gas_import",)), component=ref("gas_boiler"))

    for key in ("heat_pump", "heating_rod"):
        if key in chosen and not electricity_source and not heat_error:
            warning("needs_electricity", fixes(("grid",)), component=ref(key))

    if "gas_import" in chosen and not chosen & {"gas_boiler", "chp"}:
        warning("gas_unused", fixes(("gas_boiler",), ("chp",)), component=ref("gas_import"))

    if "battery" in chosen and not electricity_source:
        warning("battery_no_source", fixes(("grid",), ("pv",), ("wind",)), component=ref("battery"))

    if "heat_demand" not in chosen:
        for key in ("gas_boiler", "heat_pump", "heating_rod", "heat_storage"):
            if key in chosen:
                warning("no_heat_demand", fixes(("heat_demand",)), component=ref(key))

    return errors + warnings