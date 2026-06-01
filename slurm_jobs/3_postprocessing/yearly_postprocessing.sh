#!/bin/bash

while getopts 'y:w:' flag; do
    case "${flag}" in
        y) YEAR=${OPTARG} ;;
        w) wait_time=${OPTARG} ;;
        *)
            echo "Usage: $0 -y YEAR [-w wait_time]"
            exit 1
            ;;
    esac
done

if [ -z "$YEAR" ]; then
    echo "Error: Please provide a year with -y. Exiting."
    exit 1
fi

postproc_job_ids=()

for MONTH in {01..12}; do
    for part in 01 02; do
        CONFIG_FILE="${GTE_DIR}/configs/Validation_DARDAR/bulk_output/${YEAR}_tracking/${MONTH}_${part}.yaml"

        if [ ! -f "$CONFIG_FILE" ]; then
            echo "Warning: Config file not found: $CONFIG_FILE. Skipping."
            continue
        fi

        config_name="${CONFIG_FILE##*/}"
        postproc_name="${config_name::-5}_${YEAR}_postproc"

        echo "Submitting post-processing job for $CONFIG_FILE"

        if [ -z "$wait_time" ]; then
            postproc_job_id=$(sbatch --parsable \
                -J "$postproc_name" \
                "${GTE_DIR}slurm_jobs/3_postprocessing/postproc_job.bsub" \
                -c "$CONFIG_FILE")
            # postproc_job_id=$(sbatch --parsable  \
            #     -J "$postproc_name" \
            #     "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" \
            #     -c "$CONFIG_FILE")
        else
            delay_minutes=$(( (10#$MONTH / 4) * wait_time ))
            postproc_job_id=$(sbatch --parsable \
                --begin=now+${delay_minutes}minutes \
                -J "$postproc_name" \
                "${GTE_DIR}slurm_jobs/3_postprocessing/postproc_job.bsub" \
                -c "$CONFIG_FILE")
            # postproc_job_id=$(sbatch --parsable \
            #     --begin=now+${delay_minutes}minutes \
            #     -J "$postproc_name" \
            #     "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" \
            #     -c "$CONFIG_FILE")
        fi

        if [ -n "$postproc_job_id" ]; then
            postproc_job_ids+=("$postproc_job_id")
            echo "Post-processing job submitted with ID: $postproc_job_id"
        else
            echo "Failed to submit post-processing job for $CONFIG_FILE"
        fi
    done
done

glac_name="${YEAR}_glac"
GTE_CONFIG_DIR="${GTE_DIR}/configs/Validation_DARDAR/bulk_output/${YEAR}_tracking/01_01.yaml"

if [ ${#postproc_job_ids[@]} -gt 0 ]; then
    dependency_list=$(IFS=,; echo "${postproc_job_ids[*]}")
    glac_job_id=$(sbatch --parsable \
        --dependency=afterok:$dependency_list \
        -J "$glac_name" \
        "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" \
        -c "$GTE_CONFIG_DIR")
    echo "Glaciation detection job submitted with ID: $glac_job_id"
else
    echo "No post-processing jobs were submitted, so glaciation detection was not started."
fi