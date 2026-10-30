"""The forms of the components: what they show and what an input does.

No NiceGUI code in here, so it is easy to test. The block catalog (`backend/blocks.py`)
knows each setting: its kind (number or choice), unit, range, step, section and when it
is shown (`visible_if`). The texts are in the catalogs of backend/i18n, under
"field.<block>.<setting>.<label|help|unit|option.<value>>".

A form is made from the blocks of a component. Which components have a form, and for
which blocks, is `FORMS`.

An input is stored in the component (`set_value`), or refused with a message for the
reader; what is refused is never stored, so that a scenario made from the draft is
always valid. An empty number is stored as "not filled in" (the key is removed): that
is not wrong, the system check says what is still missing.
"""

import math
from dataclasses import dataclass, field

from backend.blocks import BLOCKS
from backend.i18n import ENGLISH, Msg

# component template -> the blocks that have a form (more follow with the other components)
FORMS = {"pv": ("capacity",)}

SECTIONS = ("basic", "investment", "advanced")


def has_form(component):
    return component.template in FORMS


def form_blocks(component):
    return FORMS.get(component.template, ())


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
    hint: object = None                 # a Msg: what to say about a number that does not fit


def range_hint(spec):
    """What to say about a number that does not fit the range of a setting (a Msg)."""

    low, high = spec.minimum, spec.maximum

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
    fields = []

    for spec in block.visible_fields(values):
        base = f"field.{block_name}.{spec.key}"
        value = values.get(spec.key)
        if value is None and spec.kind == "choice":
            value = spec.default                     # a choice that was not made is the default one

        fields.append(FormField(
            block=block_name,
            key=spec.key,
            kind=spec.kind,
            label=tr(f"{base}.label"),
            help=tr(f"{base}.help") if spec.help else "",
            unit=tr(f"{base}.unit") if spec.unit else "",
            value=value,
            minimum=spec.minimum,
            maximum=spec.maximum,
            step=spec.step,
            options={option: tr(f"{base}.option.{option}") for option in spec.options},
            section=spec.section,
            hint=range_hint(spec) if spec.kind == "number" else None,
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


def problem(block_name, key, raw):
    """What is wrong with an input, as a Msg, or None if it can be stored. Nothing is stored here."""

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

    if (spec.minimum is not None and value < spec.minimum) or (spec.maximum is not None and value > spec.maximum):
        return range_hint(spec)
    return None


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

    found = problem(block_name, key, raw)
    if found is not None:
        return found

    spec = spec_of(block_name, key)
    block = component.blocks.setdefault(block_name, {})

    if spec.kind == "choice":
        block[key] = raw
        return None

    value = _number(raw)
    if value is None:
        block.pop(key, None)
    else:
        block[key] = value
    return None