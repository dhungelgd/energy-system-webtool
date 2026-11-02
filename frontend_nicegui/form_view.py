"""Draw the forms of the components with NiceGUI.

What a form shows, and what an input does, is decided in forms.py (no NiceGUI there);
this file only turns it into input fields.

- A number is an input field with its unit behind it. An input that does not fit (the range,
  or the other settings of the component) is explained at the field, with the sentence for
  exactly that, and is not stored.
- A choice is a set of radio buttons. A choice can change which other settings are shown,
  so the form is drawn again after it; a number does not draw it again (the cursor stays).
- The help text of a setting is written under it.
"""

from nicegui import ui

from frontend_nicegui.forms import form_blocks, form_fields, problem, sections, set_value
from frontend_nicegui.names import display_name

TYPING_DELAY_MS = 300           # wait until the typing pauses, so that "24" does not check "2" first


def field_marker(component, field):
    """The marker that the tests use to find an input, e.g. 'field-pv-capacity-mode'."""

    return f"field-{component.id}-{field.block}-{field.key}"


def render_component_form(component, tr, on_change):
    """A card with the settings of one component. `on_change` is called after every stored input."""

    def explain(item, value):
        """The sentence for an input that cannot be taken over, or None if it can."""

        found = problem(item.block, item.key, value, component)

        return tr.message(found) if found is not None else None

    def edited(item, event):
        if set_value(component, item.block, item.key, event.value) is None:
            on_change()

    def picked(item, event):
        set_value(component, item.block, item.key, event.value)
        fields.refresh()                # other settings may appear or disappear
        on_change()

    def draw_field(item):
        marker = field_marker(component, item)

        with ui.column().classes("w-full gap-0"):
            if item.kind == "choice":
                ui.label(item.label).classes("font-medium")
                ui.radio(
                    item.options, value=item.value, on_change=lambda event, i=item: picked(i, event),
                ).mark(marker)
            else:
                ui.number(
                    item.label, value=item.value, min=item.minimum, max=item.maximum, step=item.step,
                    suffix=item.unit or None,
                    on_change=lambda event, i=item: edited(i, event),
                    validation=lambda value, i=item: explain(i, value),
                ).props(f"outlined dense debounce={TYPING_DELAY_MS}").classes("w-full").mark(marker)

            if item.help:
                ui.label(item.help).classes("text-grey text-xs")

    with ui.card().classes("w-full").mark(f"form-{component.id}"):
        ui.label(tr("form.heading", name=display_name(component, tr))).classes("text-xl font-semibold")

        @ui.refreshable
        def fields():
            for block_name in form_blocks(component):
                for name, title, group in sections(form_fields(component, block_name, tr), tr):
                    if name == "advanced":
                        with ui.expansion(title).classes("w-full"):
                            for item in group:
                                draw_field(item)
                        continue

                    if title:
                        ui.label(title).classes("font-semibold mt-2")
                    for item in group:
                        draw_field(item)

        fields()