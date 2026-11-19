"""The charts of the PDF report: the data of each chart (plain numbers, easy to test) and the drawing of it.

They are drawn with matplotlib and no browser, from the same flows and with the same colours as the charts on the
page (result_charts.py, result_charts_year.py, palette.py), in the language of the reader. A period of more than two
weeks is drawn as daily means: on paper nobody can zoom into 8760 hours.
"""

import io
from dataclasses import dataclass

import numpy as np
from matplotlib.dates import AutoDateLocator, DateFormatter
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from backend.i18n import ENGLISH
from frontend_nicegui.palette import DEMAND_LINE, color_of_name, color_of_node
from frontend_nicegui.result_charts import GRID, ZERO_FLOW, split_flows
from frontend_nicegui.result_terms import node_label, term

LONG_HOURS = 14 * 24          # a period longer than this is drawn as daily means
POINTS = 1000                 # the duration curve is thinned out to this many points
NEGLIGIBLE_COST = 0.5         # a cost item below this (in euro) is not drawn
MAX_COST_ITEMS = 20           # the chart shows the largest items (the table of the report has all of them)
WIDTH_INCH = 6.7              # 17 cm: the width of the text of the report
DPI = 200
FONT = 8


@dataclass(frozen=True)
class Line:
    name: str
    color: str
    values: object                # numpy array
    width: float = 1.5


@dataclass(frozen=True)
class FlowsData:
    index: object                 # the times (a DatetimeIndex)
    supplies: list                # [Line]: what supplies the carrier, drawn upwards
    uses: list                    # [Line]: what else uses it, drawn downwards (the values are positive)
    demand: object                # a Line or None
    daily: bool                   # True if these are daily means of the hourly values


@dataclass(frozen=True)
class MonthlyData:
    months: object
    supplies: list
    uses: list
    demand: object


@dataclass(frozen=True)
class DurationData:
    hours: object                 # numpy array
    lines: list


@dataclass(frozen=True)
class CostData:
    labels: list
    values: list
    colors: list


def _hourly_flows(summary):
    flows = summary.flows
    if flows is None or not flows.columns:
        return None

    return flows.to_frame(with_end_row=False)


def _drawn(frame, columns):
    return [column for column in columns if frame[column].abs().max() > ZERO_FLOW]


def _lines(frame, bus, tr, demand_width=2.2):
    """The supplies, the other uses and the demand of a bus as lines (nothing that is zero all the time)."""

    supply, demand, other = split_flows(frame.columns, bus)

    supplies = [Line(node_label(tr, c.split("-->")[0]), color_of_node(c.split("-->")[0]), frame[c].to_numpy())
                for c in _drawn(frame, supply)]
    uses = [Line(node_label(tr, c.split("-->")[1]), color_of_node(c.split("-->")[1]), frame[c].to_numpy())
            for c in _drawn(frame, other)]
    demands = _drawn(frame, demand)
    line = Line(term(tr, "Demand"), DEMAND_LINE, frame[demands].sum(axis=1).to_numpy(), demand_width) if demands else None

    return supplies, uses, line


# ---------------------------------------------------------------------------
# the data of each chart
# ---------------------------------------------------------------------------

def flows_data(bus, summary, tr=ENGLISH):
    """The flows of a carrier over time (kW). None if the result has no flows; a carrier through which nothing
    flows gives data without lines."""

    frame = _hourly_flows(summary)
    if frame is None:
        return None

    daily = len(frame) * summary.flows.step_hours > LONG_HOURS
    if daily:
        frame = frame.resample("D").mean()

    supplies, uses, demand = _lines(frame, bus, tr)

    return FlowsData(frame.index, supplies, uses, demand, daily)


def monthly_data(bus, summary, tr=ENGLISH):
    """The energy of each month (kWh); None if there are no flows or less than two calendar months."""

    frame = _hourly_flows(summary)
    if frame is None:
        return None

    monthly = (frame * summary.flows.step_hours).resample("MS").sum()
    if len(monthly) < 2:
        return None

    supplies, uses, demand = _lines(monthly, bus, tr)

    return MonthlyData(monthly.index, supplies, uses, demand)


def duration_data(bus, summary, tr=ENGLISH, points=POINTS):
    """Every value of each flow sorted from the highest to the lowest (kW) against the hours; None if no flows."""

    frame = _hourly_flows(summary)
    if frame is None:
        return None

    supply, demand, other = split_flows(frame.columns, bus)
    series = []
    demands = _drawn(frame, demand)
    if demands:
        series.append(Line(term(tr, "Demand"), DEMAND_LINE, frame[demands].sum(axis=1).to_numpy(), 2.2))
    series += [Line(node_label(tr, c.split("-->")[0]), color_of_node(c.split("-->")[0]), frame[c].to_numpy())
               for c in _drawn(frame, supply)]
    series += [Line(tr("result.chart.as_use", name=node_label(tr, c.split("-->")[1])),
                    color_of_node(c.split("-->")[1]), frame[c].to_numpy()) for c in _drawn(frame, other)]

    steps = len(frame)
    count = min(points, steps)
    positions = np.linspace(0, steps - 1, count)
    hours = (positions + 1) * summary.flows.step_hours
    lines = [Line(line.name, line.color, np.interp(positions, np.arange(steps), np.sort(line.values)[::-1]), line.width)
             for line in series]

    return DurationData(hours, lines)


def costs_data(result, tr=ENGLISH):
    """The cost items from the lowest (revenues) to the highest, in the colour of their component; None if none. Of
    many items the largest ones (MAX_COST_ITEMS)."""

    table = result.cost_breakdown
    if not {"Item", "Category", "Cost (€)"} <= set(table.columns):
        return None

    item, cost = table.columns.index("Item"), table.columns.index("Cost (€)")
    rows = [row for row in table.rows if row[cost] is not None and abs(row[cost]) > NEGLIGIBLE_COST]
    if not rows:
        return None
    rows = sorted(sorted(rows, key=lambda row: -abs(row[cost]))[:MAX_COST_ITEMS], key=lambda row: row[cost])

    return CostData([term(tr, row[item]) for row in rows], [row[cost] for row in rows],
                    [color_of_name(row[item]) for row in rows])


# ---------------------------------------------------------------------------
# drawing
# ---------------------------------------------------------------------------

def _figure(height_inch):
    figure = Figure(figsize=(WIDTH_INCH, height_inch), dpi=DPI)
    axes = figure.subplots()
    axes.tick_params(labelsize=FONT, length=2.5, color="#8795A3")
    axes.grid(True, color=GRID, linewidth=0.6)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color("#8795A3")

    return figure, axes


def _png(figure):
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=DPI, bbox_inches="tight", pad_inches=0.05)

    return buffer.getvalue()


def _legend(axes, count):
    if count:
        axes.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=min(5, count), frameon=False, fontsize=FONT - 0.5)


def _number(tr, axes=None, axis="y"):
    """A number on an axis as the reader writes it. With the axes, a range that is small gets decimals (an axis from
    1 to 2 must not say 1, 1, 1, 2)."""

    def text(value, _):
        decimals = 0
        if axes is not None:
            ticks = axes.get_yticks() if axis == "y" else axes.get_xticks()
            decimals = next((d for d in range(4) if all(abs(t - round(t, d)) < 1e-9 for t in ticks)), 3)

        return tr.localize(f"{value:,.{decimals}f}")

    return FuncFormatter(text)


def _label(axes, text, axis="y"):
    (axes.set_ylabel if axis == "y" else axes.set_xlabel)(text, fontsize=FONT + 0.5, fontweight="bold")


def draw_flows(data, tr=ENGLISH):
    """PNG of the flows over time: supplies stacked upwards, other uses downwards, the demand as a dark line."""

    figure, axes = _figure(2.35)
    x = data.index.to_pydatetime()

    if data.supplies:
        axes.stackplot(x, *[line.values for line in data.supplies], colors=[l.color for l in data.supplies],
                       labels=[l.name for l in data.supplies], linewidth=0.4, alpha=0.9)
    if data.uses:
        axes.stackplot(x, *[-line.values for line in data.uses], colors=[l.color for l in data.uses],
                       labels=[l.name for l in data.uses], linewidth=0.4, alpha=0.9)
    if data.demand is not None:
        axes.plot(x, data.demand.values, color=data.demand.color, linewidth=data.demand.width, label=data.demand.name)

    axes.axhline(0, color="#8795A3", linewidth=0.8)
    axes.margins(x=0)
    axes.yaxis.set_major_formatter(_number(tr, axes))
    _label(axes, tr("result.chart.power"))
    axes.xaxis.set_major_locator(AutoDateLocator(minticks=3, maxticks=7))
    axes.xaxis.set_major_formatter(_date_formatter(tr))
    _legend(axes, len(data.supplies) + len(data.uses) + (data.demand is not None))

    return _png(figure)


def _date_formatter(tr):
    return DateFormatter(tr("result.chart.date_format"))


def draw_monthly(data, tr=ENGLISH):
    """PNG of the energy of each month: supplies above the zero line, other uses below, the demand as a line."""

    figure, axes = _figure(2.35)
    x = np.arange(len(data.months))
    width = 0.7

    for sign, lines in ((1, data.supplies), (-1, data.uses)):
        bottom = np.zeros(len(x))
        for line in lines:
            axes.bar(x, sign * line.values, width, bottom=bottom, color=line.color, label=line.name, linewidth=0)
            bottom = bottom + sign * line.values
    if data.demand is not None:
        axes.plot(x, data.demand.values, color=data.demand.color, linewidth=data.demand.width, marker="o",
                  markersize=3.5, label=data.demand.name)

    axes.axhline(0, color="#8795A3", linewidth=0.8)
    axes.set_xticks(x)
    axes.set_xticklabels([month.strftime(tr("result.chart.month_format")) for month in data.months],
                         rotation=35 if len(data.months) > 6 else 0, ha="right" if len(data.months) > 6 else "center")
    axes.yaxis.set_major_formatter(_number(tr, axes))
    _label(axes, tr("result.chart.energy"))
    _legend(axes, len(data.supplies) + len(data.uses) + (data.demand is not None))

    return _png(figure)


def draw_duration(data, tr=ENGLISH):
    """PNG of the duration curve: every flow sorted from the highest to the lowest against the hours."""

    figure, axes = _figure(2.35)
    for line in data.lines:
        axes.plot(data.hours, line.values, color=line.color, linewidth=line.width, label=line.name)

    axes.set_xlim(left=0)
    axes.xaxis.set_major_formatter(_number(tr, axes, "x"))
    axes.yaxis.set_major_formatter(_number(tr, axes))
    _label(axes, tr("result.chart.power"))
    _label(axes, tr("result.chart.hours"), "x")
    _legend(axes, len(data.lines))

    return _png(figure)


def draw_costs(data, tr=ENGLISH):
    """PNG of the cost items as horizontal bars in the colour of their component; revenues point to the left."""

    figure, axes = _figure(max(1.6, 0.34 * len(data.labels) + 0.8))
    y = np.arange(len(data.labels))
    axes.barh(y, data.values, color=data.colors, height=0.62, linewidth=0)
    axes.set_yticks(y)
    axes.set_yticklabels(data.labels)
    axes.axvline(0, color="#8795A3", linewidth=0.8)
    axes.grid(axis="y", visible=False)
    axes.xaxis.set_major_formatter(_number(tr, axes, "x"))
    _label(axes, tr("result.chart.cost_axis"), "x")

    span = max(abs(v) for v in data.values) or 1.0
    for position, value in zip(y, data.values):
        axes.annotate(f"{tr.localize(f'{value:,.0f}')} €", (value, position), xytext=(4 if value >= 0 else -4, 0),
                      textcoords="offset points", ha="left" if value >= 0 else "right", va="center",
                      fontsize=FONT - 0.5, fontweight="bold")
    axes.set_xlim(min(0, min(data.values)) - span * 0.18, max(0, max(data.values)) + span * 0.18)

    return _png(figure)


def chart_png(ref, result, tr=ENGLISH):
    """The PNG of a chart of the report (a report_data.ChartRef), or None if there is nothing to draw."""

    if ref.kind == "costs":
        data = costs_data(result, tr)
        return draw_costs(data, tr) if data is not None else None

    summary = result.buses.get(ref.bus)
    if summary is None:
        return None

    maker, drawer = {
        "flows": (flows_data, draw_flows),
        "monthly": (monthly_data, draw_monthly),
        "duration": (duration_data, draw_duration),
    }[ref.kind]
    data = maker(ref.bus, summary, tr)
    if data is None or not (getattr(data, "supplies", None) or getattr(data, "lines", None) or getattr(data, "demand", None)):
        return None

    return drawer(data, tr)