#!/bin/bash
# YEARS=("$@")

while getopts 'd:y:w:' flag; do
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

for MONTH in {01..12}; do
    for part in 01 02; do
        # Set name of configuration file
        CONFIG_FILE="${GTE_DIR}/configs/${YEAR}_tracking/${MONTH}_${part}.yaml"
        # Run tracking and post-processing job for the current part of month
        if [ -z "$wait_time" ]; then
            raw=$(bash "${GTE_DIR}slurm_jobs/0_combined/All_t_tracking_and_post.sh" -c $CONFIG_FILE -y $YEAR)
        else
            # compute how many minutes to wait
            delay_minutes=$(( (10#$MONTH / 4) * wait_time ))
            raw=$(bash "${GTE_DIR}slurm_jobs/0_combined/All_t_tracking_and_post.sh" -c $CONFIG_FILE -y $YEAR -w $delay_minutes)
        fi
        # strip everything up to the last colon+space
        postproc_job_id="${raw##*ID: }"

        # now you can append the bare numeric ID
        postproc_job_ids+=( "$postproc_job_id" )
        # Build a list of job IDs for post-processing jobs
    done
done
glac_name="${YEAR}_glac"
GTE_CONFIG_DIR="${GTE_DIR}/configs/${YEAR}_tracking/01_01.yaml"
# Submit glaciation detection job after all post-processing jobs have completed
if [ ${#postproc_job_ids[@]} -gt 0 ]; then
    dependency_list=$(IFS=,; echo "${postproc_job_ids[*]}")
    sbatch  --dependency=afterok:$dependency_list -J "$glac_name" "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" -c $GTE_CONFIG_DIR
    echo "Glaciation detection job submitted with ID: $glac_name"
fi

