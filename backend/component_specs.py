"""What each component of the energy system is, and which settings it has.

One place for knowledge that forms, checks and diagrams all need:

- every setting with its label, unit, allowed range, default, help text, the
  section it belongs to (basic, investment, advanced) and the rule that says
  when it is shown (for example "only when the mode is invest"),
- the time series the component uses,
- what the component is (source, sink, converter, storage) and which energy
  carriers (buses) it connects to. A diagram of the energy system is drawn from
  this.

Only the PV plant has a specification so far. The other components follow one
by one; until then they are not checked here.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

Section = Literal["basic", "investment", "advanced"]
Role = Literal["source", "sink", "converter", "storage"]
Direction = Literal["in", "out", "both"]
Bus = Literal["electricity", "heat", "gas"]


class FieldSpec(BaseModel):
    """One setting of a component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    kind: Literal["number", "choice"]
    unit: str = ""
    default: Union[float, str, None] = None
    minimum: Union[float, None] = None
    maximum: Union[float, None] = None
    step: Union[float, None] = None
    help: str = ""
    section: Section = "basic"

    # choices: the allowed values and how they are worded for the user
    options: tuple[str, ...] = ()
    option_labels: dict[str, str] = Field(default_factory=dict)

    # shown only when every listed setting has one of the listed values
    visible_if: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self):
        if self.kind == "choice":
            if not self.options:
                raise ValueError(f"{self.key}: a choice needs options")
            if self.default is not None and self.default not in self.options:
                raise ValueError(f"{self.key}: the default is not one of the options")
            unknown = set(self.option_labels) - set(self.options)
            if unknown:
                raise ValueError(f"{self.key}: labels for unknown options {sorted(unknown)}")
        else:
            if self.options:
                raise ValueError(f"{self.key}: a number has no options")
            if (
                self.minimum is not None and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise ValueError(f"{self.key}: the minimum is above the maximum")

        return self


class SeriesSpec(BaseModel):
    """A time series the component uses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    unit: str
    # a profile between 0 and 1 that is multiplied with the size, or absolute values
    profile: Literal["capacity_factor", "absolute"]
    expected_range: Union[tuple[float, float], None] = None
    help: str = ""


class Connection(BaseModel):
    """Where a component is connected: an energy carrier and a direction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bus: Bus
    direction: Direction


class ComponentSpec(BaseModel):
    """Everything the tool knows about one kind of component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    group: str
    help: str = ""

    role: Role
    connections: tuple[Connection, ...]

    fields: tuple[FieldSpec, ...] = ()
    series: tuple[SeriesSpec, ...] = ()

    @model_validator(mode="after")
    def _consistent(self):
        field_keys = [f.key for f in self.fields]
        series_keys = [s.key for s in self.series]

        if len(set(field_keys)) != len(field_keys):
            raise ValueError(f"{self.key}: a setting is listed twice")
        if set(field_keys) & set(series_keys):
            raise ValueError(f"{self.key}: a time series has the key of a setting")

        by_key = {f.key: f for f in self.fields}
        for field in self.fields:
            for other, allowed in field.visible_if.items():
                if other not in by_key or by_key[other].kind != "choice":
                    raise ValueError(f"{field.key}: visible_if refers to '{other}', which is not a choice")
                bad = set(allowed) - set(by_key[other].options)
                if bad:
                    raise ValueError(f"{field.key}: visible_if uses unknown values {sorted(bad)}")

        directions = {c.direction for c in self.connections}
        if self.role == "source" and directions != {"out"}:
            raise ValueError(f"{self.key}: a source only gives energy out")
        if self.role == "sink" and directions != {"in"}:
            raise ValueError(f"{self.key}: a sink only takes energy in")
        if self.role == "storage" and directions != {"both"}:
            raise ValueError(f"{self.key}: a storage takes energy in and gives it out")
        if self.role == "converter" and not {"in", "out"} <= directions:
            raise ValueError(f"{self.key}: a converter needs an input and an output")

        return self

    # ------------------------------------------------------------------

    def field(self, key):
        for field in self.fields:
            if field.key == key:
                return field
        raise KeyError(key)

    def defaults(self):
        """The default of every setting that has one."""

        return {f.key: f.default for f in self.fields if f.default is not None}

    def allowed_keys(self):
        """The settings a scenario may hold: the fields, and one column name per series.

        The interface stores the name of the chosen file column under the key of
        the time series, so those keys are allowed too.
        """

        return {f.key for f in self.fields} | {s.key for s in self.series}

    def is_visible(self, field, settings):
        defaults = self.defaults()

        for other, allowed in field.visible_if.items():
            if settings.get(other, defaults.get(other)) not in allowed:
                return False

        return True

    def visible_fields(self, settings):
        """The fields to show for the current settings, in order."""

        return [f for f in self.fields if self.is_visible(f, settings)]

    def problems(self, settings):
        """Everything impossible in these settings, as readable sentences.

        Empty values are fine here: a form that is not filled in yet is not wrong,
        the system check reports what is still missing. Settings that are hidden
        for the current mode are not checked.
        """

        found = []

        for key in settings:
            if key not in self.allowed_keys():
                found.append(f"{self.label}: unknown setting '{key}'")

        for field in self.visible_fields(settings):
            value = settings.get(field.key)
            if value is None:
                continue

            found.extend(self._field_problems(field, value))

        for series in self.series:
            value = settings.get(series.key)
            if value is not None and not isinstance(value, str):
                found.append(f"{self.label}: the column name of '{series.label}' must be text")

        return found

    def _field_problems(self, field, value):
        name = f"{self.label}: {field.label}"
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
# the components
# ---------------------------------------------------------------------------

MODE = FieldSpec(
    key="mode",
    label="How is the size decided?",
    kind="choice",
    options=("fixed", "invest"),
    option_labels={
        "fixed": "I enter a fixed size",
        "invest": "The optimizer chooses the size",
    },
    default="fixed",
    help="Fixed: the size you enter is used. Invest: the optimizer chooses the "
         "size that gives the lowest total cost, within the maximum you set.",
)

PV = ComponentSpec(
    key="pv",
    label="PV system",
    group="Generation",
    help="A photovoltaic plant. Its output in every hour is its size multiplied "
         "with the generation profile.",
    role="source",
    connections=(Connection(bus="electricity", direction="out"),),
    fields=(
        MODE,
        FieldSpec(
            key="capacity", label="Installed size", kind="number", unit="kW",
            minimum=0, step=1,
            visible_if={"mode": ("fixed",)},
            help="The installed peak power of the plant.",
        ),
        FieldSpec(
            key="maximum", label="Maximum size", kind="number", unit="kW",
            minimum=0, step=1, section="investment",
            visible_if={"mode": ("invest",)},
            help="Upper limit for the optimizer, for example from the roof area. "
                 "Leave empty for no limit.",
        ),
        FieldSpec(
            key="capex", label="Investment cost", kind="number", unit="€ per kW",
            default=1200.0, minimum=0, step=50, section="investment",
            visible_if={"mode": ("invest",)},
            help="The total installed cost divided by the installed power, for "
                 "example from a quote.",
        ),
        FieldSpec(
            key="opex", label="Running cost", kind="number",
            unit="% of the investment per year",
            default=2.0, minimum=0, maximum=100, step=0.5, section="investment",
            visible_if={"mode": ("invest",)},
            help="Yearly maintenance and operation as a percentage of the investment.",
        ),
        FieldSpec(
            key="lifetime", label="Lifetime", kind="number", unit="years",
            default=25.0, minimum=1, maximum=100, step=1, section="investment",
            visible_if={"mode": ("invest",)},
            help="How long the plant is used. The investment is spread over this time.",
        ),
        FieldSpec(
            key="interest_rate", label="Interest rate", kind="number", unit="% per year",
            default=3.0, minimum=0, maximum=100, step=0.1, section="investment",
            visible_if={"mode": ("invest",)},
            help="Used to spread the investment over its lifetime. 0 means no interest.",
        ),
    ),
    series=(
        SeriesSpec(
            key="pv",
            label="PV generation profile",
            unit="capacity factor, 0 to 1",
            profile="capacity_factor",
            expected_range=(0.0, 1.0),
            help="The hourly output per installed kW: 0 without sun, 1 at full "
                 "power. It is multiplied with the size of the plant.",
        ),
    ),
)

SPECS = {spec.key: spec for spec in (PV,)}


def get_spec(key):
    """The specification of a component, or None if it has none yet."""

    return SPECS.get(key)