"""One-time change of the texts of step 17: the view 'Daily averages' of the flows chart is gone, so its text is too.
Delete this file afterwards: a test fails while a merge_*.py file lies in the project folder."""
import json
from pathlib import Path

REMOVE = ("result.range.daily",)

folder = Path(__file__).resolve().parent / "backend" / "i18n"
for language in ("en", "de"):
    path = folder / f"{language}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in REMOVE:
        data.pop(key, None)
    path.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(language, len(data), "texts")
print(len(REMOVE), "text removed per language")