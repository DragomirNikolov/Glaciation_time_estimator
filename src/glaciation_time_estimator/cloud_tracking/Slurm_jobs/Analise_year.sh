#!/bin/bash
YEARS=("$@")

postproc_job_ids=()
for YEAR in "${YEARS[@]}"; do
    YEAR=$1
    for MONTH in {01..12}; do
        for part in 01 02; do
            CONFIG_FILE="/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/${YEAR}_tracking/${MONTH}_${part}.yaml"
            postproc_job=$(bash /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/Cloud_tracking/Slurm_jobs/All_t_jobs.sh -c $CONFIG_FILE)
            postproc_job_ids+=("$postproc_job")
        done
        # if [ $((10#$MONTH % 3)) -eq 0 ]; then
        #         sleep 4h
        # fi
    done
done

glac_name="${Year}_glac"
# Submit post-processing job after all jobs have completed
if [ ${#job_ids[@]} -gt 0 ]; then
    dependency_list=$(IFS=,; echo "${postproc_job_ids[*]}")
    sbatch --dependency=afterok:$dependency_list -J "$glac_name" /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/Data_postprocessing/Slurm_jobs/glaciation_detection.bsub -c $GTE_CONFIG_DIR
    echo "Glaciation detection job submitted with ID: $glac_name"
fi
