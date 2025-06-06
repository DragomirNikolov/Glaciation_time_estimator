#!/bin/bash

if [ $# -lt 2 ]; then
    echo "Usage: $0 -y YEAR1[,YEAR2,...]"
    exit 1
fi

while getopts 'y:' flag; do
    case "${flag}" in
        y)
            IFS=',' read -r -a YEARS <<< "${OPTARG}"
            ;;
        *)
            echo "Usage: $0 -y YEAR1[,YEAR2,...]"
            exit 1
            ;;
    esac
done

if [ ${#YEARS[@]} -eq 0 ]; then
    echo "Error: no years provided"
    exit 1
fi

for year in "${YEARS[@]}"; do
    for glac_threshold in {02..05}; do
        job_name="glac_${year}_${glac_threshold}"
        config_name="${GTE_DIR}/configs/glac_configs/eu_${year}_thresh_${glac_threshold}.yaml"
        # echo "Would submit: $config_name (job name=${job_name})"
        sbatch -J "$job_name" "$GTE_DIR"/slurm_jobs/3_postprocessing/glaciation_detection.bsub -c "$config_name"
    done
done
