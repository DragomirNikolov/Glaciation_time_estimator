#!/bin/bash
YEARS=("$@")

for YEAR in "${YEARS[@]}"; do
    YEAR=$1
    for MONTH in {01..12}; do
        for part in 01 02; do
            CONFIG_FILE="${GTE_DIR}/configs/${YEAR}_tracking/${MONTH}_${part}.yaml"
            name="${YEAR}_${MONTH}_${part}_preproc"
            sbatch -J "$name" "${GTE_DIR}slurm_jobs/1_preprocessing/preproc_job.bsub" -c $CONFIG_FILE
        done
        # if [ $((10#$MONTH % 3)) -eq 0 ]; then
        #         sleep 4h
        # fi
    done
done
