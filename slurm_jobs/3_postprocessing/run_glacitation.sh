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

for MONTH in {01..03}; do
    for part in {01..02}; do
        config_name="${GTE_DIR}/configs/Validation_MODIS/${YEAR}_tracking/${MONTH}_${part}.yaml"
        job_name="${MONTH}_${part}_${YEAR}_glac"
        sbatch   -J "$job_name" "${GTE_DIR}slurm_jobs/3_postprocessing/glaciation_detection.bsub" -c $config_name
    done
done