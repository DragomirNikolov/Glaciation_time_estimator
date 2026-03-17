#!/bin/bash
YEARS=("$@")

if [ -z "$YEARS" ]; then
    echo "Error: Please select years. Exiting."
    exit 1
fi

postproc_job_ids=()
for YEAR in "${YEARS[@]}"; do
    YEAR=$1
    for MONTH in {04..12}; do
    # for MONTH in 01; do
        for part in 01 02; do
            # Set name of configuration file
            CONFIG_FILE="${GTE_DIR}/configs/Validation/${YEAR}_tracking/${MONTH}_${part}.yaml"
            # Run preprocessing job for the current part of month
            preproc_id=$(sbatch --parsable -J "${YEAR}_${MONTH}_${part}_preproc" "${GTE_DIR}slurm_jobs/1_preprocessing/preproc_job.bsub" -c $CONFIG_FILE)
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
    # Submit glaciation detection job after all post-processing jobs have completed
    if [ ${#postproc_job_ids[@]} -gt 0 ]; then
        dependency_list=$(IFS=,; echo "${postproc_job_ids[*]}")
        sbatch  --dependency=afterok:$dependency_list -J "$glac_name" "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" -c $GTE_CONFIG_DIR
        echo "Glaciation detection job submitted with ID: $glac_name"
    fi

done

