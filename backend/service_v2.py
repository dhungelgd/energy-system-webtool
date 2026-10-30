"""check and run for a layout 2 scenario: what a frontend calls.

    findings = check(scenario)        # errors and warnings, before a run
    result = run(scenario)            # a ScenarioResult, or a ScenarioError

The same two calls as in `service.py`, for layout 2. When the old engine is
replaced, this module becomes `service.py`; only the inside changes.

Today the scenario runs on the old engine through the adapter in
`scenario_convert.py`, which cannot run everything a layout 2 scenario can hold.
What it cannot run is reported as an error, so that nothing is dropped silently.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from backend import service
from backend.component_specs import INFO
from backend.findings import Finding
from backend.scenario_checks import check_data
from backend.scenario_convert import engine_gaps, scenario_to_v1
from backend.service import ScenarioNotReady


def check(scenario, labels=None):
    """Errors and warnings for a ScenarioV2 (errors first).

    An error stops the run: something the engine cannot run, or a mistake the
    system check finds. A warning does not: the data look suspicious.

    labels: readable names for the components, by template key. The names of the
    templates are the default.
    """

    names = {key: info.label for key, info in INFO.items()}
    names.update(labels or {})

    gaps = engine_gaps(scenario)
    findings = [Finding("error", gap) for gap in gaps]
    findings.extend(check_data(scenario))

    if not gaps:
        findings.extend(service.check(scenario_to_v1(scenario), labels=names))

    return sorted(findings, key=lambda finding: finding.level != "error")


def run(scenario, include_flows=True):
    """Check a ScenarioV2, optimize it, and return the numbers as a ScenarioResult.

    Raises ScenarioNotReady if there are errors (it holds them as findings), and
    ScenarioError if the model cannot be solved.
    """

    errors = [finding for finding in check(scenario) if finding.level == "error"]
    if errors:
        raise ScenarioNotReady(errors)

    return service.run(scenario_to_v1(scenario), include_flows=include_flows, check_first=False)