#!/bin/bash
YEARS=("$@")

for YEAR in "${YEARS[@]}"; do
    YEAR=$1
    for MONTH in {01..12}; do
        for part in 01 02; do
            CONFIG_FILE="/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/${YEAR}_tracking/${MONTH}_${part}.yaml"
            name="${YEAR}_${MONTH}_${part}_glaciations"
            sbatch -J "$name" /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/Data_postprocessing/glaciation_detection.bsub -c $CONFIG_FILE
        done
    done
done
