from Glaciation_time_estimator.Data_postprocessing.Tracking_result_analysis import analyse_tracked_clouds
from Glaciation_time_estimator.Data_postprocessing.Extract_glaciations import extract_glaciations
from Glaciation_time_estimator.Data_postprocessing.Copy_CLAAS_files import copy_files
from Glaciation_time_estimator.Auxiliary_func.config_reader import read_config

if __name__ == "__main__":
    config = read_config()
    # if config["collect_additional_properties"]:
    #     copy_files(config)
    analyse_tracked_clouds(config)
    extract_glaciations(config)