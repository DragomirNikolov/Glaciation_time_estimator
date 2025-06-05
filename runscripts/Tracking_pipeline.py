from glaciation_time_estimator.cloud_tracking.Copy_filtered_files import copy_filtered_files
from glaciation_time_estimator.cloud_tracking.Generate_pyflextrkr_config import generate_pyflextrkr_config
from glaciation_time_estimator.cloud_tracking.generic_pyflextrkr_tracking import run_generic_tracking
from glaciation_time_estimator.cloud_tracking.Send_results import send_results
from glaciation_time_estimator.auxiliary_func.config_reader import read_config


if __name__ == "__main__":
    # Read the configuration file
    # Read the given GTE config file - its file path should be specified as a command line argument -cf <path_to_gte_config>
    gte_config = read_config()
    # Copy the filtered CLAAS_3 files to TMP_DIR
    copy_filtered_files(gte_config)
    # Generate a pyflextrkr config file for the given period
    # The file is based on the file given under the command line argument -bc <path_to_pylextrkr_config>
    pyflextrkr_config_dir = generate_pyflextrkr_config(gte_config)
    run_generic_tracking(pyflextrkr_config_dir)
    send_results(gte_config)
    
    
    
    