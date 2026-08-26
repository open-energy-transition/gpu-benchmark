#!/bin/bash

# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
#
# SPDX-License-Identifier: MIT

#SBATCH --job-name=cpu-solve
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --array=0-11
#SBATCH --time=01:00:00
#SBATCH --partition=big
#SBATCH --mem=60G
#SBATCH -n1

# Network filepath - update this with your actual network file path
cd "/scratch/htc/${USER}/gpu-benchmark" || { echo "Error: failed to cd to /scratch/htc/${USER}/gpu-benchmark"; exit 1; }

case ${SLURM_ARRAY_TASK_ID} in
    0)
        CMD="pixi run -e cpu python test_solve.py gurobi models/dispatch_2030.nc --custom_constraints dispatch --dump_mps --condition_dispatch --condition_storage"
        ;;
    1)
        CMD="pixi run -e cpu python test_solve.py gurobi models/dispatch_2030.nc --custom_constraints dispatch --dump_mps --condition_dispatch"
        ;;
    2)
        CMD="pixi run -e cpu python test_solve.py gurobi models/dispatch_2030.nc --custom_constraints dispatch --dump_mps"
        ;;
    3)
        CMD="pixi run -e cpu python test_solve.py highs models/dispatch_2030.nc --custom_constraints dispatch --condition_dispatch --condition_storage"
        ;;
    4)
        CMD="pixi run -e cpu python test_solve.py highs models/dispatch_2030.nc --custom_constraints dispatch --condition_dispatch"
        ;;
    5)
        CMD="pixi run -e cpu python test_solve.py highs models/dispatch_2030.nc --custom_constraints dispatch"
        ;;
    6)
        CMD="pixi run -e cpu python test_solve.py gurobi models/redispatch_2030.nc --custom_constraints redispatch --dump_mps --condition_dispatch --condition_storage"
        ;;
    7)
        CMD="pixi run -e cpu python test_solve.py gurobi models/redispatch_2030.nc --custom_constraints redispatch --dump_mps --condition_dispatch"
        ;;
    8)
        CMD="pixi run -e cpu python test_solve.py gurobi models/redispatch_2030.nc --custom_constraints redispatch --dump_mps"
        ;;
    9)
        CMD="pixi run -e cpu python test_solve.py highs models/redispatch_2030.nc --custom_constraints redispatch --condition_dispatch --condition_storage"
        ;;
    10)
        CMD="pixi run -e cpu python test_solve.py highs models/redispatch_2030.nc --custom_constraints redispatch --condition_dispatch"
        ;;
    11)
        CMD="pixi run -e cpu python test_solve.py highs models/redispatch_2030.nc --custom_constraints redispatch"
        ;;
    *)
        echo "Error: no command defined for SLURM_ARRAY_TASK_ID=${SLURM_ARRAY_TASK_ID}"
        exit 1
        ;;
esac

echo "Running task ${SLURM_ARRAY_TASK_ID}: ${CMD}"

eval "${CMD}"