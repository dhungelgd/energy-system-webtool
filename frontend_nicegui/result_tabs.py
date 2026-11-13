"""The tabs of a result on the NiceGUI page: one for each energy carrier (electricity, heat, gas), the costs and
the capacities.

What is shown, and in which words, is decided in result_terms.py, result_charts.py and result_charts_year.py (no
NiceGUI there); this file only puts it on the page. The tab of a carrier has a tab inside it for each kind of view:
the flows over time, the monthly balance, the duration curve, the heat map, and who supplies the carrier and who
uses it (two tables) with a Sankey diagram. The system graph of the Streamlit page is not here: it needs the model,
not the result, and the diagram of the system comes later.
"""

from nicegui import ui

from frontend_nicegui.chart_style import as_chart
from frontend_nicegui.ranges import MODE_TEXTS, available_modes, is_long, view_frame, window_count
from frontend_nicegui.result_charts import cost_figure, flows_figure, sankey_figure
from frontend_nicegui.result_charts_year import (
    duration_figure,
    heatmap_choices,
    heatmap_figure,
    heatmap_label,
    monthly_figure,
)
from frontend_nicegui.result_terms import bus_label, table_for_display

SUB_TABS = {                                  # the words on the tabs inside the tab of an energy carrier
    "flows": "result.sub.flows",
    "monthly": "result.sub.monthly",
    "duration": "result.sub.duration",
    "heatmap": "result.sub.heatmap",
    "tables": "result.sub.tables",
}


def _table(table, tr, marker):
    columns, rows = table_for_display(table, tr)
    ui.table(columns=columns, rows=rows).props("dense flat").classes("w-full").mark(marker)


def _flows_with_window(bus, summary, tr, key):
    """The chart of the flows of a carrier. A period of more than a day has buttons for a day, a week, a month and
    the whole period (every value), and a slider that moves the window through the period. Only what is in the
    window is sent to the browser; every value of a year is about half a megabyte for a carrier with ten flows."""

    modes = available_modes(summary.flows)
    view = {"mode": "all", "position": 0}

    def figure():
        return as_chart(flows_figure(bus, summary, tr, view=(view["mode"], view["position"])), f"{bus}-flows")

    def window_text():
        frame, _ = view_frame(summary.flows, view["mode"], view["position"])
        return tr("result.range.window", start=f"{frame.index[0]:%Y-%m-%d}", end=f"{frame.index[-1]:%Y-%m-%d}")

    @ui.refreshable
    def controls():
        refs = {}

        def move(event):
            view["position"] = int(event.value)
            refs["window"].set_text(window_text())
            refs["plot"].update_figure(figure())

        with ui.row().classes("w-full items-center gap-4"):
            ui.toggle(
                {mode: tr(MODE_TEXTS[mode]) for mode in modes}, value=view["mode"], on_change=change_mode,
            ).props("dense no-caps").mark(f"{key}-range-{bus}")
            refs["window"] = ui.label(window_text()).classes("text-grey text-sm").mark(f"{key}-window-{bus}")
            if view["mode"] == "all" and is_long(summary.flows):
                ui.label(tr("result.range.zoom")).classes("text-grey text-sm").mark(f"{key}-zoom-{bus}")

        count = window_count(summary.flows, view["mode"])
        if count > 1:
            ui.slider(min=0, max=count - 1, step=1, value=view["position"], on_change=move).props(
                "label").classes("w-full").mark(f"{key}-slider-{bus}")

        refs["plot"] = ui.plotly(figure()).classes("w-full").mark(f"{key}-flows-{bus}")

    def change_mode(event):
        view["mode"], view["position"] = event.value, 0
        controls.refresh()

    controls()


def _note(text, marker):
    ui.label(text).classes("text-grey").mark(marker)


def _has_no_flows(summary):
    return summary.flows is None or not summary.flows.columns


def _flows_section(bus, summary, tr, key):
    ui.label(tr("result.section.flows")).classes("text-lg font-semibold")
    figure = flows_figure(bus, summary, tr)
    if figure is None:
        _note(tr("result.no_flows"), f"{key}-no-flows-{bus}")
    elif not figure.data:
        _note(tr("result.nothing_flows"), f"{key}-nothing-flows-{bus}")
    elif available_modes(summary.flows):
        _flows_with_window(bus, summary, tr, key)
    else:
        ui.plotly(as_chart(figure, f"{bus}-flows")).classes("w-full").mark(f"{key}-flows-{bus}")


def _monthly_section(bus, summary, tr, key):
    ui.label(tr("result.section.monthly")).classes("text-lg font-semibold")
    ui.label(tr("result.monthly.hint")).classes("text-grey text-sm")
    figure = monthly_figure(bus, summary, tr)
    marker = f"{key}-monthly-note-{bus}"
    if _has_no_flows(summary):
        _note(tr("result.no_flows"), marker)
    elif figure is None:
        _note(tr("result.monthly.none"), marker)
    elif not figure.data:
        _note(tr("result.nothing_flows"), marker)
    else:
        ui.plotly(as_chart(figure, f"{bus}-monthly")).classes("w-full").mark(f"{key}-monthly-{bus}")


def _duration_section(bus, summary, tr, key):
    ui.label(tr("result.section.duration")).classes("text-lg font-semibold")
    ui.label(tr("result.duration.hint")).classes("text-grey text-sm")
    figure = duration_figure(bus, summary, tr)
    marker = f"{key}-duration-note-{bus}"
    if figure is None:
        _note(tr("result.no_flows"), marker)
    elif not figure.data:
        _note(tr("result.nothing_flows"), marker)
    else:
        ui.plotly(as_chart(figure, f"{bus}-duration")).classes("w-full").mark(f"{key}-duration-{bus}")


def _heatmap_section(bus, summary, tr, key):
    """The heat map of the hours of the day against the date; a choice says what it shows (the demand or a supply).
    The chart is changed in place when the choice changes."""

    ui.label(tr("result.section.heatmap")).classes("text-lg font-semibold")
    ui.label(tr("result.heatmap.hint")).classes("text-grey text-sm")
    choices = heatmap_choices(bus, summary)
    marker = f"{key}-heatmap-note-{bus}"

    if _has_no_flows(summary):
        return _note(tr("result.no_flows"), marker)
    if not choices:
        return _note(tr("result.nothing_flows"), marker)

    first = heatmap_figure(bus, summary, choices[0], tr)
    if first is None:
        return _note(tr("result.heatmap.none"), marker)

    def chart(what, figure):
        return as_chart(figure, f"{bus}-heatmap-{what.split('-->')[0]}")

    def change(event):
        plot.update_figure(chart(event.value, heatmap_figure(bus, summary, event.value, tr)))

    ui.select(
        {what: heatmap_label(tr, what) for what in choices}, value=choices[0], label=tr("result.heatmap.pick"),
        on_change=change,
    ).classes("w-64").mark(f"{key}-heatmap-pick-{bus}")
    plot = ui.plotly(chart(choices[0], first)).classes("w-full").mark(f"{key}-heatmap-{bus}")


def _tables_section(bus, summary, tr, key):
    ui.label(tr("result.section.supply_use")).classes("text-lg font-semibold")
    with ui.row().classes("w-full gap-4 no-wrap"):
        for title, table, name in (
            (tr("result.supply"), summary.supply, "supply"),
            (tr("result.use"), summary.use, "use"),
        ):
            with ui.column().classes("w-1/2"):
                ui.label(title).classes("font-medium")
                _table(table, tr, f"{key}-{name}-{bus}")

    figure = sankey_figure(bus, summary, tr)
    if figure is not None:
        ui.label(tr("result.section.sankey")).classes("text-lg font-semibold")
        ui.plotly(as_chart(figure, f"{bus}-sankey")).classes("w-full").mark(f"{key}-sankey-{bus}")


def _bus_panel(bus, summary, tr, key):
    """The tab of an energy carrier: one tab for each kind of view, so that it does not become one long page."""

    sections = (
        ("flows", _flows_section), ("monthly", _monthly_section), ("duration", _duration_section),
        ("heatmap", _heatmap_section), ("tables", _tables_section),
    )

    with ui.tabs().props("dense align=left no-caps").classes("w-full") as sub:
        sub_tab = {name: ui.tab(tr(SUB_TABS[name])).mark(f"{key}-sub-{bus}-{name}") for name, _ in sections}

    with ui.tab_panels(sub, value=sub_tab["flows"]).classes("w-full"):
        for name, section in sections:
            with ui.tab_panel(sub_tab[name]).mark(f"{key}-subpanel-{bus}-{name}"):
                section(bus, summary, tr, key)


def _costs_panel(result, tr, key):
    if not result.cost_breakdown.rows:
        ui.label(tr("result.no_costs")).classes("text-grey").mark(f"{key}-no-costs")
        return

    ui.label(tr("result.section.costs")).classes("text-lg font-semibold")
    figure = cost_figure(result, tr)
    if figure is not None:
        ui.plotly(as_chart(figure, "costs")).classes("w-full").mark(f"{key}-cost-chart")
    _table(result.cost_breakdown, tr, f"{key}-costs-table")


def _capacities_panel(result, tr, key):
    table = result.capacities
    if not table.rows:
        ui.label(tr("result.no_capacities")).classes("text-grey").mark(f"{key}-no-capacities")
        return

    _table(table, tr, f"{key}-capacities-table")
    if "Mode" in table.columns and any(row[table.columns.index("Mode")] == "fixed (input)" for row in table.rows):
        ui.label(tr("result.fixed_note")).classes("text-grey text-sm").mark(f"{key}-fixed-note")


def render_result_tabs(result, tr, key):
    """The tabs of a result. `key` ('draft' or 'file') makes the markers of two results on one page different."""

    names = [(f"bus-{bus}", bus_label(tr, bus)) for bus in result.buses]
    names += [("costs", tr("result.tab.costs")), ("capacities", tr("result.tab.capacities"))]

    with ui.tabs().classes("w-full") as tabs:
        tab_of = {name: ui.tab(label).mark(f"{key}-tab-{name}") for name, label in names}

    with ui.tab_panels(tabs, value=tab_of[names[0][0]]).classes("w-full"):
        for bus, summary in result.buses.items():
            with ui.tab_panel(tab_of[f"bus-{bus}"]).mark(f"{key}-panel-bus-{bus}"):
                _bus_panel(bus, summary, tr, key)
        with ui.tab_panel(tab_of["costs"]).mark(f"{key}-panel-costs"):
            _costs_panel(result, tr, key)
        with ui.tab_panel(tab_of["capacities"]).mark(f"{key}-panel-capacities"):
            _capacities_panel(result, tr, key)