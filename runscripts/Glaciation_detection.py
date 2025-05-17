from glaciation_time_estimator.data_postprocessing.combine_datasets import combine_whole_year
from glaciation_time_estimator.data_postprocessing.Extract_glaciations import extract_glaciations_whole_year
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

if __name__=="__main__":
    config=read_config()
    combine_whole_year(config)
    extract_glaciations_whole_year(config)
    
