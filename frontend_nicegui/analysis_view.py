"""What the page of the analysis of a load profile shows, as plain data: the names of the German states, the choices of the
holidays and of the period, and the cards of the key figures with their explanations. No NiceGUI code in here, so it is easy
to test."""

from backend.load_analysis import YEAR_DAYS

ALL_YEARS = "all"                                    # the choice of the whole profile (the value of the year is None)

STATE_TEXTS = {
    "BW": "state.BW", "BY": "state.BY", "BE": "state.BE", "BB": "state.BB", "HB": "state.HB", "HH": "state.HH",
    "HE": "state.HE", "MV": "state.MV", "NI": "state.NI", "NW": "state.NW", "RP": "state.RP", "SL": "state.SL",
    "SN": "state.SN", "ST": "state.ST", "SH": "state.SH", "TH": "state.TH",
}


def state_options(tr):
    """The states to choose from as {code: name}, in the order of their names in the language of the page."""

    names = {code: tr(key) for code, key in STATE_TEXTS.items()}

    return dict(sorted(names.items(), key=lambda item: item[1].lower()))


def year_options(years, tr):
    """The periods to choose from as {value: text}: the whole profile and each calendar year that it has. `years` is
    [(year, days)] (LoadAnalysis.years). Empty if the profile is within one year."""

    if len(years) < 2:
        return {}

    return {ALL_YEARS: tr("analysis.settings.period_all"), **{str(year): str(year) for year, _ in years}}


def stamp_text(stamp, tr):
    return stamp.strftime(tr("profile.stamp_format"))


def kpi_items(analysis, tr):
    """The cards of the key figures as a list of dicts with `key`, `label`, `value`, `sub` (a line below the value or None)
    and `help` (what the figure means)."""

    kpis = analysis.kpis
    unit_kw = lambda value: f"{tr.number(round(value, 1))} kW"                                    # noqa: E731
    help_peak = tr("analysis.help.peak") + (f" {tr('analysis.help.peak_coarse')}" if analysis.step_minutes > 15 else "")

    if kpis.yearly:
        gaps = kpis.energy_estimate_kwh - kpis.energy_kwh
        energy_sub = (tr("analysis.kpi.energy_gaps", energy=tr.integer(int(round(gaps)))) if kpis.missing_share > 0 else None)
        energy_label = tr("analysis.kpi.energy_year")
    else:
        energy_sub = tr.plural("analysis.kpi.days", int(round(kpis.days)))
        energy_label = tr("analysis.kpi.energy_period")

    return [
        dict(key="energy", label=energy_label, value=f"{tr.integer(int(round(kpis.energy_kwh)))} kWh", sub=energy_sub,
             help=tr("analysis.help.energy")),
        dict(key="peak", label=tr("analysis.kpi.peak"), value=unit_kw(kpis.peak_kw),
             sub=tr("analysis.kpi.peak_when", time=stamp_text(kpis.peak_time, tr)), help=help_peak),
        dict(key="base_percentile", label=tr("analysis.kpi.base_percentile"), value=unit_kw(kpis.base_percentile_kw), sub=None,
             help=tr("analysis.help.base_percentile")),
        dict(key="base_night", label=tr("analysis.kpi.base_night"),
             value=unit_kw(kpis.base_night_kw) if kpis.base_night_kw is not None else "–",
             sub=None if kpis.base_night_kw is not None else tr("analysis.kpi.base_night_none"), help=tr("analysis.help.base_night")),
        dict(key="utilization", label=tr("analysis.kpi.utilization"),
             value=f"{tr.integer(int(round(kpis.utilization_hours)))} h" if kpis.utilization_hours is not None else "–",
             sub=None if kpis.utilization_hours is not None else tr("analysis.kpi.utilization_none", days=YEAR_DAYS),
             help=tr("analysis.help.utilization")),
        dict(key="load_factor", label=tr("analysis.kpi.load_factor"),
             value=f"{tr.number(round(100 * kpis.load_factor))} %" if kpis.load_factor is not None else "–", sub=None,
             help=tr("analysis.help.load_factor")),
    ]