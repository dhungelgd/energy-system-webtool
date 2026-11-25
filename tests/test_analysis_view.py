"""What the page of the analysis shows as plain data: the states, the periods and the cards of the key figures."""

import numpy as np
import pandas as pd

from backend.i18n import Translator
from backend.load_analysis import AnalysisOptions, analyze
from frontend_nicegui.analysis_view import (
    ALL_YEARS,
    CAP_DEFAULT_SHARE,
    CAP_MAX_SHARE,
    CAP_MIN_SHARE,
    cap_items,
    cap_limit,
    day_counts_text,
    kpi_items,
    near_peak_text,
    peak_rows,
    profile_in_period,
    state_options,
    year_options,
)
from frontend_nicegui.page_state import PageState
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


def test_the_days_of_a_year_are_counted_by_the_type_of_day_and_the_state_of_the_holidays_is_named():
    series, step = a_year()                                                   # 2023: 248 workdays, 52 Saturdays, 65 Sundays and holidays in Bavaria

    bavaria = day_counts_text(analyze(series, step), EN)
    north_rhine = day_counts_text(analyze(series, step, AnalysisOptions(state="NW")), DE)

    assert bavaria == "Days in the period: Workday: 248 · Saturday: 52 · Sunday or holiday: 65 (holidays of Bavaria)."
    assert north_rhine.startswith("Tage im Zeitraum: Werktag: 2") and north_rhine.endswith("(Feiertage von Nordrhein-Westfalen).")
    assert "Samstag: 52" in north_rhine


def test_the_days_of_a_week_are_counted_too():
    assert day_counts_text(analyze(*week()), EN) == "Days in the period: Workday: 5 · Saturday: 1 · Sunday or holiday: 1 (holidays of Bavaria)."


# ---------------------------------------------------------------------------
# the peaks tab
# ---------------------------------------------------------------------------

def test_the_highest_peaks_are_rows_of_text_with_the_date_the_time_the_power_and_the_kind_of_day():
    rows = peak_rows(analyze(*week()), EN)

    assert len(rows) == 5
    assert rows[0] == {"rank": "1", "date": "2023-02-08", "time": "10:00", "power": "150", "daytype": "Workday", "season": "Winter"}
    assert rows[1] == {"rank": "2", "date": "2023-02-06", "time": "08:00", "power": "100", "daytype": "Workday", "season": "Winter"}
    assert [row["rank"] for row in rows] == ["1", "2", "3", "4", "5"]


def test_the_rows_are_in_german_with_the_date_and_the_names_of_the_language():
    rows = peak_rows(analyze(*week()), DE)

    assert rows[0] == {"rank": "1", "date": "08.02.2023", "time": "10:00", "power": "150", "daytype": "Werktag", "season": "Winter"}


def test_a_peak_on_a_saturday_and_in_summer_names_its_kind_of_day_and_its_season():
    series, step = week(start="2023-06-05")
    series[(series.index.dayofweek == 5) & (series.index.hour == 11)] = 200.0

    first = peak_rows(analyze(series, step), EN)[0]

    assert (first["daytype"], first["season"], first["power"]) == ("Saturday", "Summer", "200")


def test_the_limit_is_a_share_of_the_peak_and_a_share_outside_the_range_is_brought_into_it():
    analysis = analyze(*week())

    assert cap_limit(analysis, 95) == 142.5 and cap_limit(analysis, 60) == 90.0 and cap_limit(analysis, 100) == 150.0
    assert cap_limit(analysis, 10) == 75.0 and cap_limit(analysis, 500) == 150.0 and (CAP_MIN_SHARE, CAP_MAX_SHARE) == (50, 100)


def test_what_is_above_a_limit_is_shown_as_figures_that_can_be_worked_out_by_hand():
    items = {item["key"]: item for item in cap_items(analyze(*week()), 60, EN)}

    assert list(items) == ["limit", "reduction", "hours", "energy", "days", "longest"]
    assert items["limit"]["value"] == "90 kW (60 %)" and items["reduction"]["value"] == "60 kW" and items["hours"]["value"] == "40 h"
    assert items["energy"]["value"] == "450 kWh" and items["days"]["value"] == "5" and items["longest"]["value"] == "8 h"


def test_the_figures_above_a_limit_are_in_german_and_a_limit_near_the_peak_has_little_above_it():
    items = {item["key"]: item for item in cap_items(analyze(*week()), 95, DE)}

    assert items["limit"]["label"] == "Grenze" and items["limit"]["value"] == "142,5 kW (95 %)" and items["reduction"]["value"] == "7,5 kW"
    assert items["hours"]["value"] == "1 h" and items["energy"]["value"] == "8 kWh" and items["longest"]["label"] == "Längste Zeit am Stück über der Grenze"


def test_how_rare_the_highest_values_are_is_said_in_a_sentence():
    assert near_peak_text(analyze(*week()), EN) == "At 90 % of the peak (135 kW) or more: 1 h (days with such values: 1)."
    assert near_peak_text(analyze(*week()), DE) == "Bei 90 % der Spitze (135 kW) oder mehr: 1 h (Tage mit solchen Werten: 1)."


def test_the_slider_begins_at_the_share_that_the_state_of_the_page_has():
    assert PageState().profile_cap_share == CAP_DEFAULT_SHARE == 95


def test_the_profile_of_the_period_is_the_whole_profile_or_the_year_that_was_analysed():
    series = pd.Series(np.arange(2 * 365 * 24, dtype=float), index=pd.date_range("2022-01-01", periods=2 * 365 * 24, freq="60min", tz=ZONE))

    whole = analyze(series, 60, AnalysisOptions(year=None))
    year = analyze(series, 60, AnalysisOptions(year=2023))

    assert len(profile_in_period(series, whole)) == 2 * 8760
    assert len(profile_in_period(series, year)) == 8760 and profile_in_period(series, year).index[0].year == 2023