#!/bin/bash -l
#SBATCH --job-name=qmmm
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
set -eo pipefail
# Add the local account, partition, and environment/module setup here.
# Activate the Python environment containing turbomole-namd as needed.
command -v namd3
command -v ridft
command -v rdgrad
command -v turbomole-namd
# These variables apply to a compatible TURBOMOLE SMP installation.
export PARA_ARCH=SMP
export PARNODES=${SLURM_CPUS_PER_TASK:-1}
export OMP_NUM_THREADS=$PARNODES
namd3 +p1 qmmm.conf > qmmm.log 2>&1
