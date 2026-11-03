"""Things that must not be left lying in the project folder."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_no_one_time_merge_script_is_left_in_the_project_folder():
    # such a script adds some texts to the catalogs once; it is deleted afterwards, and never committed
    left = sorted(path.name for path in ROOT.glob("merge_*.py"))

    assert left == [], f"delete these files (they were meant to be used once): {left}"