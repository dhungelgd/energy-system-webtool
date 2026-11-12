"""The tabs of a result on the NiceGUI page: one for each energy carrier (electricity, heat, gas), the costs and
the capacities.

What is shown, and in which words, is decided in result_terms.py and result_charts.py (no NiceGUI there); this
file only puts it on the page. The tab of a carrier has the flows over time, who supplies the carrier and who uses
it (two tables) and a Sankey diagram. The system graph of the Streamlit page is not here: it needs the model, not
the result, and the diagram of the system comes later.
"""

from nicegui import ui

from frontend_nicegui.chart_style import as_chart
from frontend_nicegui.ranges import MODE_TEXTS, available_modes, is_long, view_frame, window_count
from frontend_nicegui.result_charts import cost_figure, flows_figure, sankey_figure
from frontend_nicegui.result_terms import bus_label, table_for_display


def _table(table, tr, marker):
    columns, rows = table_for_display(table, tr)
    ui.table(columns=columns, rows=rows).props("dense flat").classes("w-full").mark(marker)


def _flows_with_window(bus, summary, tr, key):
    """The chart of the flows of a carrier. A period of more than a day has buttons for a day, a week, a month,
    the whole period (every value) and, for a long period, its daily averages, and a slider that moves the window
    through the period. Only what is in the window is sent to the browser; the daily averages are light and are
    the first look, every value of a year is about half a megabyte and is there for zooming into."""

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


def _bus_panel(bus, summary, tr, key):
    ui.label(tr("result.section.flows")).classes("text-lg font-semibold")
    figure = flows_figure(bus, summary, tr)
    if figure is None:
        ui.label(tr("result.no_flows")).classes("text-grey").mark(f"{key}-no-flows-{bus}")
    elif not figure.data:
        ui.label(tr("result.nothing_flows")).classes("text-grey").mark(f"{key}-nothing-flows-{bus}")
    elif available_modes(summary.flows):
        _flows_with_window(bus, summary, tr, key)
    else:
        ui.plotly(as_chart(figure, f"{bus}-flows")).classes("w-full").mark(f"{key}-flows-{bus}")

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