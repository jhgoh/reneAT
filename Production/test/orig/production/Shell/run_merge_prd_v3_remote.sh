#!/bin/bash
#SBATCH --partition=normal
#SBATCH --nodelist=suicune

run=$1
# SHELLDIR is injected by submit_merge_prd_v3_remote.sh via --export so that
# $(realpath $0) does not resolve to the SLURM spool copy of this script.
bash ${SHELLDIR}/merge_FADC_SADC_v3_remote.sh $run
