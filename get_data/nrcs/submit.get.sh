#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=24:00:00
#SBATCH --output=./logs/get_wsf_nrcs_%A_%a.out
#SBATCH --error=./logs/get_wsf_nrcs_%A_%a.err
#SBATCH -A 2306081036
#SBATCH --job-name=get_wsf_nrcs

# Make log dir
mkdir -p ./logs

# Load your Conda module
eval "$(conda shell.bash hook)"
conda activate npl-2024b

# Get WSF forecasts
sh get_wsf_nrcs.sh

# Get NRCS observations
sh get_obs_nrcs.sh

