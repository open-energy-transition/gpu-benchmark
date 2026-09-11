# gpu-benchmark

Benchmarking GPU- and CPU-based linear programming solvers on [PyPSA](https://pypsa.org) power system models.

The aim is to compare wall-clock solve time and solution quality for the same network across:

- **[cuPDLPx](https://github.com/MIT-Lu-Lab/cuPDLPx)** — a GPU-accelerated first-order (PDLP) solver.
- **[Gurobi](https://www.gurobi.com)** — barrier method, crossover disabled.
- **[HiGHS](https://highs.dev)** — the `hipo` interior point solver, crossover disabled.

Because first-order methods are sensitive to problem conditioning, the benchmark can optionally "condition" a network by giving otherwise cost-free dispatch and storage decisions a small marginal cost, which removes degeneracy in the objective.

This repository has been built around benchmarking models derived from the [gb-dispatch-model PyPSA workflow](https://github.com/open-energy-transition/gb-dispatch-model).

## Repository layout

| Path | Contents |
| --- | --- |
| [test_solve.py](test_solve.py) | CLI entry point: load a network, optionally segment it, solve, and record the timing. |
| [extras/](extras/) | Custom PyPSA constraint functions (`dispatch`, `redispatch`) and the ETYS boundary data they use. This is specific to [gb-dispatch-model PyPSA workflow](https://github.com/open-energy-transition/gb-dispatch-model) models |
| [analysis/compare_results.ipynb](analysis/compare_results.ipynb) | Notebook comparing solved networks and timings. |
| [models/](models/) | Input networks (`*.nc`, not tracked in git). |
| [results/](results/) | Solved networks, optional MPS dumps, and `timings.yaml` (not tracked in git). |
| [logs/](logs/) | Solver logs and Slurm job output (not tracked in git). |
| [submit-cpu.sh](submit-cpu.sh) / [submit-gpu.sh](submit-gpu.sh) | Slurm array job scripts for the CPU and GPU benchmark sweeps. |

## Setup

Dependencies are managed with [pixi](https://pixi.sh):

```bash
pixi install -e cpu       # Gurobi + HiGHS (linux-64, osx-arm64)
pixi install -e gpu       # CUDA toolchain and cuPDLPx (linux-64 only)
pixi install -e analyse   # Jupyter + plotly for the analysis notebook
```

Gurobi requires a valid licence; cuPDLPx requires an NVIDIA GPU and is only built for `linux-64`.

## Running a benchmark

```bash
pixi run -e cpu python test_solve.py gurobi models/<my-model>.nc \
    --custom_constraints dispatch \
    --segment 2920 \
    --condition_dispatch --condition_storage
```

Arguments:

- `SOLVER_NAME` — one of `cupdlpx`, `gurobi`, `highs`.
- `MODEL_PATH` — path to a PyPSA network file.

Options:

| Option | Effect |
| --- | --- |
| `--custom_constraints {dispatch,redispatch}` | Apply the matching `extra_functionality` from [extras/](extras/). |
| `--segment N` | Temporally segment the network to `N` segments before solving. |
| `--condition_dispatch` | Give zero-cost generators, links, storage units, and stores a small marginal cost. |
| `--condition_storage` | Give storage a small state-of-charge and spill cost. |
| `--dump_mps` | Also write the model out in MPS format. |
| `--log_dir` / `--output_dir` | Override the default `logs/` and `results/` directories. |

Each run appends `{filename: seconds}` to `results/timings.yaml` and writes the solved network to `results/`, with the applied conditioning and segmentation encoded in the filename.

All solvers are given a 1800 s time limit (`TIMELIMIT` in [test_solve.py](test_solve.py)).

## Running on a cluster

[submit-cpu.sh](submit-cpu.sh) and [submit-gpu.sh](submit-gpu.sh) are Slurm array jobs that sweep the conditioning options for each solver.
They expect the repository to live at `/scratch/htc/$USER/gpu-benchmark` (CPU) and `/scratch/gcp1/$USER/gpu-benchmark` (GPU); adjust the `cd` target and the `--partition` if yours differs.

```bash
sbatch submit-cpu.sh
sbatch submit-gpu.sh
```

### Pixi on the cluster

Every persistent filesystem on ZIB is a network filesystem — `$HOME` and `/scratch/gcp1` are NFS, `/scratch/htc` is HDD-backed CephFS.
The pixi package cache is thousands of small files and is painfully slow on all of them.
Point it at node-local storage instead, once, in your user-level pixi config:

```bash
pixi config set --global cache-dir /tmp/gpu-benchmark-$USER
```

This writes to `~/.config/pixi/config.toml` and applies to every `pixi install` on that machine.

Install on a **login node** and run on the **compute nodes** — the cache does not need to be shared between them:

- the cache (`/tmp/gpu-benchmark-$USER`) is only read at install time, and can stay node-local;
- the environment (`.pixi/envs/`) is created next to `pixi.toml` in the scratch checkout, so it is on shared storage and the compute nodes pick it up.

Because the two are on different filesystems, pixi copies packages into the environment rather than hardlinking them, so the environment stays intact when `/tmp` is cleared.

The submit scripts use `pixi run --frozen`, which takes the environment as-is instead of re-solving against `pixi.lock`.
Without it, a job that thinks something is missing would try to re-download into an empty cache on the compute node.
Re-run `pixi install` on the login node after changing dependencies.

>[!WARNING]
>`/tmp` is `tmpfs`, i.e. RAM, not disk — a populated cache is several GB of memory held on a shared login node until it reboots.
>Release it once the environments are installed:
>
>```bash
>pixi clean cache
>```
>
>`/tmp` is also per-node, so a different login node means a cold cache and a full re-download.

The `sync` environment wraps rsync for moving code to and results back from the cluster:

```bash
pixi run -e sync sync-send /scratch/htc/$USER/gpu-benchmark
pixi run -e sync sync-receive '/scratch/htc/$USER/gpu-benchmark/results/*'
```

`exclude-send.txt` and `exclude-receive.txt` control what each direction transfers — notably, models and results are not synced by default.

>[!WARNING]
>On ZIB, the GCP nodes do not recognise the `htc` scratch directory.
>The `gcp` directory is significantly slower for IO so you should sync-send to both `gcp1` and `htc` and then sbatch from each of those separately for GPU and CPU tests, respectively.

## Development

Pre-commit checks are managed with [lefthook](https://lefthook.dev) and run [ruff](https://docs.astral.sh/ruff/) plus [nbstripout](https://github.com/kynan/nbstripout) on staged files:

```bash
pixi run -e lint lefthook install   # once, to register the git hook
pixi run lint                       # run all checks manually
```

## Licence

[MIT](LICENSES/MIT.txt) for code and [CC-BY-4.0](LICENSES/CC-BY-4.0.txt) for most other content.
See the SPDX headers and the REUSE.toml file for per-file specifics.
