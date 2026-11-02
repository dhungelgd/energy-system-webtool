"""The forms of the components: what they show and what an input does.

No NiceGUI code in here, so it is easy to test. The block catalog (`backend/blocks.py`)
knows each setting: its kind (number or choice), unit, range, step, section and when it
is shown (`visible_if`). The texts are in the catalogs of backend/i18n, under
"field.<block>.<setting>.<label|help|unit|option.<value>>".

A form is made from the blocks of a component. Which components have a form, for which
blocks and which settings of them, is `FORMS`. A form only shows settings that the engine
reads (a grid has a price, no revenue), and every setting the engine reads is in it; a test
compares the table with what the adapter to the engine consumes.

A component can have words of its own for a setting: the text "field.costs.variable_costs.
label@grid" is used for the grid instead of the general "field.costs.variable_costs.label"
(there it says "Electricity price", not "Variable costs").

The key of a setting can be a path ("outputs.heat.efficiency"): the conversion keeps its
values for each output in a dictionary.

An input is stored in the component (`set_value`), or refused with a message for the
reader; what is refused is never stored, so that a scenario made from the draft is
always valid. That includes what only a few settings together can get wrong (the
efficiencies of a CHP plant cannot add up to more than 100 %). An empty number is stored
as "not filled in" (the key is removed): that is not wrong, the system check says what is
still missing.
"""

import copy
import math
from dataclasses import dataclass, field

from backend.blocks import BLOCKS, conversion_problems, get_path, put_path
from backend.i18n import ENGLISH, Msg

# component template -> {block: the settings of it that the form shows (None: all of them)}
# The settings of how a component works come first and its size after them, because the
# size has a section of its own (Investment) that would otherwise sit between them.
STORAGE = ("c_rate", "efficiency_charge", "efficiency_discharge", "loss_rate")      # not initial_level: the engine ignores it

FORMS = {
    "pv": {"capacity": None},
    "wind": {"capacity": None},
    "demand": {"demand": None},
    "heat_demand": {"demand": None},
    "grid": {"costs": ("variable_costs",)},
    "grid_feedin": {"costs": ("revenue",)},
    "gas_import": {"costs": ("variable_costs",)},
    "gas_boiler": {"conversion": ("outputs.heat.efficiency",), "capacity": None},
    "heating_rod": {"conversion": ("outputs.heat.efficiency",), "capacity": None},
    "chp": {"conversion": ("outputs.electricity.efficiency", "outputs.heat.efficiency"), "capacity": None},
    "heat_pump": {"conversion": ("outputs.heat.ratio",), "capacity": None},        # a COP series comes with the upload
    "battery": {"storage": STORAGE, "capacity": None},
    "heat_storage": {"storage": STORAGE, "capacity": None},
}

SECTIONS = ("basic", "investment", "advanced")


def has_form(component):
    return component.template in FORMS


def form_blocks(component):
    return tuple(FORMS.get(component.template, {}))


def _text(tr, base, part, template):
    """A text of a setting: the one of the component if it has one of its own, else the general one."""

    return tr.own(f"{base}.{part}", template)


def spec_of(block_name, key):
    """The specification of one setting of a block. KeyError if the block has no such setting."""

    for spec in BLOCKS[block_name].fields:
        if spec.key == key:
            return spec

    raise KeyError(f"the block '{block_name}' has no setting '{key}'")


@dataclass
class FormField:
    """One input of a form, ready to be drawn: its texts are in the language of the reader."""

    block: str
    key: str
    kind: str                           # "number" or "choice"
    label: str
    help: str
    unit: str                           # "" if there is none
    value: object                       # what is stored now: a number, a choice or None
    minimum: object = None
    maximum: object = None
    step: object = None
    options: dict = field(default_factory=dict)      # choice: {value: label}
    section: str = "basic"


def range_hint(spec):
    """What to say about a number that does not fit the range of a setting (a Msg)."""

    low, high = spec.minimum, spec.maximum

    if low is not None and spec.minimum_exclusive:
        if high is not None:
            return Msg("form.hint.above_range", min=float(low), max=float(high))
        return Msg("form.hint.above", min=float(low))
    if low is not None and high is not None:
        return Msg("form.hint.range", min=float(low), max=float(high))
    if low is not None:
        return Msg("form.hint.min", min=float(low))
    if high is not None:
        return Msg("form.hint.max", max=float(high))
    return Msg("form.hint.number")


def form_fields(component, block_name, tr=ENGLISH):
    """The inputs of a block that are shown now, in the order of the specification."""

    block = BLOCKS[block_name]
    values = component.blocks.get(block_name, {})
    shown = FORMS.get(component.template, {}).get(block_name)         # None: all settings of the block
    template = component.template
    fields = []

    for spec in block.visible_fields(values):
        if shown is not None and spec.key not in shown:
            continue

        base = f"field.{block_name}.{spec.key}"
        value = get_path(values, spec.key)
        if value is None and spec.kind == "choice":
            value = spec.default                     # a choice that was not made is the default one

        fields.append(FormField(
            block=block_name,
            key=spec.key,
            kind=spec.kind,
            label=_text(tr, base, "label", template),
            help=_text(tr, base, "help", template) if spec.help else "",
            unit=_text(tr, base, "unit", template) if spec.unit else "",
            value=value,
            minimum=spec.minimum,
            maximum=spec.maximum,
            step=spec.step,
            options={option: _text(tr, base, f"option.{option}", template) for option in spec.options},
            section=spec.section,
        ))

    return fields


def sections(fields, tr=ENGLISH):
    """The inputs grouped for drawing: [(section, title, [fields])]. The basic section has no title."""

    titles = {"basic": None, "investment": tr("form.section.investment"), "advanced": tr("form.section.advanced")}

    return [
        (name, titles[name], [f for f in fields if f.section == name])
        for name in SECTIONS
        if any(f.section == name for f in fields)
    ]


def _block_problem(component, block_name, key, value):
    """What an input gets wrong together with the other settings of its component (a Msg), or None."""

    if component is None or block_name != "conversion":
        return None

    candidate = copy.deepcopy(component.blocks.get(block_name, {}))
    put_path(candidate, key, value)
    carriers = {c.carrier for c in component.connections if c.direction == "out"}

    if not conversion_problems(candidate, carriers, component.id):
        return None

    efficiencies = [
        entry["efficiency"] for entry in candidate.get("outputs", {}).values()
        if isinstance(entry, dict) and isinstance(entry.get("efficiency"), (int, float))
    ]
    return Msg("form.hint.efficiency_sum") if sum(efficiencies) > 100 + 1e-9 else Msg("form.hint.invalid")


def problem(block_name, key, raw, component=None):
    """What is wrong with an input, as a Msg, or None if it can be stored. Nothing is stored here.

    With the component, it is also checked against its other settings."""

    spec = spec_of(block_name, key)

    if spec.kind == "choice":
        if raw not in spec.options:
            raise ValueError(f"'{raw}' is not one of the options of '{key}'")
        return None

    value = _number(raw)
    if value is _WRONG:
        return Msg("form.hint.number")
    if value is None:
        return None                                   # empty: not filled in yet

    too_low = spec.minimum is not None and (value <= spec.minimum if spec.minimum_exclusive else value < spec.minimum)
    if too_low or (spec.maximum is not None and value > spec.maximum):
        return range_hint(spec)

    return _block_problem(component, block_name, key, value)


_WRONG = object()


def _number(raw):
    """A float, None for empty, or _WRONG."""

    if raw is None:
        return None
    if isinstance(raw, bool):
        return _WRONG
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None

    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _WRONG

    return value if math.isfinite(value) else _WRONG


def set_value(component, block_name, key, raw):
    """Store an input in the component. Returns None, or a Msg that says why it was refused."""

    found = problem(block_name, key, raw, component)
    if found is not None:
        return found

    spec = spec_of(block_name, key)
    block = component.blocks.setdefault(block_name, {})

    put_path(block, key, raw if spec.kind == "choice" else _number(raw))
    return None