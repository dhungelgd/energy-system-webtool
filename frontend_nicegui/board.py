"""The board: the components of the system as tiles, in lanes (electricity, heat, gas) and columns (demand and
export first, then supply, conversion, storage), and what a tile says about its component.

No NiceGUI code in here, so it is easy to test. The words take a translator `tr`.
"""

from types import SimpleNamespace

from backend.component_specs import INFO
from backend.findings import ComponentRef, finding_text
from frontend_nicegui.scenario_view import component_rows
from frontend_nicegui.status import Status, status_text

LANES = ("electricity", "heat", "gas")
COLUMNS = ("demand", "supply", "conversion", "storage")

# lane -> column -> the components that can be there (a component belongs to exactly one place)
BOARD = {
    "electricity": {
        "supply": ("grid", "pv", "wind"),
        "conversion": (),
        "storage": ("battery",),
        "demand": ("demand", "grid_feedin"),
    },
    "heat": {
        "supply": (),
        "conversion": ("heat_pump", "heating_rod", "gas_boiler", "chp"),
        "storage": ("heat_storage",),
        "demand": ("heat_demand",),
    },
    "gas": {
        "supply": ("gas_import",),
        "conversion": (),
        "storage": (),
        "demand": (),
    },
}

# the words above the columns
COLUMN_TEXTS = {
    "supply": "board.column.supply",
    "conversion": "board.column.conversion",
    "storage": "board.column.storage",
    "demand": "board.column.demand",
}

# the colour of a lane (the same colours that the charts use for the carriers)
LANE_COLORS = {"electricity": "#C98200", "heat": "#D9482B", "gas": "#7A5CB5"}

# component -> (icon, the colour of the icon, the tint behind it)
STYLE = {
    "grid": ("electrical_services", "#5B6B7B", "#E8EDF2"),
    "grid_feedin": ("output", "#1F6FB2", "#DCEBFA"),
    "gas_import": ("local_fire_department", "#6B4FA3", "#ECE6F7"),
    "pv": ("wb_sunny", "#9A6B00", "#FFF1C9"),
    "wind": ("air", "#1F6FB2", "#DCEBFA"),
    "gas_boiler": ("local_fire_department", "#6B4FA3", "#ECE6F7"),
    "heating_rod": ("thermostat", "#B5391F", "#FDE5DE"),
    "chp": ("bolt", "#6B4FA3", "#ECE6F7"),
    "heat_pump": ("thermostat", "#B5391F", "#FDE5DE"),
    "battery": ("battery_full", "#1E7F55", "#DDF3E8"),
    "heat_storage": ("battery_charging_full", "#1E7F55", "#DDF3E8"),
    "demand": ("home", "#14202B", "#E6E9ED"),
    "heat_demand": ("whatshot", "#14202B", "#E6E9ED"),
}

# findings that name no component in their parameters but are about these tiles
CODE_TILES = {
    "feedin_above_price": ("grid", "grid_feedin"),
    "feedin_above_lowest_price": ("grid", "grid_feedin"),
}


def place_of(key):
    """The (lane, column) of a component on the board."""

    for lane, columns in BOARD.items():
        for column, keys in columns.items():
            if key in keys:
                return lane, column

    raise KeyError(key)


def addable(lane, column, selected):
    """The components that can still be added in this place of the board, in the order of the board."""

    return [key for key in BOARD[lane][column] if key not in selected]


# ---------------------------------------------------------------------------
# what a tile says
# ---------------------------------------------------------------------------

def tile_detail(component, tr):
    """The short line under the name of a tile: its size, its price, its yearly demand."""

    blocks = component.blocks

    if "capacity" in blocks:
        row = component_rows(SimpleNamespace(components=[component]), tr)[0]
        return f"{row['mode']}: {row['size']}"

    demand = blocks.get("demand")
    if demand is not None:
        annual = demand.get("annual_demand")
        if demand.get("profile_type", "annual_share") == "annual_share":
            return tr("board.detail.annual", value=tr.integer(round(annual))) if annual else tr("board.detail.not_set")
        return tr("board.detail.absolute")

    costs = blocks.get("costs", {})
    if "revenue" in costs:
        revenue = costs["revenue"]
        return tr("board.detail.revenue", value=tr.number(revenue)) if revenue is not None else tr("board.detail.not_set")

    if "variable_costs" in costs:
        price = costs["variable_costs"]
        return tr("board.detail.price", value=tr.number(price)) if price is not None else tr("board.detail.not_set")

    return tr("board.detail.price_series")        # a price that comes from a time series


def finding_keys(finding, names):
    """The components that a finding is about. `names` maps the name of a component to its key (for a component
    that has a name of its own, a finding names it by that name)."""

    keys = set(CODE_TILES.get(finding.code, ()))

    for value in finding.params.values():
        for item in value if isinstance(value, (list, tuple)) else [value]:
            if isinstance(item, ComponentRef):
                keys.add(item.key)
            elif isinstance(item, str) and item in names:
                keys.add(names[item])

    return keys


def findings_by_component(findings, components):
    """Component key -> the findings about it (a finding about several components is in each of them)."""

    names = {component.name: component.template for component in components}
    found = {component.template: [] for component in components}

    for finding in findings:
        for key in finding_keys(finding, names):
            if key in found:
                found[key].append(finding)

    return found


def tile_state(findings):
    """'error', 'warning' or 'ok' for the findings about one component."""

    if any(finding.level == "error" for finding in findings):
        return "error"

    return "warning" if findings else "ok"


def tile_problem_text(findings, tr):
    """'1 error, 1 warning' for the findings about one component (empty when there are none)."""

    errors = sum(1 for finding in findings if finding.level == "error")
    warnings = len(findings) - errors

    if errors:
        return status_text(Status("errors", errors, warnings), tr)

    return status_text(Status("warnings", warnings=warnings), tr) if warnings else ""


def problem_texts(findings, tr):
    """The full sentences of the findings about one component, errors first."""

    ordered = sorted(findings, key=lambda finding: finding.level != "error")

    return [(finding.level, finding_text(finding, tr)) for finding in ordered]


def every_component_has_a_place():
    """True if the board holds each component of the registry exactly once (a guard, used by a test)."""

    placed = [key for columns in BOARD.values() for keys in columns.values() for key in keys]

    return sorted(placed) == sorted(INFO) and set(STYLE) == set(INFO)