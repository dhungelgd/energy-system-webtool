"""Excel export of the results """

import io

import pandas as pd


def build_excel(output):
    """Workbook with the key figures, costs, capacities and the data of every bus.

    Returns the file content as bytes.
    """

    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:

        pd.DataFrame(output["key_figures"])[["label", "value", "unit"]].rename(
            columns={"label": "Key figure", "value": "Value", "unit": "Unit"}
        ).to_excel(writer, sheet_name="Key figures", index=False)

        output["cost_breakdown"].to_excel(writer, sheet_name="Costs", index=False)
        output["capacities"].to_excel(writer, sheet_name="Capacities", index=False)

        for bus, data in output["buses"].items():

            # energy per component (kWh): supply on the left, use on the right
            data["supply"].to_excel(
                writer, sheet_name=f"Energy {bus}", index=False, startcol=0
            )
            data["use"].to_excel(
                writer, sheet_name=f"Energy {bus}", index=False, startcol=5
            )

            # power per time step (kW)
            data["flows"].to_excel(writer, sheet_name=f"Flows {bus} (kW)")

    return buffer.getvalue()