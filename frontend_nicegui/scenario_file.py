"""The file of a scenario that is saved from the page: what it holds and what it is called.

No NiceGUI code in here, so it is easy to test. The file is the layout that the tool opens again (ScenarioV2 as
JSON, with its time series): what the visitor saves can be opened in the page, and it stays with the visitor; the
server keeps nothing.
"""

import re
import unicodedata

DEFAULT_FILE_NAME = "scenario"
MAX_FILE_NAME_LENGTH = 60
MEDIA_TYPE = "application/json"


def scenario_bytes(scenario):
    """The bytes of the file of a scenario (compact JSON: a time series of a year has thousands of values)."""

    return scenario.model_dump_json().encode("utf-8")


def file_name_for(name):
    """A file name for a scenario name: letters, digits, '-' and '_', no accents, and '.json'.
    'PV + Batterie, Größe 5' gives 'pv_batterie_grosse_5.json'; a name without letters or digits gives 'scenario.json'."""

    plain = unicodedata.normalize("NFKD", str(name or "").replace("ß", "ss")).encode("ascii", "ignore").decode("ascii")
    words = re.sub(r"[^a-z0-9-]+", "_", plain.lower()).strip("_-")[:MAX_FILE_NAME_LENGTH].strip("_-")

    return f"{words or DEFAULT_FILE_NAME}.json"