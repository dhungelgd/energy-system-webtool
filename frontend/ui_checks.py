import streamlit as st
from frontend.ui_registry import UI_REGISTRY
from frontend.ui_selection import add_components


def component_labels():
    """Readable names of all components, e.g. {"pv": "PV System"}."""

    return {key: spec["label"] for key, spec in UI_REGISTRY.items()}


def render_findings(findings):
    """Show the result of backend.system_check.check_system.

    Every finding that has a possible fix gets a button which adds the
    missing components to the selection.
    """

    labels = component_labels()

    for i, finding in enumerate(findings):

        if finding.level == "error":
            st.error(finding.message)
        else:
            st.warning(finding.message)

        for j, fix in enumerate(finding.fixes):
            st.button(
                "Add " + " + ".join(labels[key] for key in fix),
                key=f"fix_{i}_{j}",
                on_click=add_components,
                args=(fix,)
            )