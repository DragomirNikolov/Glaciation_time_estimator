import yaml
import argparse
import os
from datetime import datetime
from glaciation_time_estimator.auxiliary_func.Helper_fun import generate_temp_range


def parse_cmd_args():
    # Retrieve cmd arguments
    parser = argparse.ArgumentParser(
        description="Create a custom PyFLEXTRKR config file from terminal."
    )
    parser.add_argument('-cf', "--configuration_filepath",
                        help="Path to config function", required=True)

    # parser.add_argument("-wd", "--work_directory", help="Base yaml config file on which to draw upon", required=True)
    # args = parser.parse_args()
    args, _ = parser.parse_known_args()
    assert os.path.exists(
        args.configuration_filepath), "Configuration file doesn't exist"
    return args.configuration_filepath


def remove_filesystem_name(string):
    return string.strip(f'{os.uname()[1].split("-")[0]}:')


def check_keys(config):
    keys_to_check = [
        "start_time",
        "end_time",
        "Resample",
        "pole_split",
        "struct_boundary_date",
        "pole_folders",
        "aux_fps",
        "aux_fps_agg",
        "CLAAS_fp",
        "job_output_fp",
        "agg_fact",
        "t_deltas",
        "postprocessing_fast_mode",
        "fast_mode_arr_size",
        "write_csv",
        "postprocessing_output_dir",
        "time_folder_format",
        "collect_additional_properties",
        'Global_sqrt_mse',
        'n_preproc_cores',
        'n_preproc_threads',
        'grid_fps',
        'glac_threshold',
        'n_postproc_cores'
    ]
    config_keys_set = set(config.keys())
    if config.get('Analyze_year',False):
        keys_to_check.extend(['Analyze_year','n_month_parts','yearly_config_folder'])
    expected_keys_set = set(keys_to_check) 
    if not config.get('Analyze_year',False):
        config_keys_set -= {'Analyze_year','n_month_parts','yearly_config_folder'}
    assert config_keys_set == expected_keys_set, f"The keys: {config_keys_set.symmetric_difference(expected_keys_set)} are missing or redundant in the configuration file"


def format_config(config):
    check_keys(config)
    date_format = "%Y%m%d_%H%M"
    config["start_time"] = datetime.strptime(config["start_time"], date_format)
    config["end_time"] = datetime.strptime(config["end_time"], date_format)
    assert config["start_time"] < config["end_time"], "Start time should be before end time"
    config["struct_boundary_date"] = datetime.strptime(
        config["struct_boundary_date"], date_format)
    min_temp_arr, max_temp_arr = generate_temp_range(config["t_deltas"])
    config["min_temp_arr"] = min_temp_arr
    config["max_temp_arr"] = max_temp_arr
    config["time_folder_name"] = f"{config['start_time'].strftime(config['time_folder_format'])}_{config['end_time'].strftime(config['time_folder_format'])}"
    config['CLAAS_fp'] = remove_filesystem_name(config['CLAAS_fp'])
    config['job_output_fp'] = remove_filesystem_name(config['job_output_fp'])
    config['postprocessing_output_dir'] = remove_filesystem_name(
        config['postprocessing_output_dir'])

    return config


def read_config(config_fp=None):
    if config_fp is None:
        config_fp = parse_cmd_args()
        print(f"Reading config at {config_fp}")
    with open(config_fp) as stream:
        try:
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    config = format_config(config)
    return config


if __name__ == "__main__":
    print(read_config())
