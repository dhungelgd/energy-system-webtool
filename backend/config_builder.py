from backend.tech_config_registry import TECH_CONFIG_REGISTRY

def build_config(
    selected_techs,
    tech_inputs,
    input_data,
    solver_cfg
):

    config = {"buses": {"electricity_bus": {"label": "electricity"}}, "technologies": {}, "solver": solver_cfg}

    # build technologies via registry
    for tech in selected_techs:

        if tech not in TECH_CONFIG_REGISTRY:
            raise ValueError(f"Unknown technology: {tech}")

        config["technologies"][tech] = TECH_CONFIG_REGISTRY[tech](
            tech_inputs=tech_inputs,
            input_data=input_data,
        )

    return config