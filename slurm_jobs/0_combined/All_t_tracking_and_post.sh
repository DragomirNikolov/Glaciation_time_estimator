#!/bin/bash

while getopts 'c:d:y:w:a:' flag; do
    case "${flag}" in
    c) GTE_CONFIG_DIR=${OPTARG};;
    d) init_dependency=${OPTARG};;
    y) YEAR=${OPTARG};;
    w) wait_time=${OPTARG};;
    a) agg_fact=${OPTARG};;
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

# Check if GTE_CONFIG_DIR is empty
if [ -z "$agg_fact" ]; then
    agg_fact=20
    echo "Assuming default value 20 for aggregation factor."
fi
job_ids=()
config_name="${GTE_CONFIG_DIR##*/}"
# for dt in 3 5 6; do
for dt in 6; do
    for min_temp in $(seq $dt $dt 38); do
        # max = min - dt because we deal with absolutes of negative numbers
        max_temp=$((min_temp - dt))
        for pole in "np" "sp"; do
            if [ -z "$YEAR" ]; then
                name=T_"$min_temp"_"$max_temp"_"$pole"_"${config_name::-5}"
            else
                name=T_"$min_temp"_"$max_temp"_"$pole"_"${config_name::-5}"_"$YEAR"
            fi
            if [ -z "$init_dependency" ]; then
                if [ -z "$wait_time" ]; then
                    job_id=$(sbatch --parsable -J "$name" "$GTE_DIR"slurm_jobs/2_tracking/tracking_job.bsub -h $max_temp -l $min_temp -p $pole -c $GTE_CONFIG_DIR)
                else
                    # compute how many minutes to wait
                    job_id=$(sbatch --parsable --begin=now+${wait_time}minutes -J "$name" "$GTE_DIR"slurm_jobs/2_tracking/tracking_job.bsub -h $max_temp -l $min_temp -p $pole -c $GTE_CONFIG_DIR)
                fi
            else
                job_id=$(sbatch --parsable -J "$name" --dependency=afterok:$init_dependency "$GTE_DIR"slurm_jobs/2_tracking/tracking_job.bsub -h $max_temp -l $min_temp -p $pole -c $GTE_CONFIG_DIR)
            fi
            job_ids+=("$job_id")
            echo "Submited tracking job: ${name}"
        done
    done
done

postproc_name="${config_name::-5}_${YEAR}_postproc"
# Submit post-processing job after all jobs have completed
if [ ${#job_ids[@]} -gt 0 ]; then
    dependency_list=$(IFS=,; echo "${job_ids[*]}")
    postproc_job_id=$(sbatch --parsable --dependency=afterok:$dependency_list -J "$postproc_name" "$GTE_DIR"slurm_jobs/3_postprocessing/postproc_job.bsub -c $GTE_CONFIG_DIR)
    echo "Post-processing job submitted with ID: $postproc_job_id"
    # echo "$postproc_job_id"
fi
