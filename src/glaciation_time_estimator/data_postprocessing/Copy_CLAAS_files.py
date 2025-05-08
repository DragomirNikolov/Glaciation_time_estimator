import subprocess
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from glaciation_time_estimator.data_preprocessing.File_name_generator import generate_filename_dict
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
from datetime import datetime
import numpy as np

def generate_remote_fps(config, pole):
    target_dict = generate_filename_dict(config, exclude_existing=False)
    return target_dict[pole]["resample_CPP"]

def copy_files(config):
    tmp_dir = os.environ["TMPDIR"]
    vec_dirname = np.vectorize(os.path.dirname)
    for pole in config["pole_folders"]:
        target_fps = generate_remote_fps(config, pole)
        target_folders = np.unique(vec_dirname(target_fps))
        data_dir = os.path.join(tmp_dir, "Data", pole, "")
        os.makedirs(data_dir, exist_ok=True)
        print("Target folders:", target_folders)
        print("Data directory:", data_dir)
        print("Other config values:", config["postprocessing_output_dir"], config["CLAAS_fp"])
        for folder in target_folders:
            # The 'check=True' parameter will raise a CalledProcessError if rsync fails.
            subprocess.run(
                ["rsync", "-v", "-auq", os.path.join(folder, ""), data_dir],
                check=True
            )

if __name__ == "__main__":
    copy_files(read_config())
