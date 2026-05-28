from oemof import solph
from .model_builder import build_model

def run_scenario(config: dict, input_data: dict):

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

    return es, results, meta_results