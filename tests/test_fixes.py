"""Do the repairs that the checks propose really repair?

A finding can carry repairs: each is a tuple of components that would solve it (the interfaces make a button
of it). A button that does not solve what it promises is worse than none, so this goes through every system
that can be built from the components (2 to the power of 13 = 8192) and tries every repair that is proposed.
"""

import itertools
import random

import pytest

from backend.component_specs import INFO
from backend.i18n import Translator
from backend.system_check import check_system
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.names import component_label, fix_label

KEYS = list(INFO)


def all_systems():
    for size in range(len(KEYS) + 1):
        for combo in itertools.combinations(KEYS, size):
            yield frozenset(combo)


def same_finding(a, b):
    return (a.level, a.code, a.params) == (b.level, b.code, b.params)


def repairs():
    """Every (system, finding, repair) that the system check proposes, for all systems."""

    for system in all_systems():
        for finding in check_system(system):
            for repair in finding.fixes:
                yield system, finding, repair


def test_every_repair_that_is_proposed_removes_the_finding_it_belongs_to():
    tried, failures = 0, []

    for system, finding, repair in repairs():
        tried += 1
        if any(same_finding(finding, f) for f in check_system(system | set(repair))):
            failures.append((sorted(system), finding.code, repair))

    assert tried > 10_000                                       # the walk through the systems did take place
    assert failures == []


def test_a_repair_names_components_that_exist_and_that_are_missing():
    for system, finding, repair in repairs():
        assert repair, finding.code                              # not an empty button
        assert all(key in INFO for key in repair), (finding.code, repair)
        assert not set(repair) & system, (finding.code, repair)  # nothing that is chosen already
        assert len(set(repair)) == len(repair), (finding.code, repair)


def test_a_finding_does_not_propose_the_same_repair_twice():
    for system in all_systems():
        for finding in check_system(system):
            assert len(set(finding.fixes)) == len(finding.fixes), finding.code


def test_two_ways_that_lack_the_same_thing_are_one_repair():
    # a boiler and a CHP plant are there and both only lack the gas import: one button, not two
    finding = next(f for f in check_system({"heat_demand", "gas_boiler", "chp"}) if f.code == "heat_not_supplied")

    assert finding.fixes == (("gas_import",), ("heat_pump", "grid"), ("heating_rod", "grid"))


def test_every_repair_that_can_be_proposed_has_the_text_of_a_button_in_both_languages():
    proposed = {repair for _, _, repair in repairs()}

    assert len(proposed) >= 15                                   # (the walk found them all: 18 today)
    for language in ("en", "de"):
        tr = Translator(language)
        for repair in proposed:
            text = fix_label(tr, repair)
            assert "{" not in text and all(component_label(tr, key) in text for key in repair), (language, repair)


def test_the_text_of_a_button_names_what_it_adds_in_the_language_of_the_reader():
    assert fix_label(Translator("en"), ("chp", "gas_import")) == "Add CHP plant + Gas import"
    assert fix_label(Translator("de"), ("chp", "gas_import")) == "BHKW + Gasbezug hinzufügen"
    assert fix_label(Translator("de"), ("grid",)) == "Stromnetz hinzufügen"


def test_the_repair_for_an_unused_feed_in_names_the_heat_demand_that_a_chp_plant_needs():
    # a CHP plant only supplies electricity when its gas arrives and its heat is used; the repair used to leave
    # out the heat demand, so that the warning stayed after the button was pressed (half of the systems)
    finding = next(f for f in check_system({"grid_feedin"}) if f.code == "feedin_unused")

    assert finding.fixes == (("pv",), ("wind",), ("chp", "gas_import", "heat_demand"))
    assert not any(f.code == "feedin_unused" for f in check_system({"grid_feedin", "chp", "gas_import", "heat_demand"}))

    finding = next(f for f in check_system({"grid_feedin", "heat_demand"}) if f.code == "feedin_unused")
    assert finding.fixes[2] == ("chp", "gas_import")             # the heat demand is there: only two are missing


def test_a_repair_in_the_draft_removes_the_finding_in_the_draft_too():
    # the same thing through the draft and the whole check of the scenario (a sample: it is slower)
    rng = random.Random(11)
    tried = 0

    for _ in range(150):
        system = [key for key in KEYS if rng.random() < 0.4]
        draft = ScenarioDraft(steps=24)
        for key in system:
            draft.set(key, True)

        for finding in draft.findings():
            for repair in finding.fixes:
                fixed = ScenarioDraft(steps=24)
                for key in set(system) | set(repair):
                    fixed.set(key, True)
                tried += 1
                assert not any(same_finding(finding, f) for f in fixed.findings()), (system, finding.code, repair)

    assert tried > 100


@pytest.mark.parametrize("key", KEYS)
def test_every_component_can_be_added_to_the_draft(key):
    draft = ScenarioDraft(steps=24)

    draft.set(key, True)

    assert draft.is_selected(key)