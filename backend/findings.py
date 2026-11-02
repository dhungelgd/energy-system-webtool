"""Findings of the checks: what is wrong or doubtful, as a code plus parameters.

A finding says WHAT is the matter, not in finished words: a code ("no_demand") and
parameters (which component, how many values). Each interface words it in the language
of its reader with `finding_text`; the sentences are in the catalogs (backend/i18n)
under "check.<code>".

The English wording is also kept in `message`, for places that do not translate: the
Streamlit interface and the text of an error. It is made from the English catalog, so
there is one source for it.

Parameters:
  ComponentRef(key)   a component by its key; worded as its name in the language of the reader
  SettingRef(...)     a setting of a component; worded as its label in the form (with words of its own)
  Fixed(value, n)     a number with n decimals (0.900 or 0,900)
  a list              joined with "and" / "und"
  a float             written with a decimal point or comma
  n                   (reserved) selects the singular or plural text, "check.<code>.one" / ".other"

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from dataclasses import dataclass, field

from backend.component_specs import INFO
from backend.i18n import ENGLISH


@dataclass
class Finding:
    """One result of a check."""

    level: str            # "error" blocks the run, "warning" does not
    message: str          # the English wording
    fixes: tuple = ()     # each fix is a tuple of component keys that would solve it
    code: str = None      # what is the matter; None for a finding that only has its message
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentRef:
    """A component, named by its key (e.g. "pv")."""

    key: str

    def render(self, tr, names=None):
        if names is not None:
            return names.get(self.key, self.key)
        return tr(f"component.{self.key}.label")


@dataclass(frozen=True)
class SettingRef:
    """A setting of a component: its block, its key (or path) and the template it belongs to."""

    block: str
    key: str
    template: str = None

    def render(self, tr, names=None):
        return tr.own(f"field.{self.block}.{self.key}.label", self.template)


@dataclass(frozen=True)
class Fixed:
    """A number written with a fixed number of decimals."""

    value: float
    decimals: int

    def render(self, tr, names=None):
        return tr.localize(f"{self.value:.{self.decimals}f}")


def reference(component):
    """A component of a scenario, as a message should name it.

    A component that still has the standard name of its template is a ComponentRef, so
    that its name follows the language. A component with a name of its own keeps it.
    """

    info = INFO.get(component.template)

    if info is not None and component.name == info.label:
        return ComponentRef(component.template)

    return component.name


def _text(value, tr, names):
    if hasattr(value, "render"):
        return value.render(tr, names)
    if isinstance(value, (list, tuple)):
        return f" {tr('common.and')} ".join(_text(item, tr, names) for item in value)
    if isinstance(value, float):
        return tr.number(value)
    return str(value)


def finding_text(finding, tr, names=None):
    """The sentence for a finding in the language of `tr`.

    names: readable names for the components, by key; if given, they are used instead of
    the names of the catalog (and a key without a name stays as it is).
    """

    if finding.code is None:
        return finding.message

    params = {name: _text(value, tr, names) for name, value in finding.params.items() if name != "n"}
    key = f"check.{finding.code}"

    if "n" in finding.params:
        return tr.plural(key, finding.params["n"], **params)

    return tr(key, **params)


def coded(level, code, names=None, fixes=(), **params):
    """A finding with its code and parameters, and its English wording as the message."""

    finding = Finding(level, "", tuple(fixes), code, params)
    finding.message = finding_text(finding, ENGLISH, names)

    return finding