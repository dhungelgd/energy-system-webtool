"""The scenario that a user is building in the page.

No NiceGUI code in here, so it is easy to test. The draft owns the real components
(with their default settings), so that what a user has typed into a component stays
when other components are added or removed. At any moment it can hand over a valid
scenario (`scenario()`) and the result of the system check (`findings()`).

A draft is valid by construction: its setters refuse what a scenario cannot hold and
say why in a sentence for the user.

The time series belong to the components: a component keeps its series (`set_series`) as long as
it is part of the draft, and loses it when it is removed, like what was typed into it.
"""

import math
from datetime import date, datetime, time

from backend import service_v2
from backend.blocks import get_path, put_path
from backend.component_specs import INFO
from backend.scenario_v2 import ScenarioV2
from backend.series_input import slot_of
from backend.system_templates import SYSTEM_TEMPLATES, in_order
from backend.templates import carriers_for, new_component

DEFAULT_NAME = ScenarioV2.model_fields["name"].default
MAX_NAME_LENGTH = 200

MIN_STEPS, MAX_STEPS = 1, 8784                 # one hour to a leap year
DEFAULT_STEPS = ScenarioV2().time.steps

MIN_YEAR, MAX_YEAR = 1980, 2100                # the weather data of renewables.ninja start in 1980
DEFAULT_START = ScenarioV2().time.start.date()

STEPS_HINT = f"Enter a whole number from {MIN_STEPS} to {MAX_STEPS:,}."
START_HINT = f"Use the format YYYY-MM-DD (for example 2021-01-01), in the years {MIN_YEAR} to {MAX_YEAR}."


def parse_steps(value):
    """The number of hourly steps as an int, or ValueError with a sentence for the user."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(STEPS_HINT)
    if isinstance(value, float) and not (math.isfinite(value) and value.is_integer()):
        raise ValueError(STEPS_HINT)
    if not MIN_STEPS <= value <= MAX_STEPS:
        raise ValueError(STEPS_HINT)

    return int(value)


def parse_start(value):
    """The start as a date, from a date or from text like '2021-01-01'. ValueError if it is not one."""

    if isinstance(value, datetime):
        found = value.date()
    elif isinstance(value, date):
        found = value
    elif isinstance(value, str):
        try:
            found = datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(START_HINT) from None
    else:
        raise ValueError(START_HINT)

    if not MIN_YEAR <= found.year <= MAX_YEAR:
        raise ValueError(START_HINT)

    return found


class ScenarioDraft:
    """A scenario in the making: a name, a period and the chosen components."""

    def __init__(self, name="", start=DEFAULT_START, steps=DEFAULT_STEPS):
        self._components = {}
        self._series = {}                  # component key -> its time series (a SeriesData)
        self._constants = {}               # component key -> the constant that a series replaced
        self.name = name
        self.start = start
        self.steps = steps

    # ----- name and period -------------------------------------------------

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        text = (value or "").strip() if isinstance(value, str) or value is None else None
        if text is None:
            raise ValueError("The name has to be text.")
        if len(text) > MAX_NAME_LENGTH:
            raise ValueError(f"The name can have at most {MAX_NAME_LENGTH} characters.")

        self._name = text

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, value):
        self._start = parse_start(value)

    @property
    def steps(self):
        return self._steps

    @steps.setter
    def steps(self, value):
        self._steps = parse_steps(value)

    # ----- components ------------------------------------------------------

    def set(self, key, chosen=True):
        """Add a component with its default settings, or remove it. Unknown components are refused."""

        if key not in INFO:
            raise KeyError(f"unknown component '{key}'")

        if chosen:
            self._components.setdefault(key, new_component(key))
        else:
            self._components.pop(key, None)
            self._forget(key)

    def is_selected(self, key):
        return key in self._components

    def __len__(self):
        return len(self._components)

    def component(self, key):
        """The component itself (what a form edits). KeyError if it is not part of the draft."""

        return self._components[key]

    def components(self):
        """The components in the order of the groups, as the engine expects them."""

        return [self._components[key] for key in in_order(self._components)]

    def apply_template(self, name):
        """Choose exactly the components of a system template.

        Components that stay keep what was typed into them; the others are removed,
        and new ones start with their defaults.
        """

        if name not in SYSTEM_TEMPLATES:
            raise KeyError(f"unknown template '{name}'")

        wanted = set(SYSTEM_TEMPLATES[name])

        for key in list(self._components):
            if key not in wanted:
                del self._components[key]
                self._forget(key)
        for key in wanted:
            self.set(key)

    def clear(self):
        self._components = {}
        self._series = {}
        self._constants = {}

    # ----- time series -----------------------------------------------------

    def _forget(self, key):
        self._series.pop(key, None)
        self._constants.pop(key, None)

    def series_of(self, key):
        """The time series of a component (a SeriesData), or None if it has none."""

        return self._series.get(key)

    def set_series(self, key, data):
        """Give a component its time series (a SeriesData made by series_input.series_data).

        A component that can also use a constant (the grid price, the COP) is switched to the series.
        The constant of the heat pump is kept and comes back with `clear_series`.
        """

        component = self.component(key)
        slot = slot_of(component)
        if slot is None:
            raise ValueError(f"the component '{key}' has no time series")

        block = component.blocks.setdefault(slot.block, {})
        constant = get_path(block, "outputs.heat.ratio") if key == "heat_pump" else None
        if constant is not None:
            self._constants[key] = constant                      # a series and a constant exclude each other
            put_path(block, "outputs.heat.ratio", None)

        self._series[key] = data
        put_path(block, slot.field, slot.series_id)

    def clear_series(self, key):
        """Take the time series away. A component with a constant goes back to it."""

        component = self.component(key)
        slot = slot_of(component)
        if slot is None or key not in self._series:
            return

        del self._series[key]
        block = component.blocks.setdefault(slot.block, {})
        put_path(block, slot.field, None)

        if key == "heat_pump":
            constant = self._constants.pop(key, None)
            if constant is None:
                constant = get_path(new_component(key).blocks[slot.block], "outputs.heat.ratio")
            put_path(block, "outputs.heat.ratio", constant)

    def uses_series(self, key):
        """True if the component works with a time series now (for the grid and the heat pump: and not the constant)."""

        return key in self._series

    # ----- what it makes ---------------------------------------------------

    def scenario(self, default_name=DEFAULT_NAME):
        """A valid ScenarioV2 of the draft (a copy: changing it does not change the draft).

        A draft that has no name yet gets the default name that is given (in the language
        of the reader).
        """

        components = [component.model_copy(deep=True) for component in self.components()]
        series = {
            slot_of(component).series_id: self._series[component.id].model_copy(deep=True)
            for component in components
            if component.id in self._series
        }

        return ScenarioV2(
            name=self.name or default_name,
            time={"start": datetime.combine(self.start, time.min), "steps": self.steps},
            carriers=carriers_for(components),
            components=components,
            series=series,
        )

    def findings(self):
        """The system check of the draft as it is now: errors first, then warnings."""

        return service_v2.check(self.scenario())