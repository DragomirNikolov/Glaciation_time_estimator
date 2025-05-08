import os
import sys
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
from glaciation_time_estimator.data_preprocessing.Preprocessing_pipeline import preprocessing_pipeline

config = read_config("/cluster/work/climate/dnikolo/n2o/Glaciation_time_estimator/configs/April_testing/euler_template.yaml")
preprocessing_pipeline(config)