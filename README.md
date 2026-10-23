# Energy System Web Tool

A web tool to model and optimise small energy systems (electricity, heat, gas)
and to compare technology options by cost. It is built with
[oemof.solph](https://oemof-solph.readthedocs.io) for the optimisation and
[Streamlit](https://streamlit.io) for the user interface.

> Status: under active development as part of a research project that supports
> small and medium-sized companies in the Allgäu on their way to decarbonisation.

## What it does

1. Choose the components of your system (or start from a template such as
   "PV + battery" or "Heat pump + PV").
2. Upload time series (demand, PV and wind profiles, prices, COP) as CSV files.
3. A **system check** points out missing inputs and impossible combinations
   before the optimisation starts.
4. The model finds the cheapest operation, and in *invest* mode also the
   cheapest capacity of each component.
5. Look at key figures, cost breakdown, capacities and energy flows, and export
   the results to Excel.

Available components: electricity demand, heat demand, grid import, grid
feed-in, PV, wind, gas import, gas boiler, heat pump, heating rod, CHP,
battery and heat storage.

Every sized component can be used in **fixed** mode (you set the capacity) or in
**invest** mode (the optimiser chooses the capacity using annualised costs).
Storages are limited in charge and discharge power by a C-rate
(kW per kWh of capacity).

## Installation

You need Python 3.11 or newer and the CBC solver.

```bash
# CBC solver (Ubuntu / Debian)
sudo apt-get install coinor-cbc

# Python packages (run this in the repository folder)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

To import the project from anywhere (other scripts, notebooks, the tests), also
install it into the environment. This adds only a link to this folder and
changes no other package:

```bash
pip install -e . --no-deps
```

On Windows or macOS, install CBC from [coin-or.org](https://github.com/coin-or/Cbc)
or with your package manager (for example `brew install coin-or-tools/coinor/cbc`),
and make sure `cbc` is on your `PATH`.

## Run the app

From the repository root:

```bash
streamlit run streamlit_app.py
```

`streamlit_app.py` needs no installation of the project, because Streamlit puts
its folder on the import path. This is also the file to use on Streamlit
Community Cloud.

Add `?admin=1` to the address to see the live session counter.

If you start `frontend/app.py` directly and the page says that the project is not
installed, run `pip install -e . --no-deps` in the repository folder (in the same
environment that runs Streamlit), or use `streamlit_app.py` instead.

## Input data

Time series can be uploaded as **CSV** (also `.txt`, `.tsv`) or **Excel**
(`.xlsx`, `.xlsm`), either one file with all time series or one file per
component. The layout is detected automatically:

- separator: semicolon, comma, tab or pipe
- decimal sign: `12,5` (German) or `12.5`, also with thousands separators
  (`1.234,5` or `1,234.5`)
- character encoding: UTF-8 (with or without BOM), Windows-1252, UTF-16
- title or metadata lines above the column names and a unit line below them
- Excel: the sheet with the data is chosen automatically, numbers stored as text
  are converted

The app shows what it detected ("Read as: ..."). If the preview is wrong, change
the settings under **Import settings** (separator, decimal sign, encoding,
sheet, line numbers). Warnings name the exact line of the file, for example
`Column 'Last': 1 values are not numbers (first in line 3: 'abc')`.

Requirements for the data:

- one value per hour, **8760 rows** (one year); a time step other than one hour
  is reported, but the data is not converted yet
- the app asks you to pick the column that holds the values
- electricity prices can be given in EUR/kWh, ct/kWh or EUR/MWh
- demand and heat demand profiles are multiplied by a scaling factor, so a
  profile normalised to a maximum of 1 and a scaling factor of 100 means a peak
  of 100 kW
- the old Excel format `.xls` is not supported: save the file as `.xlsx`

## Project structure

```
pyproject.toml       package definition (backend and frontend)
streamlit_app.py     entry point for `streamlit run` (also for Streamlit Cloud)
backend/     model and calculations (no Streamlit code)
  system_check.py      checks a system before the run
  oemof_components.py  one function per component, adds it to the oemof model
  timeseries_import.py reads CSV and Excel files (layout detection)
  tech_config_registry.py  turns user inputs into component settings
  model_builder.py / scenario_runner.py   build and solve the model
  kpis.py / postprocessing.py / results_summary.py   results and cost tables
frontend/    Streamlit user interface
  ui_registry.py       which inputs each component shows
  ui_upload.py         file upload and import settings
tests/       automatic tests
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The model tests need the CBC solver and are skipped when it is not installed.
They use small systems whose cost can be calculated by hand, for example a
10 kW demand for 24 hours at 0.30 €/kWh costs 72 €.

## Contributing

Create a branch for each change, add or update a test, and run `pytest` before
you commit. The tests also run automatically on GitHub for every push.


