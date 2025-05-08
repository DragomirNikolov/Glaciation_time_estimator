from glaciation_time_estimator.cloud_tracking.Copy_filtered_files import copy_filtered_files
from glaciation_time_estimator.cloud_tracking.Generate_pyflextrkr_config import generate_pyflextrkr_config
from glaciation_time_estimator.cloud_tracking.generic_pyflextrkr_tracking import run_generic_tracking
from galciation_time_estimator.auxiliary_func.config_reader import read_config
from glaciation_time_estimator.cloud_tracking.send_results import send_results

if __name__ == "__main__":
    # Read the configuration file
    gte_config = read_config()
    copy_filtered_files(gte_config)
    pyflextrkr_config_dir = generate_config(gte_config)
    run_generic_tracking(pyflextrkr_config_dir)
    send_results(gte_config)
    
    
    
    