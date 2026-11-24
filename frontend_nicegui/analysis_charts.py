"""The charts of the analysis of a load profile, as Plotly figures: the typical days, the duration curve and the months.

Each function takes a LoadAnalysis (backend/load_analysis.py) and the translator of the page and gives a figure, or None if
there is nothing to draw. The fonts and the sizes are those of the other charts of the tool (chart_style.py). No NiceGUI code
in here, so it is easy to test.
"""

import calendar
from datetime import date

import plotly.graph_objects as go

from backend.holidays_de import DAY_TYPES, SATURDAY, SUNDAY, WORKDAY
from backend.i18n import ENGLISH
from frontend_nicegui.chart_style import style_figure
from frontend_nicegui.palette import with_alpha

GRID = "#E3E8ED"
DAY_TYPE_COLORS = {WORKDAY: "#005D9D", SATURDAY: "#C98200", SUNDAY: "#6B7C8D"}        # blue, amber, grey
DAY_TYPE_TEXTS = {WORKDAY: "analysis.daytype.workday", SATURDAY: "analysis.daytype.saturday", SUNDAY: "analysis.daytype.sunday"}
BAND_OPACITY = 0.16                  # the middle half of the days is drawn see-through
ENERGY_COLOR, ENERGY_COLOR_PALE = "#005D9D", "#9CC3E0"
PEAK_COLOR = "#B25E00"
BASE_COLORS = ("#2A9D6B", "#6B4FA3")          # the two base loads
HEIGHT = 380
HOURS_BETWEEN_TICKS = 3


def clock(minutes):
    """Minutes after midnight as '08:15'."""

    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _layout(figure, x_title, y_title, tr, **more):
    figure.update_layout(
        template="plotly_white", height=HEIGHT, margin=dict(l=10, r=10, t=20, b=10), xaxis_title=x_title, yaxis_title=y_title,
        legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="left", x=0), **more)
    figure.update_xaxes(gridcolor=GRID)
    figure.update_yaxes(gridcolor=GRID, rangemode="tozero")

    return style_figure(figure)


def typical_days_figure(analysis, tr=ENGLISH):
    """The mean load at each time of day for each type of day (all seasons together), with the middle half of the days as
    a band. A type of day that has too few days is not drawn; None if none is."""

    days = {day.day_type: day for day in analysis.typical_days if day.season is None}
    if not days:
        return None

    figure = go.Figure()
    for kind in DAY_TYPES:
        day = days.get(kind)
        if day is None:
            continue

        color = DAY_TYPE_COLORS[kind]
        hours = [slot / 60 for slot in day.slots]
        times = [clock(slot) for slot in day.slots]
        figure.add_trace(go.Scatter(x=hours, y=day.p75, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        figure.add_trace(go.Scatter(
            x=hours, y=day.p25, mode="lines", line=dict(width=0), fill="tonexty", fillcolor=with_alpha(color, BAND_OPACITY),
            showlegend=False, hoverinfo="skip"))
        figure.add_trace(go.Scatter(
            x=hours, y=day.mean, mode="lines", line=dict(color=color, width=3), customdata=times,
            name=tr("analysis.chart.typical_name", name=tr(DAY_TYPE_TEXTS[kind]), days=day.days),
            hovertemplate="%{customdata}<br>%{y:.1f} kW<extra>" + tr(DAY_TYPE_TEXTS[kind]) + "</extra>"))

    slot = days[next(iter(days))].slots
    last = (slot[-1] + (slot[1] - slot[0] if len(slot) > 1 else 0)) / 60
    ticks = list(range(0, 25, HOURS_BETWEEN_TICKS))
    figure = _layout(figure, tr("analysis.chart.time_of_day"), tr("result.chart.power"), tr)
    figure.update_xaxes(range=[0, last], tickmode="array", tickvals=ticks, ticktext=[clock(60 * hour) for hour in ticks])

    return figure


def duration_figure(analysis, tr=ENGLISH):
    """The duration curve: how many hours the load is at least as high as a value, with the two base loads as lines."""

    curve = analysis.duration
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=curve.hours, y=curve.kw, mode="lines", line=dict(color=ENERGY_COLOR, width=3), showlegend=False,
        hovertemplate="%{x:,.0f} h<br>%{y:.1f} kW<extra></extra>"))

    kpis = analysis.kpis
    for value, key, color in ((kpis.base_percentile_kw, "analysis.chart.base_percentile_line", BASE_COLORS[0]),
                              (kpis.base_night_kw, "analysis.chart.base_night_line", BASE_COLORS[1])):
        if value is None:
            continue
        figure.add_trace(go.Scatter(
            x=[0, curve.total_hours], y=[value, value], mode="lines", line=dict(color=color, width=2, dash="dot"),
            name=tr(key, value=tr.number(round(value, 1))), hoverinfo="skip"))

    figure = _layout(figure, tr("result.chart.hours"), tr("result.chart.power"), tr)
    figure.update_xaxes(range=[0, curve.total_hours])

    return figure


def month_label(month, tr):
    return date(month.year, month.month, 1).strftime(tr("result.chart.month_format"))


def monthly_figure(analysis, tr=ENGLISH):
    """The energy of each month as bars (a month that is not complete is drawn pale) and the highest power of each month as
    a line on a second axis."""

    months = analysis.months
    if not months:
        return None

    labels = [month_label(month, tr) for month in months]
    complete = [month.missing_share == 0 and month.days >= calendar.monthrange(month.year, month.month)[1] for month in months]
    days = [month.days for month in months]
    figure = go.Figure()
    figure.add_trace(go.Bar(
        x=labels, y=[month.energy_kwh for month in months], name=tr("result.chart.energy"),
        marker_color=[ENERGY_COLOR if full else ENERGY_COLOR_PALE for full in complete], customdata=days,
        hovertemplate="%{x}<br>%{y:,.0f} kWh<br>" + tr("analysis.chart.month_days", days="%{customdata}") + "<extra></extra>"))
    figure.add_trace(go.Scatter(
        x=labels, y=[month.peak_kw for month in months], name=tr("analysis.chart.peak_axis"), yaxis="y2", mode="lines+markers",
        line=dict(color=PEAK_COLOR, width=3), marker=dict(size=8),
        hovertemplate="%{x}<br>%{y:.1f} kW<extra></extra>"))

    figure = _layout(figure, None, tr("result.chart.energy"), tr)
    figure.update_layout(yaxis2=dict(
        title=tr("analysis.chart.peak_axis"), overlaying="y", side="right", rangemode="tozero", showgrid=False,
        tickfont=figure.layout.yaxis.tickfont, title_font=figure.layout.yaxis.title.font))
    figure.update_xaxes(type="category")

    return figure