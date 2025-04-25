#!/usr/bin/env bash
CONFIG_FILE="$1"               # keep the full path
CONFIG_NAME="$(basename "$CONFIG_FILE")"   # strip everything but the last path element

sbatch -J "$CONFIG_NAME" \
      /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/Data_preprocessing/Slurm_jobs/preproc_job.bsub \
      -c "$CONFIG_FILE"
