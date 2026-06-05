from oemof import solph
from .model_builder import build_model
from .plotting import plot_energy_system_graph

def run_scenario(config: dict, input_data: dict, plot_graph: bool = False):

    #build energy system
    es = build_model(config, input_data)

    # solver settings
    solver_cfg = config["solver"]

    # optimization
    model = solph.Model(es)

    model.solve(
        solver=solver_cfg.name,
        solve_kwargs={"tee": solver_cfg.tee}
    )

    # results
    results = solph.processing.results(model)
    meta_results = solph.processing.meta_results(model)

    fig = plot_energy_system_graph(es) if plot_graph else None

    return es, results, meta_results, fig