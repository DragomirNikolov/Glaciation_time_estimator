#!/usr/bin/env bash

# Cancel your own Slurm jobs submitted less than 5 minutes ago

now=$(date +%s)

squeue -h -u "$USER" -o "%i|%V" | while IFS='|' read -r jobid submit_time; do
    # Skip jobs with unknown submit time
    [[ -z "$submit_time" || "$submit_time" == "N/A" ]] && continue

    submit_epoch=$(date -d "$submit_time" +%s 2>/dev/null) || continue
    age=$((now - submit_epoch))

    if (( age >= 0 && age < 900 )); then
        echo "Cancelling job $jobid (submitted $age seconds ago)"
        scancel "$jobid"
    fi
done

