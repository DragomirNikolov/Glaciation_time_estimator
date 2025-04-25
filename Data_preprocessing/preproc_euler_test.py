import os
import sys
from Glaciation_time_estimator.Auxiliary_func.config_reader import read_config
from Glaciation_time_estimator.Data_preprocessing.Preprocessing_pipeline import preprocessing_pipeline

config = read_config("/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/April_testing/euler_template.yaml")
preprocessing_pipeline(config)