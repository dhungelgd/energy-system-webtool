"""The charts of the analysis of a load profile, as Plotly figures: the typical days, the duration curve, the months, the
heat map, the typical days by season and the mean load by weekday.

Each function takes a LoadAnalysis (backend/load_analysis.py) and the translator of the page and gives a figure, or None if
there is nothing to draw. The fonts and the sizes are those of the other charts of the tool (chart_style.py). No NiceGUI code
in here, so it is easy to test.
"""

import calendar
from datetime import date

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backend.holidays_de import DAY_TYPES, SATURDAY, SUMMER, SUNDAY, TRANSITION, WINTER, WORKDAY
from backend.i18n import ENGLISH
from frontend_nicegui.chart_style import style_figure
from frontend_nicegui.palette import with_alpha

GRID = "#E3E8ED"
DAY_TYPE_COLORS = {WORKDAY: "#005D9D", SATURDAY: "#C98200", SUNDAY: "#6B7C8D"}        # blue, amber, grey
DAY_TYPE_TEXTS = {WORKDAY: "analysis.daytype.workday", SATURDAY: "analysis.daytype.saturday", SUNDAY: "analysis.daytype.sunday"}
BAND_OPACITY = 0.16                  # the middle half of the days is drawn see-through
ENERGY_COLOR, ENERGY_COLOR_PALE = "#005D9D", "#9CC3E0"
PEAK_COLOR = "#B25E00"
BASE_COLORS = ("#2A9D6B", "#6B4FA3")          # the two base loads#
LIMIT_COLOR = "#C0392B"                       # the limit of the power, and what is above it
LIMIT_OPACITY = 0.30
HEIGHT = 380
HEATMAP_HEIGHT = 460
HOURS_BETWEEN_TICKS = 3
SEASON_HOURS_BETWEEN_TICKS = 6               # three charts side by side are narrow
HEATMAP_COLORS = [[0.0, "#EAF3FA"], [0.5, "#4C9BD8"], [1.0, "#14202B"]]
WEEKDAY_COLOR = "#005D9D"
SEASON_ORDER = (WINTER, TRANSITION, SUMMER)          # as the year goes: winter, the time in between, summer
SEASON_TEXTS = {WINTER: "analysis.season.winter", TRANSITION: "analysis.season.transition", SUMMER: "analysis.season.summer"}
WEEKDAY_TEXTS = ("analysis.weekday.0", "analysis.weekday.1", "analysis.weekday.2", "analysis.weekday.3", "analysis.weekday.4",
                 "analysis.weekday.5", "analysis.weekday.6")                # Monday to Sunday


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


def duration_figure(analysis, tr=ENGLISH, limit_kw=None):
    """The duration curve: how many hours the load is at least as high as a value, with the two base loads as lines. With a
    limit the part of the curve above it is shaded, and the limit is a line."""

    curve = analysis.duration
    figure = go.Figure()
    if limit_kw is not None:
        figure.add_trace(go.Scatter(
            x=[0, curve.total_hours], y=[limit_kw, limit_kw], mode="lines", line=dict(color=LIMIT_COLOR, width=2, dash="dash"),
            name=tr("analysis.chart.cap_line", value=tr.number(round(limit_kw, 1))), hoverinfo="skip"))
        figure.add_trace(go.Scatter(
            x=curve.hours, y=[max(value, limit_kw) for value in curve.kw], mode="lines", line=dict(width=0), fill="tonexty",
            fillcolor=with_alpha(LIMIT_COLOR, LIMIT_OPACITY), name=tr("analysis.chart.above_limit"), hoverinfo="skip"))
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


def heatmap_figure(analysis, tr=ENGLISH):
    """The load at each time of each day: the day along the horizontal axis, the time of day down the vertical axis (midnight
    at the top), a cell is empty where there is no value."""

    heat = analysis.heatmap
    if not heat.dates:
        return None

    values = heat.values.T                                                       # a row for each time of day
    z = [[None if np.isnan(value) else round(float(value), 1) for value in row] for row in values]
    times = [clock(slot) for slot in heat.slots]
    low = float(np.nanmin(values)) if not np.isnan(values).all() else 0.0

    figure = go.Figure(go.Heatmap(
        x=[day.isoformat() for day in heat.dates], y=times, z=z, colorscale=HEATMAP_COLORS, zmin=min(0.0, low), hoverongaps=False,
        colorbar=dict(title=dict(text=tr("analysis.chart.heatmap_color")), thickness=14, len=0.9),
        hovertemplate="%{x}<br>%{y}<br>%{z:.1f} kW<extra></extra>"))

    figure.update_layout(
        template="plotly_white", height=HEATMAP_HEIGHT, margin=dict(l=10, r=10, t=20, b=10), xaxis_title=None, yaxis_title=tr("analysis.chart.time_of_day"))
    figure.update_xaxes(type="date", hoverformat=tr("result.chart.date_format"))
    figure.update_yaxes(
        type="category", autorange="reversed", tickmode="array", tickvals=[clock(60 * hour) for hour in range(0, 24, HOURS_BETWEEN_TICKS)
                                                                          if clock(60 * hour) in times])

    return style_figure(figure)


def seasonal_figure(analysis, tr=ENGLISH):
    """The typical days of each season side by side: for each type of day a line of the mean load. A season without a typical
    day is left out; None if there is none."""

    found = {(day.season, day.day_type): day for day in analysis.typical_days if day.season is not None}
    seasons = [name for name in SEASON_ORDER if any((name, kind) in found for kind in DAY_TYPES)]
    if not seasons:
        return None

    figure = make_subplots(rows=1, cols=len(seasons), shared_yaxes=True, horizontal_spacing=0.03,
                           subplot_titles=[tr(SEASON_TEXTS[name]) for name in seasons])
    shown = set()
    for column, name in enumerate(seasons, start=1):
        for kind in DAY_TYPES:
            day = found.get((name, kind))
            if day is None:
                continue
            figure.add_trace(go.Scatter(
                x=[slot / 60 for slot in day.slots], y=day.mean, mode="lines", line=dict(color=DAY_TYPE_COLORS[kind], width=3),
                name=tr(DAY_TYPE_TEXTS[kind]), legendgroup=kind, showlegend=kind not in shown,
                customdata=[clock(slot) for slot in day.slots],
                hovertemplate="%{customdata}<br>%{y:.1f} kW<extra>" + tr("analysis.chart.typical_name", name=tr(DAY_TYPE_TEXTS[kind]), days=day.days) + "</extra>"),
                row=1, col=column)
            shown.add(kind)

    last = max(day.slots[-1] + (day.slots[1] - day.slots[0] if len(day.slots) > 1 else 0) for day in found.values()) / 60
    ticks = list(range(0, 25, SEASON_HOURS_BETWEEN_TICKS))
    figure.update_layout(template="plotly_white", height=HEIGHT, margin=dict(l=10, r=10, t=40, b=10),
                         legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0))
    figure.update_xaxes(gridcolor=GRID, range=[0, last], tickmode="array", tickvals=ticks, ticktext=[clock(60 * hour) for hour in ticks])
    figure.update_yaxes(gridcolor=GRID, rangemode="tozero")
    figure.update_yaxes(title_text=tr("result.chart.power"), col=1)
    figure.update_annotations(font=dict(size=17, weight="bold"))

    return style_figure(figure)


def weekday_figure(analysis, tr=ENGLISH):
    """The mean power on each weekday as bars (a weekday that the profile does not have is left out); None if none."""

    days = [(number, value) for number, value in enumerate(analysis.weekdays) if value is not None]
    if not days:
        return None

    figure = go.Figure(go.Bar(
        x=[tr(WEEKDAY_TEXTS[number]) for number, _ in days], y=[value for _, value in days], marker_color=WEEKDAY_COLOR,
        hovertemplate="%{x}<br>%{y:.1f} kW<extra></extra>"))

    return _layout(figure, None, tr("analysis.chart.mean_power"), tr, showlegend=False)