"""How the charts are written and downloaded: a large, bold font for the axes, the ticks, the legend and the text
on the chart (it must stay readable when the picture is downloaded and put into a report), and the settings of
the download button of Plotly (twice the resolution, a file name that says what the picture shows).

No NiceGUI code in here, so it is easy to test.
"""

FONT_FAMILY = "Roboto, Arial, sans-serif"
TEXT_COLOR = "#14202B"

BASE_SIZE = 15           # every text that has no size of its own
AXIS_TITLE_SIZE = 17     # the title of an axis
TICK_SIZE = 15           # the numbers and dates at the ticks
LEGEND_SIZE = 15
TITLE_SIZE = 19          # the title of a chart
HOVER_SIZE = 14
TEXT_SIZE = 15           # the amounts on the bars and the names in a Sankey diagram

BOLD = "bold"
SCALE = 2                # the downloaded picture has twice the pixels of the chart on the screen


def style_figure(figure):
    """Set the fonts of a figure: bold and large for the axes, the ticks, the legend and the title. Gives the
    figure back."""

    figure.update_layout(
        font=dict(family=FONT_FAMILY, size=BASE_SIZE, color=TEXT_COLOR),
        legend=dict(font=dict(size=LEGEND_SIZE, weight=BOLD)),
        hoverlabel=dict(font=dict(family=FONT_FAMILY, size=HOVER_SIZE)),
    )

    if any(trace.type in ("scatter", "bar", "heatmap") for trace in figure.data):  # a Sankey diagram has no axes
        figure.update_xaxes(tickfont=dict(size=TICK_SIZE, weight=BOLD), title_font=dict(size=AXIS_TITLE_SIZE, weight=BOLD))
        figure.update_yaxes(tickfont=dict(size=TICK_SIZE, weight=BOLD), title_font=dict(size=AXIS_TITLE_SIZE, weight=BOLD))

    if figure.layout.title.text:
        figure.update_layout(title_font=dict(size=TITLE_SIZE, weight=BOLD))

    return figure


def chart_config(name):
    """The settings of the chart in the browser: no Plotly logo, no tools that are not needed, and a download
    button that gives a PNG of twice the resolution, named `name`."""

    return {
        "displaylogo": False,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        "toImageButtonOptions": {"format": "png", "scale": SCALE, "filename": name},
    }


def as_chart(figure, name):
    """A figure as NiceGUI wants it when it is to have settings of its own: a dict with `data`, `layout` and
    `config`. `name` is the name of the downloaded file (without the ending)."""

    chart = figure.to_plotly_json()
    chart["config"] = chart_config(name)

    return chart