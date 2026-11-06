"""One validated, saveable description of a scenario: everything a run needs.

Until now the inputs of a run were four loose objects (the selected components,
the settings per component, the time series and the solver settings). A
`Scenario` holds all of them in one object that

- is checked when it is created (unknown components, wrong modes, broken numbers),
- can be written to and read from a JSON file, and
- can be turned into the four objects the existing backend functions expect,
  so nothing else has to change (`to_inputs`) and back (`from_inputs`).

This module does not use Streamlit, so any frontend can use it.
"""

import datetime
import math
from pathlib import Path
from typing import Literal, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.component_specs import get_spec
from backend.input_schema import SolverConfig
from backend.oemof_components import TECH_MAPPING
from backend.solving import DEFAULT_SOLVER

# the layout of a saved scenario
SCHEMA_VERSION = 1

# the components the model knows
COMPONENTS = tuple(TECH_MAPPING)

# the time series a scenario may contain (key in the input data)
SERIES_KEYS = (
    "electricity_demand",
    "heat_demand",
    "pv",
    "wind",
    "grid_price",
    "cop_series",
)

# settings that can only have a few values
CHOICES = {
    "mode": ("fixed", "invest"),
    "price_mode": ("constant", "timeseries"),
    "cop_mode": ("constant", "timeseries"),
}

# a single setting of a component: a number, a word, a yes/no or nothing (empty)
Setting = Union[float, str, bool, None]


class SolverSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["highs", "cbc"] = DEFAULT_SOLVER
    tee: bool = False


class TimeSettings(BaseModel):
    """The simulated period: hourly steps from a start time."""

    model_config = ConfigDict(extra="forbid")

    start: datetime.datetime = datetime.datetime(2021, 1, 1)
    steps: int = Field(default=8760, ge=1, le=8784)
    resolution: Literal["1h"] = "1h"


def _is_nan(value):
    return isinstance(value, float) and math.isnan(value)


class Scenario(BaseModel):
    """Everything needed to check and run one energy system."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: int = SCHEMA_VERSION
    name: str = Field(default="Unnamed scenario", min_length=1, max_length=200)

    components: list[str] = Field(default_factory=list)
    settings: dict[str, dict[str, Setting]] = Field(default_factory=dict)

    time: TimeSettings = Field(default_factory=TimeSettings)
    series: dict[str, list[Union[float, None]]] = Field(default_factory=dict)

    solver: SolverSettings = Field(default_factory=SolverSettings)

    # ------------------------------------------------------------------
    # checks
    # ------------------------------------------------------------------

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, version):
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"this scenario was saved with a newer version of the tool "
                f"(layout {version}, this tool reads up to {SCHEMA_VERSION})"
            )
        return version

    @field_validator("name")
    @classmethod
    def _clean_name(cls, name):
        name = name.strip()
        if not name:
            raise ValueError("the name must not be empty")
        return name

    @field_validator("components")
    @classmethod
    def _known_components(cls, components):
        unknown = [c for c in components if c not in COMPONENTS]
        if unknown:
            raise ValueError(
                f"unknown components: {', '.join(unknown)}. "
                f"Known components: {', '.join(COMPONENTS)}"
            )

        duplicates = sorted({c for c in components if components.count(c) > 1})
        if duplicates:
            raise ValueError(f"components listed twice: {', '.join(duplicates)}")

        return components

    @field_validator("series")
    @classmethod
    def _clean_series(cls, series):
        cleaned = {}

        for key, values in series.items():
            if key not in SERIES_KEYS:
                raise ValueError(
                    f"unknown time series '{key}'. Known: {', '.join(SERIES_KEYS)}"
                )

            result = []
            for value in values:
                if value is None or _is_nan(value):
                    result.append(None)             # empty value, stays visible
                elif math.isinf(value):
                    raise ValueError(f"time series '{key}' contains an infinite value")
                else:
                    result.append(float(value))

            cleaned[key] = result

        return cleaned

    @model_validator(mode="after")
    def _settings_fit_the_components(self):
        problems = []

        for component, values in self.settings.items():

            if component not in self.components:
                raise ValueError(
                    f"settings for '{component}', but this component is not selected"
                )

            for key, value in values.items():

                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError(
                        f"{component}.{key} must be a finite number, not {value}"
                    )

                if key in CHOICES and value not in CHOICES[key]:
                    allowed = " or ".join(f"'{c}'" for c in CHOICES[key])
                    raise ValueError(
                        f"{component}.{key} must be {allowed}, not {value!r}"
                    )

            # components with a specification are checked in detail: unknown
            # settings, wrong types and values outside the allowed range
            spec = get_spec(component)
            if spec is not None:
                problems.extend(spec.problems(values))

        if problems:
            raise ValueError("; ".join(problems))

        return self

    # ------------------------------------------------------------------
    # the way into the existing backend
    # ------------------------------------------------------------------

    def timeindex(self):
        return pd.date_range(
            start=self.time.start, periods=self.time.steps, freq=self.time.resolution
        )

    def to_inputs(self):
        """The four objects the backend functions expect.

        Returns (selected_techs, tech_inputs, input_data, solver_cfg), the same
        as `build_ui()` of the Streamlit app.
        """

        selected_techs = list(self.components)

        tech_inputs = {
            component: dict(values) for component, values in self.settings.items()
        }

        input_data = {"timeindex": self.timeindex()}
        for key, values in self.series.items():
            input_data[key] = [math.nan if v is None else v for v in values]

        solver_cfg = SolverConfig(name=self.solver.name, tee=self.solver.tee)

        return selected_techs, tech_inputs, input_data, solver_cfg

    @classmethod
    def from_inputs(
        cls, selected_techs, tech_inputs, input_data, solver_cfg=None,
        name="Unnamed scenario",
    ):
        """Build a scenario from the four objects the backend works with."""

        index = input_data.get("timeindex")
        if index is None or len(index) == 0:
            raise ValueError("the input data has no time index")

        index = pd.DatetimeIndex(index)
        if len(index) > 1 and (index[1] - index[0]) != pd.Timedelta(hours=1):
            raise ValueError("only hourly time steps are supported")

        series = {
            key: [_plain(v) for v in values]
            for key, values in input_data.items()
            if key != "timeindex" and values is not None
        }
        settings = {
            component: {key: _plain(v) for key, v in values.items()}
            for component, values in (tech_inputs or {}).items()
        }

        solver = {}
        if solver_cfg is not None:
            solver = {"name": solver_cfg.name, "tee": solver_cfg.tee}

        return cls(
            name=name,
            components=list(selected_techs),
            settings=settings,
            time={"start": index[0].to_pydatetime(), "steps": len(index)},
            series=series,
            solver=solver,
        )

    # ------------------------------------------------------------------
    # saving and loading
    # ------------------------------------------------------------------

    def save(self, path):
        Path(path).write_text(self.model_dump_json(), encoding="utf-8")

    @classmethod
    def load(cls, path):
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _plain(value):
    """numpy numbers and similar become plain Python values."""

    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (ValueError, TypeError):
            return value
    return value