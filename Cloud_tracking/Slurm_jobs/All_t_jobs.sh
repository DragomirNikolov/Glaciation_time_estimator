#!/bin/bash

while getopts 'c:' flag; do
    case "${flag}" in
    c) GTE_CONFIG_DIR=${OPTARG};;
    *)
        print_usage
        exit 1
        ;;
    esac
done

# Check if GTE_CONFIG_DIR is empty
if [ -z "$GTE_CONFIG_DIR" ]; then
    echo "Error: GTE_CONFIG_DIR is empty. Exiting."
    exit 1
fi

agg_fact=3
job_ids=()
config_name="${GTE_CONFIG_DIR##*/}"
# for dt in 3 5 6; do
for dt in 6; do
    for min_temp in $(seq $dt $dt 38); do
        # max = min - dt because we deal with absolutes of negative numbers
        max_temp=$((min_temp - dt))
        for pole in "np" "sp"; do
            name=T_"$min_temp"_"$max_temp"_"$agg_fact"_"$pole"_"${config_name::-5}"
            job_id=$(sbatch --parsable -J "$name" "$GTE_DIR"/Cloud_tracking/Slurm_jobs/job.bsub -h $max_temp -l $min_temp -p $pole -c $GTE_CONFIG_DIR)
            job_ids+=("$job_id")
        done
    done
done

postproc_name="${config_name::-5}_postproc"
# Submit post-processing job after all jobs have completed
if [ ${#job_ids[@]} -gt 0 ]; then
    dependency_list=$(IFS=,; echo "${job_ids[*]}")
    sbatch --dependency=afterok:$dependency_list -J "$postproc_name" /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/Data_postprocessing/postproc_job.bsub -c $GTE_CONFIG_DIR
fi
