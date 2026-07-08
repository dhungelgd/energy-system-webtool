"""
Postprocessing functions for energy system results.
Separates result extraction and processing from visualization.
"""

from oemof.solph import views
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional

from .models import InputData


class ResultsProcessor:
    """Processor for extracting and processing simulation results."""
    
    def __init__(self, results: Any):
        """
        Initialize with oemof results object.
        
        Args:
            results: oemof.solph.processing.results object
        """
        self.results = results
    
    def get_bus_flows(self, bus_name: str) -> pd.DataFrame:
        """
        Extract flows from a specific bus.
        
        Args:
            bus_name: Name of the bus
            
        Returns:
            DataFrame with flow data
        """
        try:
            node = views.node(self.results, bus_name)
            
            if node is None:
                return pd.DataFrame()
            
            flows = node.get("sequences")
            
            if flows is None or len(flows) == 0:
                return pd.DataFrame()
            
            return flows
            
        except Exception:
            return pd.DataFrame()
    
    def flatten_flows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Flatten multi-index column names to simple strings.
        
        Args:
            df: DataFrame with multi-index columns
            
        Returns:
            DataFrame with flattened column names
        """
        if df is None or df.empty:
            return df
        
        df_flat = df.copy()
        df_flat.columns = [
            f"{col[0][0]}-->{col[0][1]}" for col in df.columns
        ]
        
        return df_flat
    
    def split_supply_demand(self, flows: pd.DataFrame, bus_name: str) -> Tuple[List[str], List[str]]:
        """
        Split flow columns into supply and demand.
        
        Args:
            flows: DataFrame with flow data
            bus_name: Name of the bus
            
        Returns:
            Tuple of (supply_columns, demand_columns)
        """
        if flows is None or flows.empty:
            return [], []
        
        supply_cols = [c for c in flows.columns if c.endswith(f"-->{bus_name}")]
        demand_cols = [c for c in flows.columns if c.startswith(f"{bus_name}-->")]
        
        return sorted(supply_cols), demand_cols
    
    def compute_energy_sums(self, flows: pd.DataFrame) -> pd.Series:
        """
        Compute total energy per flow.
        
        Args:
            flows: DataFrame with flow data
            
        Returns:
            Series with energy sums
        """
        if flows is None or flows.empty:
            return pd.Series()
        
        return flows.sum()
    
    def process_bus_results(self, bus_name: str) -> pd.DataFrame:
        """
        Full processing pipeline for a bus.
        
        Args:
            bus_name: Name of the bus
            
        Returns:
            Processed DataFrame with flows
        """
        flows = self.get_bus_flows(bus_name)
        flows = self.flatten_flows(flows)
        return flows
    
    def get_investment_capacities(self) -> Dict[str, float]:
        """
        Extract investment capacities from results.
        
        Returns:
            Dictionary mapping technology names to invested capacities
        """
        capacities = {}
        
        for (comp, bus), data in self.results.items():
            if not hasattr(comp, "label"):
                continue
            
            tech = comp.label
            scalars = data.get("scalars")
            
            if scalars is None:
                continue
            
            invest_val = None
            
            try:
                invest_val = scalars.get("invest", None)
            except Exception:
                pass
            
            if invest_val is None:
                try:
                    for item in scalars:
                        if isinstance(item, tuple) and item[0] == "invest":
                            invest_val = item[1]
                            break
                except Exception:
                    pass
            
            if invest_val is not None:
                capacities[tech] = float(invest_val)
        
        return capacities


class ActiveBusDetector:
    """Detects which buses are active based on selected technologies."""
    
    @staticmethod
    def get_active_bus_labels(selected_techs: List[str], config: Dict[str, Any]) -> List[str]:
        """
        Get labels of buses that are used by selected technologies.
        
        Args:
            selected_techs: List of selected technology types
            config: System configuration dictionary
            
        Returns:
            Sorted list of active bus labels
        """
        active_buses = set()
        
        for tech in selected_techs:
            tech_cfg = config["technologies"].get(tech, {})
            bus_id = tech_cfg.get("bus")
            
            if bus_id:
                bus_label = config["buses"][bus_id]["label"]
                active_buses.add(bus_label)
        
        return sorted(active_buses)


# Standalone functions for backward compatibility

def get_bus_flows(results: Any, bus_name: str) -> pd.DataFrame:
    """Extract flows from a bus (standalone function)."""
    processor = ResultsProcessor(results)
    return processor.get_bus_flows(bus_name)


def flatten_flows(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten column names (standalone function)."""
    processor = ResultsProcessor(None)
    return processor.flatten_flows(df)


def split_supply_demand(flows: pd.DataFrame, bus_name: str) -> Tuple[List[str], List[str]]:
    """Split flows into supply and demand (standalone function)."""
    processor = ResultsProcessor(None)
    return processor.split_supply_demand(flows, bus_name)


def compute_energy_sums(flows: pd.DataFrame) -> pd.Series:
    """Compute energy sums (standalone function)."""
    processor = ResultsProcessor(None)
    return processor.compute_energy_sums(flows)


def process_results(results: Any, bus_name: str) -> pd.DataFrame:
    """Full processing pipeline (standalone function)."""
    processor = ResultsProcessor(results)
    return processor.process_bus_results(bus_name)


def get_active_bus_labels(selected_techs: List[str], config: Dict[str, Any]) -> List[str]:
    """Get active bus labels (standalone function)."""
    return ActiveBusDetector.get_active_bus_labels(selected_techs, config)


def get_investment_capacities(results: Any) -> Dict[str, float]:
    """Extract investment capacities (standalone function)."""
    processor = ResultsProcessor(results)
    return processor.get_investment_capacities()
