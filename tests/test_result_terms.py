"""The words of a result: nothing that the backend writes in English is missing from the table, and the table is right."""

import ast
import json
from pathlib import Path

import pytest

from backend import kpis, service_v2
from backend.i18n import ENGLISH, Translator
from backend.kpis import CAPACITY_UNITS, CATEGORY_ENERGY, CATEGORY_INVEST, CATEGORY_REVENUE
from backend.plotting import NODE_NAMES
from backend.results import Table
from backend.scenario_v2 import ScenarioV2
from frontend_nicegui.result_terms import (
    DECIMALS,
    TERMS,
    TEXT_COLUMNS,
    bus_label,
    cell_text,
    node_label,
    table_for_display,
    term,
)
from tests.helpers import needs_cbc
from tests.test_solving import many_components

DE = Translator("de")
CATALOGS = Path(__file__).resolve().parent.parent / "backend" / "i18n"
EN_CATALOG = json.loads((CATALOGS / "en.json").read_text(encoding="utf-8"))
DE_CATALOG = json.loads((CATALOGS / "de.json").read_text(encoding="utf-8"))
EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"

SAME_IN_EVERY_LANGUAGE = {"kW", "kWh"}                      # not in the table at all


def written_by_the_key_figures():
    """Every label and help text that kpis.compute_key_figures can write (read from its source)."""

    tree = ast.parse(Path(kpis.__file__).read_text(encoding="utf-8"))
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "compute_key_figures")
    found = set()

    for node in ast.walk(function):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in ("label", "help"):
                    found.update(n.value for n in ast.walk(value) if isinstance(n, ast.Constant) and isinstance(n.value, str))

    return found


def written_by_real_results():
    """Every text of a real result: the labels of the figures, the columns, and the cells of the text columns."""

    found = set()
    scenarios = [many_components(steps=24), ScenarioV2.load(EXAMPLES / "pv_and_grid.json")]
    fixed = many_components(steps=24)
    for component in fixed.components:
        if component.template == "pv":
            component.blocks["capacity"].update(mode="fixed", capacity=5.0)
    scenarios.append(fixed)

    for scenario in scenarios:
        result = service_v2.run(scenario)
        tables = [result.cost_breakdown, result.capacities] + [t for b in result.buses.values() for t in (b.supply, b.use)]
        for figure in result.key_figures:
            found.update((figure.label, figure.help))
        for table in tables:
            found.update(table.columns)
            for position, name in enumerate(table.columns):
                if name in TEXT_COLUMNS:
                    found.update(row[position] for row in table.rows)

    return found


# ---------------------------------------------------------------------------
# nothing is missing
# ---------------------------------------------------------------------------

def test_every_text_that_the_backend_can_write_is_in_the_table():
    backend = set(NODE_NAMES.values()) | {CATEGORY_INVEST, CATEGORY_ENERGY, CATEGORY_REVENUE}
    backend |= set(CAPACITY_UNITS.values()) - SAME_IN_EVERY_LANGUAGE
    backend |= written_by_the_key_figures()
    backend |= {"Item", "Category", "Cost (€)", "Component", "Mode", "Capacity", "Unit", "Annualised cost (€/a)",
                "Energy (kWh)", "Share (%)", "optimized", "fixed (input)", "Demand"}

    assert sorted(backend - set(TERMS)) == []


@needs_cbc
def test_every_text_of_a_real_result_is_in_the_table():
    # the figures, the columns and the names that the real runs write (invest and fixed size, three buses)
    assert sorted(text for text in written_by_real_results() - SAME_IN_EVERY_LANGUAGE if text not in TERMS) == []


def test_the_table_has_nothing_that_the_backend_does_not_write():
    backend = set(NODE_NAMES.values()) | {CATEGORY_INVEST, CATEGORY_ENERGY, CATEGORY_REVENUE}
    backend |= set(CAPACITY_UNITS.values()) | written_by_the_key_figures()
    backend |= {"Item", "Category", "Cost (€)", "Component", "Mode", "Capacity", "Unit", "Annualised cost (€/a)",
                "Energy (kWh)", "Share (%)", "optimized", "fixed (input)", "Demand"}

    assert sorted(set(TERMS) - backend) == []


def test_the_columns_with_decimals_are_columns_that_the_backend_writes():
    columns = {"Cost (€)", "Annualised cost (€/a)", "Energy (kWh)", "Share (%)", "Capacity"}

    assert set(DECIMALS) == columns and set(TEXT_COLUMNS) == {"Item", "Category", "Component", "Mode", "Unit"}


# ---------------------------------------------------------------------------
# the table itself
# ---------------------------------------------------------------------------

def test_every_term_has_a_text_in_both_catalogs_and_the_english_one_is_the_text_of_the_backend():
    for english, key in TERMS.items():
        assert key in EN_CATALOG and key in DE_CATALOG, key
        assert EN_CATALOG[key] == english, key                 # the English page says exactly what the backend wrote


def test_the_german_text_of_every_term_is_a_translation_and_has_no_placeholder():
    for english, key in TERMS.items():
        assert DE_CATALOG[key] != english and "{" not in DE_CATALOG[key], key


def test_two_terms_do_not_share_a_key():
    assert len(set(TERMS.values())) == len(TERMS)


def test_the_german_words_are_the_ones_of_the_forms():
    # the same thing is called the same in the forms and in the result
    for key in ("pv", "wind", "gas_boiler", "heat_pump", "heating_rod", "chp", "battery", "heat_storage", "demand", "heat_demand"):
        assert term(DE, NODE_NAMES[key]) == DE_CATALOG[f"component.{key}.label"], key


# ---------------------------------------------------------------------------
# term, bus_label, node_label
# ---------------------------------------------------------------------------

def test_a_term_is_translated_and_an_unknown_text_is_shown_as_it_is():
    assert term(DE, "Grid import") == "Netzbezug" and term(ENGLISH, "Grid import") == "Grid import"
    assert term(DE, "kW") == "kW" and term(DE, "something else") == "something else"
    assert term(DE, "Self-sufficiency") == "Autarkie" and term(ENGLISH, "Self-sufficiency") == "Self-sufficiency"


def test_the_help_of_a_figure_is_translated_as_a_sentence():
    english = "Electricity bought from the grid."

    assert term(DE, english) == "Strom, der aus dem Netz bezogen wird." and term(ENGLISH, english) == english


@pytest.mark.parametrize("bus, english, german", [
    ("electricity", "Electricity", "Strom"), ("heat", "Heat", "Wärme"), ("gas", "Gas", "Gas"),
    ("hydrogen", "Hydrogen", "Hydrogen"), ("district_heat", "District heat", "District heat"),
])
def test_the_name_of_an_energy_carrier(bus, english, german):
    assert bus_label(ENGLISH, bus) == english and bus_label(DE, bus) == german


@pytest.mark.parametrize("node, english, german", [
    ("grid_import", "Grid import", "Netzbezug"), ("heat_pump", "Heat pump", "Wärmepumpe"),
    ("demand", "Electricity demand", "Strombedarf"), ("electricity", "Electricity", "Strom"),
    ("heat", "Heat", "Wärme"), ("some_new_part", "Some New Part", "Some New Part"),
])
def test_the_name_of_what_a_flow_comes_from_or_goes_to(node, english, german):
    assert node_label(ENGLISH, node) == english and node_label(DE, node) == german


# ---------------------------------------------------------------------------
# the cells and the tables
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("column, value, english, german", [
    ("Cost (€)", 1234.56, "1,235", "1.235"),
    ("Cost (€)", -0.4, "-0", "-0"),
    ("Annualised cost (€/a)", 19080.3, "19,080", "19.080"),
    ("Energy (kWh)", 120909.09, "120,909", "120.909"),
    ("Share (%)", 24.8120, "24.8", "24,8"),
    ("Capacity", 2471.0446, "2,471.0", "2.471,0"),
    ("Capacity", 0.0, "0.0", "0,0"),
    ("Other column", 12.5, "12.5", "12,5"),
])
def test_a_number_has_the_decimals_of_its_column_and_the_separators_of_the_language(column, value, english, german):
    assert cell_text(column, value, ENGLISH) == english and cell_text(column, value, DE) == german


def test_a_text_cell_is_translated_only_in_a_column_of_text_and_an_empty_cell_is_a_dash():
    assert cell_text("Component", "Heat pump", DE) == "Wärmepumpe"
    assert cell_text("Mode", "optimized", DE) == "optimiert" and cell_text("Unit", "kW (heat)", DE) == "kW (Wärme)"
    assert cell_text("Category", "Revenue", DE) == "Erlös"
    assert cell_text("Anything", "Heat pump", DE) == "Heat pump"            # a column that is not one of text
    assert cell_text("Capacity", None, DE) == "-" and cell_text("Component", None, DE) == "-"


def test_a_table_for_the_page_has_translated_columns_aligned_by_what_they_hold_and_cells_by_position():
    table = Table(columns=["Component", "Capacity", "Unit"], rows=[["Heat pump", 12.34, "kW (heat)"], ["PV", 0.0, "kW"]])

    columns, rows = table_for_display(table, DE)

    assert [c["label"] for c in columns] == ["Bauteil", "Größe", "Einheit"]
    assert [c["align"] for c in columns] == ["left", "right", "left"]
    assert [c["field"] for c in columns] == ["0", "1", "2"]
    assert rows == [{"0": "Wärmepumpe", "1": "12,3", "2": "kW (Wärme)"}, {"0": "PV-Anlage", "1": "0,0", "2": "kW"}]


def test_a_table_with_two_columns_of_the_same_name_or_a_strange_name_still_works():
    table = Table(columns=["a.b", "a.b", "c d"], rows=[[1.0, 2.0, "x"]])

    columns, rows = table_for_display(table, ENGLISH)

    assert [c["field"] for c in columns] == ["0", "1", "2"] and rows == [{"0": "1", "1": "2", "2": "x"}]


def test_an_empty_table_gives_columns_and_no_rows():
    columns, rows = table_for_display(Table(columns=["Item", "Cost (€)"]), DE)

    assert [c["label"] for c in columns] == ["Posten", "Kosten (€)"] and rows == []