# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
# SPDX-FileCopyrightText: gb-dispatch-model contributors
#
# SPDX-License-Identifier: MIT

"""Custom constraints provider.

Defines custom constraints for the GB model.
"""

import logging
from pathlib import Path

import pandas as pd
import pypsa
from dispatch_custom_constraints import remove_KVL_constraints
from linopy import merge

logger = logging.getLogger(__name__)

curdir = Path(__file__).parent


def set_boundary_constraints(
    n: pypsa.Network,
    snapshots: pd.Index,
) -> None:
    """Limit new line flows across each boundary to satisfy ETYS boundary capabilities.

    Args:
        n (pypsa.Network): The PyPSA network to add constraints.
        snapshots (pd.Index): The snapshots of the network.
        snakemake (snakemake.Snakemake): The snakemake object for parameters and config.
    """
    # Load ETYS capacities
    etys_capacities = pd.read_csv(
        curdir / "etys_boundary_capabilities.csv", index_col="boundary_name"
    ).capability_mw

    year = n.meta["wildcards"]["year"]
    future_caps = pd.read_csv(
        curdir / "future_etys_boundary_capabilities.csv",
        index_col=["boundary_name", "year"],
    ).capability_mw.xs(year, level="year")
    manual_caps = pd.DataFrame(n.meta["etys"]["manual_future_capacities"]).loc[year]
    etys_capacities_all_boundaries = pd.concat([future_caps, manual_caps]).reindex(
        etys_capacities.index
    )
    if (isna := etys_capacities_all_boundaries.isna()).any():
        logger.warning(
            f"Future ETYS capacities are missing for some boundaries: "
            f"{etys_capacities_all_boundaries[isna].index.tolist()}. \n"
            "Filling missing values with current capacities."
        )
    etys_capacities = etys_capacities_all_boundaries.fillna(etys_capacities)

    etys_boundary_crossings = pd.read_csv(curdir / "etys_boundary_crossings.csv")

    # Define Line-s and Link-p variable (power flow)
    line_s = n.model["Line-s"]
    link_p = n.model["Link-p"]

    lhs_exprs = []
    etys_capacities.index.name = "boundary"  # Ensure index has a name for later merging
    for boundary in etys_capacities.index:
        # Get boundary capability
        capacity_mw = etys_capacities.loc[boundary]

        boundary_lines_mask = etys_boundary_crossings.query(
            "Boundary_n == @boundary and component == 'Line'"
        )
        boundary_links_mask = etys_boundary_crossings.query(
            "Boundary_n == @boundary and component == 'Link'"
        )

        if boundary_lines_mask.empty and boundary_links_mask.empty:
            logger.warning(
                f"No lines or links found for boundary '{boundary}'. "
                f"Cannot apply ETYS constraint. Check configuration."
            )
            continue

        logger.info(
            f"Boundary {boundary}: {len(boundary_lines_mask)} lines, {len(boundary_links_mask)} DC links, "
            f"capacity={capacity_mw} MW"
        )
        boundary_lines = boundary_lines_mask.set_index("name").flow_direction
        line_s_boundary = (
            line_s.sel(snapshot=snapshots, name=boundary_lines.index) * boundary_lines
        )

        boundary_links = boundary_links_mask.set_index("name").flow_direction
        link_p_boundary = (
            link_p.sel(snapshot=snapshots, name=boundary_links.index) * boundary_links
        )

        # Sum across lines and DC links to get total flow at the boundary
        lhs = line_s_boundary.sum("name") + link_p_boundary.sum("name")
        lhs_exprs.append(lhs)

    lhs_merged = merge(lhs_exprs, dim="boundary").assign_coords(
        boundary=etys_capacities.index
    )

    boundary_scaling = n.meta["redispatch"]["monthly_boundary_capability_scaling"]
    boundary_scaling_sns = pd.Series(boundary_scaling).reindex(n.snapshots.month)
    boundary_scaling_sns.index = n.snapshots
    assert boundary_scaling_sns.notnull().all(), "Missing monthly scaling factors"
    bounds = etys_capacities.to_xarray() * boundary_scaling_sns.to_xarray()

    n.model.add_constraints(lhs_merged <= bounds, name="etys_boundary_forward")
    n.model.add_constraints(lhs_merged >= -bounds, name="etys_boundary_backward")

    logger.info(
        f"Added {len(etys_capacities.index)} boundary constraints with explicit 'boundary' dimension"
    )


def update_storage_p_bounds(n: pypsa.Network) -> None:
    """Update the bounds of storage unit dispatch and store power to make up for insufficient default bounding.

    Args:
        n (pypsa.Network): The PyPSA network to update.
    """
    # `p_dispatch`/`p_store` have correct upper bounds but no lower, so we copy one from the other to _fix_ the storage unit flows.
    for direction in ["dispatch", "store"]:
        n.model.constraints[
            f"StorageUnit-fix-p_{direction}-lower"
        ].rhs = n.model.constraints[f"StorageUnit-fix-p_{direction}-upper"].rhs


def update_storage_balance(n: pypsa.Network) -> None:
    """Update the energy balance mathematics to include up and down ramping.

    Args:
        n (pypsa.Network): The PyPSA network to update.
    """
    storage_unit_balance = n.model.constraints["StorageUnit-energy_balance"]
    ramp_names = n.generators[
        n.generators.carrier.str.startswith("StorageUnit ramp")
    ].index
    ramp_p = n.model["Generator-p"].sel(name=ramp_names)
    idx = ramp_p.coords["name"].str.replace(r" ramp (up|down)", "")
    ramp_p_grouped = ramp_p.groupby(idx).sum() * n.snapshot_weightings["stores"]

    # ramping up and ramping down `p` already have the correct signs (positive and negative, respectively),
    # so no need to invert one of them when applying to the LHS.
    # `ramp_up` is equivalent to `p_dispatch`, `ramp_down` is equivalent to `p_store`
    storage_unit_balance.lhs -= ramp_p_grouped.sel(storage_unit_balance.coords)
    # Log a randomly selected snapshot for verification
    logger.info(
        f"Updated energy balance math for storage units. Example: {storage_unit_balance.isel(snapshot=10)}"
    )


def add_redispatch_penalty(n: pypsa.Network) -> None:
    """Add a penalty to the objective function for redispatching generation.

    Args:
        n (pypsa.Network): The PyPSA network to update.
        snakemake (snakemake.Snakemake): The snakemake object for parameters and config.
    """
    penalty = n.meta["redispatch"]["redispatch_profit_mitigation_penalty"]
    if penalty == 0:
        logger.info("No redispatch penalty applied to the objective function.")
        return

    idx = n.generators.filter(regex="ramp (up|down)", axis=0).index
    is_neg = n.get_switchable_as_dense("Generator", "p_min_pu")[idx] < 0
    obj_cost = is_neg.replace({True: -penalty, False: penalty}).stack().to_xarray()
    gen_p = n.model["Generator-p"].sel(**obj_cost.coords)
    penalty_expr = obj_cost * gen_p * n.snapshot_weightings.objective
    n.model.objective += penalty_expr.sum()
    logger.info(
        f"Added redispatch penalty of {penalty} per MWh to the following number of "
        "redispatch generators in the objective function to mitigate profit manipulation:\n"
        f"{n.generators.loc[idx].carrier.value_counts()}"
    )


def custom_constraints(
    n: pypsa.Network,
    snapshots: pd.Index,
) -> None:
    """Apply custom constraints to the PyPSA network.

    Args:
        n (pypsa.Network): The PyPSA network to modify.
        snapshots (pd.Index): The snapshots of the network.
    """
    # Apply boundary constraints
    set_boundary_constraints(n, snapshots)
    remove_KVL_constraints(n)
    update_storage_p_bounds(n)
    update_storage_balance(n)
    add_redispatch_penalty(n)
