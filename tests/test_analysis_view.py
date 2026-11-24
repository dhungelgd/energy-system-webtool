"""What the page of the analysis shows as plain data: the states, the periods and the cards of the key figures."""

import numpy as np
import pandas as pd

from backend.i18n import Translator
from backend.load_analysis import analyze
from frontend_nicegui.analysis_view import ALL_YEARS, kpi_items, state_options, year_options
from tests.test_load_analysis import ZONE, a_year, week

DE, EN = Translator("de"), Translator("en")


def items(analysis, tr=EN):
    return {item["key"]: item for item in kpi_items(analysis, tr)}


def test_the_states_are_listed_by_their_names_in_the_language_of_the_page():
    german = list(state_options(DE).values())

    assert german[:5] == ["Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen"] and len(german) == 16
    assert list(state_options(EN).values())[:3] == ["Baden-Württemberg", "Bavaria", "Berlin"]
    assert state_options(DE)["BY"] == "Bayern" and state_options(EN)["NW"] == "North Rhine-Westphalia"


def test_a_profile_within_one_year_has_no_choice_of_the_period_and_a_longer_one_has_the_whole_and_each_year():
    assert year_options([], EN) == {} and year_options([(2023, 365)], EN) == {}
    assert year_options([(2022, 100), (2023, 365)], EN) == {ALL_YEARS: "Whole profile", "2022": "2022", "2023": "2023"}
    assert year_options([(2022, 100), (2023, 365)], DE)[ALL_YEARS] == "Ganzer Zeitraum"


def test_the_cards_of_a_week_say_the_energy_of_the_period_and_have_no_hours_of_use():
    cards = items(analyze(*week()))

    assert list(cards) == ["energy", "peak", "base_percentile", "base_night", "utilization", "load_factor"]
    assert (cards["energy"]["label"], cards["energy"]["value"], cards["energy"]["sub"]) == ("Energy in the period", "6,610 kWh", "7 days")
    assert (cards["peak"]["value"], cards["peak"]["sub"]) == ("150 kW", "on 2023-02-08 10:00")
    assert cards["base_percentile"]["value"] == "20 kW" and cards["base_night"]["value"] == "20 kW"
    assert (cards["utilization"]["value"], cards["utilization"]["sub"]) == ("–", "Only for 330 days or more")
    assert cards["load_factor"]["value"] == f"{round(100 * 6610 / 168 / 150)} %"


def test_the_cards_of_a_year_say_the_yearly_energy_and_the_hours_of_use():
    series, step = a_year()
    series.iloc[100] = 100.0

    cards = items(analyze(series, step))

    assert cards["energy"]["label"] == "Yearly energy" and cards["energy"]["value"] == f"{50 * 8760 + 50:,} kWh" and cards["energy"]["sub"] is None
    assert cards["utilization"]["value"] == f"{round((50 * 8760 + 50) / 100):,} h" and cards["utilization"]["sub"] is None


def test_the_yearly_energy_says_how_much_the_gaps_would_add_and_nothing_if_there_are_none():
    series, step = a_year()
    series.iloc[:24 * 10] = np.nan                                            # ten days missing

    gaps = items(analyze(series, step))["energy"]

    assert gaps["sub"] == f"plus about {50 * 24 * 10:,} kWh for the gaps" and gaps["value"] == f"{50 * 8760 - 50 * 240:,} kWh"


def test_the_cards_are_in_german_with_the_separators_and_the_dates_of_the_language():
    cards = items(analyze(*week()), DE)

    assert cards["energy"]["value"] == "6.610 kWh" and cards["energy"]["sub"] == "7 Tage" and cards["energy"]["label"] == "Energie im Zeitraum"
    assert cards["peak"]["value"] == "150 kW" and cards["peak"]["sub"] == "am 08.02.2023 10:00"
    assert items(analyze(*a_year()), DE)["base_percentile"]["value"] == "50 kW"
    assert cards["base_percentile"]["label"] == "Grundlast (95-%-Wert)" and cards["base_night"]["label"] == "Grundlast (Nacht)"
    assert cards["utilization"]["sub"] == "Erst ab 330 Tagen" and cards["load_factor"]["label"] == "Lastfaktor"


def test_a_profile_without_a_night_has_a_dash_and_says_so():
    index = pd.date_range("2023-02-06 06:00", periods=12, freq="60min", tz=ZONE)

    card = items(analyze(pd.Series(np.full(12, 40.0), index=index), 60))["base_night"]

    assert (card["value"], card["sub"]) == ("–", "No night in the data")


def test_every_card_explains_itself_and_no_text_has_a_gap_in_it():
    for tr in (EN, DE):
        for card in kpi_items(analyze(*week()), tr):
            assert card["help"] and "{" not in card["help"] and "analysis." not in card["help"], card["key"]
            assert "{" not in card["label"] and "{" not in (card["sub"] or "") and "analysis." not in card["label"]


def test_the_explanation_of_the_peak_says_that_the_real_peak_is_higher_if_the_time_step_is_longer_than_a_quarter_of_an_hour():
    quarter = items(analyze(*week("15min")))["peak"]["help"]
    hourly = items(analyze(*week("60min")))["peak"]["help"]

    assert "quarter-hour" in quarter and "longer than a quarter" not in quarter
    assert "longer than a quarter of an hour" in hourly and hourly.startswith(quarter)


def test_the_two_base_loads_have_different_explanations():
    cards = items(analyze(*week()))

    assert "95 %" in cards["base_percentile"]["help"] and "night" in cards["base_night"]["help"]
    assert cards["base_percentile"]["help"] != cards["base_night"]["help"]


def test_a_value_with_decimals_is_written_with_the_decimal_sign_of_the_language():
    series, step = week()
    series[series == 150.0] = 150.5

    cards_de, cards_en = items(analyze(series, step), DE), items(analyze(series, step), EN)

    assert cards_de["peak"]["value"] == "150,5 kW" and cards_en["peak"]["value"] == "150.5 kW"


def test_all_the_states_are_in_the_order_of_their_names_in_each_language():
    assert list(state_options(DE).values()) == [
        "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen", "Mecklenburg-Vorpommern",
        "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"]
    assert list(state_options(EN).values()) == [
        "Baden-Württemberg", "Bavaria", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hesse", "Lower Saxony",
        "Mecklenburg-Western Pomerania", "North Rhine-Westphalia", "Rhineland-Palatinate", "Saarland", "Saxony", "Saxony-Anhalt",
        "Schleswig-Holstein", "Thuringia"]