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


def remove_filesystem_name(path: str) -> str:
    host = os.uname()[1].split("-")[0]
    prefix = f"{host}:"
    return path[len(prefix):] if path.startswith(prefix) else path

# top_key is the key in the config that informs the function if the extra keys should be expected
def optional_key_check(config: dict, keys_to_check: list , config_keys_set: set, top_key: any, top_key_values: list, extra_keys: list):
    """
    Adds extra keys to chck if the top_key is within the values in top_key_values
    
    :param config: GTE config dictionary
    :param keys_to_check: List of keys that have already been determined to be expected in the config.
                         This function will append to this list if the top_key condition is met.
    :param config_keys_set: Set of keys in the config that will be compared to keys to check. This function will remove the extra keys from this set if the top_key condition is not met.
    :param top_key: 
    :param top_key_value: Description
    :param extra_keys: Description
    """
    extra_keys.append(top_key)
    try:
        if config[top_key] in top_key_values:
            keys_to_check.extend(extra_keys)
        else:
            config_keys_set -= set(extra_keys)
        return keys_to_check, config_keys_set
    except KeyError:
        config_keys_set -= set(extra_keys)
        return keys_to_check, config_keys_set

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
    # if config.get('Analyze_year',False):
    #     keys_to_check.extend(['Analyze_year','n_month_parts','yearly_config_folder'])
    # else:
    #     config_keys_set -= {'Analyze_year','n_month_parts','yearly_config_folder'}
    keys_to_check, config_keys_set = optional_key_check(config, keys_to_check, config_keys_set, 'Analyze_year', [True], ['n_month_parts','yearly_config_folder'])
    keys_to_check, config_keys_set = optional_key_check(config, keys_to_check, config_keys_set, 'validation_mode', ["dardar", "DARDAR", "modis", "MODIS"], ["val_CPH_fp"])
    expected_keys_set = set(keys_to_check)
    assert config_keys_set == expected_keys_set, f"The keys: {config_keys_set.symmetric_difference(expected_keys_set)} are missing or redundant in the configuration file"


def format_config(config):
    # Ensures optional validation mode key exists in the final config
    if config.get("validation_mode", False) == False:
        config["validation_mode"]=""
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
    config["validation_mode"] = config["validation_mode"].lower()
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
