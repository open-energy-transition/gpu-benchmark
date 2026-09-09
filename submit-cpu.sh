#!/bin/bash

# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
#
# SPDX-License-Identifier: MIT

#SBATCH --job-name=cpu-solve
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --array=0-23
#SBATCH --time=01:00:00
#SBATCH --partition=big
#SBATCH --mem=60G
#SBATCH -n1

# Network filepath - update this with your actual network file path
cd "/scratch/htc/${USER}/gpu-benchmark" || { echo "Error: failed to cd to /scratch/htc/${USER}/gpu-benchmark"; exit 1; }

# Build the full matrix of commands: model x solver x conditioning x scaling.
# Keep the array directive above in sync with the number of commands generated
# (currently 2 models x 2 solvers x 3 conditionings x 2 scalings = 24, i.e. 0-23).
MODELS=("dispatch" "redispatch")
SOLVERS=("gurobi --dump_mps" "highs")
CONDITIONS=("" "--condition_dispatch" "--condition_dispatch --condition_storage")
SCALINGS=("" "--scale")

CMDS=()
for model in "${MODELS[@]}"; do
    for solver in "${SOLVERS[@]}"; do
        for condition in "${CONDITIONS[@]}"; do
            for scaling in "${SCALINGS[@]}"; do
                CMDS+=("pixi run -e cpu python test_solve.py ${solver} models/${model}_2030.nc --custom_constraints ${model} ${condition} ${scaling}")
            done
        done
    done
done

if [[ ${SLURM_ARRAY_TASK_ID} -ge ${#CMDS[@]} ]]; then
    echo "Error: no command defined for SLURM_ARRAY_TASK_ID=${SLURM_ARRAY_TASK_ID}"
    exit 1
fi
CMD="${CMDS[${SLURM_ARRAY_TASK_ID}]}"

echo "Running task ${SLURM_ARRAY_TASK_ID}: ${CMD}"

eval "${CMD}"