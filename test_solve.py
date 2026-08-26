# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
#
# SPDX-License-Identifier: MIT

import logging
import sys
from pathlib import Path
from time import time
from typing import Any

import click
import pypsa
import yaml

sys.path.append(str(Path(__file__).parent / "extras"))
from extras import dispatch_fn, redispatch_fn

SMALL_N = 0.01
TIMELIMIT = 1800
SOLVER_OPTIONS: dict[str, dict[str, Any]] = {
    "cupdlpx": {
        "io_api": "direct",
        "OptimalityTol": 1e-5,
        "FeasibilityTol": 1e-6,
        "FeasibilityPolishing": True,
        "FeasibilityPolishingTol": 1e-8,
        "TimeLimit": TIMELIMIT,
    },
    "gurobi": {
        "threads": 8,
        "method": 2,
        "crossover": 0,
        "BarConvTol": 1.0e-05,
        "Seed": 123,
        "AggFill": 0,
        "PreDual": 0,
        "TimeLimit": TIMELIMIT,
        "GURO_PAR_BARDENSETHRESH": 200,
    },
    "highs": {
        "solver": "hipo",
        "threads": 8,
        "parallel": "on",
        "primal_feasibility_tolerance": 1.0e-05,
        "dual_feasibility_tolerance": 1.0e-05,
        "random_seed": 123,
        "run_crossover": "off",
        "time_limit": TIMELIMIT,
    },
}
CUSTOM_CONSTRAINTS_PATH = {
    "dispatch": dispatch_fn,
    "redispatch": redispatch_fn,
}

logging.basicConfig(level=logging.INFO)


def optimize(
    n: pypsa.Network,
    solver_name: str,
    custom_constraints: str | None,
    log_path: Path,
    condition_dispatch: bool,
    condition_storage: bool,
) -> float:
    """Optimize a network with the given solver.

    Args:
        n (pypsa.Network): PyPSA network to optimize
        solver_name (str): Solver name to use for optimization
        custom_constraints (str | None): Name of custom constraints function, if required
        log_path (Path): Path to log file for solver output
        condition_dispatch (bool): Whether to condition the dispatch of generators and links by setting their marginal costs to a small value
        condition_storage (bool): Whether to condition the storage of generators and links by setting their marginal costs to a small value

    Returns:
        float: Optimization time (including time to send to and receive from the solver)
    """
    if condition_dispatch:
        n.storage_units.marginal_cost = SMALL_N
        n.stores.marginal_cost = SMALL_N
        n.generators.loc[n.generators.marginal_cost == 0, "marginal_cost"] = SMALL_N
        directional_links = (
            n.get_switchable_as_dense("Link", "p_min_pu")
            .min()
            .where(lambda x: x >= 0)
            .dropna()
            .index
        )
        n.links.loc[
            (n.links.marginal_cost == 0) & n.links.index.isin(directional_links),
            "marginal_cost",
        ] = SMALL_N
    if condition_storage:
        n.storage_units.marginal_cost_storage = SMALL_N / 10
        n.storage_units.spill_cost = SMALL_N
        n.stores.marginal_cost_storage = SMALL_N / 10

    ts = time()
    n.optimize(
        solver_name=solver_name,
        io_api="direct",
        include_objective_constant=False,
        solver_options=SOLVER_OPTIONS[solver_name],
        log_fn=log_path,
        extra_functionality=CUSTOM_CONSTRAINTS_PATH[custom_constraints]
        if custom_constraints
        else None,
    )
    te = time()
    opt_time = te - ts
    return opt_time


@click.command()
@click.argument("solver_name", type=click.Choice(list(SOLVER_OPTIONS.keys())))
@click.argument(
    "model_path",
    type=click.Path(exists=True, dir_okay=False, file_okay=True, path_type=Path),
)
@click.option(
    "--custom_constraints", type=click.Choice(list(CUSTOM_CONSTRAINTS_PATH.keys()))
)
@click.option(
    "--log_dir",
    default="logs",
    type=click.Path(exists=True, dir_okay=True, file_okay=False, path_type=Path),
)
@click.option(
    "--output_dir",
    default="results",
    type=click.Path(exists=True, dir_okay=True, file_okay=False, path_type=Path),
)
@click.option("--dump_mps", is_flag=True, default=False)
@click.option("--condition_dispatch", is_flag=True, default=False)
@click.option("--condition_storage", is_flag=True, default=False)
@click.option("--segment", type=int)
def main(
    solver_name: str,
    model_path: Path,
    custom_constraints: str | None,
    log_dir: Path,
    output_dir: Path,
    dump_mps: bool,
    condition_dispatch: bool,
    condition_storage: bool,
    segment: int | None,
):
    network = pypsa.Network(model_path)
    if segment is not None:
        network = network.cluster.temporal.segment(segment)

    conditioned = (
        f"_conditioned-{'dispatch' if condition_dispatch else ''}{',storage' if condition_storage else ''}"
        if condition_dispatch or condition_storage
        else ""
    )
    segmented = f"_segmented-{segment}" if segment is not None else ""
    filename = f"{model_path.stem}_{solver_name}{conditioned}{segmented}.nc"

    opt_time = optimize(
        network,
        solver_name,
        custom_constraints,
        (log_dir / filename).with_suffix(".log"),
        condition_dispatch,
        condition_storage,
    )
    outpath = output_dir / filename
    network.export_to_netcdf(outpath)
    yaml.safe_dump(
        [{filename: opt_time}],
        (output_dir / "timings.yaml").open("a"),
        default_flow_style=False,
    )
    if dump_mps:
        network.model.to_file(outpath.with_suffix(".mps"))


def benchmark_matrix():
    for solver_name in SOLVER_OPTIONS:
        for condition_dispatch in [False, True]:
            for condition_storage in [False, True]:
                model_path = Path("models", "test_model.nc")
                log_dir = Path("logs")
                output_dir = Path("results")
                segment = None
                main(
                    solver_name=solver_name,
                    model_path=model_path,
                    log_dir=log_dir,
                    output_dir=output_dir,
                    condition_dispatch=condition_dispatch,
                    condition_storage=condition_storage,
                    segment=segment,
                )


if __name__ == "__main__":
    main()
