"""What the NiceGUI pages show about a scenario (layout 2).

No NiceGUI code in here, only the decisions about what to show and how to word
it, so that it is easy to test.
"""

import json

from pydantic import ValidationError

from backend.blocks import series_references
from backend.component_specs import INFO
from backend.scenario_v2 import SCHEMA_VERSION, ScenarioV2


class ScenarioFileError(ValueError):
    """The file cannot be opened as a scenario. The message is for the user."""


def load_scenario(content):
    """Read the bytes of a scenario file. Raises ScenarioFileError with a clear text."""

    try:
        return ScenarioV2.model_validate_json(content)

    except ValidationError as error:
        first = error.errors()[0]

        if first["type"] == "json_invalid":
            raise ScenarioFileError(
                "This file is not valid JSON. Choose a scenario file saved by this tool."
            ) from error

        if _looks_like_a_result(content):
            raise ScenarioFileError(
                "This looks like a saved result, not a scenario. Results are opened "
                "in the Streamlit interface under 'Open a saved result'."
            ) from error

        problem = _version_problem(content)
        if problem:
            raise ScenarioFileError(problem) from error

        where = ".".join(str(part) for part in first["loc"]) or "file"
        message = first["msg"].removeprefix("Value error, ")
        raise ScenarioFileError(
            "This file is not a scenario saved by this tool, or it is damaged "
            f"({where}: {message})."
        ) from error


def _data(content):
    try:
        data = json.loads(content)
    except ValueError:
        return None

    return data if isinstance(data, dict) else None


def _looks_like_a_result(content):
    data = _data(content)

    return data is not None and "objective" in data and "buses" in data


def _version_problem(content):
    """A sentence if the file was saved in an older or newer format, else None."""

    data = _data(content)
    version = data.get("schema_version") if data else None

    if not isinstance(version, int):
        return None
    if version > SCHEMA_VERSION:
        return (
            "This scenario was saved with a newer version of the tool. "
            "Please update the tool to open it."
        )
    if version < SCHEMA_VERSION:
        return "This scenario file is in an old format that this version cannot open."
    return None


def describe_period(scenario):
    """For example: '168 hourly steps (7 days) from 01.06.2021 00:00'."""

    time = scenario.time
    days = f"{time.steps / 24:g}"

    return f"{time.steps} hourly steps ({days} days) from {time.start:%d.%m.%Y %H:%M}"


def _size_text(kind, mode, capacity):
    unit = "kWh" if kind == "storage" else "kW"

    if mode == "fixed":
        size = capacity.get("capacity")
        return f"{size:g} {unit}" if size else "not set"

    if mode == "invest":
        maximum = capacity.get("maximum")
        return f"up to {maximum:g} {unit}" if maximum else "no upper limit"

    return "-"


def component_rows(scenario):
    """One row per component: its name, what it is, mode (fixed or invest), size."""

    rows = []

    for component in scenario.components:
        capacity = component.blocks.get("capacity")
        mode = (capacity.get("mode") or "fixed") if capacity is not None else None
        info = INFO.get(component.template)

        rows.append({
            "component": component.name,
            "type": info.label if info else "Custom component",
            "mode": mode or "-",
            "size": _size_text(component.kind, mode, capacity or {}),
        })

    return rows


def _number(value):
    return "-" if value is None else f"{value:.4g}"


def series_rows(scenario):
    """One row per time series: its unit, who uses it, how many values, how many empty, smallest, largest."""

    users = {}
    for component in scenario.components:
        for block, values in component.blocks.items():
            for series_id in series_references(block, values):
                users.setdefault(series_id, []).append(component.name)

    rows = []

    for series_id, data in scenario.series.items():
        numbers = [value for value in data.values if value is not None]

        rows.append({
            "series": series_id,
            "unit": data.unit or "-",
            "used_by": ", ".join(users.get(series_id, [])) or "nothing",
            "values": len(data.values),
            "empty": len(data.values) - len(numbers),
            "min": _number(min(numbers)) if numbers else "-",
            "max": _number(max(numbers)) if numbers else "-",
        })

    return rows