#!/bin/bash
YEARS=("$@")

for YEAR in "${YEARS[@]}"; do
    YEAR=$1
    for MONTH in {01..12}; do
        for part in 01 02; do
            CONFIG_FILE="/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/${YEAR}_tracking/${MONTH}_${part}.yaml"
            bash /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/Cloud_tracking/Slurm_jobs/All_t_jobs.sh -c $CONFIG_FILE
        done
        # if [ $((10#$MONTH % 3)) -eq 0 ]; then
        #         sleep 4h
        # fi
    done
done
