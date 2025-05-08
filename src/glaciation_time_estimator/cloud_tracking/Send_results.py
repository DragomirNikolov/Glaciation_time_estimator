import os
import argparse
import subprocess
from glaciation_time_estimator.data_preprocessing.File_name_generator import generate_filename_dict
from glaciation_time_estimator.auxiliary_func.config_reader import read_config


def parse_cmd_args():
    # Retrieve cmd arguments
    parser = argparse.ArgumentParser(
        description="Create a custom PyFLEXTRKR config file from terminal."
    )
    parser.add_argument('-rd', "--results_dir",
                        help="Directory of results to be copied", required=True)
    parser.add_argument('-t', "--temperature_bounds", nargs=2,
                        help="Min temp and max temp of file for analysis", type=int, required=True)
    parser.add_argument('-p', "--pole_folder",
                        help="Folder of pole (e.x. np)", required=True)

    # parser.add_argument("-wd", "--work_directory", help="Base yaml config file on which to draw upon", required=True)
    # args = parser.parse_args()
    args,_ = parser.parse_known_args()
    # Put arguments in a dictionary
    args_dict = {
        'results_dir': args.results_dir,
        'temp_bounds': args.temperature_bounds,
        'pole': args.pole_folder
    }
    return args_dict


if __name__ == "__main__":
    # pole/Agg_03_T_05_00/pixel_path_tracking/YmD.HM(start)_YmD.HM(end)
    config = read_config()
    cmd_args = parse_cmd_args()
    # print(config['start_time'])
    time_format = "%Y%m%d.%H%M"
    time_folder = f"{config['start_time'].strftime(time_format)}_{config['end_time'].strftime(time_format)}"
    # print(time_folder)
    min_temp = cmd_args["temp_bounds"][0]
    max_temp = cmd_args["temp_bounds"][1]
    output_dir = os.path.join(
        config['job_output_fp'], cmd_args["pole"], f"Agg_{config['agg_fact']:02}_T_{abs(min_temp):02}_{abs(max_temp):02}", time_folder)
    os.makedirs(output_dir, exist_ok=True)
    subprocess.run(
        ["rsync", "-auq", cmd_args["results_dir"], output_dir])
#n2o_fp
#rsync -aq –rsync-path=”mkdir -p n2o_fp && rsync” file user@remote:n2o_fp