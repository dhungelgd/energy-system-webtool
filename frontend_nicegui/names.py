"""The names of components, groups and templates in the language of the reader.

The English names are the ones in the backend (`component_specs.INFO`, the groups and
templates of `system_templates.py`); the catalogs hold them in every language.
"""

from backend.findings import ComponentRef, reference
from backend.i18n import ENGLISH
from frontend_nicegui.markers import slug


def component_label(tr, key):
    return tr(f"component.{key}.label")


def component_short(tr, key):
    return tr(f"component.{key}.short")


def group_label(tr, group):
    return tr(f"group.{slug(group)}")


def template_label(tr, name):
    return tr(f"template.{slug(name)}")


def fix_label(tr, keys):
    """The text of a repair button: what it adds, e.g. 'Add CHP plant + Gas import'."""

    return tr("fix.add", names=" + ".join(component_label(tr, key) for key in keys))


def display_name(component, tr=ENGLISH):
    """The name of a component as shown to the reader.

    A name that nobody changed (it is still the standard name of its template) follows
    the language of the reader. A name that someone chose stays as it is.
    """

    name = reference(component)

    return name.render(tr) if isinstance(name, ComponentRef) else name



# the text for each reason that a scenario cannot be taken into the draft (see draft.EDIT_REASONS)
EDIT_PROBLEM_TEXTS = {
    "resolution": "open.edit.problem.resolution",
    "start_time": "open.edit.problem.start_time",
    "period": "open.edit.problem.period",
    "constraints": "open.edit.problem.constraints",
    "carriers": "open.edit.problem.carriers",
    "no_template": "open.edit.problem.no_template",
    "many": "open.edit.problem.many",
    "own_id": "open.edit.problem.own_id",
    "unused_series": "open.edit.problem.unused_series",
}