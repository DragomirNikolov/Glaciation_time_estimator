#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: Config_generator.py
Author: Dragomir Nikolov    
Date: 2024-10-11  (YYYY-MO-DD)
Version: 1.0
Description: 
    This file is used to generate configuration files for the PyFLEXTRKR library within an existing job.
    This is neded to be able to place the output directory in $TEMPDIR

License: MIT License
Contact: dnikolo@student.ethz.ch / dragomird.nikolov@gmail.com
Dependencies: os, sys
"""

# Import statements
import yaml
import os
import argparse
from datetime import datetime
from glaciation_time_estimator.auxiliary_func.config_reader import read_config

def parse_cmd_args():
    # Retrieve cmd arguments
    parser = argparse.ArgumentParser(
        description="Create a custom PyFLEXTRKR config file from terminal."
    )
    parser.add_argument('-t', "--temperature_bounds", nargs=2,
                        help="Min temp and max temp of file for analysis", type=int, required=True)
    parser.add_argument("-bc", "--base_configuration",
                        help="Base yaml config file on which to draw upon", required=True)

    # parser.add_argument("-wd", "--work_directory", help="Base yaml config file on which to draw upon", required=True)
    args, _ = parser.parse_known_args()

    # Put arguments in a dictionary
    args_dict = {
        'temp_bounds': args.temperature_bounds,
        'base_config': args.base_configuration,
    }
    return args_dict


def config_setup(work_dir: str, base_setup_contnet: list, arg_dict: dict, config: dict) -> str:
    """
    Writes configuratuin file

    Input:
    work_dir: Base directory in which the results will be stored
    min_temp: Minimum CTT of clouds after filtering
    max_temp: Maximum CTT of clouds after filtering
    base_setup_content: The contents of a setup file that will be used as a basis for the new one. 
                        This file should contain all the variables necessary for PyFLEXTRKR to run.
    Outout:
    temp_setup_fp: location of the newly created configuation file
    """
    min_temp = abs(round(arg_dict['temp_bounds'][0]))
    max_temp = abs(round(arg_dict['temp_bounds'][1]))
    start_time = config['start_time']
    end_time = config['end_time']
    agg_fact = config['agg_fact']
    temp_setup = base_setup_contnet

    # Create root path
    root_path = os.path.join(work_dir, "Result", "")
    # Create root path folder if it doesn't exist
    if not os.path.exists(root_path):
        os.makedirs(root_path, exist_ok=True)
    print(root_path)

    # Update config file parameters
    temp_setup['root_path'] = root_path
    temp_setup["databasename"] = f"Agg_{round(agg_fact):02}_T_{round(abs(min_temp)):02}_{round(abs(max_temp)):02}_"
    temp_setup["clouddata_path"] = os.path.join(work_dir, "Data","")
    temp_setup['logger_filepath'] = os.path.join(root_path, 'log.log')
    temp_setup['error_filepath'] = os.path.join(root_path, 'err.log')
    temp_setup['pixel_radius'] = temp_setup['pixel_radius']*agg_fact
    temp_setup["startdate"] = start_time.strftime("%Y%m%d.%H%M")
    temp_setup["enddate"] = end_time.strftime("%Y%m%d.%H%M")

    # Save temporaty setup
    temp_setup_fp = os.path.join(root_path, 'setup.yml')
    with open(temp_setup_fp, 'w') as temp_setup_file:
        yaml.dump(temp_setup, temp_setup_file)
    return temp_setup_fp


if __name__ == "__main__":
    # base_dir = os.environ['TMPDIR']
    base_dir = os.environ.get('TMPDIR', "/cluster/work/climate/dnikolo/dump")
    if base_dir == "/":
        base_dir = "/cluster/work/climate/dnikolo/dump"
    arg_dict = parse_cmd_args()
    config = read_config()

    with open(arg_dict['base_config'], 'r') as stream:
        try:
            base_config_content = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
            exit
    config_setup(base_dir, base_config_content, arg_dict, config)
