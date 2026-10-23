"""What the NiceGUI pages show about a scenario.

No NiceGUI code in here, only the decisions about what to show and how to word
it, so that it is easy to test.
"""

import json

from pydantic import ValidationError

from backend.scenario import Scenario
from frontend.ui_registry import UI_REGISTRY


class ScenarioFileError(ValueError):
    """The file cannot be opened as a scenario. The message is for the user."""


def component_labels():
    """Readable names of the components, e.g. {"pv": "PV System"}."""

    return {key: spec["label"] for key, spec in UI_REGISTRY.items()}


def load_scenario(content):
    """Read the bytes of a scenario file. Raises ScenarioFileError with a clear text."""

    try:
        return Scenario.model_validate_json(content)

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

        where = ".".join(str(part) for part in first["loc"]) or "file"
        raise ScenarioFileError(
            "This file is not a scenario saved by this tool, or it is damaged "
            f"({where}: {first['msg']})."
        ) from error


def _looks_like_a_result(content):
    try:
        data = json.loads(content)
    except ValueError:
        return False

    return isinstance(data, dict) and "objective" in data and "buses" in data


def describe_period(scenario):
    """For example: '168 hourly steps (7 days) from 01.06.2021 00:00'."""

    time = scenario.time
    days = f"{time.steps / 24:g}"

    return f"{time.steps} hourly steps ({days} days) from {time.start:%d.%m.%Y %H:%M}"


def _size_text(mode, settings):
    if mode == "fixed":
        capacity = settings.get("capacity")
        return f"{capacity:g}" if capacity else "not set"

    if mode == "invest":
        maximum = settings.get("maximum")
        return f"up to {maximum:g}" if maximum else "no upper limit"

    return "-"


def component_rows(scenario):
    """One row per component: readable name, mode (fixed or invest), size."""

    labels = component_labels()
    rows = []

    for key in scenario.components:
        settings = scenario.settings.get(key, {})
        mode = settings.get("mode")

        rows.append({
            "component": labels.get(key, key),
            "mode": mode or "-",
            "size": _size_text(mode, settings),
        })

    return rows


def _number(value):
    return "-" if value is None else f"{value:.4g}"


def series_rows(scenario):
    """One row per time series: how many values, how many empty, smallest, largest."""

    rows = []

    for key, values in scenario.series.items():
        numbers = [value for value in values if value is not None]

        rows.append({
            "series": key,
            "values": len(values),
            "empty": len(values) - len(numbers),
            "min": _number(min(numbers)) if numbers else "-",
            "max": _number(max(numbers)) if numbers else "-",
        })

    return rows