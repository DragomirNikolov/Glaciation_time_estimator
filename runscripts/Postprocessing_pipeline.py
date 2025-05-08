from glaciation_time_estimator.data_postprocessing.Tracking_result_analysis import analyze_tracked_clouds
from glaciation_time_estimator.data_postprocessing.Extract_glaciations import extract_glaciations
from glaciation_time_estimator.data_postprocessing.Copy_CLAAS_files import copy_files
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

if __name__ == "__main__":
    config = read_config()
    # if config["collect_additional_properties"]:
    #     copy_files(config)
    analyze_tracked_clouds(config)
    # extract_glaciations(config)