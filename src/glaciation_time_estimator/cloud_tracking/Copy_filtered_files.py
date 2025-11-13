import subprocess
import sys
import os
import tempfile
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from glaciation_time_estimator.data_preprocessing.File_name_generator import generate_filename_dict
from glaciation_time_estimator.auxiliary_func.config_reader import read_config
import numpy as np
import argparse

def parse_cmd_args():
    parser = argparse.ArgumentParser(
        description="Create a custom PyFLEXTRKR config file from terminal."
    )
    parser.add_argument('-t', "--temperature_bounds", nargs=2,
                        help="Min temp and max temp of file for analysis", type=int, required=True)
    parser.add_argument('-p', "--pole_folder",
                        help="Name of pole folder", required=True)
    args, _ = parser.parse_known_args()
    return {
        'temp_bounds': args.temperature_bounds,
        'pole': args.pole_folder
    }

def generate_remote_fps(config, cmd_args):
    target_dict = generate_filename_dict(config, exclude_existing=False)
    # Replace filename parts to include temperature bounds.
    if config["Resample"]:
        agg_tag = f"R_Agg_{config['agg_fact']:02}"
    else:
        agg_tag = f"Agg_{config['agg_fact']:02}"
    target_fps = np.char.replace(
        target_dict[cmd_args["pole"]]["filter"],
        f"{agg_tag}_{config['agg_fact']:02}_",
        f"{agg_tag}_T_{abs(cmd_args['temp_bounds'][0]):02}_{abs(cmd_args['temp_bounds'][1]):02}_"
    )
    # print(target_dict[cmd_args["pole"]]["filter"])
    # print(config["CLAAS_fp"])
    # print(target_fps)

    target_fps = np.char.replace(target_fps, config["CLAAS_fp"],"")
    return np.char.replace(target_fps, "Resampled_Data", "Filtered_Data")


def copy_filtered_files(config):
    target_fps = generate_remote_fps(config, parse_cmd_args())
    # Create the local destination directory.
    tmp_dir = os.environ["TMPDIR"]
    data_dir = os.path.join(tmp_dir, "Data")
    os.makedirs(data_dir, exist_ok=True)
    print(f"Copying needed files from {config['CLAAS_fp']} to {data_dir}")

    # Write the file list to a temporary file.
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        tmp_filename = f.name
        for path in target_fps:
            f.write(path + "\n")

    # Use rsync's --files-from option.
    # The source directory is set to "/" so that the file paths in the list (which are absolute)
    # are interpreted correctly on the remote machine.
    cmd = [
        "rsync", "-auq","--no-relative",
        f"--files-from={tmp_filename}",
        config["CLAAS_fp"],  # Source: remote host's root directory.
        data_dir           # Destination: local data_dir.
    ]
    print("Running rsync with --files-from")
    subprocess.run(cmd)

    # Remove the temporary file.
    os.remove(tmp_filename) 

if __name__ == "__main__":
    copy_filtered_files(read_config())

    

