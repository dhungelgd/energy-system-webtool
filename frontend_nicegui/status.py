"""The status of the scenario that is being built, as the top bar shows it, and what the Run button may do.

One short state that says what the visitor can do next: choose components, fix errors, run, or look at a result that
is out of date. No NiceGUI code in here, so it is easy to test; the words take a translator `tr`.
"""

from dataclasses import dataclass

# the words of the states that need no number (the others are made in status_text)
TEXTS = {"empty": "status.empty", "outdated": "status.outdated", "ready": "status.ready"}

# what the chip looks like for each state: its colour (a Quasar colour) and its icon
COLORS = {
    "empty": "grey-7",
    "running": "primary",
    "errors": "negative",
    "outdated": "warning",
    "warnings": "warning",
    "ready": "positive",
}
ICONS = {
    "empty": "add_circle_outline",
    "running": "hourglass_top",
    "errors": "error",
    "outdated": "update",
    "warnings": "warning",
    "ready": "check_circle",
}


@dataclass(frozen=True)
class Status:
    """kind: 'empty', 'running', 'errors', 'outdated', 'warnings' or 'ready'; and what the check found."""

    kind: str
    errors: int = 0
    warnings: int = 0

    @property
    def can_run(self):
        """The draft may be run: it has components, the check finds no error, and nothing else is running."""

        return self.kind in ("ready", "warnings", "outdated")


def draft_status(has_components, errors, warnings, running, outdated):
    """The status from what is known: components chosen, the findings of the check, a run going on, a result that
    is out of date. A run that is going on comes first, then what is missing, then errors, then the rest."""

    if running:
        kind = "running"
    elif not has_components:
        kind = "empty"
    elif errors:
        kind = "errors"
    elif outdated:
        kind = "outdated"
    elif warnings:
        kind = "warnings"
    else:
        kind = "ready"

    return Status(kind, errors, warnings)


def status_text(status, tr, elapsed="0:00"):
    """The words of the chip: 'Ready', '2 errors, 1 warning', 'Result outdated', 'Running 1:12' ..."""

    if status.kind == "running":
        return tr("status.running", time=elapsed)

    if status.kind == "errors":
        text = tr.plural("status.errors", status.errors)
        if status.warnings:
            text += ", " + tr.plural("status.warnings", status.warnings)
        return text

    if status.kind == "warnings":
        return tr.plural("status.warnings", status.warnings)

    return tr(TEXTS[status.kind])


def run_hint(status, tr):
    """Why the Run button cannot be pressed now (empty when it can)."""

    if status.can_run:
        return ""

    return tr({"empty": "status.choose_first", "running": "status.wait"}.get(status.kind, "status.fix_first"))


def badge_of(status):
    """What the badge on the tab of the check shows: (the number, a Quasar colour). The number is 0 for no badge."""

    count = status.errors + status.warnings

    return (count, "negative" if status.errors else "warning") if count else (0, "grey")