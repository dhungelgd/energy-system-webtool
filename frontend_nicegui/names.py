"""The names of components, groups and templates in the language of the reader.

The English names are the ones in the backend (`component_specs.INFO`, the groups and
templates of `system_templates.py`); the catalogs hold them in every language.
"""

from backend.component_specs import INFO
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


def display_name(component, tr=ENGLISH):
    """The name of a component as shown to the reader.

    A name that nobody changed (it is still the standard name of its template) follows
    the language of the reader. A name that someone chose stays as it is.
    """

    info = INFO.get(component.template)

    if info is not None and component.name == info.label:
        return component_label(tr, component.template)

    return component.name