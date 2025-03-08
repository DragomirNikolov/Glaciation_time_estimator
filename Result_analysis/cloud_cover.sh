#!/bin/bash

# Exit if the year variable is empty
if [ -z "$1" ]; then
    echo "Year variable is empty. Exiting..."
    exit 1
fi

year=$1

# for month_dir in "${CLAAS_DIR}np/${year}"/*/
# do
#     for day_dir in "${month_dir}"/*/
#     do
#         cd "$day_dir" || { echo "Failed to change directory to $day_dir"; exit 1; }
#         echo "$day_dir"
#         cdo -O -setmissval,0 -mergetime -apply,-selname,ctt [ "${day_dir}CTX*.nc" ] "combined.nc"
#         cdo merge "${CLAAS_DIR}/np/CM_SAF_CLAAS3_L2_AUX.nc" "combined.nc" combined_aux.nc 
#         cdo expr,"mean_area=(ctt>237.15)*(ctt<273.15)*(pixel_area<66)*pixel_area" combined_aux.nc area_fields.nc
#         cdo fldsum area_fields.nc cloud_cover.nc
        
#         if [[ $day_dir =~ ([0-9]{4})/([0-9]{2})//([0-9]{2})/ ]]; then
#             filename="${BASH_REMATCH[1]}_${BASH_REMATCH[2]}_${BASH_REMATCH[3]}.nc"
#             echo "${CLAAS_DIR}/Cloud_cover/np/$filename"
#             cdo timmean cloud_cover.nc "${CLAAS_DIR}/Cloud_cover/np/$filename"
#         else
#             echo "Didn't read name correctly"
#             exit 1
#         fi
#         rm -f cloud_cover.nc area_fields.nc combined_aux.nc combined.nc
#         # Terminate the inner loop after the first iteration
#     done
# done

for month_dir in "${CLAAS_DIR}sp/${year}"/*/
do
    for day_dir in "${month_dir}"/*/
    do
        cd "$day_dir" || { echo "Failed to change directory to $day_dir"; exit 1; }
        echo "$day_dir"
        cdo -O -setmissval,0 -mergetime -apply,-selname,ctt [ "${day_dir}CTX*.nc" ] "combined.nc"
        cdo merge "${CLAAS_DIR}/sp/CM_SAF_CLAAS3_L2_AUX.nc" "combined.nc" combined_aux.nc 
        cdo expr,"mean_area=(ctt>237.15)*(ctt<273.15)*(pixel_area<66)*pixel_area" combined_aux.nc area_fields.nc
        cdo fldsum area_fields.nc cloud_cover.nc
        
        if [[ $day_dir =~ ([0-9]{4})/([0-9]{2})//([0-9]{2})/ ]]; then
            filename="${BASH_REMATCH[1]}_${BASH_REMATCH[2]}_${BASH_REMATCH[3]}.nc"
            echo "${CLAAS_DIR}/Cloud_cover/sp/$filename"
            cdo timmean cloud_cover.nc "${CLAAS_DIR}/Cloud_cover/sp/$filename"
        else
            echo "Didn't read name correctly"
            exit 1
        fi
        rm -f cloud_cover.nc area_fields.nc combined_aux.nc combined.nc
        # Terminate the inner loop after the first iteration
    done
done