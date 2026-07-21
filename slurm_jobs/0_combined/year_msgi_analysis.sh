# bash /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/slurm_jobs/0_combined/Complete_analysis_config_list.sh \
#   -m msgi \
#   -w 10 \
#   -p /cluster/work/climate/dnikolo/MSGI/configs/testing/nudged_3y.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/01_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/01_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/01_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/02_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/02_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/03_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/03_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/04_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/04_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/05_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/05_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/06_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/06_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/07_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/07_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/08_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/08_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/09_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/09_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/10_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/10_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/11_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/11_02.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/12_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/nudged_3y/2007_tracking/12_02.yaml

# bash /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/slurm_jobs/0_combined/Complete_analysis_config_list.sh \
#   -m msgi \
#   -w 30 \
#   -p /cluster/work/climate/dnikolo/MSGI/configs/testing/r2b5_wbf_v3_1y.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/r2b5_wbf_v3_1y/2007_tracking/01_01.yaml \
#   -c /cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/ICON_output/r2b5_wbf_v3_1y/2007_tracking/01_02.yaml \

while getopts 'y:w:p:c:' flag; do
    case "${flag}" in
        y) YEAR=${OPTARG} ;;
        w) wait_time=${OPTARG} ;;
        p) MSGI_CONFIG_DIR=${OPTARG} ;;
        c) GTE_CONFIG_DIR=${OPTARG} ;;
        *)
            print_usage
            exit 1
            ;;
    esac
done

if [ -z "$YEAR" ]; then
    echo "Error: YEAR is empty. Enter -y <year wanted>."
    exit 1
fi

if [ -z "$MSGI_CONFIG_DIR" ]; then
    echo "Error: MSGI_CONFIG_DIR is empty. Enter -p <msgi_config_file_path>."
    exit 1
fi

if [ -z "$GTE_CONFIG_DIR" ]; then
    echo "Error: GTE_CONFIG_DIR is empty. Enter -c <GTE_CONFIG_DIR>. GTE_CONFIG_DIR is the folder where all the <year>_tracking/<#month>_<#part>.yaml files are stored."
    exit 1
fi

config_list=()
for i in {1..12}; do
    for j in {1..2}; do
        config_list+=(
            -c "${GTE_CONFIG_DIR}/${YEAR}_tracking/$(printf "%02d" "$i")_$(printf "%02d" "$j").yaml"
        )
    done
done

cmd=(
    bash "${GTE_DIR}slurm_jobs/0_combined/Complete_analysis_config_list.sh"
    -m msgi
    -w "${wait_time}"
    -p "${MSGI_CONFIG_DIR}"
    "${config_list[@]}"
)

"${cmd[@]}"

