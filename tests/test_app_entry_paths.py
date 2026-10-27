"""frontend/app.py must also work as the main file of a deployment.

Streamlit Community Cloud starts the main file of an app with only its own
folder on the import path, and the main file cannot be changed after the app is
deployed. Under pytest the repository root is always on the path (pytest.ini),
so these tests start a fresh Python process and take the root off the path, as
a deployment would.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parent.parent

# what a deployment does: only the folder of the main file is on the path
SCRIPT = textwrap.dedent('''
    import importlib.util, json, os, sys

    app_file, root = sys.argv[1], os.path.realpath(sys.argv[2])
    sys.path = [p for p in sys.path if os.path.realpath(p or os.getcwd()) != root]
    sys.meta_path = [f for f in sys.meta_path
                     if "editable" not in (type(f).__module__ + type(f).__name__).lower()]
    sys.path.insert(0, os.path.dirname(os.path.realpath(app_file)))

    if importlib.util.find_spec("backend") is not None:
        print("CANNOT_SIMULATE")
        sys.exit(0)

    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(app_file, default_timeout=120)
    app.run()
    print(json.dumps({
        "exceptions": len(app.exception),
        "errors": [e.value for e in app.error],
        "titles": [t.value for t in app.title],
    }))
''')


def start_in_fresh_process(app_file, tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(app_file), str(ROOT)],
        cwd=tmp_path, capture_output=True, text=True, timeout=300,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]

    if lines and lines[-1] == "CANNOT_SIMULATE":
        pytest.skip("the project is installed normally here, so a deployment cannot be simulated")

    assert lines, f"the process printed nothing:\n{result.stderr[-2000:]}"
    return json.loads(lines[-1])


def test_frontend_app_works_as_the_main_file_of_a_deployment(tmp_path):
    outcome = start_in_fresh_process(ROOT / "frontend" / "app.py", tmp_path)

    assert outcome["exceptions"] == 0
    assert outcome["errors"] == []
    assert outcome["titles"] == ["Energy System Web Tool (oemof)"]


def test_a_lone_copy_without_the_project_still_explains_what_is_missing(tmp_path):
    lone = tmp_path / "frontend"
    lone.mkdir()
    (lone / "app.py").write_text((ROOT / "frontend" / "app.py").read_text(encoding="utf-8"), encoding="utf-8")

    outcome = start_in_fresh_process(lone / "app.py", tmp_path)

    assert outcome["exceptions"] == 0
    assert any("pip install -e ." in error for error in outcome["errors"])