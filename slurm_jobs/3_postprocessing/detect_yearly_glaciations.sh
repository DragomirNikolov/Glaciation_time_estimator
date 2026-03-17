#!/bin/bash
while getopts 'd:y:' flag; do
    case "${flag}" in
    y) YEAR=${OPTARG};;
    *)
        print_usage
        exit 1
        ;;
    esac
done
if [ -z "$YEAR" ]; then
    echo "Error: Please select year. Exiting."
    exit 1
fi
postproc_job_ids=()

for MONTH in {01..12}; do
    for part in {01..02}; do
        config_name="${GTE_DIR}/configs/Validation/${YEAR}_tracking/${MONTH}_${part}.yaml"
        job_name="${MONTH}_${part}_${YEAR}_postproc"
        postproc_job_id=$(sbatch --parsable -J "$job_name" "${GTE_DIR}slurm_jobs/3_postprocessing/postproc_job.bsub" -c $config_name)
        postproc_job_ids+=( "$postproc_job_id" )
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