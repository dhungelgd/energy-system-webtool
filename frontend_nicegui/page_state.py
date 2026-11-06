"""What the page remembers while one visitor uses it.

No NiceGUI code in here, so it is easy to test. The page is drawn from this state: when
the language changes, the whole page is drawn again from it, and nothing the visitor has
done is lost (the scenario that is being built, the file that was opened, the result).
"""

import time
from dataclasses import dataclass

from backend import service_v2
from backend.i18n import DEFAULT_LANGUAGE, LANGUAGES, Translator
from frontend_nicegui.draft import DEFAULT_NAME, ScenarioDraft
from frontend_nicegui.scenario_view import ScenarioFileError, load_scenario


@dataclass
class OpenedFile:
    """A scenario that was opened from a file."""

    scenario: object
    file_name: str


@dataclass
class DraftRun:
    """A run of the scenario that is being built: what was run, and what came out of it."""

    scenario: object              # the scenario that was run (a copy: the draft goes on changing)
    result: object = None         # the ScenarioResult
    error: object = None          # a Msg: why there is no result


def same_scenario(a, b):
    """True if two scenarios are the same apart from their name (a name that nobody chose follows the language)."""

    return a.model_dump(exclude={"name"}) == b.model_dump(exclude={"name"})


class PageState:
    """The language, the scenario being built, the opened file, and the runs."""

    def __init__(self, language=DEFAULT_LANGUAGE):
        self.draft = ScenarioDraft()
        self.uploads = {}             # component key -> the UploadSession of a file that is being prepared
        self.series_wanted = set()    # components switched to "time series" that have none yet
        self.opened = None            # an OpenedFile
        self.file_error = None        # a Msg: why the last file could not be opened
        self.result = None            # the ScenarioResult of the opened scenario
        self.run_error = None         # a Msg: why the last run did not give a result
        self.running = False          # a run is going on (of the draft or of the opened file: one at a time)
        self.running_draft = False    # ... and it is the run of the draft
        self.clock = time.monotonic   # where the time comes from (the tests put their own here)
        self.run_started = None       # the time on the clock when the run that is going on started
        self.draft_run = None         # a DraftRun: the last run of the scenario that is being built
        self.language_toggle = None   # the page puts its language switch here, to block it during a run
        self.language = language

    # ----- the language ----------------------------------------------------

    @property
    def language(self):
        return self._tr.language

    @language.setter
    def language(self, value):
        if value not in LANGUAGES:
            raise ValueError(f"unknown language '{value}'")
        self._tr = Translator(value)

    @property
    def tr(self):
        return self._tr

    # ----- time series that are being prepared -----------------------------

    def drop_stale_uploads(self):
        """Forget the files and choices of components that are not part of the draft any more."""

        for key in [key for key in self.uploads if not self.draft.is_selected(key)]:
            del self.uploads[key]
        self.series_wanted = {key for key in self.series_wanted if self.draft.is_selected(key)}

    # ----- the opened file -------------------------------------------------

    def open_file(self, content, file_name):
        """Open the bytes of a scenario file. A file that cannot be opened is explained (file_error)."""

        self.result = None
        self.run_error = None

        try:
            scenario = load_scenario(content)
        except ScenarioFileError as error:
            self.opened = None
            self.file_error = error.msg
        else:
            self.opened = OpenedFile(scenario, file_name)
            self.file_error = None

    # ----- how long the run has been going on ------------------------------

    def elapsed(self):
        """The seconds since the run that is going on started (0 if nothing is running)."""

        return 0.0 if self.run_started is None else max(0.0, self.clock() - self.run_started)

    # ----- the run of the scenario that is being built ---------------------

    def start_draft_run(self, default_name=DEFAULT_NAME):
        """Note that a run of the draft starts. Returns the DraftRun (with a copy of the scenario that is run),
        or None if nothing can be started now: a run is going on, nothing is chosen, or the check finds errors."""

        if self.running or len(self.draft) == 0:
            return None

        scenario = self.draft.scenario(default_name)
        if any(finding.level == "error" for finding in service_v2.check(scenario)):
            return None

        self.running = True
        self.running_draft = True
        self.run_started = self.clock()
        self.draft_run = DraftRun(scenario)          # the result of an earlier run is gone
        return self.draft_run

    def finish_draft_run(self, started, result=None, error=None):
        """Note that the run of the draft is over."""

        self.running = False
        self.running_draft = False
        self.run_started = None

        if self.draft_run is started:
            started.result = result
            started.error = error

    def draft_changed_since_run(self):
        """True if the draft is not the scenario that was run any more (a result of a run that is over, or its error)."""

        run = self.draft_run

        if run is None or (run.result is None and run.error is None):
            return False

        return not same_scenario(run.scenario, self.draft.scenario())

    # ----- the run of the opened file ----------------------------------------

    def start_run(self):
        """Note that a run starts. Returns what is being run, or None if nothing can be started now."""

        if self.running or self.opened is None:
            return None

        self.running = True
        self.run_started = self.clock()
        self.result = None
        self.run_error = None
        return self.opened

    def finish_run(self, started, result=None, error=None):
        """Note that the run is over. The outcome is only kept if the same file is still open."""

        self.running = False
        self.run_started = None

        if self.opened is started:
            self.result = result
            self.run_error = error