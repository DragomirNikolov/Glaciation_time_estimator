import subprocess
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Glaciation_time_estimator.Data_preprocessing.File_name_generator import generate_filename_dict
from Glaciation_time_estimator.Auxiliary_func.config_reader import read_config
from Glaciation_time_estimator.Data_postprocessing.Copy_CLAAS_files import copy_files
import numpy as np

if __name__ == "__main__":
    copy_files(read_config())
