#!/usr/bin/env bash
CONFIG_FILE="$1"               # keep the full path
# Check if GTE_CONFIG_DIR is empty
if [ -z "$CONFIG_FILE" ]; then
    echo "Error: CONFIG_FILE is empty. Exiting."
    exit 1
fi
CONFIG_NAME="$(basename "$CONFIG_FILE")"   # strip everything but the last path element

sbatch -J "${CONFIG_NAME}_preproc" \
      "${GTE_DIR}/slurm_jobs/1_preprocessing/preproc_job.bsub" \
      -c "$CONFIG_FILE"
