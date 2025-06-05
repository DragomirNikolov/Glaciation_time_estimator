from glaciation_time_estimator.data_postprocessing.combine_datasets import combine_whole_year
from glaciation_time_estimator.data_postprocessing.Extract_glaciations import extract_glaciations_whole_year
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

if __name__=="__main__":
    # Read the given GTE config file - its file path should be specified as a command line argument -cf <path_to_config>
    config=read_config()
    # Combines all detected clouds in the year_all.parquet file in the Final results folder
    if config.get("Analyze_year",True):
        combine_whole_year(config)
    # Extracts the glaciations from the year_all.parquet file to year_glac.parquet in the Final results folder
    extract_glaciations_whole_year(config)
    
