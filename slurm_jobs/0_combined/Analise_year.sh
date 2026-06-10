#!/bin/bash
# Most important file in the codebase.
# This script is used to run the preprocessing, tracking, post-processing and glaciation_detection jobs for a given year.

print_usage() {
  echo "Usage: $0 -y YEAR [-w WAIT_MIN] [-d GTE_DIR]" >&2
}

while getopts 'y:w:' flag; do
    case "${flag}" in
    y) YEAR=${OPTARG};;
    w) wait_time=${OPTARG};;
    *)
        print_usage
        exit 1
        ;;
    esac
done

if [ -z "$YEAR" ]; then
    echo "Error: Please select years. Exiting."
    exit 1
fi

postproc_job_ids=()

#Iterate over all months and all (in my case 2) parts of each month
for MONTH in {01..12}; do
    for part in 01 02; do
        # Set name of configuration file
        
        CONFIG_FILE="${GTE_DIR}configs/Validation_DARDAR/${YEAR}_tracking/${MONTH}_${part}.yaml"
        # Run preprocessing job for the current part of month
        if [ -z "$wait_time" ]; then
            preproc_id=$(sbatch --parsable -J "${YEAR}_${MONTH}_${part}_preproc" "${GTE_DIR}slurm_jobs/1_preprocessing/preproc_job.bsub" -c $CONFIG_FILE)
        else
            # compute how many minutes to wait
            delay_minutes=$(( ((10#$MONTH - 1) / 4) * wait_time ))
            preproc_id=$(sbatch --parsable --begin=now+${delay_minutes}minutes -J "${YEAR}_${MONTH}_${part}_preproc" "${GTE_DIR}slurm_jobs/1_preprocessing/preproc_job.bsub" -c $CONFIG_FILE)
        fi
        # Run tracking and post-processing job for the current part of month
        raw=$(bash "${GTE_DIR}slurm_jobs/0_combined/All_t_tracking_and_post.sh" -c $CONFIG_FILE -d $preproc_id -y $YEAR)
        # strip everything up to the last colon+space
        postproc_job_id="${raw##*ID: }"

        # now you can append the bare numeric ID
        postproc_job_ids+=( "$postproc_job_id" )
        # Build a list of job IDs for post-processing jobs
    done
done
glac_name="${YEAR}_glac"
GTE_CONFIG_DIR="${GTE_DIR}configs/Validation_DARDAR/${YEAR}_tracking/01_01.yaml"
# Submit glaciation detection job after all post-processing jobs have completed
if [ ${#postproc_job_ids[@]} -gt 0 ]; then
    dependency_list=$(IFS=,; echo "${postproc_job_ids[*]}")
    sbatch  --dependency=afterok:$dependency_list -J "$glac_name" "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" -c $GTE_CONFIG_DIR
    echo "Glaciation detection job submitted with ID: $glac_name"
fi

