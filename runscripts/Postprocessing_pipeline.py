from glaciation_time_estimator.data_postprocessing.Tracking_result_analysis import analyze_tracked_clouds
from glaciation_time_estimator.data_postprocessing.Copy_CLAAS_files import copy_files
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

if __name__ == "__main__":
    # Read the given GTE config file - its file path should be specified as a command line argument -cf <path_to_config>
    config = read_config()
    # if config["collect_additional_properties"]:
    #     copy_files(config)'
    # Analyze the tracked clouds from a single temperature range for a single period
    analyze_tracked_clouds(config)