"""More charts of an energy carrier over the whole period: the energy of each month, the duration curve, and the
heat map of the hour of the day against the date.

Like result_charts.py they are made from a ScenarioResult, in the language of the reader and with the colour of each
component (palette.py), they give Plotly figures and do not use NiceGUI, so they are easy to test. They are light:
the monthly balance is a dozen bars, the duration curve is thinned out to a thousand points (it only falls, so
nothing that the eye can see is lost) and the heat map is one number for each hour of a year.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from backend.i18n import ENGLISH
from frontend_nicegui.chart_style import BOLD, FONT_FAMILY, TICK_SIZE, style_figure
from frontend_nicegui.palette import DEMAND_LINE, color_of_node
from frontend_nicegui.result_charts import DAY_MS, GRID, ZERO_FLOW, split_flows
from frontend_nicegui.result_terms import node_label, term

POINTS = 1000                 # the duration curve has at most this many points for each line
HEAT_LOW = "#FFFFFF"          # the colour of a heat map where nothing flows; it ends in the colour of the component
MIN_DAYS = 2                  # a heat map of less than two days has nothing to compare


def _hourly_flows(summary):
    """The flows of a result as a DataFrame, or None if the result has none."""

    flows = summary.flows
    if flows is None or not flows.columns:
        return None

    return flows.to_frame(with_end_row=False)


def _drawn(frame, columns):
    return [c for c in columns if frame[c].abs().max() > ZERO_FLOW]


# ---------------------------------------------------------------------------
# the energy of each month
# ---------------------------------------------------------------------------

def monthly_figure(bus, summary, tr=ENGLISH):
    """The energy of each month (kWh): what supplies the carrier above the zero line, what else uses it below
    (charging, feed-in, conversion), and the demand as a line. None if the result has no flows or the period is
    shorter than two calendar months (a single bar says nothing). A month at the start or the end of the period
    that is not whole has the energy of the part that is there."""

    frame = _hourly_flows(summary)
    if frame is None:
        return None

    monthly = (frame * summary.flows.step_hours).resample("MS").sum()           # kW x hours = kWh in each month
    if len(monthly) < 2:
        return None

    supply, demand, other = split_flows(monthly.columns, bus)
    months = [month.to_pydatetime() for month in monthly.index]
    month_format = tr("result.chart.month_format")

    def bar(column, node, sign):
        name = node_label(tr, node)
        return go.Bar(
            x=months, y=sign * monthly[column].to_numpy(), name=name, marker_color=color_of_node(node),
            xperiod="M1", xperiodalignment="middle",
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:,.0f}} kWh<extra></extra>",
        )

    figure = go.Figure()

    for column in _drawn(monthly, supply):
        figure.add_trace(bar(column, column.split("-->")[0], 1))

    demand = _drawn(monthly, demand)
    if demand:
        name = term(tr, "Demand")
        figure.add_trace(go.Scatter(
            x=months, y=monthly[demand].sum(axis=1).to_numpy(), name=name, mode="lines+markers",
            line=dict(color=DEMAND_LINE, width=2.5), marker=dict(size=8), xperiod="M1", xperiodalignment="middle",
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:,.0f}} kWh<extra></extra>",
        ))

    for column in _drawn(monthly, other):
        figure.add_trace(bar(column, column.split("-->")[1], -1))

    figure.update_layout(
        template="plotly_white",
        height=450,
        barmode="relative",
        xaxis=dict(title=tr("result.chart.month"), tickformat=month_format, hoverformat=month_format, dtick="M1",
                   gridcolor=GRID),
        yaxis=dict(title=tr("result.chart.energy"), gridcolor=GRID, zerolinecolor="#8795A3"),
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.22, title_text=""),
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return style_figure(figure)


# ---------------------------------------------------------------------------
# the duration curve
# ---------------------------------------------------------------------------

def duration_figure(bus, summary, tr=ENGLISH, points=POINTS):
    """The duration curve of a carrier: every value of each flow, sorted from the highest to the lowest, against the
    hours of the period (kW). It says for how many hours a power is reached. The demand is the black line; what
    supplies the carrier and what else uses it ('(use)') have the colour of their component. None if the result
    has no flows; a carrier through which nothing flows gives a figure without lines."""

    frame = _hourly_flows(summary)
    if frame is None:
        return None

    supply, demand, other = split_flows(frame.columns, bus)
    lines = []                                             # (name, colour, width, values)

    demand = _drawn(frame, demand)
    if demand:
        lines.append((term(tr, "Demand"), DEMAND_LINE, 2.5, frame[demand].sum(axis=1).to_numpy()))
    for column in _drawn(frame, supply):
        node = column.split("-->")[0]
        lines.append((node_label(tr, node), color_of_node(node), 1.5, frame[column].to_numpy()))
    for column in _drawn(frame, other):
        node = column.split("-->")[1]
        lines.append((tr("result.chart.as_use", name=node_label(tr, node)), color_of_node(node), 1.5, frame[column].to_numpy()))

    # a long period is thinned out to `points` values at equal distances (the first and the last stay as they are),
    # so that the hours need no list of their own: they are a start and a step, as in the chart of the flows
    steps = len(frame)
    count = min(points, steps)
    positions = np.linspace(0, steps - 1, count)
    hours = summary.flows.step_hours                                 # the first value is the value of the first hour
    spacing = hours * (steps - 1) / (count - 1) if count > 1 else hours

    figure = go.Figure()
    for name, color, width, values in lines:
        thinned = np.interp(positions, np.arange(steps), np.sort(values)[::-1])
        figure.add_trace(go.Scatter(
            x0=hours, dx=spacing, y=thinned.astype("float32"), mode="lines", name=name,
            line=dict(color=color, width=width),
            hovertemplate=f"{name}<br>%{{x:,.0f}} h<br>%{{y:.2f}} kW<extra></extra>",
        ))

    figure.update_layout(
        template="plotly_white",
        height=450,
        xaxis=dict(title=tr("result.chart.hours"), gridcolor=GRID, rangemode="tozero"),
        yaxis=dict(title=tr("result.chart.power"), gridcolor=GRID, zerolinecolor="#8795A3"),
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.22, title_text=""),
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return style_figure(figure)


# ---------------------------------------------------------------------------
# the heat map
# ---------------------------------------------------------------------------

DEMAND = "demand"             # what a heat map can show besides the supplies (their columns, 'pv-->electricity')


def heatmap_choices(bus, summary):
    """What a heat map of this carrier can show, in the order of the choice: the demand, then each supply that
    is not zero all the time (as the name of its flow, 'pv-->electricity'). Empty if there are no flows."""

    frame = _hourly_flows(summary)
    if frame is None:
        return []

    supply, demand, _ = split_flows(frame.columns, bus)

    return ([DEMAND] if _drawn(frame, demand) else []) + _drawn(frame, supply)


def heatmap_label(tr, what):
    """The name of a choice of the heat map in the language of the reader."""

    return term(tr, "Demand") if what == DEMAND else node_label(tr, what.split("-->")[0])


def heatmap_figure(bus, summary, what, tr=ENGLISH):
    """The hour of the day against the date, coloured by the power (kW): `what` is DEMAND or the name of a supply
    flow. It shows the daily rhythm and the seasons at once, in the colour of the component. None if there is
    nothing to show: no flows, steps longer than an hour, a period of less than two days, or a choice that is not
    in the result. A day that is only partly in the period has gaps for the hours that are not."""

    frame = _hourly_flows(summary)
    if frame is None or summary.flows.step_hours > 1 or what not in heatmap_choices(bus, summary):
        return None

    supply, demand, _ = split_flows(frame.columns, bus)
    if what == DEMAND:
        series, color = frame[_drawn(frame, demand)].sum(axis=1), DEMAND_LINE
    else:
        series, color = frame[what], color_of_node(what.split("-->")[0])

    if summary.flows.step_hours < 1:
        series = series.resample("h").mean()                      # a value for each hour, whatever the step

    days = pd.date_range(series.index[0].normalize(), series.index[-1].normalize(), freq="D")
    if len(days) < MIN_DAYS:
        return None

    grid = pd.DataFrame({"v": series.to_numpy(), "date": series.index.normalize(), "hour": series.index.hour})
    z = grid.pivot(index="hour", columns="date", values="v").reindex(index=range(24), columns=days)
    date_format = tr("result.chart.date_format")

    figure = go.Figure(go.Heatmap(
        z=z.to_numpy(dtype="float32"), x0=days[0].to_pydatetime(), dx=DAY_MS, y=list(range(24)),
        colorscale=[[0, HEAT_LOW], [1, color]], hoverongaps=False,
        colorbar=dict(title=dict(text="kW", font=dict(size=TICK_SIZE, family=FONT_FAMILY, weight=BOLD)),
                      tickfont=dict(size=TICK_SIZE, family=FONT_FAMILY, weight=BOLD)),
        hovertemplate="%{x}<br>%{y}:00<br>%{z:.2f} kW<extra></extra>",
    ))
    figure.update_layout(
        template="plotly_white",
        height=450,
        xaxis=dict(title=tr("result.chart.date"), tickformat=date_format, hoverformat=date_format),
        yaxis=dict(title=tr("result.chart.hour_of_day"), autorange="reversed", dtick=3),         # midnight at the top
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return style_figure(figure)