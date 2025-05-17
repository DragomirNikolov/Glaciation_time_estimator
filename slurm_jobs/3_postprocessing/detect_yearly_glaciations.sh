#!/bin/bash
YEARS=("$@")

for YEAR in "${YEARS[@]}"; do
    YEAR=$1
    for MONTH in {01..12}; do
        for part in 01 02; do
            CONFIG_FILE="${GTE_DIR}/configs/${YEAR}_tracking/${MONTH}_${part}.yaml"
            name="${YEAR}_${MONTH}_${part}_glaciations"
            sbatch -J "$name" "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" -c $CONFIG_FILE
        done
    done
done
