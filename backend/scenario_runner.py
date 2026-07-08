"""
Scenario runner for executing energy system optimizations.
Handles the execution flow and result processing.
"""

from oemof import solph
from typing import Dict, Any, Optional, Tuple
import matplotlib.figure

from .model_builder import build_energy_system
from .plotting import plot_energy_system_graph
from .models import SystemConfig, InputData, SimulationResults


def run_scenario(
    config: SystemConfig,
    input_data: InputData,
    plot_graph: bool = False
) -> Tuple[Any, Any, Dict[str, Any], Optional[matplotlib.figure.Figure]]:
    """
    Run an optimization scenario.
    
    Args:
        config: System configuration
        input_data: Input data container
        plot_graph: Whether to generate a system graph
        
    Returns:
        Tuple containing:
        - energy_system: The oemof EnergySystem
        - results: Processing results
        - meta_results: Meta results dictionary
        - fig: System graph figure (if plot_graph=True)
    """
    # Build energy system
    es = build_energy_system(config, input_data)
    
    # Get solver settings from config
    solver_cfg = config.solver if hasattr(config, 'solver') else config.get("solver", {})
    
    # Create and solve model
    model = solph.Model(es)
    
    model.solve(
        solver=solver_cfg.name if hasattr(solver_cfg, 'name') else solver_cfg.get("name", "cbc"),
        solve_kwargs={"tee": solver_cfg.tee if hasattr(solver_cfg, 'tee') else solver_cfg.get("tee", False)}
    )
    
    # Process results
    results = solph.processing.results(model)
    meta_results = solph.processing.meta_results(model)
    
    # Generate graph if requested
    fig = plot_energy_system_graph(es) if plot_graph else None
    
    return es, results, meta_results, fig


def run_scenario_with_results(
    config: SystemConfig,
    input_data: InputData,
    plot_graph: bool = False
) -> SimulationResults:
    """
    Run an optimization scenario and return structured results.
    
    Args:
        config: System configuration
        input_data: Input data container
        plot_graph: Whether to generate a system graph
        
    Returns:
        SimulationResults: Structured results container
    """
    es, results, meta_results, fig = run_scenario(config, input_data, plot_graph)
    
    return SimulationResults(
        energy_system=es,
        results=results,
        meta_results=meta_results,
        investment_capacities={},
        flows={}
    )
