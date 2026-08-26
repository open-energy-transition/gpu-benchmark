#!/bin/bash

# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
# SPDX-FileCopyrightText: 2026 open-energy-transition/gpu-benchmark contributors
#
# SPDX-License-Identifier: MIT

#SBATCH --job-name=cpu-solve
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --array=0-2
#SBATCH --time=01:00:00
#SBATCH --partition=gcp1-gpu
#SBATCH --gpus=1
#SBATCH --mem=60G
#SBATCH -n1

# Network filepath - update this with your actual network file path
cd "/scratch/htc/${USER}/gpu-benchmark" || { echo "Error: failed to cd to /scratch/htc/${USER}/gpu-benchmark"; exit 1; }

case ${SLURM_ARRAY_TASK_ID} in
    0)
        CMD="pixi run -e gpu python test_solve.py cupdlpx models/dispatch_2030.nc --custom_constraints dispatch --condition_dispatch --condition_storage"
        ;;
    1)
        CMD="pixi run -e gpu python test_solve.py cupdlpx models/dispatch_2030.nc --custom_constraints dispatch  --condition_dispatch"
        ;;
    2)
        CMD="pixi run -e gpu python test_solve.py cupdlpx models/dispatch_2030.nc --custom_constraints dispatch "
        ;;
    3)
        CMD="pixi run -e gpu python test_solve.py cupdlpx models/redispatch_2030.nc --custom_constraints redispatch --condition_dispatch --condition_storage"
        ;;
    4)
        CMD="pixi run -e gpu python test_solve.py cupdlpx models/redispatch_2030.nc --custom_constraints redispatch  --condition_dispatch"
        ;;
    5)
        CMD="pixi run -e gpu python test_solve.py cupdlpx models/redispatch_2030.nc --custom_constraints redispatch "
        ;;
    *)
        echo "Error: no command defined for SLURM_ARRAY_TASK_ID=${SLURM_ARRAY_TASK_ID}"
        exit 1
        ;;
esac

echo "Running task ${SLURM_ARRAY_TASK_ID}: ${CMD}"

eval "${CMD}"