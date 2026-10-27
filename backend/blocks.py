"""The capability blocks a component can have.

A component in a scenario is a kind (source, sink, converter, storage) plus
blocks: named groups of settings, such as the size and investment costs
(`capacity`), a time series profile (`profile`) or the conversion efficiency
(`conversion`). A curated template is a component with some blocks switched on
and filled with defaults; a user's own component is the same without the
defaults.

Rules for all blocks:

- every percentage is stored as a percentage (interest 3 means 3 %, an
  efficiency of 95 means 95 %), never as a fraction,
- a value that is empty (None) is not wrong: a form that is not filled in yet
  is fine, the system check says what is still missing,
- settings that are hidden for the current choice (for example the investment
  costs while the size is fixed) are not checked.

Some blocks are known to the file format but not supported by the engine yet
(`engine_supported`). The file can hold them; a check reports them.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.component_specs import PV, FieldSpec

Kind = Literal["source", "sink", "converter", "storage"]


class BlockSpec(BaseModel):
    """One kind of block: its settings, and which kinds of component may have it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    kinds: tuple[Kind, ...]
    help: str = ""
    fields: tuple[FieldSpec, ...] = ()
    series_keys: tuple[str, ...] = ()       # settings that hold the id of a time series
    extra_keys: tuple[str, ...] = ()        # settings checked elsewhere (they need the whole component)
    engine_supported: bool = True

    def defaults(self):
        return {f.key: f.default for f in self.fields if f.default is not None}

    def allowed_keys(self):
        return {f.key for f in self.fields} | set(self.series_keys) | set(self.extra_keys)

    def visible_fields(self, values):
        defaults = self.defaults()

        def visible(field):
            return all(
                values.get(other, defaults.get(other)) in allowed
                for other, allowed in field.visible_if.items()
            )

        return [f for f in self.fields if visible(f)]

    def problems(self, values, owner):
        """What is impossible in these settings, as readable sentences."""

        prefix = f"{owner}: {self.label}"
        found = [
            f"{prefix}: unknown setting '{key}'"
            for key in values
            if key not in self.allowed_keys()
        ]

        for field in self.visible_fields(values):
            value = values.get(field.key)
            if value is not None:
                found.extend(_field_problems(prefix, field, value))

        for key in self.series_keys:
            value = values.get(key)
            if value is not None and not isinstance(value, str):
                found.append(f"{prefix}: '{key}' must be the id of a time series")

        return found


def _field_problems(prefix, field, value):
    name = f"{prefix}: {field.label}"
    unit = f" {field.unit}" if field.unit else ""

    if field.kind == "choice":
        if value not in field.options:
            return [f"{name} must be one of: {', '.join(field.options)}"]
        return []

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{name} must be a number"]

    found = []
    if field.minimum is not None and value < field.minimum:
        found.append(f"{name} must be at least {field.minimum:g}{unit}")
    if field.maximum is not None and value > field.maximum:
        found.append(f"{name} must be at most {field.maximum:g}{unit}")

    return found


# ---------------------------------------------------------------------------
# the conversion block: efficiency (a percentage) or a ratio, for each output
# ---------------------------------------------------------------------------

CONVERSION_KEYS = ("efficiency", "ratio", "ratio_series")


def conversion_problems(values, output_carriers, owner):
    """Check the `outputs` of a conversion block against the carriers the component gives to.

    outputs: {carrier: {"efficiency": 65}}        a percentage of the input
             {carrier: {"ratio": 3.5}}            output per input, for example a heat pump
             {carrier: {"ratio_series": "cop"}}   the ratio as a time series
    """

    prefix = f"{owner}: Conversion"
    found = [
        f"{prefix}: unknown setting '{key}'" for key in values if key != "outputs"
    ]

    outputs = values.get("outputs")
    if outputs is None:
        return found
    if not isinstance(outputs, dict):
        return found + [f"{prefix}: 'outputs' must list a value for each output carrier"]

    efficiencies = []

    for carrier, entry in outputs.items():
        name = f"{prefix} for {carrier}"

        if carrier not in output_carriers:
            found.append(f"{name}: the component does not give energy to '{carrier}'")
            continue
        if not isinstance(entry, dict):
            found.append(f"{name}: expected one of {', '.join(CONVERSION_KEYS)}")
            continue

        given = [key for key in entry if entry[key] is not None]
        unknown = [key for key in entry if key not in CONVERSION_KEYS]
        if unknown:
            found.append(f"{name}: unknown setting '{unknown[0]}'")
            continue
        if len(given) > 1:
            found.append(f"{name}: give only one of {', '.join(CONVERSION_KEYS)}")
            continue
        if not given:
            continue

        key, value = given[0], entry[given[0]]

        if key == "ratio_series":
            if not isinstance(value, str):
                found.append(f"{name}: 'ratio_series' must be the id of a time series")
            continue

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            found.append(f"{name}: {key} must be a number")
        elif key == "efficiency":
            if not 0 < value <= 100:
                found.append(f"{name}: efficiency must be above 0 and at most 100 %")
            else:
                efficiencies.append(value)
        elif value <= 0:
            found.append(f"{name}: ratio must be above 0")

    if sum(efficiencies) > 100 + 1e-9:
        found.append(f"{prefix}: the efficiencies of all outputs together cannot exceed 100 %")

    return found


def series_references(block_name, values):
    """The ids of the time series a block refers to."""

    spec = BLOCKS[block_name]
    ids = [values[key] for key in spec.series_keys if isinstance(values.get(key), str)]

    if block_name == "conversion" and isinstance(values.get("outputs"), dict):
        for entry in values["outputs"].values():
            if isinstance(entry, dict) and isinstance(entry.get("ratio_series"), str):
                ids.append(entry["ratio_series"])

    return ids


# ---------------------------------------------------------------------------
# the catalog
# ---------------------------------------------------------------------------

BLOCKS = {
    block.name: block
    for block in (
        BlockSpec(
            name="capacity",
            label="Capacity",
            kinds=("source", "sink", "converter", "storage"),
            help="The size of the component: fixed, or chosen by the optimizer "
                 "with the investment costs.",
            fields=PV.fields,                 # the same settings as the PV plant
            extra_keys=("rated_flow",),       # which flow the size refers to (converters)
        ),
        BlockSpec(
            name="profile",
            label="Generation profile",
            kinds=("source",),
            help="The hourly availability between 0 and 1, multiplied with the size.",
            series_keys=("series",),
        ),
        BlockSpec(
            name="demand",
            label="Demand",
            kinds=("sink",),
            help="The hourly demand: a time series, either as shares of the annual "
                 "demand or as absolute values.",
            fields=(
                FieldSpec(
                    key="profile_type", label="What does the profile hold?", kind="choice",
                    options=("annual_share", "absolute"),
                    option_labels={
                        "annual_share": "Shares that add up to 1 over a year",
                        "absolute": "The demand in kW",
                    },
                    default="annual_share",
                    help="A normalized profile adds up to 1 over a year: the demand of "
                         "every hour is its share times the annual demand. An absolute "
                         "profile already holds the demand in kW.",
                ),
                FieldSpec(
                    key="annual_demand", label="Annual demand", kind="number",
                    unit="kWh per year", minimum=0, step=1000,
                    visible_if={"profile_type": ("annual_share",)},
                    help="The energy per year. Every hour gets its share of it.",
                ),
            ),
            series_keys=("series",),
        ),
        BlockSpec(
            name="costs",
            label="Costs",
            kinds=("source", "sink", "converter"),
            help="What the energy costs, or what it earns.",
            fields=(
                FieldSpec(
                    key="variable_costs", label="Variable costs", kind="number",
                    unit="€ per kWh", minimum=0, step=0.01,
                    help="The cost of every kWh, for example the price of grid electricity.",
                ),
                FieldSpec(
                    key="revenue", label="Revenue", kind="number",
                    unit="€ per kWh", minimum=0, step=0.01,
                    help="What every kWh earns, for example a feed-in tariff.",
                ),
            ),
            series_keys=("variable_costs_series",),
        ),
        BlockSpec(
            name="conversion",
            label="Conversion",
            kinds=("converter",),
            help="How much of each output comes out per unit of input.",
            extra_keys=("outputs",),
        ),
        BlockSpec(
            name="storage",
            label="Storage",
            kinds=("storage",),
            help="How the storage is charged, discharged and how it loses energy.",
            fields=(
                FieldSpec(
                    key="c_rate", label="Charge and discharge power", kind="number",
                    unit="times the capacity per hour", minimum=0, step=0.05,
                    help="0.5 means that a full storage can be emptied in two hours.",
                ),
                FieldSpec(
                    key="efficiency_charge", label="Charging efficiency", kind="number",
                    unit="%", minimum=0, maximum=100, step=1,
                    help="The share of the energy that arrives in the storage.",
                ),
                FieldSpec(
                    key="efficiency_discharge", label="Discharging efficiency", kind="number",
                    unit="%", minimum=0, maximum=100, step=1,
                    help="The share of the stored energy that comes out.",
                ),
                FieldSpec(
                    key="loss_rate", label="Self-discharge", kind="number",
                    unit="% per hour", minimum=0, maximum=100, step=0.01,
                    help="The share of the stored energy that is lost every hour.",
                ),
                FieldSpec(
                    key="initial_level", label="Initial charge level", kind="number",
                    unit="% of the capacity", minimum=0, maximum=100, step=5,
                    help="The charge level at the start. Leave empty to not fix it.",
                ),
            ),
        ),
        BlockSpec(
            name="on_off",
            label="On/off behaviour",
            kinds=("source", "converter"),
            help="A minimum load, start-up costs and minimum run and off times. "
                 "This makes the problem harder to solve.",
            fields=(
                FieldSpec(
                    key="minimum_load", label="Minimum load", kind="number",
                    unit="% of the size", minimum=0, maximum=100, step=5,
                    help="While running, the component cannot go below this share of its size.",
                ),
                FieldSpec(
                    key="startup_cost", label="Start-up cost", kind="number",
                    unit="€ per start", minimum=0, step=1,
                    help="What every start costs.",
                ),
                FieldSpec(
                    key="minimum_uptime", label="Minimum run time", kind="number",
                    unit="hours", minimum=0, step=1,
                    help="Once started, it runs at least this long.",
                ),
                FieldSpec(
                    key="minimum_downtime", label="Minimum off time", kind="number",
                    unit="hours", minimum=0, step=1,
                    help="Once stopped, it stays off at least this long.",
                ),
            ),
            engine_supported=False,
        ),
    )
}