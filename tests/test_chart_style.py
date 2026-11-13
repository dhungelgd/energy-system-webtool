"""How the charts are written and downloaded: large bold fonts, and the settings of the download button."""

import plotly.graph_objects as go

from frontend_nicegui.chart_style import (
    AXIS_TITLE_SIZE,
    BASE_SIZE,
    BOLD,
    SCALE,
    TICK_SIZE,
    TITLE_SIZE,
    as_chart,
    chart_config,
    style_figure,
)


def line():
    return go.Figure(go.Scatter(x=[1, 2], y=[1, 2]))


def test_the_sizes_are_large_enough_to_read_in_a_report():
    assert BASE_SIZE >= 15 and TICK_SIZE >= 15 and AXIS_TITLE_SIZE > TICK_SIZE and TITLE_SIZE > AXIS_TITLE_SIZE
    assert BOLD == "bold"


def test_a_figure_with_axes_gets_bold_ticks_and_bold_axis_titles_and_a_bold_legend():
    figure = style_figure(line())

    for axis in (figure.layout.xaxis, figure.layout.yaxis):
        assert axis.tickfont.size == TICK_SIZE and axis.tickfont.weight == BOLD
        assert axis.title.font.size == AXIS_TITLE_SIZE and axis.title.font.weight == BOLD
    assert figure.layout.legend.font.weight == BOLD and figure.layout.font.size == BASE_SIZE


def test_a_bar_chart_has_axes_too():
    figure = style_figure(go.Figure(go.Bar(x=[1], y=["a"], orientation="h")))

    assert figure.layout.xaxis.tickfont.weight == BOLD and figure.layout.yaxis.tickfont.weight == BOLD


def test_a_figure_without_axes_is_not_given_any():
    figure = style_figure(go.Figure(go.Sankey(node=dict(label=["a", "b"]), link=dict(source=[0], target=[1], value=[1]))))

    assert figure.layout.xaxis.tickfont.size is None and figure.layout.yaxis.tickfont.size is None
    assert figure.layout.font.size == BASE_SIZE


def test_a_title_is_larger_and_bold_and_a_figure_without_a_title_gets_no_title_font():
    titled = line().update_layout(title="A title")
    plain = line()

    assert style_figure(titled).layout.title.font.size == TITLE_SIZE and titled.layout.title.font.weight == BOLD
    assert style_figure(plain).layout.title.font.size is None


def test_styling_gives_the_same_figure_back():
    figure = line()

    assert style_figure(figure) is figure


def test_the_download_button_gives_a_png_of_twice_the_resolution_with_a_name_that_says_what_it_shows():
    config = chart_config("electricity-flows")

    assert config["toImageButtonOptions"] == {"format": "png", "scale": SCALE, "filename": "electricity-flows"} and SCALE == 2
    assert config["displaylogo"] is False and "lasso2d" in config["modeBarButtonsToRemove"]


def test_a_chart_for_the_page_is_a_dict_with_data_layout_and_config_and_the_figure_is_not_changed():
    figure = style_figure(line())
    before = figure.to_json()

    chart = as_chart(figure, "costs")

    assert set(chart) >= {"data", "layout", "config"} and chart["config"]["toImageButtonOptions"]["filename"] == "costs"
    assert figure.to_json() == before
    assert len(go.Figure(chart).data) == 1                                  # and a figure can be made of it again


def test_a_heat_map_has_axes_too():
    figure = style_figure(go.Figure(go.Heatmap(z=[[1, 2], [3, 4]])))

    assert figure.layout.xaxis.tickfont.weight == BOLD and figure.layout.yaxis.title.font.size == AXIS_TITLE_SIZE