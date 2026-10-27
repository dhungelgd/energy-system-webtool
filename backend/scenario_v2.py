"""Scenario, version 2: carriers, component instances and blocks.

Version 1 (`backend/scenario.py`) names its components by type: one "pv", one
"grid". Version 2 describes *instances* with their own id, so a scenario can hold
two PV systems, and it describes the energy carriers as data, so a user can add
hydrogen. A component is a kind (source, sink, converter, storage), the carriers
it is connected to, and blocks of settings (see `backend/blocks.py`).

    {"id": "pv_east", "name": "PV east roof", "template": "pv", "kind": "source",
     "connections": [{"carrier": "electricity", "direction": "out"}],
     "blocks": {"capacity": {...}, "profile": {"series": "pv_east_profile"}}}

What is checked when a scenario is created (structure, not completeness):

- ids are well formed and unique, carriers and time series exist,
- the connections fit the kind (a source only gives energy out, and so on),
- only blocks that the kind may have, with settings inside their ranges.

A form that is not filled in yet is not wrong, so empty values are accepted; the
system check reports what is still missing.

All percentages are stored as percentages (an efficiency of 95 means 95 %).

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

import math
import re
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.blocks import (
    BLOCKS,
    Kind,
    conversion_problems,
    series_references,
)
from backend.scenario import SolverSettings, TimeSettings

# the layout of a saved scenario; increase it when the layout changes
SCHEMA_VERSION = 2

# lower case letters, digits and underscores; starts with a letter
ID_PATTERN = r"^[a-z][a-z0-9_]{0,39}$"

# carriers the tool knows; others are defined by the user
BUILT_IN_CARRIERS = ("electricity", "heat", "gas")


class Carrier(BaseModel):
    """An energy carrier: electricity, heat, gas, or one the user defines."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=60)
    custom: bool = False


class Connection(BaseModel):
    """Where a component is connected: a carrier and a direction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    carrier: str = Field(pattern=ID_PATTERN)
    direction: Literal["in", "out", "both"]


class Component(BaseModel):
    """One instance of a component in the energy system."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    template: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    kind: Kind
    connections: list[Connection] = Field(min_length=1)
    blocks: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, name):
        name = name.strip()
        if not name:
            raise ValueError("the name must not be empty")
        return name


class SeriesSource(BaseModel):
    """Where a time series came from (for the record, not used in the calculation)."""

    model_config = ConfigDict(extra="forbid")

    file: Optional[str] = None
    column: Optional[str] = None


class SeriesData(BaseModel):
    """A time series: its unit, where it came from, and the values."""

    model_config = ConfigDict(extra="forbid")

    unit: str = ""
    source: Optional[SeriesSource] = None
    values: list[Union[float, None]]

    @field_validator("values")
    @classmethod
    def _clean_values(cls, values):
        cleaned = []

        for value in values:
            if value is None or (isinstance(value, float) and math.isnan(value)):
                cleaned.append(None)                # empty value, stays visible
            elif math.isinf(value):
                raise ValueError("a time series contains an infinite value")
            else:
                cleaned.append(float(value))

        return cleaned


def _not_finite(value):
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_not_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_not_finite(v) for v in value)
    return False


def _connection_problems(component):
    found = []
    pairs = [(c.carrier, c.direction) for c in component.connections]
    directions = [c.direction for c in component.connections]
    name = component.id

    if len(set(pairs)) != len(pairs):
        found.append(f"{name}: a carrier is connected twice in the same direction")

    if component.kind == "source" and set(directions) != {"out"}:
        found.append(f"{name}: a source only gives energy out")
    if component.kind == "sink" and set(directions) != {"in"}:
        found.append(f"{name}: a sink only takes energy in")
    if component.kind == "storage" and directions != ["both"]:
        found.append(f"{name}: a storage has exactly one connection, in both directions")
    if component.kind == "converter" and not (
        directions.count("in") == 1 and "out" in directions and "both" not in directions
    ):
        found.append(
            f"{name}: a converter takes energy from exactly one carrier and gives it to at least one"
        )

    return found


class ScenarioV2(BaseModel):
    """Everything needed to check and run one energy system (version 2)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: int = SCHEMA_VERSION
    name: str = Field(default="Unnamed scenario", min_length=1, max_length=200)

    time: TimeSettings = Field(default_factory=TimeSettings)
    carriers: list[Carrier] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    series: dict[str, SeriesData] = Field(default_factory=dict)
    constraints: list[dict[str, Any]] = Field(default_factory=list)

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
        if version < SCHEMA_VERSION:
            raise ValueError(
                f"this is a layout {version} scenario; it has to be converted to "
                f"layout {SCHEMA_VERSION} first"
            )
        return version

    @field_validator("name")
    @classmethod
    def _clean_name(cls, name):
        name = name.strip()
        if not name:
            raise ValueError("the name must not be empty")
        return name

    @field_validator("series")
    @classmethod
    def _series_ids(cls, series):
        bad = [key for key in series if not re.match(ID_PATTERN, key)]
        if bad:
            raise ValueError(
                f"time series ids must be lower case letters, digits and underscores: {', '.join(bad)}"
            )
        return series

    @model_validator(mode="after")
    def _consistent(self):
        problems = []

        carrier_ids = [c.id for c in self.carriers]
        for duplicate in sorted({i for i in carrier_ids if carrier_ids.count(i) > 1}):
            problems.append(f"carrier '{duplicate}' is listed twice")
        for carrier in self.carriers:
            if carrier.custom and carrier.id in BUILT_IN_CARRIERS:
                problems.append(f"carrier '{carrier.id}' is built in and cannot be marked as custom")
            if not carrier.custom and carrier.id not in BUILT_IN_CARRIERS:
                problems.append(f"carrier '{carrier.id}' is not built in; mark it as custom")

        component_ids = [c.id for c in self.components]
        for duplicate in sorted({i for i in component_ids if component_ids.count(i) > 1}):
            problems.append(f"component id '{duplicate}' is used twice")

        for component in self.components:
            problems.extend(self._component_problems(component, set(carrier_ids)))

        if self.constraints:
            problems.append("constraints are not available yet")

        if problems:
            raise ValueError("; ".join(problems))

        return self

    def _component_problems(self, component, carrier_ids):
        found = []
        name = component.id

        for connection in component.connections:
            if connection.carrier not in carrier_ids:
                found.append(f"{name}: the carrier '{connection.carrier}' is not defined")

        found.extend(_connection_problems(component))

        output_carriers = {c.carrier for c in component.connections if c.direction == "out"}
        all_carriers = {c.carrier for c in component.connections}

        for block_name, values in component.blocks.items():
            spec = BLOCKS.get(block_name)

            if spec is None:
                found.append(f"{name}: unknown block '{block_name}'")
                continue
            if component.kind not in spec.kinds:
                found.append(f"{name}: a {component.kind} cannot have the block '{block_name}'")
                continue
            if _not_finite(values):
                found.append(f"{name}: {spec.label} contains a value that is not a finite number")
                continue

            found.extend(spec.problems(values, name))

            if block_name == "capacity" and values.get("rated_flow") is not None:
                rated = values["rated_flow"]
                if component.kind != "converter":
                    found.append(f"{name}: only a converter has a rated flow")
                elif rated not in all_carriers:
                    found.append(f"{name}: the rated flow '{rated}' is not one of its connections")

            if block_name == "conversion":
                found.extend(conversion_problems(values, output_carriers, name))

            for series_id in series_references(block_name, values):
                if series_id not in self.series:
                    found.append(f"{name}: the time series '{series_id}' does not exist")

        return found

    # ------------------------------------------------------------------
    # looking things up
    # ------------------------------------------------------------------

    def carrier_ids(self):
        return [c.id for c in self.carriers]

    def component_ids(self):
        return [c.id for c in self.components]

    def component(self, component_id):
        for component in self.components:
            if component.id == component_id:
                return component
        raise KeyError(f"unknown component '{component_id}'")

    # ------------------------------------------------------------------
    # saving and loading
    # ------------------------------------------------------------------

    def save(self, path):
        Path(path).write_text(self.model_dump_json(), encoding="utf-8")

    @classmethod
    def load(cls, path):
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))