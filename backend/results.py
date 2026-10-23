"""The numbers of a result as plain, saveable data.

`collect_results` returns a dictionary with DataFrames, Plotly figures and an
Excel file. That is fine to show on a page, but it cannot be written to a file,
sent to a browser or compared with another run. A `ScenarioResult` holds the
numbers of a run (headline figures, cost breakdown, capacities, energy shares
per bus, solver information) in a form that

- is made of plain numbers and text only,
- can be written to and read from a JSON file, and
- gives the tables back as DataFrames (`Table.to_frame`).

The hourly flows of every bus are part of it too (`FlowTable`), stored column
by column with the start time and the length of a time step.

This module does not use Streamlit, so any frontend can use it.
"""

import datetime
import math
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# the layout of a saved result; increase it when the layout changes
RESULT_SCHEMA_VERSION = 1

# one cell of a table: a number, a text, or empty
Cell = Union[float, str, None]


def _cell(value):
    """numpy numbers become plain numbers, NaN and infinity become empty."""

    if value is None:
        return None

    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()

    if isinstance(value, (bool, int)):
        return float(value)

    if isinstance(value, float) and not math.isfinite(value):
        return None

    return value


def _number(value):
    value = _cell(value)
    return value if isinstance(value, float) else None


def _name(value):
    """Solver status values are enums; use their plain text."""

    return str(getattr(value, "value", value))


class Table(BaseModel):
    """A small table: column names and rows."""

    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    rows: list[list[Cell]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rows_fit_the_columns(self):
        for number, row in enumerate(self.rows, start=1):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"row {number} has {len(row)} cells, but there are "
                    f"{len(self.columns)} columns"
                )
        return self

    @classmethod
    def from_frame(cls, frame):
        return cls(
            columns=[str(column) for column in frame.columns],
            rows=[
                [_cell(value) for value in row]
                for row in frame.itertuples(index=False, name=None)
            ],
        )

    def to_frame(self):
        frame = pd.DataFrame(self.rows, columns=self.columns)

        # a column with numbers and empty cells (or only empty cells) is a number
        # column with NaN, as in the table the result came from
        for column in frame.columns:
            values = frame[column]
            if len(values) and values.map(lambda v: v is None or isinstance(v, float)).all():
                frame[column] = values.astype(float)

        return frame


class KeyFigure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: Union[float, None]
    unit: str = ""
    help: str = ""


class SolverInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    termination: str
    message: str = ""
    seconds: Union[float, None] = None


class FlowTable(BaseModel):
    """The flows of one bus over time, stored column by column.

    Each column is one connection (for example "grid_import-->electricity") in
    kW. The time of each value follows from the start and the length of a time
    step, so no list of timestamps has to be saved.
    """

    model_config = ConfigDict(extra="forbid")

    start: datetime.datetime
    step_hours: float = Field(gt=0)
    columns: list[str]
    values: list[list[Union[float, None]]]

    @model_validator(mode="after")
    def _columns_fit_the_values(self):
        if len(self.columns) != len(self.values):
            raise ValueError(
                f"{len(self.columns)} column names, but {len(self.values)} lists of values"
            )

        duplicates = sorted({c for c in self.columns if self.columns.count(c) > 1})
        if duplicates:
            raise ValueError(f"column names used twice: {', '.join(duplicates)}")

        lengths = {len(column) for column in self.values}
        if len(lengths) > 1:
            raise ValueError(f"the columns have different lengths: {sorted(lengths)}")

        return self

    @property
    def n_steps(self):
        return len(self.values[0]) if self.values else 0

    @classmethod
    def from_frame(cls, frame):
        """Take the flows of a bus (DataFrame with a DatetimeIndex).

        The empty row at the end that oemof adds (the end of the last time step)
        is not stored; `to_frame` adds it again.
        """

        if not isinstance(frame.index, pd.DatetimeIndex) or len(frame) == 0:
            raise ValueError("the flows need a time index and at least one row")

        # everything up to the last row that has any value
        rows_with_values = np.flatnonzero(frame.notna().any(axis=1).to_numpy())
        if len(rows_with_values) == 0:
            raise ValueError("the flows contain no values")
        real = frame.iloc[: rows_with_values[-1] + 1]

        step = 1.0
        if len(frame.index) > 1:
            differences = frame.index[1:] - frame.index[:-1]
            if (differences != differences[0]).any():
                raise ValueError("the time steps of the flows are not regular")
            step = differences[0].total_seconds() / 3600

        return cls(
            start=frame.index[0].to_pydatetime(),
            step_hours=step,
            columns=[str(column) for column in frame.columns],
            values=[
                [_cell(value) for value in real[column]] for column in real.columns
            ],
        )

    def index(self, with_end_row=False):
        periods = self.n_steps + (1 if with_end_row else 0)
        return pd.date_range(
            start=self.start, periods=periods, freq=pd.Timedelta(hours=self.step_hours)
        )

    def to_frame(self, with_end_row=True):
        """The flows as a DataFrame with a time index.

        with_end_row=True gives the same shape as the flows of a run: one empty
        row at the end, which the plots and the Excel export expect.
        """

        extra = [math.nan] if with_end_row else []

        return pd.DataFrame(
            {
                name: [math.nan if v is None else v for v in column] + extra
                for name, column in zip(self.columns, self.values)
            },
            index=self.index(with_end_row),
            columns=self.columns,
        )


class BusSummary(BaseModel):
    """The energy of one bus (electricity, heat, gas): sums and shares."""

    model_config = ConfigDict(extra="forbid")

    energy_sums: dict[str, float]
    supply: Table
    use: Table
    flows: Union[FlowTable, None] = None


class ScenarioResult(BaseModel):
    """The numbers of one optimization run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = RESULT_SCHEMA_VERSION

    objective: float
    horizon_hours: float
    solver: Union[SolverInfo, None] = None

    key_figures: list[KeyFigure] = Field(default_factory=list)
    cost_breakdown: Table
    capacities: Table
    buses: dict[str, BusSummary] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, version):
        if version > RESULT_SCHEMA_VERSION:
            raise ValueError(
                f"this result was saved with a newer version of the tool "
                f"(layout {version}, this tool reads up to {RESULT_SCHEMA_VERSION})"
            )
        return version

    # ------------------------------------------------------------------
    # from the result of a run
    # ------------------------------------------------------------------

    @classmethod
    def from_output(cls, output, meta_results=None, include_flows=True):
        """Take the numbers out of the dictionary `collect_results` returns.

        meta_results is the third value `run_scenario` returns (solver
        information); it is optional. include_flows=False leaves out the hourly
        flows, which gives a much smaller result.
        """

        solver = None
        if meta_results is not None and "solver" in meta_results:
            info = meta_results["solver"]
            solver = SolverInfo(
                status=_name(info.get("Status", "unknown")),
                termination=_name(info.get("Termination condition", "unknown")),
                message=str(info.get("Termination message", "")),
                seconds=_number(info.get("Time")),
            )

        return cls(
            objective=float(output["objective"]),
            horizon_hours=float(output["horizon_hours"]),
            solver=solver,
            key_figures=[
                KeyFigure(
                    label=figure["label"],
                    value=_number(figure.get("value")),
                    unit=figure.get("unit", ""),
                    help=figure.get("help", ""),
                )
                for figure in output["key_figures"]
            ],
            cost_breakdown=Table.from_frame(output["cost_breakdown"]),
            capacities=Table.from_frame(output["capacities"]),
            buses={
                bus: BusSummary(
                    energy_sums={
                        str(name): float(value)
                        for name, value in data["energy_sums"].items()
                    },
                    supply=Table.from_frame(data["supply"]),
                    use=Table.from_frame(data["use"]),
                    flows=(
                        FlowTable.from_frame(data["flows"])
                        if include_flows and data.get("flows") is not None
                        else None
                    ),
                )
                for bus, data in output["buses"].items()
            },
        )

    # ------------------------------------------------------------------
    # saving and loading
    # ------------------------------------------------------------------

    def save(self, path):
        Path(path).write_text(self.model_dump_json(), encoding="utf-8")

    @classmethod
    def load(cls, path):
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
