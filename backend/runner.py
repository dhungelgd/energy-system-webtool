from oemof.solph import Model

def solve_model(es, solver_config):

    model = Model(es)

    model.solve(
        solver=solver_config.name,
        solve_kwargs={"tee": solver_config.tee}
    )

    return model.results()