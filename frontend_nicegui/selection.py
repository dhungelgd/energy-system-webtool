"""Which components a user has chosen for an energy system.

No NiceGUI code in here, so it is easy to test. It follows the Streamlit
interface: the components are ordered by group (Demand, Grid & fuel, ...) and,
inside a group, in the order of the registry. The same choice therefore gives
the same list of components in both interfaces.
"""

import re

from frontend.ui_registry import GROUP_ORDER, UI_REGISTRY
from frontend.ui_templates import TEMPLATES


def components_by_group():
    """{group: [component keys]} in the order the groups are shown."""

    groups = {name: [] for name in GROUP_ORDER}

    for key, spec in UI_REGISTRY.items():
        groups.setdefault(spec.get("group", "Other"), []).append(key)

    return {name: keys for name, keys in groups.items() if keys}


def template_names():
    return list(TEMPLATES)


def slug(text):
    """A name that can be used as a marker: 'PV + battery' -> 'pv-battery'."""

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class ComponentSelection:
    """The chosen components. Unknown components are refused."""

    def __init__(self, components=()):
        self._chosen = set()

        for key in components:
            self.set(key, True)

    def set(self, key, chosen=True):
        if key not in UI_REGISTRY:
            raise KeyError(f"unknown component '{key}'")

        if chosen:
            self._chosen.add(key)
        else:
            self._chosen.discard(key)

    def is_selected(self, key):
        return key in self._chosen

    def __len__(self):
        return len(self._chosen)

    def components(self):
        """The chosen component keys, ordered by group (as the model expects them)."""

        return [
            key
            for keys in components_by_group().values()
            for key in keys
            if key in self._chosen
        ]

    def selected_by_group(self):
        """[(group, [(key, readable name)])] for the groups with a chosen component."""

        result = []

        for group, keys in components_by_group().items():
            chosen = [(key, UI_REGISTRY[key]["label"]) for key in keys if key in self._chosen]
            if chosen:
                result.append((group, chosen))

        return result

    def apply_template(self, name):
        """Choose exactly the components of a template."""

        if name not in TEMPLATES:
            raise KeyError(f"unknown template '{name}'")

        self._chosen = set(TEMPLATES[name])

    def clear(self):
        self._chosen = set()