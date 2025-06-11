#!/bin/bash

# Exit if the year variable is empty
if [ -z "$1" ]; then
    echo "Year variable is empty. Exiting..."
    exit 1
fi

year=$1
while getopts 'y:m:' flag; do
    case "${flag}" in
    y) day_dir=${OPTARG};;
    *)
        print_usage
        exit 1
        ;;
    esac
done



cd "$day_dir" || { echo "Failed to change directory to $day_dir"; exit 1; }
echo "$day_dir"

# 1) Merge CTX and CPP files
cdo -O -setmissval,0 -mergetime -apply,-selname,ctt,ctp [ "${day_dir}CTX*.nc" ] "combined_ctx.nc" &
cdo -O -setmissval,0 -mergetime -apply,-selname,cot [ "${day_dir}CPP*.nc" ] "combined_cpp.nc" &
wait

# 2) Merge them and also merge with your AUX file
cdo merge combined_ctx.nc combined_cpp.nc combined_total.nc
cdo merge "${CLAAS_DIR}/sp/CM_SAF_CLAAS3_L2_AUX.nc" "combined_total.nc" combined_aux.nc

# 3) (Optional) Filter by cloud-top temperature (ctt) and pixel_area if you wish
#    Here we keep your existing ctp_filtered logic:
#    ctp_filtered is ctp only if 237.15 K < ctt < 273.15 K and pixel_area < 66
cdo expr,"ctp_filtered=(ctt>237.15)*(ctt<273.15)*(pixel_area<66)*ctp; \
                    cot=cot; \
                    pixel_area=pixel_area" \
    combined_aux.nc classification_fields.nc

# 4) Define each cloud category area and a 'total' area mask in one go
#    (Below we do ctp_filtered>0 to ensure it's a valid cloud pixel
#     and use the ISCCP bounds on ctp and cot.)
cdo expr,"\
    total     = (ctp_filtered>0)*(cot>0)*pixel_area; \
    \
    ci        = (ctp_filtered<440)*(ctp_filtered>0)*(cot>0)*(cot<3.6)*pixel_area; \
    cs        = (ctp_filtered<440)*(ctp_filtered>0)*(cot>3.6)*(cot<23)*pixel_area; \
    dc        = (ctp_filtered<440)*(ctp_filtered>0)*(cot>23)*(cot<379)*pixel_area; \
    \
    ac        = (ctp_filtered>=440)*(ctp_filtered<680)*(cot>0)*(cot<3.6)*pixel_area; \
    as        = (ctp_filtered>=440)*(ctp_filtered<680)*(cot>3.6)*(cot<23)*pixel_area; \
    ns        = (ctp_filtered>=440)*(ctp_filtered<680)*(cot>23)*(cot<379)*pixel_area; \
    \
    cu        = (ctp_filtered>=680)*(ctp_filtered<1000)*(cot>0)*(cot<3.6)*pixel_area; \
    sc        = (ctp_filtered>=680)*(ctp_filtered<1000)*(cot>3.6)*(cot<23)*pixel_area; \
    st        = (ctp_filtered>=680)*(ctp_filtered<1000)*(cot>23)*(cot<379)*pixel_area" \
    classification_fields.nc area_fields.nc

# 5) Sum over the field (spatial sum) to get total area per category
cdo fldsum area_fields.nc class_cover_area.nc

# 6) Compute the fraction of each category wrt total
cdo expr,"\
    ci_frac=ci/total; \
    cs_frac=cs/total; \
    dc_frac=dc/total; \
    ac_frac=ac/total; \
    as_frac=as/total; \
    ns_frac=ns/total; \
    cu_frac=cu/total; \
    sc_frac=sc/total; \
    st_frac=st/total" \
    class_cover_area.nc class_cover.nc

# 7) Extract year_month_day from the directory structure
if [[ $day_dir =~ ([0-9]{4})/([0-9]{2})//([0-9]{2})/ ]]; then
    filename="${BASH_REMATCH[1]}_${BASH_REMATCH[2]}_${BASH_REMATCH[3]}.nc"
    echo "${CLAAS_DIR}/Cloud_cover_by_class/sp/$filename"
    cdo timmean class_cover.nc "${CLAAS_DIR}/Cloud_cover_by_class/sp/$filename"
else
    echo "Didn't read name correctly"
    exit 1
fi

# 8) Clean up
rm -f class_cover_area.nc area_fields.nc classification_fields.nc \
        combined_aux.nc combined_total.nc combined_ctx.nc combined_cpp.nc

# NOTE: Currently your script 'exit 0' after first iteration, so if you
#       want to process *all* days, remove the 'exit 0'.
exit 0