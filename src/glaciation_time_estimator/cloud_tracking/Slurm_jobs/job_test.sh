#!/bin/bash
min_temp=5
max_temp=0
pole="np"
# sbatch -J "$name"  "$GTE_DIR"/Cloud_tracking/job.bsub -h $max_temp -l $min_temp -a 3 -s $start_time -e $end_time -p $pole
bash "$GTE_DIR"/Cloud_tracking/job.bsub  -h $max_temp -l $min_temp -p $pole

