from oemof import solph
from backend.model_builder import build_model
from backend.plotting import plot_energy_system_graph
from backend.solving import solve

def run_scenario(config: dict, input_data: dict, selected_techs=None, plot_graph: bool = False):

    #build energy system
    es = build_model(config, input_data)

    # solver settings
    solver_cfg = config["solver"]

    # optimization
    model = solph.Model(es)

    info = solve(model, solver_cfg.name, solver_cfg.tee)

    # results
    results = solph.processing.results(model)
    meta_results = solph.processing.meta_results(model)
    meta_results["solver"]["Name"] = info.name              # the solver that ran (not always the one asked for)
    meta_results["solver"]["Time"] = info.seconds           # measured here, for every solver

    fig = plot_energy_system_graph(es, selected_techs=selected_techs) if plot_graph else None

    return es, results, meta_results, fig