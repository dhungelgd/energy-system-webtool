"""What the page remembers while one visitor uses it.

No NiceGUI code in here, so it is easy to test. The page is drawn from this state: when
the language changes, the whole page is drawn again from it, and nothing the visitor has
done is lost (the scenario that is being built, the file that was opened, the result).
"""

from dataclasses import dataclass

from backend.i18n import DEFAULT_LANGUAGE, LANGUAGES, Translator
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.scenario_view import ScenarioFileError, load_scenario


@dataclass
class OpenedFile:
    """A scenario that was opened from a file."""

    scenario: object
    file_name: str


class PageState:
    """The language, the scenario being built, the opened file, and the run."""

    def __init__(self, language=DEFAULT_LANGUAGE):
        self.draft = ScenarioDraft()
        self.opened = None            # an OpenedFile
        self.file_error = None        # a Msg: why the last file could not be opened
        self.result = None            # the ScenarioResult of the opened scenario
        self.run_error = None         # a Msg: why the last run did not give a result
        self.running = False
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

    # ----- the run ---------------------------------------------------------

    def start_run(self):
        """Note that a run starts. Returns what is being run, or None if nothing can be started now."""

        if self.running or self.opened is None:
            return None

        self.running = True
        self.result = None
        self.run_error = None
        return self.opened

    def finish_run(self, started, result=None, error=None):
        """Note that the run is over. The outcome is only kept if the same file is still open."""

        self.running = False

        if self.opened is started:
            self.result = result
            self.run_error = error