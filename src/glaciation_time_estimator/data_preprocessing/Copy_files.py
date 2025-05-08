
import subprocess
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from glaciation_time_estimator.data_preprocessing.File_name_generator import generate_filename_dict
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
import numpy as np


def generate_remote_folders(config):
    target_dict = generate_filename_dict(config)
    vec_dirname=np.vectorize(os.path.dirname)
    target_folders= {}
    for pole in config["pole_folders"]:
        target_folders[pole] = np.unique(vec_dirname(target_dict[pole]["resample_CPP"]))
    return target_folders

def copy_from_n2o(config=None):
    config = read_config()
    target_folders = generate_remote_folders(config)
    
    tmp_dir = os.environ["TMPDIR"]
    data_dir= os.path.join(tmp_dir, "Data", "")
    os.makedirs(data_dir, exist_ok=True)
    print(data_dir)
    print(target_folders)
    for folder in target_folders:
        subprocess.run(["rsync", "-auq", f"{os.path.join(folder,'')}", data_dir ])

    # subprocess.run("scp", )

def copy_to_n2o(config=None):