import streamlit as st
from frontend.ui_registry import UI_REGISTRY, GROUP_ORDER
from frontend.ui_templates import TEMPLATES


def components_by_group():
    """Component keys grouped as defined by the "group" entry in UI_REGISTRY."""

    groups = {name: [] for name in GROUP_ORDER}

    for key, spec in UI_REGISTRY.items():
        groups.setdefault(spec.get("group", "Other"), []).append(key)

    return {name: keys for name, keys in groups.items() if keys}


def _state_key(group):
    return f"sel_{group}"


def set_selection(components):
    """Select exactly these components (used by the template buttons)."""

    for group, keys in components_by_group().items():
        st.session_state[_state_key(group)] = [k for k in keys if k in components]


def add_components(components):
    """Add components to the current selection (used by the fix buttons)."""

    for group, keys in components_by_group().items():

        current = list(st.session_state.get(_state_key(group), []))

        for key in keys:
            if key in components and key not in current:
                current.append(key)

        st.session_state[_state_key(group)] = current


# component selector
def select_components():

    st.sidebar.header("System Components")

    groups = components_by_group()
    has_selection = any(st.session_state.get(_state_key(g)) for g in groups)

    # templates: the buttons run their callback before the page is redrawn
    with st.sidebar.expander("Start from a template", expanded=not has_selection):

        for name, components in TEMPLATES.items():
            st.button(
                name,
                key=f"template_{name}",
                on_click=set_selection,
                args=(components,),
                width="stretch"
            )

        st.button(
            "Clear selection",
            key="template_clear",
            on_click=set_selection,
            args=([],),
            width="stretch"
        )

    # one multi-select per group, shown with readable labels
    selected = []

    for group, keys in groups.items():

        chosen = st.sidebar.pills(
            group,
            options=keys,
            selection_mode="multi",
            format_func=lambda key: UI_REGISTRY[key]["label"],
            key=_state_key(group)
        )

        selected.extend(chosen or [])

    return selected