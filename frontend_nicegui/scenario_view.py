"""What the NiceGUI pages show about a scenario (layout 2).

No NiceGUI code in here, only the decisions about what to show and how to word
it, so that it is easy to test. What is shown in words takes a translator `tr`
(English if none is given).
"""

import json

from pydantic import ValidationError

from backend.blocks import series_references
from backend.component_specs import INFO
from backend.i18n import ENGLISH, Msg
from backend.scenario_v2 import SCHEMA_VERSION, ScenarioV2
from frontend_nicegui.names import component_label, display_name


class ScenarioFileError(ValueError):
    """The file cannot be opened as a scenario.

    `msg` is the message for the reader (a key and parameters, to be worded in the
    language of the page); the text of the exception is its English wording.
    """

    def __init__(self, key, **params):
        self.msg = Msg(key, **params)
        super().__init__(ENGLISH.message(self.msg))


def load_scenario(content):
    """Read the bytes of a scenario file. Raises ScenarioFileError with a clear message."""

    try:
        return ScenarioV2.model_validate_json(content)

    except ValidationError as error:
        first = error.errors()[0]

        if first["type"] == "json_invalid":
            raise ScenarioFileError("file_error.json") from error

        if _looks_like_a_result(content):
            raise ScenarioFileError("file_error.result") from error

        problem = _version_problem(content)
        if problem:
            raise ScenarioFileError(problem) from error

        where = ".".join(str(part) for part in first["loc"]) or "file"
        message = first["msg"].removeprefix("Value error, ")
        raise ScenarioFileError("file_error.damaged", where=where, message=message) from error


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
    """The key of the message if the file was saved in an older or newer format, else None."""

    data = _data(content)
    version = data.get("schema_version") if data else None

    if not isinstance(version, int):
        return None
    if version > SCHEMA_VERSION:
        return "file_error.newer"
    if version < SCHEMA_VERSION:
        return "file_error.old"
    return None


def describe_period(scenario, tr=ENGLISH):
    """For example: '168 hourly steps (7 days) from 01.06.2021 00:00'."""

    time = scenario.time
    days = time.steps / 24

    return tr(
        "period.description",
        steps=tr.plural("period.steps", time.steps, steps=time.steps),
        days=tr.plural("period.days", days, days=tr.number(days, significant=3)),
        start=f"{time.start:%d.%m.%Y %H:%M}",
    )


def _size_text(tr, kind, mode, capacity):
    unit = "kWh" if kind == "storage" else "kW"

    if mode == "fixed":
        size = capacity.get("capacity")
        return f"{tr.number(size)} {unit}" if size else tr("row.size.not_set")

    if mode == "invest":
        maximum = capacity.get("maximum")
        if maximum:
            return tr("row.size.up_to", size=tr.number(maximum), unit=unit)
        return tr("row.size.no_limit")

    return "-"


def component_rows(scenario, tr=ENGLISH):
    """One row per component: its name, what it is, mode (fixed or invest), size."""

    rows = []

    for component in scenario.components:
        capacity = component.blocks.get("capacity")
        mode = (capacity.get("mode") or "fixed") if capacity is not None else None

        rows.append({
            "component": display_name(component, tr),
            "type": component_label(tr, component.template) if component.template in INFO else tr("row.custom"),
            "mode": tr(f"row.mode.{mode}") if mode else "-",
            "size": _size_text(tr, component.kind, mode, capacity or {}),
        })

    return rows


def series_rows(scenario, tr=ENGLISH):
    """One row per time series: its unit, who uses it, how many values, how many empty, smallest, largest."""

    def number(value):
        return tr.number(value, significant=4)

    users = {}
    for component in scenario.components:
        for block, values in component.blocks.items():
            for series_id in series_references(block, values):
                users.setdefault(series_id, []).append(display_name(component, tr))

    rows = []

    for series_id, data in scenario.series.items():
        numbers = [value for value in data.values if value is not None]

        rows.append({
            "series": series_id,
            "unit": data.unit or "-",
            "used_by": ", ".join(users.get(series_id, [])) or tr("row.used_by.nothing"),
            "values": len(data.values),
            "empty": len(data.values) - len(numbers),
            "min": number(min(numbers)) if numbers else "-",
            "max": number(max(numbers)) if numbers else "-",
        })

    return rows