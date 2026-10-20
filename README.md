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

You need Python 3.12 and the CBC solver.

```bash
# CBC solver (Ubuntu / Debian)
sudo apt-get install coinor-cbc

# Python packages
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

On Windows or macOS, install CBC from [coin-or.org](https://github.com/coin-or/Cbc)
or with your package manager (for example `brew install coin-or-tools/coinor/cbc`),
and make sure `cbc` is on your `PATH`.

## Run the app

From the repository root:

```bash
streamlit run frontend/app.py
```

## Input data

- One CSV file per time series, one value per hour, **8760 rows** (one year).
- The app asks you to pick the column that holds the values.
- Electricity prices can be given in €/kWh, ct/kWh or €/MWh.
- Demand and heat demand profiles are multiplied by a scaling factor, so a
  profile normalised to a maximum of 1 and a scaling factor of 100 means a peak
  of 100 kW.



